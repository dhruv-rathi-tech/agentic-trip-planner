from datetime import date, timedelta
from typing import List
from pydantic import BaseModel, Field, field_validator


class TripPlan(BaseModel):
    origin: str
    destination: str
    start_date: date
    end_date: date
    duration_days: int
    budget: float = 0.0
    preferences: List[str] = Field(default_factory=list)

    @field_validator("start_date", "end_date", mode="before")
    @classmethod
    def _fallback_date(cls, value):
        if isinstance(value, str):
            try:
                return date.fromisoformat(value)
            except ValueError:
                return (date.today() + timedelta(days=14)).isoformat()
        return value

    @field_validator("duration_days", mode="after")
    @classmethod
    def _positive_duration(cls, value):
        if value <= 0:
            raise ValueError("duration_days must be greater than zero")
        return value


class TripState(BaseModel):
    origin: str
    destination: str
    start_date: date
    end_date: date
    duration_days: int
    budget: float = 0.0
    preferences: List[str] = Field(default_factory=list)
    weather: dict = Field(default_factory=dict)
    weather_status: str = ""
    selected_combination: dict = Field(default_factory=dict)
    verification: dict = Field(default_factory=dict)
    attempt: int = 0
    dates_changed: bool = False
