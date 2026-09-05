import asyncio

from tools.flight_tool import search_flights
from tools.hotel_tool import search_hotels
from tools.routestack_client import RouteStackAuthError
from tools.weather_tool import evaluate_weather, get_weather_forecast


async def run_weather(state):
    weather = await asyncio.to_thread(
        get_weather_forecast,
        state.destination,
        state.start_date,
        state.end_date
    )
    return weather, evaluate_weather(weather)


async def run_flights(state, client):
    return await asyncio.to_thread(
        search_flights,
        client,
        state.origin,
        state.destination,
        state.start_date,
        state.end_date
    )


async def run_hotels(state, client):
    rooms = [{
        "adults": 2,
        "children": 0,
        "roomCount": 1
    }]

    return await asyncio.to_thread(
        search_hotels,
        client,
        state.destination,
        state.start_date,
        state.end_date,
        rooms
    )


async def run_parallel_searches(state, client):
    # Authentication is deliberately done before this function so two
    # concurrent threads never race to create the first token.
    results = await asyncio.gather(
        run_flights(state, client),
        run_hotels(state, client),
        return_exceptions=True
    )

    flights, hotels = results

    for label, result in (("Flight", flights), ("Hotel", hotels)):
        if isinstance(result, Exception):
            if isinstance(result, RouteStackAuthError):
                raise result
            print(f"{label} search failed: {result}")
            result = None

        if label == "Flight":
            flights = result
        else:
            hotels = result

    return flights, hotels
