"""Persistent memory store for events, approvals, and history."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


class MemoryStore:
    def __init__(self, path: str):
        self.path = Path(path)
        self.state: Dict[str, Any] = {
            "events": [],
            "approvals": {},
            "history": [],
            "run_count": 0,
            "rejections": {},
            "pending_event_ids": [],
        }
        self.load()

    def load(self) -> None:
        if self.path.exists():
            self.state = json.loads(self.path.read_text(encoding="utf-8"))

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.state, indent=2), encoding="utf-8")

    def add_events(self, events: List[Dict[str, Any]]) -> None:
        existing_ids = {event.get("id") for event in self.state["events"]}
        for event in events:
            event_id = event.get("id")
            if event_id and event_id in existing_ids:
                continue
            self.state["events"].append(event)
            if event_id:
                existing_ids.add(event_id)

    def add_history(self, entry: str) -> None:
        self.state["history"].append(entry)

    def set_approval(self, event_id: str, approved: bool) -> None:
        self.state["approvals"][event_id] = approved
        if not approved:
            self.state["rejections"][event_id] = self.state.get("run_count", 0)

    def increment_run_count(self) -> int:
        self.state["run_count"] = int(self.state.get("run_count", 0)) + 1
        return self.state["run_count"]

    def get_blocked_event_ids(self, ttl_runs: int = 2) -> List[str]:
        current_run = int(self.state.get("run_count", 0))
        blocked = []
        for event_id, rejected_run in self.state.get("rejections", {}).items():
            if current_run - int(rejected_run) <= ttl_runs:
                blocked.append(event_id)
        return blocked

    def summarize_history(self, max_entries: int = 5) -> str:
        entries = self.state.get("history", [])[-max_entries:]
        return "\n".join(entries)

    def summarize_approvals(self, max_entries: int = 5) -> str:
        approvals = self.state.get("approvals", {})
        items = list(approvals.items())[-max_entries:]
        return "\n".join([f"{event_id}: {approved}" for event_id, approved in items])
