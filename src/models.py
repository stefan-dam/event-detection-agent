from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class Source(BaseModel):
    title: str = Field(..., description="Short title for the source")
    url: str = Field(..., description="Source URL")
    snippet: str = Field(..., description="Relevant excerpt from the source")


class Event(BaseModel):
    id: str = Field(..., description="Stable event identifier")
    category: Literal["hazard", "opportunity"] = Field(
        ..., description="Type of event"
    )
    title: str = Field(..., description="Short headline")
    location: str = Field(..., description="Location tied to the event")
    date: str = Field(..., description="Date of relevance, ISO YYYY-MM-DD")
    time_window: Optional[str] = Field(
        None, description="Time window if applicable"
    )
    description: str = Field(..., description="What is happening")
    rationale: str = Field(..., description="Why this matters for the traveler")
    recommendation: str = Field(..., description="Suggested action or mitigation")
    proposed_change: str = Field(
        ..., description="Concrete change suggested to the itinerary"
    )
    itinerary_day: Optional[str] = Field(
        None, description="Associated itinerary day number"
    )
    itinerary_row_id: Optional[str] = Field(
        None, description="Stable row identifier from the itinerary"
    )
    change_type: Optional[Literal["move", "cancel", "swap", "add", "replace"]] = Field(
        None, description="Type of itinerary change"
    )
    new_time: Optional[str] = Field(
        None, description="New proposed time window"
    )
    new_location: Optional[str] = Field(
        None, description="New proposed location"
    )
    sources: List[Source] = Field(
        default_factory=list, description="Supporting sources"
    )
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Confidence score 0-1"
    )


class EventList(BaseModel):
    events: List[Event] = Field(default_factory=list)
