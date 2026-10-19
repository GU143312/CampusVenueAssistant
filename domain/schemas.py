from datetime import date, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator

Equipment = Literal["projector", "whiteboard", "video_conference"]
Building = Literal["B", "C"]


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    date_local: date
    earliest_start: time
    latest_end: time
    duration_minutes: StrictInt = Field(ge=30, le=120)
    participants: StrictInt = Field(ge=1, le=100)
    required_equipment: list[Equipment]
    required_building: Building | None = None
    preferred_building: Building | None = None
    limit: StrictInt = Field(default=5, ge=1, le=20)

    @field_validator("earliest_start", "latest_end")
    @classmethod
    def half_hour(cls, value):
        if value.tzinfo or value.minute % 30 or value.second or value.microsecond:
            raise ValueError("Use local HH:MM on a 30-minute boundary")
        return value

    @model_validator(mode="after")
    def valid_window(self):
        if self.duration_minutes % 30:
            raise ValueError("Duration must be a multiple of 30 minutes")
        if self.earliest_start >= self.latest_end:
            raise ValueError("End must be later than start; overnight queries are unsupported")
        if self.earliest_start < time(8) or self.latest_end > time(22):
            raise ValueError("Query window must be within 08:00-22:00")
        if len(self.required_equipment) != len(set(self.required_equipment)):
            raise ValueError("Duplicate equipment")
        return self
