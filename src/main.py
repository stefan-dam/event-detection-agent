from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .agent import build_agent, detect_events
from .agent_queries import build_queries
from .loaders import (
    extract_itinerary_context,
    format_itinerary_rows,
    load_itinerary,
    load_preferences,
)
from .patcher import apply_changes, write_updated_itinerary
from .memory import MemoryStore
from .tools import (
    official_hazard_scrape,
    official_hazard_search,
    web_scrape,
    web_search,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AI Event Detection Agent")
    parser.add_argument(
        "--preferences",
        required=True,
        help="Path to user preferences (.docx or .txt)",
    )
    parser.add_argument(
        "--itinerary",
        required=True,
        help="Path to itinerary Excel file (.xlsx)",
    )
    parser.add_argument(
        "--sheet",
        default=None,
        help="Optional Excel sheet name",
    )
    parser.add_argument(
        "--output",
        default="outputs/itinerary_changes.txt",
        help="Output path for approved changes",
    )
    parser.add_argument(
        "--json-output",
        default="outputs/itinerary_changes.json",
        help="Output path for JSON patch file",
    )
    parser.add_argument(
        "--updated-itinerary",
        default="outputs/Itinerary_updated.xlsx",
        help="Output path for updated itinerary Excel file",
    )
    parser.add_argument(
        "--state",
        default="outputs/state.json",
        help="Path to memory/state file",
    )
    parser.add_argument(
        "--max-events",
        type=int,
        default=8,
        help="Maximum number of events to return",
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("GROQ_MODEL", "llama-3.1-70b-versatile"),
        help="Groq model name",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if not os.environ.get("GROQ_API_KEY"):
        print("GROQ_API_KEY is not set. See README for setup.")
        return 1

    preferences = load_preferences(args.preferences)
    itinerary_rows = load_itinerary(args.itinerary, sheet_name=args.sheet)
    itinerary_text = format_itinerary_rows(itinerary_rows)
    itinerary_context = extract_itinerary_context(itinerary_rows)

    memory = MemoryStore(args.state)
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
        model=args.model,
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
        max_events=args.max_events,
    )

    approved_changes = []
    rejected_changes = []
    for event in events.events:
        print("\n" + "=" * 60)
        print(f"{event.category.upper()}: {event.title}")
        print(f"Where/When: {event.location} | {event.date} | {event.time_window}")
        print(f"Details: {event.description}")
        print(f"Why it matters: {event.rationale}")
        print(f"Recommendation: {event.recommendation}")
        print(f"Proposed change: {event.proposed_change}")
        print(
            f"Patch: day={event.itinerary_day} row={event.itinerary_row_id} "
            f"type={event.change_type} new_time={event.new_time} "
            f"new_location={event.new_location}"
        )
        if event.sources:
            print("Sources:")
            for source in event.sources:
                print(f" - {source.title}: {source.url}")

        answer = input("Approve this change? (y/n): ").strip().lower()
        approved = answer in {"y", "yes"}
        memory.set_approval(event.id, approved)
        record = {
            "id": event.id,
            "date": event.date,
            "title": event.title,
            "rationale": event.rationale,
            "proposed_change": event.proposed_change,
            "location": event.location,
            "itinerary_day": event.itinerary_day,
            "itinerary_row_id": event.itinerary_row_id,
            "change_type": event.change_type,
            "new_time": event.new_time,
            "new_location": event.new_location,
        }
        if approved:
            approved_changes.append(record)
        else:
            rejected_changes.append(record)

    memory.add_events([e.model_dump() for e in events.events])
    memory.add_history(
        f"Run completed with {len(events.events)} events, "
        f"{len(approved_changes)} approved."
    )
    memory.save()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_lines = []
    output_lines.append("APPROVED CHANGES")
    if approved_changes:
        for change in approved_changes:
            output_lines.append(
                f"- [{change['id']}] {change['date']} | {change['title']} "
                f"| {change['rationale']} | {change['proposed_change']}"
            )
    else:
        output_lines.append("- None")
    output_lines.append("")
    output_lines.append("REJECTED CHANGES")
    if rejected_changes:
        for change in rejected_changes:
            output_lines.append(
                f"- [{change['id']}] {change['date']} | {change['title']} "
                f"| {change['rationale']} | {change['proposed_change']}"
            )
    else:
        output_lines.append("- None")

    output_path.write_text("\n".join(output_lines), encoding="utf-8")

    json_output = Path(args.json_output)
    json_output.parent.mkdir(parents=True, exist_ok=True)
    patch_payload = {
        "approved": approved_changes,
        "rejected": rejected_changes,
    }
    json_output.write_text(
        json.dumps(patch_payload, indent=2),
        encoding="utf-8",
    )

    if approved_changes:
        updated_rows = apply_changes(itinerary_rows, approved_changes)
        write_updated_itinerary(updated_rows, args.updated_itinerary)

    print(f"\nSaved changes to {output_path}")
    print(f"Saved JSON patch to {json_output}")
    if approved_changes:
        print(f"Saved updated itinerary to {args.updated_itinerary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
