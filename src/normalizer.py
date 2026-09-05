# NORMALIZE FLIGHTS

def normalize_flights(raw_response):
    """
    Convert SerpApi Google Flights response into the internal flight format used by the evaluator.
    Preserves total price, duration, stops, airline, flight number, departure, and arrival info.
    """
    if not isinstance(raw_response, dict):
        return []

    flight_items = []
    if isinstance(raw_response.get("best_flights"), list):
        flight_items.extend(raw_response["best_flights"])
    if isinstance(raw_response.get("other_flights"), list):
        flight_items.extend(raw_response["other_flights"])

    search_params = raw_response.get("search_parameters", {})

    normalized = []
    for index, item in enumerate(flight_items):
        if not isinstance(item, dict):
            continue

        legs = item.get("flights") if isinstance(item.get("flights"), list) else []
        first_leg = legs[0] if legs and isinstance(legs[0], dict) else {}
        last_leg = legs[-1] if len(legs) > 1 and isinstance(legs[-1], dict) else None

        # Price
        price_val = item.get("price")
        try:
            price = float(price_val) if price_val is not None else 0.0
        except (TypeError, ValueError):
            price = 0.0

        # Duration
        duration_val = item.get("total_duration") or first_leg.get("duration")
        try:
            duration_minutes = int(duration_val) if duration_val is not None else 0
        except (TypeError, ValueError):
            duration_minutes = 0

        # Stops
        stops = max(len(legs) - 1, 0)

        # Airline & Flight number
        airline = first_leg.get("airline") or item.get("airline") or "Unknown"
        flight_number = first_leg.get("flight_number") or "Unknown"

        # Airports
        dep_airport = first_leg.get("departure_airport") if isinstance(first_leg.get("departure_airport"), dict) else {}
        arr_airport = (
            (last_leg.get("arrival_airport") if isinstance(last_leg.get("arrival_airport"), dict) else {})
            if last_leg else
            (first_leg.get("arrival_airport") if isinstance(first_leg.get("arrival_airport"), dict) else {})
        )

        origin = dep_airport.get("id") or search_params.get("departure_id")
        destination = arr_airport.get("id") or search_params.get("arrival_id")

        # Dates
        dep_time = dep_airport.get("time")
        dep_date = str(dep_time)[:10] if dep_time else search_params.get("outbound_date")
        ret_date = search_params.get("return_date")

        # Outbound and Return segments for round trip
        outbound_legs = legs
        return_legs = item.get("return_flights") or []

        normalized.append({
            "id": str(item.get("departure_token") or index),
            "trip_type": "ROUND_TRIP",
            "origin": origin,
            "destination": destination,
            "departure_date": dep_date,
            "return_date": ret_date,
            "airline": airline,
            "flight_number": flight_number,
            "price": price,
            "currency": "INR",
            "duration_minutes": duration_minutes,
            "stops": stops,
            "outbound_legs": outbound_legs,
            "return_legs": return_legs,
            "outbound": first_leg or None,
            "return": (return_legs[0] if return_legs else (last_leg or None)),
            "raw": item
        })

    return normalized


# HELPERS & NORMALIZED HOTELS
def _get_first(data, keys, default=None):
    if not isinstance(data, dict):
        return default
    for key in keys:
        if key in data and data[key] is not None:
            return data[key]
    return default


def _extract_list(data, possible_keys):
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        return []
    for key in possible_keys:
        value = data.get(key)
        if isinstance(value, list):
            return value
    return []


