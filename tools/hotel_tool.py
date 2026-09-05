def resolve_destination(client, destination):
    response = client.search_hotel_destination(destination)

    candidates = []

    if isinstance(response, dict):
        direct = response.get("citySearchDestination")
        if isinstance(direct, dict):
            candidates.append(direct)

        result = response.get("result")
        if isinstance(result, list):
            candidates.extend(x for x in result if isinstance(x, dict))
        elif isinstance(result, dict):
            direct = result.get("citySearchDestination")
            if isinstance(direct, dict):
                candidates.append(direct)

            candidates.extend(
                x for x in (
                    result.get("destinations"),
                    result.get("results"),
                    result.get("data")
                )
                if isinstance(x, list)
                for x in x
                if isinstance(x, dict)
            )

    if not candidates:
        raise ValueError(
            f"Could not resolve hotel destination: {destination}"
        )

    # Pick the best candidate dynamically based on relevance to the query
    dest_lower = destination.strip().lower()

    def candidate_score(c):
        score = 0
        name = str(c.get("fullName") or c.get("name") or c.get("city") or "").lower()
        ctype = str(c.get("type") or "").lower()

        # Exact or prefix match with the query
        if name.startswith(dest_lower):
            score += 50
        elif dest_lower in name:
            score += 30

        # Prefer standard destination types (city, state, region, country) over specific POIs or stations
        if ctype in {"city", "neighborhood", "state", "region", "country"}:
            score += 20
        elif ctype in {"trainstation", "pointofinterest"}:
            score -= 10
        return score

    candidates.sort(key=candidate_score, reverse=True)
    destination_info = candidates[0]

    destination_id = (
        destination_info.get("destinationId")
        or destination_info.get("destination_id")
        or destination_info.get("id")
    )

    coordinates = destination_info.get("coordinates") if isinstance(destination_info.get("coordinates"), dict) else {}

    latitude = (
        destination_info.get("lat")
        or destination_info.get("latitude")
        or coordinates.get("lat")
    )

    longitude = (
        destination_info.get("long")
        or destination_info.get("longitude")
        or coordinates.get("long")
    )

    if not destination_id:
        raise ValueError(
            f"RouteStack did not return destinationId for {destination}."
        )

    if latitude is None or longitude is None:
        raise ValueError(
            f"RouteStack did not return coordinates for {destination}."
        )

    return {
        "destination_id": destination_id,
        "latitude": latitude,
        "longitude": longitude
    }


def search_hotels(client, destination, check_in, check_out, rooms):
    if check_out <= check_in:
        raise ValueError("Hotel check-out must be after check-in.")

    location = resolve_destination(client, destination)

    response = client.search_hotels(
        destination_id=location["destination_id"],
        latitude=location["latitude"],
        longitude=location["longitude"],
        check_in=str(check_in),
        check_out=str(check_out),
        rooms=rooms
    )

    return {
        "location": location,
        "response": response
    }
