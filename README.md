# Trip Planner

A deterministic agentic workflow with LLM-powered travel planning system that converts natural-language trip requests into verified, budget-constrained, weather-checked round-trip itineraries.

## Overview

Trip Planner takes a plain-language trip request and turns it into a complete, budget-checked itinerary — flights, hotel, and weather — without the user having to manually cross-check multiple sites.

An agentic pipeline handles this end-to-end: one stage understands the request, another searches flights, hotels, and weather concurrently, another scores and combines the results, and a final stage verifies the chosen plan actually fits the budget before presenting it.

Multiple external services are used because no single source reliably covers flights, hotels, and weather together. Budget is enforced as a constraint throughout the process, not just checked at the end, so the final output is dependable rather than approximate.

## Key Features

- Natural-language trip parsing into structured plan (origin, destination, dates, budget, preferences)
- Concurrent flight, hotel, and weather searches via asyncio
- Weather-aware planning with automatic alternate-date search on poor forecasts
- Multi-factor scoring for flights (price, duration, stops) and hotels (price, rating, reviews)
- Budget-aware combination generation with configurable tolerance buffer
- Reflection/verification step before finalizing a plan
- LLM-generated final itinerary in a clean, readable format

## How It Works

1. User enters a natural-language trip request.
2. The LLM planner extracts origin, destination, dates, duration, and budget as validated structured JSON.
3. Weather is checked first; if poor, the user can request alternative dates. The system scans the next 10 days to find a window with suitable conditions.
4. With dates confirmed, flight and hotel searches execute concurrently. 
5. The flight tool then queries SerpApi for round-trip options.
6. The hotel tool resolves the destination through RouteStack and retrieves available properties for the selected dates.
7. Both API responses are normalized into flat internal schemas with validated types.
8. Flights are scored on price (50%), duration (30%), and stops (20%). Hotels are scored on price (35%), star rating (40%), and review volume (25%). All using min-max normalization.
9. Valid flight+hotel combinations are generated and ranked by combined score, filtered by budget.
10. The top combination is verified against the budget in a reflection step.
11. If verified, an LLM composes the final itinerary from structured trip data.

## Architecture

```
User Query
   |
Planner (Groq LLM) -> TripPlan
   |
TripState
   |
   +--> Weather Check (Open-Meteo) --> alt dates if poor
   |
   +--> Executor (asyncio.gather)
          +--> Flight Search (SerpApi)
          +--> Hotel Search (RouteStack)
   |
Normalizer (flights, hotels)
   |
Evaluator (scoring + combination generation)
   |
Reflection (budget verification)
   |
Final Answer (Groq LLM) --> Itinerary
```

## Project Structure

```
trip-planner/
├── config/
│   └── config.py              # Environment variables, scoring constants, thresholds
├── src/
│   ├── models.py              # Pydantic schemas: TripPlan, TripState
│   ├── planner.py             # Groq LLM call with strict JSON schema output
│   ├── executor.py            # Async orchestration (weather, concurrent search)
│   ├── normalizer.py          # SerpApi and RouteStack response normalization
│   ├── evaluator.py           # Scoring, combination generation, budget filtering
│   ├── reflection.py          # Post-selection budget verification
│   └── prompts.py             # System prompts for planner and itinerary LLM calls
├── tools/
│   ├── flight_tool.py         # IATA resolution + SerpApi round-trip search
│   ├── hotel_tool.py          # RouteStack destination resolution + hotel search
│   ├── routestack_client.py   # HMAC-SHA256 authenticated RouteStack HTTP client
│   └── weather_tool.py        # Open-Meteo geocoding, forecast, alternative dates
├── main.py                    # CLI entry point, pipeline orchestration, output formatting
├── .env.example               # Environment variable template
└── requirements.txt           # Python dependencies
```

## Tech Stack

| Category           | Technology                        |
|--------------------|-----------------------------------|
| Language           | Python 3.10+                      |
| LLM                | Groq (`openai/gpt-oss-20b`)       |
| Flight Search      | SerpApi Google Flights            |
| Hotel Search       | RouteStack API (HMAC-authenticated)        |
| Weather            | Open-Meteo (Forecast + Archive)   |
| Data Validation    | Pydantic                        |
| HTTP               | Requests                          |
| Config      | python-dotenv                     |

## Core Components


### Planner

Sends the user query and today's date to Groq with a strict JSON schema. The model returns a validated `TripPlan` containing the origin, destination, dates, duration, and budget.

### Weather Agent

Geocodes the destination using Open-Meteo and retrieves daily precipitation data to determine whether the selected dates are suitable. Historical data is used as a fallback for dates beyond the forecast window.

### Flight Agent

Dynamically resolves city names to 3-letter IATA codes and submits a single round-trip query to SerpApi Google Flights. Matching return segments are retrieved using the corresponding `departure_token`.

### Hotel Agent

Dynamically resolves the destination through RouteStack and retrieves available properties for the selected check-in and check-out dates.

### Evaluation

Normalizes and scores flight and hotel candidates using weighted criteria, then generates and ranks flight + hotel combinations while filtering out those exceeding the allowed budget.

### Verification

Independently verifies the selected candidates and confirms that the total cost satisfies the budget constraint before the itinerary is generated.

## Budget Handling

Budget awareness is built into the combination-selection process rather than applied after candidate selection.

When a budget is specified:

* Allowed budget = stated budget × 1.05 by default
* Combinations exceeding the allowed budget are excluded
* Feasible combinations are ranked by their combined evaluation score
* The selected combination is independently verified before generating the itinerary

If no budget is provided, budget filtering is skipped and combinations are ranked by quality instead.

If no feasible combination exists, the system reports this rather than presenting an over-budget itinerary.


## Example

**Input**

```
Chennai to Singapore, 3 days, budget=60000 inr, starting date=15 sept 2026
```

**Output**

```
FINAL TRIP PLAN

Chennai -> Singapore | 15 Sep 2026 -> 18 Sep 2026 (3 days)

Outbound: IndiGo 6E1234, 15 Sep, 08:20 -> 14:10, Nonstop, Economy
Return:   IndiGo 6E5678, 18 Sep, 16:40 -> 18:05, Nonstop, Economy

Hotel: Hotel Marina Bay View, 4-star, 3 nights

Cost Summary
Flight: ₹32,400.00
Hotel:  ₹21,000.00
Total:  ₹53,400.00
Budget: ₹60,000.00
Remaining: ₹6,600.00

Weather: Mostly clear, low rain probability across all 3 days.

No bookings have been made; the information above is based on verified travel results.
```

## Setup

1. Clone the repository and install dependencies:
   ```
   pip install -r requirements.txt
   ```

2. Copy `.env.example` to `.env` and fill in:
   - `GROQ_API_KEY`
   - `ROUTESTACK_ACCOUNT_ID`, `ROUTESTACK_API_KEY`, `ROUTESTACK_API_SECRET`
   - `SERPAPI_API_KEY`

3. Run:
   ```
   python main.py
   ```


## Limitations

- All prices are indicative; live fares change in real time and are not locked
- SerpApi free tier is limited to 250 searches/month
- Weather data beyond 15 days uses historical estimates from the previous year
- No booking or payment functionality — the system is informational only


## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.


## Author

**Dhruv Rathi**