def _extract_hotel_list(raw_response):
    # Extract hotel results from common RouteStack response wrappers.

    if raw_response is None:
        return []

    if isinstance(raw_response, list):
        return raw_response

    if not isinstance(raw_response, dict):
        return []

    # Direct response
    hotels = _extract_list(
        raw_response,
        [
            "hotels",
            "hotelResults",
            "results",
            "data"
        ]
    )

    if hotels:
        return hotels

    # Nested response
    response = raw_response.get("response")

    if isinstance(response, list):
        return response

    if isinstance(response, dict):
        hotels = _extract_list(
            response,
            [
                "result",
                "hotels",
                "hotelResults",
                "results",
                "data"
            ]
        )

        if hotels:
            return hotels

        result = response.get("result")

        if isinstance(result, list):
            return result

        if isinstance(result, dict):
            hotels = _extract_list(
                result,
                [
                    "result",
                    "hotels",
                    "hotelResults",
                    "results",
                    "data"
                ]
            )

            if hotels:
                return hotels

    # Nested result directly under raw response
    result = raw_response.get("result")

    if isinstance(result, list):
        return result

    if isinstance(result, dict):
        hotels = _extract_list(
            result,
            [
                "result",
                "hotels",
                "hotelResults",
                "results",
                "data"
            ]
        )

        if hotels:
            return hotels

    return []


def _extract_hotel_price(hotel):
    # Extract hotel price.

    price = _get_first(
        hotel,
        [
            "ourprice",
            "publishedRate",
            "baseprice",
            "price",
            "totalPrice",
            "amount",
            "rate",
            "total"
        ]
    )

    if isinstance(price, dict):
        price = _get_first(
            price,
            [
                "amount",
                "value",
                "total"
            ]
        )

    try:
        return float(price)
    except (TypeError, ValueError):
        return 0.0


def normalize_hotels(raw_response):
    """
    Convert RouteStack hotel results into the internal format used by the evaluator.
    Current project scope: Hotel price is treated as the price returned by the RouteStack search result.
    No additional taxes, meals, transportation, activities, etc. are added.
    """

    raw_hotels = _extract_hotel_list(raw_response)
    normalized = []

    # Detect currency
    raw_currency = "INR"
    if isinstance(raw_response, dict):
        raw_currency = (
            raw_response.get("currency")
            or raw_response.get("result", {}).get("currency")
            or (raw_response.get("response", {}).get("result", {}).get("currency") if isinstance(raw_response.get("response"), dict) and isinstance(raw_response.get("response", {}).get("result"), dict) else None)
            or "INR"
        )

    for index, hotel in enumerate(raw_hotels):
        if not isinstance(hotel, dict):
            continue

        raw_price = _extract_hotel_price(hotel)
        # If RouteStack returns USD, convert to INR for consistency with user INR budget
        if raw_currency.upper() == "USD" or hotel.get("currency", "").upper() == "USD":
            price_inr = round(raw_price * 85.0, 2)
        else:
            price_inr = raw_price

        # Extract facilities/amenities
        facilities = hotel.get("facilities") or hotel.get("amenities") or []
        if isinstance(facilities, list):
            amenity_names = [
                f.get("name") if isinstance(f, dict) else str(f)
                for f in facilities
            ]
        else:
            amenity_names = []

        normalized_hotel = {
            "id": _get_first(
                hotel,
                [
                    "id",
                    "hotelId",
                    "propertyId"
                ],
                str(index)
            ),

            "name": _get_first(
                hotel,
                [
                    "name",
                    "hotelName",
                    "propertyName"
                ],
                "Unknown Hotel"
            ),

            "price": price_inr,

            "currency": "INR",

            "rating": _get_first(
                hotel,
                [
                    "starRating",
                    "rating",
                    "hotelRating"
                ],
                0
            ),

            "review_count": _get_first(
                hotel,
                [
                    "reviewCount",
                    "review_count",
                    "numberOfReviews"
                ],
                0
            ),

            "address": _get_first(
                hotel,
                [
                    "address",
                    "hotelAddress"
                ],
                ""
            ),

            "amenities": amenity_names,

            # Preserve original API result.
            "raw": hotel
        }

        try:
            normalized_hotel["rating"] = float(
                normalized_hotel["rating"] or 0
            )
        except (TypeError, ValueError):
            normalized_hotel["rating"] = 0.0

        try:
            normalized_hotel["review_count"] = int(
                normalized_hotel["review_count"] or 0
            )
        except (TypeError, ValueError):
            normalized_hotel["review_count"] = 0

        normalized.append(normalized_hotel)

    return normalized