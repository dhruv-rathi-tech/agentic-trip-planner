from config.config import BUDGET_BUFFER_PERCENT


def check_budget(items, total_budget):
    total_cost = round(sum(float(x) for x in items), 2)

    # budget <= 0 means the user did not specify a budget.
    if total_budget <= 0:
        return {
            "total_cost": total_cost,
            "budget": 0.0,
            "allowed_budget": None,
            "difference": None,
            "within_stated_budget": None,
            "within_tolerance": True,
            "verified": True,
            "reason": "No budget was specified; ranking was used instead."
        }

    allowed_budget = round(total_budget * (1 + BUDGET_BUFFER_PERCENT), 2)
    within_stated = total_cost <= total_budget
    within_tolerance = total_cost <= allowed_budget

    if within_stated:
        reason = "Selected combination is within stated budget."
    elif within_tolerance:
        reason = f"Selected combination is within the allowed {BUDGET_BUFFER_PERCENT * 100:.0f}% tolerance."
    else:
        reason = "Selected combination exceeds budget tolerance."

    return {
        "total_cost": total_cost,
        "budget": total_budget,
        "allowed_budget": allowed_budget,
        "difference": round(total_budget - total_cost, 2),
        "within_stated_budget": within_stated,
        "within_tolerance": within_tolerance,
        "verified": within_tolerance,
        "reason": reason
    }


def normalize(value, minimum, maximum):
    if maximum == minimum:
        return 1.0
    return (value - minimum) / (maximum - minimum)


def inverse_normalize(value, minimum, maximum):
    return 1 - normalize(value, minimum, maximum)


def score_flights(flights):
    if not flights:
        return []

    prices = [flight["price"] for flight in flights]
    durations = [flight["duration_minutes"] for flight in flights]
    stops = [flight["stops"] for flight in flights]

    min_price, max_price = min(prices), max(prices)
    min_duration, max_duration = min(durations), max(durations)
    min_stops, max_stops = min(stops), max(stops)

    scored = []

    for flight in flights:
        price_score = inverse_normalize(
            flight["price"], min_price, max_price
        )
        duration_score = inverse_normalize(
            flight["duration_minutes"], min_duration, max_duration
        )
        stops_score = inverse_normalize(
            flight["stops"], min_stops, max_stops
        )

        result = flight.copy()
        result["evaluation_score"] = round(
            (0.50 * price_score +
             0.30 * duration_score +
             0.20 * stops_score) * 100,
            2
        )
        scored.append(result)

    return sorted(
        scored,
        key=lambda x: x["evaluation_score"],
        reverse=True
    )


def score_hotels(hotels):
    if not hotels:
        return []

    prices = [hotel["price"] for hotel in hotels]
    ratings = [hotel.get("rating", 0) or 0 for hotel in hotels]
    reviews = [hotel.get("review_count", 0) or 0 for hotel in hotels]

    min_price, max_price = min(prices), max(prices)
    min_rating, max_rating = min(ratings), max(ratings)
    min_reviews, max_reviews = min(reviews), max(reviews)

    scored = []

    for hotel in hotels:
        price_score = inverse_normalize(
            hotel["price"], min_price, max_price
        )
        rating_score = normalize(
            hotel.get("rating", 0) or 0,
            min_rating,
            max_rating
        )
        review_score = normalize(
            hotel.get("review_count", 0) or 0,
            min_reviews,
            max_reviews
        )

        result = hotel.copy()
        result["evaluation_score"] = round(
            (0.35 * price_score +
             0.40 * rating_score +
             0.25 * review_score) * 100,
            2
        )
        scored.append(result)

    return sorted(
        scored,
        key=lambda x: x["evaluation_score"],
        reverse=True
    )


def generate_combinations(flights, hotels, budget):
    combinations = []

    allowed_budget = (
        None
        if budget <= 0
        else budget * (1 + BUDGET_BUFFER_PERCENT)
    )

    for flight in flights:
        for hotel in hotels:
            total_cost = flight["price"] + hotel["price"]

            if allowed_budget is not None and total_cost > allowed_budget:
                continue

            combination_score = (
                0.45 * flight["evaluation_score"]
                + 0.55 * hotel["evaluation_score"]
            )

            combinations.append({
                "flight": flight,
                "hotel": hotel,
                "flight_cost": flight["price"],
                "hotel_cost": hotel["price"],
                "total_cost": round(total_cost, 2),
                "budget": budget,
                "allowed_budget": (
                    round(allowed_budget, 2)
                    if allowed_budget is not None
                    else None
                ),
                "budget_difference": (
                    round(total_cost - budget, 2)
                    if budget > 0 else None
                ),
                "within_stated_budget": (
                    total_cost <= budget if budget > 0 else None
                ),
                "within_tolerance": (
                    total_cost <= allowed_budget
                    if allowed_budget is not None
                    else True
                ),
                "combination_score": round(combination_score, 2)
            })

    return sorted(
        combinations,
        key=lambda x: x["combination_score"],
        reverse=True
    )
