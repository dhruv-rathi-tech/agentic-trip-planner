from src.evaluator import check_budget


def reflect(flights, hotels, combination, budget):
    """
    Constraint-validation and reflection stage.
    Verifies that flight and hotel candidates are available and that
    the selected combination fits within the user's budget tolerance.
    """
    if not flights:
        return {
            "verified": False,
            "reason": "No flight candidates were found.",
            "total_cost": None,
            "budget": budget
        }

    if not hotels:
        return {
            "verified": False,
            "reason": "No hotel candidates were found.",
            "total_cost": None,
            "budget": budget
        }

    if not combination:
        return {
            "verified": False,
            "reason": "No candidate combination was available.",
            "total_cost": None,
            "budget": budget
        }

    return check_budget(
        [combination["flight_cost"], combination["hotel_cost"]],
        budget
    )
