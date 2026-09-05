import asyncio
import re
import sys
from datetime import datetime, date
# pyrefly: ignore [missing-import]
from groq import Groq
from config.config import *
from src.planner import create_plan
from src.models import TripState
from tools.routestack_client import RouteStackClient
from src.executor import run_weather, run_parallel_searches
from src.evaluator import score_flights, score_hotels, generate_combinations
from src.reflection import reflect
from src.normalizer import normalize_flights, normalize_hotels
from src.prompts import FINAL_RESPONSE_PROMPT
from tools.weather_tool import find_better_dates

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

groq_client = Groq(api_key=GROQ_API_KEY)


def display_plan(plan):
    print("\n" + "=" * 60)
    print("AGENT PLAN")
    print("=" * 60)
    print(f"Origin: {plan.origin}")
    print(f"Destination: {plan.destination}")
    print(f"Dates: {plan.start_date} -> {plan.end_date} ({plan.duration_days} days)")
    print(f"Budget: ₹{plan.budget}")
    if plan.preferences:
        print(f"Preferences: {', '.join(plan.preferences)}")


def display_weather(evaluation):
    print("\n" + "=" * 60)
    print("WEATHER CHECK")
    print("=" * 60)
    print(f"Status: {evaluation['status']}")
    print(f"Bad days: {evaluation['bad_days']}/{evaluation['total_days']}")
    for day in evaluation.get("forecast", []):
        rain_prob = day.get('precipitation_probability')
        prob_str = f"{rain_prob}%" if rain_prob is not None else "N/A"
        print(
            f"{day['date']} | "
            f"Rain probability: {prob_str} | "
            f"Rain: {day.get('precipitation_mm', 0)} mm"
        )


def ask_weather_decision():
    print("\nThe weather is not ideal for these dates.")
    print("\nWhat would you like to do?")
    print("1. Find better dates")
    print("2. Continue with these dates")
    print("3. Stop planning")

    while True:
        choice = input("\nEnter 1, 2, or 3: ").strip()
        if choice in {"1", "2", "3"}:
            return choice


def _format_date(d):
    try:
        if isinstance(d, (date, datetime)):
            return d.strftime("%d %b %Y").lstrip("0")
        dt = datetime.fromisoformat(str(d)[:10])
        return dt.strftime("%d %b %Y").lstrip("0")
    except Exception:
        return str(d)


def _format_short_date(d):
    try:
        if isinstance(d, (date, datetime)):
            return d.strftime("%d %b").lstrip("0")
        dt = datetime.fromisoformat(str(d)[:10])
        return dt.strftime("%d %b").lstrip("0")
    except Exception:
        return str(d)


def _format_duration(duration_val):
    if duration_val is None:
        return "N/A"
    try:
        minutes = int(duration_val)
        hrs = minutes // 60
        mins = minutes % 60
        if hrs and mins:
            return f"{hrs}h {mins}m"
        elif hrs:
            return f"{hrs}h"
        else:
            return f"{mins}m"
    except (ValueError, TypeError):
        return str(duration_val)


def _format_time(iso_or_time_str):
    if not iso_or_time_str:
        return "N/A"
    s = str(iso_or_time_str).strip()
    if len(s) >= 16 and " " in s:
        return s.split(" ")[1][:5]
    if len(s) >= 16 and "T" in s:
        return s.split("T")[1][:5]
    if ":" in s:
        return s[:5]
    return s


def clean_cli_text(text: str) -> str:
    if not text:
        return ""
    # Strip markdown code fences
    text = re.sub(r"^```[a-zA-Z0-9]*\n?", "", text, flags=re.MULTILINE)
    text = text.replace("```", "")
    # Strip bold marks (**)
    text = text.replace("**", "")
    # Strip backticks
    text = text.replace("`", "")

    cleaned_lines = []
    for line in text.split("\n"):
        # Strip markdown table dividers like |---|---|
        if re.match(r"^\s*\|?[\s\-:|]+\|?\s*$", line) and "-" in line:
            continue
        # Strip bullet points (* or -) at start of line
        line = re.sub(r"^\s*[\*\-]\s+", "", line)
        # Strip remaining markdown asterisks
        line = line.replace("*", "")
        # If line was a markdown table row | A | B |, convert to clean text
        if line.strip().startswith("|") and line.strip().endswith("|"):
            parts = [p.strip() for p in line.strip().strip("|").split("|") if p.strip()]
            line = " - ".join(parts)
        cleaned_lines.append(line)

    result = "\n".join(cleaned_lines).strip()
    disclaimer = "No bookings have been made; the information above is based on verified travel results."
    if disclaimer in result:
        result = result.replace(disclaimer, "").strip() + f"\n\n{disclaimer}"
    return result


