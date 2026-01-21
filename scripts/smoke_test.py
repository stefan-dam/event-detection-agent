"""Minimal smoke test for grading."""

from __future__ import annotations

import os
from pathlib import Path

from src.agent import build_agent, detect_events
from src.agent_queries import build_queries
from src.loaders import extract_itinerary_context, format_itinerary_rows, load_itinerary, load_preferences
from src.memory import MemoryStore
from src.patcher import apply_changes, write_updated_itinerary
from src.tools import (
    official_hazard_scrape,
    official_hazard_search,
    web_scrape,
    web_search,
)


def main() -> None:
    if not os.environ.get("GROQ_API_KEY"):
        raise SystemExit("GROQ_API_KEY is not set.")

    preferences = load_preferences("data/User_prefrences.docx")
    itinerary_rows = load_itinerary("data/Itinerary.xlsx")
    itinerary_text = format_itinerary_rows(itinerary_rows)
    itinerary_context = extract_itinerary_context(itinerary_rows)

    memory = MemoryStore("outputs/state.json")
    memory.increment_run_count()
    blocked_event_ids = memory.get_blocked_event_ids(ttl_runs=2)
    memory_summary = (
        "Approvals:\n"
        + memory.summarize_approvals()
        + "\nHistory:\n"
        + memory.summarize_history()
    )

    agent = build_agent(
        tools=[web_search, web_scrape, official_hazard_search, official_hazard_scrape],
        model=os.environ.get("GROQ_MODEL", "llama-3.1-70b-versatile"),
    )

    events = detect_events(
        agent=agent,
        preferences=preferences,
        itinerary=itinerary_text,
        memory_events=memory.state.get("events", []),
        memory_summary=memory_summary,
        blocked_event_ids=blocked_event_ids,
        queries=build_queries(itinerary_context, preferences),
        context=itinerary_context,
        required_categories=["hazard", "opportunity"],
        max_events=6,
    )

    memory.add_events([e.model_dump() for e in events.events])
    approved = [e.model_dump() for e in events.events]
    for event in events.events:
        memory.set_approval(event.id, True)
    memory.add_history(f"Smoke test run with {len(events.events)} events.")
    memory.save()

    if approved:
        updated_rows = apply_changes(itinerary_rows, approved)
        write_updated_itinerary(updated_rows, "outputs/Itinerary_updated.xlsx")

    output_text = Path("outputs/itinerary_changes.txt")
    output_text.write_text(
        f"Approved changes: {len(approved)}\n",
        encoding="utf-8",
    )

    hazards = len([e for e in events.events if e.category == "hazard"])
    opportunities = len([e for e in events.events if e.category == "opportunity"])
    print(f"Detected {hazards} hazards and {opportunities} opportunities.")


if __name__ == "__main__":
    main()
