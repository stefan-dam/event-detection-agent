"""FastAPI service for the Event Detection Agent."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .agent import build_agent, detect_events
from .agent_queries import build_queries
from .loaders import extract_itinerary_context, format_itinerary_rows, load_itinerary, load_preferences
from .memory import MemoryStore
from .patcher import apply_changes, write_updated_itinerary
from .tools import (
    official_hazard_scrape,
    official_hazard_search,
    web_scrape,
    web_search,
)


class DetectRequest(BaseModel):
    preferences_path: str
    itinerary_path: str
    sheet_name: Optional[str] = None
    max_events: int = 8


class DetectWithApprovalsRequest(DetectRequest):
    approvals: dict[str, bool]


class ApproveRequest(BaseModel):
    event_id: str
    approved: bool


app = FastAPI(title="AI Event Detection Agent")


def _build_change_records(memory: MemoryStore) -> dict:
    records = {}
    for event in memory.state.get("events", []):
        records[event.get("id")] = event

    approved = []
    rejected = []
    for event_id, approved_flag in memory.state.get("approvals", {}).items():
        event = records.get(event_id)
        if not event:
            continue
        record = {
            "id": event.get("id"),
            "date": event.get("date"),
            "title": event.get("title"),
            "rationale": event.get("rationale"),
            "proposed_change": event.get("proposed_change"),
            "location": event.get("location"),
            "itinerary_day": event.get("itinerary_day"),
            "itinerary_row_id": event.get("itinerary_row_id"),
            "change_type": event.get("change_type"),
            "new_time": event.get("new_time"),
            "new_location": event.get("new_location"),
        }
        if approved_flag:
            approved.append(record)
        else:
            rejected.append(record)

    return {"approved": approved, "rejected": rejected}


def _write_outputs(memory: MemoryStore, output_path: str, json_output: str) -> None:
    payload = _build_change_records(memory)
    lines: List[str] = []
    lines.append("ITINERARY CHANGES (APPROVED)")
    if payload["approved"]:
        for change in payload["approved"]:
            lines.append(
                f"- [{change['id']}] {change['date']} | {change['title']} "
                f"| {change['rationale']} | {change['proposed_change']}"
            )
    else:
        lines.append("- None")

    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text("\n".join(lines), encoding="utf-8")

    json_file = Path(json_output)
    json_file.parent.mkdir(parents=True, exist_ok=True)
    json_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")


@app.post("/detect-events")
def detect_events_endpoint(request: DetectRequest) -> dict:
    if not os.environ.get("GROQ_API_KEY"):
        raise HTTPException(status_code=400, detail="GROQ_API_KEY is not set.")

    preferences = load_preferences(request.preferences_path)
    itinerary_rows = load_itinerary(request.itinerary_path, sheet_name=request.sheet_name)
    itinerary_text = format_itinerary_rows(itinerary_rows)
    itinerary_context = extract_itinerary_context(itinerary_rows)

    memory = MemoryStore("outputs/state.json")
    memory.state["last_itinerary_rows"] = itinerary_rows
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
        max_events=request.max_events,
    )

    memory.add_events([e.model_dump() for e in events.events])
    memory.state["pending_event_ids"] = [
        event.id
        for event in events.events
        if event.id not in memory.state.get("approvals", {})
    ]
    memory.add_history(f"API run completed with {len(events.events)} events.")
    memory.save()

    return events.model_dump()


@app.post("/detect-events-with-approvals")
def detect_events_with_approvals(request: DetectWithApprovalsRequest) -> dict:
    if not os.environ.get("GROQ_API_KEY"):
        raise HTTPException(status_code=400, detail="GROQ_API_KEY is not set.")

    preferences = load_preferences(request.preferences_path)
    itinerary_rows = load_itinerary(request.itinerary_path, sheet_name=request.sheet_name)
    itinerary_text = format_itinerary_rows(itinerary_rows)
    itinerary_context = extract_itinerary_context(itinerary_rows)

    memory = MemoryStore("outputs/state.json")
    memory.state["last_itinerary_rows"] = itinerary_rows
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
        max_events=request.max_events,
    )

    memory.add_events([e.model_dump() for e in events.events])
    memory.state["pending_event_ids"] = [
        event.id
        for event in events.events
        if event.id not in memory.state.get("approvals", {})
    ]

    for event in events.events:
        approved = request.approvals.get(event.id)
        if approved is None:
            continue
        memory.set_approval(event.id, approved)

    memory.add_history(
        f"API detect+approve completed with {len(events.events)} events."
    )
    memory.save()

    _write_outputs(memory, "outputs/itinerary_changes.txt", "outputs/itinerary_changes.json")

    approved_changes = _build_change_records(memory)["approved"]
    if approved_changes:
        updated_rows = apply_changes(itinerary_rows, approved_changes)
        write_updated_itinerary(updated_rows, "outputs/Itinerary_updated.xlsx")

    return {
        "events": events.model_dump(),
        "approvals_applied": request.approvals,
    }


def _get_event_by_id(memory: MemoryStore, event_id: str) -> dict | None:
    for event in memory.state.get("events", []):
        if event.get("id") == event_id:
            return event
    return None


@app.get("/next-approval")
def next_approval_endpoint() -> dict:
    memory = MemoryStore("outputs/state.json")
    pending = memory.state.get("pending_event_ids", [])
    if not pending:
        return {"event": None}
    event_id = pending[0]
    event = _get_event_by_id(memory, event_id)
    return {"event": event}


@app.post("/submit-approval")
def submit_approval_endpoint(request: ApproveRequest) -> dict:
    memory = MemoryStore("outputs/state.json")
    memory.set_approval(request.event_id, request.approved)
    pending = memory.state.get("pending_event_ids", [])
    if request.event_id in pending:
        pending.remove(request.event_id)
        memory.state["pending_event_ids"] = pending
    memory.add_history(
        f"Approval updated: {request.event_id} -> {request.approved}"
    )
    memory.save()

    _write_outputs(memory, "outputs/itinerary_changes.txt", "outputs/itinerary_changes.json")
    approved_changes = _build_change_records(memory)["approved"]
    if approved_changes:
        original_rows = memory.state.get("last_itinerary_rows", [])
        if original_rows:
            updated_rows = apply_changes(original_rows, approved_changes)
            write_updated_itinerary(updated_rows, "outputs/Itinerary_updated.xlsx")
    return {"status": "ok", "event_id": request.event_id, "approved": request.approved}


@app.post("/approve")
def approve_endpoint(request: ApproveRequest) -> dict:
    memory = MemoryStore("outputs/state.json")
    memory.set_approval(request.event_id, request.approved)
    pending = memory.state.get("pending_event_ids", [])
    if request.event_id in pending:
        pending.remove(request.event_id)
        memory.state["pending_event_ids"] = pending
    memory.add_history(
        f"Approval updated: {request.event_id} -> {request.approved}"
    )
    memory.save()

    _write_outputs(memory, "outputs/itinerary_changes.txt", "outputs/itinerary_changes.json")
    approved_changes = _build_change_records(memory)["approved"]
    if approved_changes:
        original_rows = memory.state.get("last_itinerary_rows", [])
        if original_rows:
            updated_rows = apply_changes(original_rows, approved_changes)
            write_updated_itinerary(updated_rows, "outputs/Itinerary_updated.xlsx")
    return {"status": "ok", "event_id": request.event_id, "approved": request.approved}


@app.get("/state")
def state_endpoint() -> dict:
    memory = MemoryStore("outputs/state.json")
    return {
        "run_count": memory.state.get("run_count", 0),
        "approvals": memory.state.get("approvals", {}),
        "history": memory.state.get("history", []),
        "events": memory.state.get("events", []),
    }