def generate_final_answer(state, verification):
    combo = state.selected_combination or {}
    flight = combo.get("flight") or {}
    hotel = combo.get("hotel") or {}

    hotel_nights = (state.end_date - state.start_date).days

    outbound_legs = flight.get("outbound_legs") or []
    return_legs = flight.get("return_legs") or []

    first_out = outbound_legs[0] if outbound_legs and isinstance(outbound_legs[0], dict) else (flight.get("outbound") or {})
    last_out = outbound_legs[-1] if len(outbound_legs) > 1 and isinstance(outbound_legs[-1], dict) else first_out

    first_ret = return_legs[0] if return_legs and isinstance(return_legs[0], dict) else (flight.get("return") or {})
    last_ret = return_legs[-1] if len(return_legs) > 1 and isinstance(return_legs[-1], dict) else first_ret

    out_airline = first_out.get("airline") or flight.get("airline") or "Unknown"
    out_fn = first_out.get("flight_number") or flight.get("flight_number") or ""
    out_flight_str = f"{out_airline} {out_fn}".strip()

    out_dep_time = _format_time((first_out.get("departure_airport") or {}).get("time"))
    out_arr_time = _format_time((last_out.get("arrival_airport") or {}).get("time"))
    out_dep_date = _format_date((first_out.get("departure_airport") or {}).get("time", "")[:10] or state.start_date)
    out_duration = _format_duration(first_out.get("duration") or flight.get("duration_minutes"))
    out_stops = "Nonstop" if flight.get("stops", 0) == 0 else (f"{flight.get('stops')} stop" if flight.get('stops') == 1 else f"{flight.get('stops')} stops")
    out_class = first_out.get("travel_class") or "Economy"

    ret_airline = first_ret.get("airline") or flight.get("airline") or "Unknown"
    ret_fn = first_ret.get("flight_number") or ""
    ret_flight_str = f"{ret_airline} {ret_fn}".strip()

    ret_dep_time = _format_time((first_ret.get("departure_airport") or {}).get("time"))
    ret_arr_time = _format_time((last_ret.get("arrival_airport") or {}).get("time"))
    ret_dep_date = _format_date((first_ret.get("departure_airport") or {}).get("time", "")[:10] or state.end_date)
    ret_duration = _format_duration(first_ret.get("duration"))
    ret_stops = "Nonstop" if len(return_legs) <= 1 else f"{len(return_legs) - 1} stops"
    ret_class = first_ret.get("travel_class") or "Economy"

    flight_price = flight.get("price", 0.0)
    hotel_price = hotel.get("price", 0.0)
    total_cost = verification.get("total_cost", flight_price + hotel_price)
    budget = state.budget
    remaining = max(budget - total_cost, 0.0) if budget > 0 else 0.0

    hotel_name = hotel.get("name") or "Selected Hotel"
    hotel_rating = hotel.get("rating") or 3
    try:
        hotel_rating = int(float(hotel_rating))
    except (ValueError, TypeError):
        pass

    forecast = (state.weather or {}).get("forecast", [])
    weather_lines = []
    for day in forecast:
        d_str = _format_short_date(day.get("date"))
        t_max = day.get("temperature_max", "N/A")
        t_min = day.get("temperature_min", "N/A")
        rain_mm = day.get("precipitation_mm", 0.0)
        rain_prob = day.get("precipitation_probability", 0)
        weather_lines.append(f"{d_str}: {t_max}°C / {t_min}°C | Rain: {rain_mm} mm | Probability: {rain_prob}%")
    weather_text = "\n".join(weather_lines) if weather_lines else "Weather data unavailable"

    prompt = f"""
Trip Details:
Origin: {state.origin}
Destination: {state.destination}
Start Date: {_format_date(state.start_date)}
End Date: {_format_date(state.end_date)}
Duration Days: {state.duration_days}
Budget: {f"₹{budget:,.2f}" if budget > 0 else "Not specified"}

Outbound Flight:
Airline: {out_airline}
Flight Number: {out_fn}
Route: {state.origin} → {state.destination}
Date: {out_dep_date}
Departure: {out_dep_time}
Arrival: {out_arr_time}
Duration: {out_duration}
Stops: {out_stops}
Class: {out_class}
Price: ₹{flight_price:,.2f}

Return Flight:
Airline: {ret_airline}
Flight Number: {ret_fn}
Route: {state.destination} → {state.origin}
Date: {ret_dep_date}
Departure: {ret_dep_time}
Arrival: {ret_arr_time}
Duration: {ret_duration}
Stops: {ret_stops}
Class: {ret_class}

Hotel:
Name: {hotel_name}
Rating: {hotel_rating}-star
Check-in: {_format_date(state.start_date)}
Check-out: {_format_date(state.end_date)}
Nights: {hotel_nights}
Price: ₹{hotel_price:,.2f}

Cost Summary:
Flight: ₹{flight_price:,.2f}
Hotel: ₹{hotel_price:,.2f}
Total: ₹{total_cost:,.2f}
Budget: {f"₹{budget:,.2f}" if budget > 0 else "Not specified"}
Remaining: {f"₹{remaining:,.2f}" if budget > 0 else "N/A"}

Weather Forecast:
{weather_text}

Selection Evaluation Data:
Flight score: {combo.get('flight_score', 'N/A')}
Hotel score: {combo.get('hotel_score', 'N/A')}
Verification reason: {verification.get('reason', '')}
Dates changed: {state.dates_changed}
"""

    response = groq_client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {
                "role": "system",
                "content": FINAL_RESPONSE_PROMPT
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        temperature=0.2
    )

    return response.choices[0].message.content


