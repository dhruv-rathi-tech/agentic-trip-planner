import os
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")

ROUTESTACK_ACCOUNT_ID = os.getenv("ROUTESTACK_ACCOUNT_ID")
ROUTESTACK_API_KEY = os.getenv("ROUTESTACK_API_KEY")
ROUTESTACK_API_SECRET = os.getenv("ROUTESTACK_API_SECRET")
ROUTESTACK_ENDPOINT = os.getenv(
    "ROUTESTACK_ENDPOINT",
    "https://evolvemcp.routestack.ai"
).rstrip("/")

SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY")

MAX_ATTEMPTS = 3
TOP_FLIGHTS = 3
TOP_HOTELS = 3

# 0.05 = allow up to 5% over the stated budget.
BUDGET_BUFFER_PERCENT = 0.05

WEATHER_BAD_DAY_THRESHOLD = 2
RAIN_PROBABILITY_THRESHOLD = 60

# Alternative-date search window.
MAX_ALTERNATIVE_DAYS = 10
