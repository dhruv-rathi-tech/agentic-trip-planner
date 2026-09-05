import requests
from datetime import date as _date, timedelta as _timedelta

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

FORECAST_MAX_DAYS_AHEAD = 15
RAIN_PROBABILITY_THRESHOLD = 60
WEATHER_BAD_DAY_THRESHOLD = 2


def geocode_city(city, country_code=None, count=10):
    params = {
        "name": city,
        "count": count,
        "language": "en",
        "format": "json"
    }

    if country_code:
        params["countryCode"] = country_code

    response = requests.get(
        GEOCODING_URL,
        params=params,
        timeout=30
    )
    response.raise_for_status()

    return response.json().get("results", [])


def _resolve_location(destination):
    # IMPORTANT: never force countryCode=IN. The trip may be international.
    results = geocode_city(destination)

    if not results:
        raise ValueError(f"Could not find location: {destination}")

    destination_lower = destination.strip().lower()

    # Prefer an exact-name match.
    exact = [
        result for result in results
        if str(result.get("name", "")).strip().lower() == destination_lower
    ]

    candidates = exact or results

    # Prefer country-level results when the requested destination itself
    # resolves to a country (e.g. "Thailand"), otherwise prefer populated
    # city results.
    country_results = [
        result for result in candidates
        if str(result.get("feature_code", "")).upper().startswith("PCLI")
        or str(result.get("feature_code", "")).upper() in {"A", "PCL"}
    ]

    if country_results:
        return max(
            country_results,
            key=lambda r: r.get("population") or 0
        )

    return max(
        candidates,
        key=lambda r: r.get("population") or 0
    )


def get_weather_forecast(destination, start_date, end_date):
    location = _resolve_location(destination)

    latitude = location["latitude"]
    longitude = location["longitude"]

    start = _date.fromisoformat(str(start_date))
    end = _date.fromisoformat(str(end_date))

    if end <= start:
        raise ValueError("Weather end date must be after start date.")

    days_ahead = (end - _date.today()).days
    start_ahead = (start - _date.today()).days

    daily_fields = ",".join([
        "temperature_2m_max",
        "temperature_2m_min",
        "precipitation_sum",
        "precipitation_probability_max",
        "weather_code"
    ])

    if 0 <= start_ahead and days_ahead <= FORECAST_MAX_DAYS_AHEAD:
        url = FORECAST_URL
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "daily": daily_fields,
            "timezone": "auto",
            "start_date": str(start),
            "end_date": str(end)
        }
        is_estimate = False
    else:
        hist_start = start.replace(year=start.year - 1)
        hist_end = end.replace(year=end.year - 1)

        url = ARCHIVE_URL
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "daily": daily_fields,
            "timezone": "auto",
            "start_date": str(hist_start),
            "end_date": str(hist_end)
        }
        is_estimate = True

    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()

    daily = response.json().get("daily", {})
    dates = daily.get("time", [])

    required = [
        "temperature_2m_max",
        "temperature_2m_min",
        "precipitation_sum",
        "precipitation_probability_max",
        "weather_code"
    ]

    for key in required:
        if key not in daily:
            raise ValueError(
                f"Weather API response is missing daily field: {key}"
            )

    forecast = []
    for i, day in enumerate(dates):
        forecast.append({
            "date": day,
            "temperature_max": daily["temperature_2m_max"][i],
            "temperature_min": daily["temperature_2m_min"][i],
            "precipitation_mm": daily["precipitation_sum"][i],
            "precipitation_probability": (
                daily["precipitation_probability_max"][i]
            ),
            "weather_code": daily["weather_code"][i]
        })

    return {
        "destination": destination,
        "resolved_name": location.get("name"),
        "country": location.get("country"),
        "latitude": latitude,
        "longitude": longitude,
        "forecast": forecast,
        "is_estimate": is_estimate
    }


def evaluate_weather(weather_data):
    forecast = weather_data.get("forecast", [])
    bad_days = 0

    for day in forecast:
        probability = day.get("precipitation_probability") or 0
        if probability >= RAIN_PROBABILITY_THRESHOLD:
            bad_days += 1

    status = (
        "POOR"
        if bad_days >= WEATHER_BAD_DAY_THRESHOLD
        else "SUITABLE"
    )

    return {
        "status": status,
        "bad_days": bad_days,
        "total_days": len(forecast),
        "forecast": forecast,
        "is_estimate": weather_data.get("is_estimate", False)
    }


def find_better_dates(destination, original_start_date, duration_days, max_shift_days=10):
    start = _date.fromisoformat(str(original_start_date))
    best_candidate = None
    min_bad_days = 999

    for offset in range(1, max_shift_days + 1):
        candidate_start = start + _timedelta(days=offset)
        candidate_end = candidate_start + _timedelta(days=duration_days)

        try:
            weather_data = get_weather_forecast(destination, candidate_start, candidate_end)
            evaluation = evaluate_weather(weather_data)

            if evaluation["status"] == "SUITABLE":
                return {
                    "start_date": candidate_start,
                    "end_date": candidate_end,
                    "weather": weather_data,
                    "evaluation": evaluation
                }

            if evaluation["bad_days"] < min_bad_days:
                min_bad_days = evaluation["bad_days"]
                best_candidate = {
                    "start_date": candidate_start,
                    "end_date": candidate_end,
                    "weather": weather_data,
                    "evaluation": evaluation
                }
        except Exception:
            continue

    return best_candidate