async def run_agent(user_query):
    print("\nCreating explicit plan...")
    plan = create_plan(user_query)
    display_plan(plan)

    state = TripState(
        origin=plan.origin,
        destination=plan.destination,
        start_date=plan.start_date,
        end_date=plan.end_date,
        duration_days=plan.duration_days,
        budget=plan.budget,
        preferences=plan.preferences
    )
    client = RouteStackClient()

    print("\nChecking weather first...")
    weather, weather_evaluation = await run_weather(state)

    state.weather = weather
    state.weather_status = weather_evaluation["status"]
    display_weather(weather_evaluation)

    if weather_evaluation["status"] == "POOR":
        choice = ask_weather_decision()

        if choice == "3":
            print("\nPlanning stopped.")
            return

        if choice == "1":
            print(f"\nSearching for alternative dates within {MAX_ALTERNATIVE_DAYS} days...")
            better = await asyncio.to_thread(
                find_better_dates,
                state.destination,
                state.start_date,
                state.duration_days,
                MAX_ALTERNATIVE_DAYS
            )
            if better and better.get("evaluation", {}).get("status") == "SUITABLE":
                state.start_date = better["start_date"]
                state.end_date = better["end_date"]
                state.dates_changed = True
                state.weather = better["weather"]
                state.weather_status = better["evaluation"]["status"]
                print(f"\nFound better dates: {state.start_date} -> {state.end_date}")
                display_weather(better["evaluation"])
            elif better:
                state.start_date = better["start_date"]
                state.end_date = better["end_date"]
                state.dates_changed = True
                state.weather = better["weather"]
                state.weather_status = better["evaluation"]["status"]
                print(f"\nFound best available alternative dates ({better['evaluation']['bad_days']} bad days): {state.start_date} -> {state.end_date}")
                display_weather(better["evaluation"])
            else:
                print(f"\nNo alternative dates found within {MAX_ALTERNATIVE_DAYS} days.")
                cont = input("\nContinue with original dates anyway? (y/n): ").strip().lower()
                if cont != "y":
                    print("\nPlanning stopped.")
                    return

    # Execute search attempts (retrying only on transient failures)
    for attempt in range(1, MAX_ATTEMPTS + 1):
        state.attempt = attempt
        print(f"\nSearch attempt {attempt}/{MAX_ATTEMPTS}")

        print("\nSearching flights and hotels concurrently...")
        raw_flights, raw_hotels = await run_parallel_searches(state, client)

        flights = normalize_flights(raw_flights)
        hotels = normalize_hotels(raw_hotels)

        if not flights or not hotels:
            missing_item = "flights" if not flights else "hotels"
            print(f"\nCould not find available {missing_item} for the selected dates.")
            # Do not repeatedly retry empty API results when parameters have not changed
            print(f"Travel options unavailable for {state.destination}.")
            return

        scored_flights = score_flights(flights)
        scored_hotels = score_hotels(hotels)

        combinations = generate_combinations(scored_flights, scored_hotels, state.budget)

        if not combinations:
            print("\nNo combination fits the budget.")
            print("No honest budget-fitting trip could be produced.")
            return

        best_combination = combinations[0]
        verification = reflect(
            scored_flights,
            scored_hotels,
            best_combination,
            state.budget
        )

        print("\nVerification:")
        print(verification)

        if verification["verified"]:
            state.selected_combination = best_combination
            state.verification = verification
            break
        else:
            print("\nVerification failed: " + verification.get("reason", ""))
            return

    print("\nGenerating final itinerary...")
    answer = generate_final_answer(state, state.verification)
    cleaned = clean_cli_text(answer)
    if not cleaned.startswith("## FINAL TRIP PLAN"):
        if "## FINAL TRIP PLAN" in cleaned:
            cleaned = cleaned[cleaned.find("## FINAL TRIP PLAN"):]
        else:
            cleaned = f"## FINAL TRIP PLAN\n\n{cleaned}"

    print()
    print(cleaned)


if __name__ == "__main__":
    user_query = input("\nWhat trip would you like to plan?\n> ")
    asyncio.run(run_agent(user_query))