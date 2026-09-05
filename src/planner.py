import json
from datetime import date
from groq import Groq

from config.config import GROQ_API_KEY, GROQ_MODEL
from src.models import TripPlan
from src.prompts import PLANNER_SYSTEM_PROMPT

if not GROQ_API_KEY:
    raise RuntimeError(
        "GROQ_API_KEY is missing. Put it in your .env file."
    )

client = Groq(api_key=GROQ_API_KEY)

PLANNER_SCHEMA = {
    "type": "object",
    "properties": {
        "origin": {"type": "string"},
        "destination": {"type": "string"},
        "start_date": {"type": "string"},
        "end_date": {"type": "string"},
        "duration_days": {"type": "integer"},
        "budget": {"type": "number"},
        "preferences": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "origin", "destination", "start_date", "end_date",
        "duration_days", "budget", "preferences"
    ],
    "additionalProperties": False
}


def create_plan(user_query):
    today = date.today().isoformat()
    user_content = (
        f"Today's date: {today}\n\n"
        f"User request: {user_query}"
    )

    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
            {"role": "user", "content": user_content}
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "trip_plan",
                "strict": True,
                "schema": PLANNER_SCHEMA
            }
        },
        temperature=0
    )

    content = response.choices[0].message.content
    if not content:
        raise RuntimeError("Planner returned an empty response.")

    try:
        data = json.loads(content)
        plan = TripPlan(**data)
    except (json.JSONDecodeError, ValueError) as exc:
        raise RuntimeError(f"Could not parse planner response: {exc}") from exc

    # Ensure duration_days is mathematically consistent
    calculated_duration = (plan.end_date - plan.start_date).days
    if calculated_duration <= 0:
        raise ValueError("End date must be after start date.")

    plan.duration_days = calculated_duration
    return plan
