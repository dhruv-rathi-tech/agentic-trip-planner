import requests
from config.config import SERPAPI_API_KEY


def resolve_airport(term):
    """Dynamically resolve an airport/city term to airport and city results via public travel autocomplete API."""
    url = "https://autocomplete.travelpayouts.com/places2"
    params = {"term": term, "locale": "en"}
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        results = response.json()
        return results if isinstance(results, list) else []
    except requests.RequestException as exc:
        print(f"Airport resolution request failed for {term}: {exc}")
        return []


def get_airport_code(term, client=None):
    """
    Dynamically resolve a term to its 3-letter IATA airport code.
    Accepts an optional client parameter for backward compatibility.
    """
    results = resolve_airport(term)
    if not results:
        raise ValueError(f"Could not resolve flight location: {term}")

    clean_term = term.strip().lower()

    # 1. First priority: match exact query in city name or airport name
    for item in results:
        if not isinstance(item, dict):
            continue
        code = str(item.get("code") or "").strip().upper()
        if len(code) != 3:
            continue
        name = str(item.get("name") or "").lower()
        city = str(item.get("city_name") or "").lower()
        if clean_term == name or clean_term == city:
            return code

    # 2. Second priority: substring match in name or city
    for item in results:
        if not isinstance(item, dict):
            continue
        code = str(item.get("code") or "").strip().upper()
        if len(code) != 3:
            continue
        name = str(item.get("name") or "").lower()
        city = str(item.get("city_name") or "").lower()
        if clean_term in name or clean_term in city:
            return code

    # 3. Third priority: first valid 3-letter code from top-ranked results
    for item in results:
        if isinstance(item, dict):
            code = str(item.get("code") or "").strip().upper()
            if len(code) == 3:
                return code

    raise ValueError(f"Could not extract airport code for: {term}")


def search_flights(
    client,
    origin,
    destination,
    departure_date,
    return_date,
    adults=1,
    cabin="Economy"
):
    """
    Search round-trip flights using SerpApi Google Flights.
    Preserves the interface expected by executor.py.
    """
    if return_date <= departure_date:
        raise ValueError("Return date must be after departure date.")

    origin_code = get_airport_code(origin)
    destination_code = get_airport_code(destination)

    print(f"Resolved origin: {origin} -> {origin_code}")
    print(f"Resolved destination: {destination} -> {destination_code}")

    if not SERPAPI_API_KEY:
        raise ValueError("SERPAPI_API_KEY is not configured in .env")

    params = {
        "engine": "google_flights",
        "departure_id": origin_code,
        "arrival_id": destination_code,
        "outbound_date": str(departure_date),
        "return_date": str(return_date),
        "adults": adults,
        "currency": "INR",
        "hl": "en",
        "api_key": SERPAPI_API_KEY
    }

    try:
        response = requests.get(
            "https://serpapi.com/search.json",
            params=params,
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        if "error" in data:
            print(f"SerpApi returned error: {data['error']}")
            return None

        # Enhance top flight candidates with matching return flight segments from Google Flights
        all_candidates = (data.get("best_flights") or []) + (data.get("other_flights") or [])
        for candidate in all_candidates[:5]:
            dep_token = candidate.get("departure_token")
            if dep_token and "return_flights" not in candidate:
                ret_params = params.copy()
                ret_params["departure_token"] = dep_token
                try:
                    ret_resp = requests.get(
                        "https://serpapi.com/search.json",
                        params=ret_params,
                        timeout=15
                    )
                    if ret_resp.status_code == 200:
                        ret_data = ret_resp.json()
                        ret_options = ret_data.get("best_flights") or ret_data.get("other_flights") or []
                        if ret_options:
                            candidate["return_flights"] = ret_options[0].get("flights", [])
                            # Preserve the matched return flight total price and details
                            if ret_options[0].get("price"):
                                candidate["price"] = ret_options[0]["price"]
                except Exception:
                    pass

        return data
    except requests.RequestException as exc:
        print(f"SerpApi request failed: {exc}")
        return None
