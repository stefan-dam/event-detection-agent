"""Apply approved changes to itinerary rows and write updated Excel."""

from __future__ import annotations

from typing import Dict, List

import pandas as pd


def apply_changes(rows: List[Dict[str, str]], approved_changes: List[Dict[str, str]]) -> List[Dict[str, str]]:
    row_index = {row.get("row_id"): row for row in rows}

    for change in approved_changes:
        row_id = change.get("itinerary_row_id")
        change_type = change.get("change_type")
        new_time = change.get("new_time")
        new_location = change.get("new_location")
        title = change.get("title", "")
        rationale = change.get("rationale", "")
        proposed_change = change.get("proposed_change", "")

        target = row_index.get(row_id)
        if change_type in {"move", "replace", "swap"} and target:
            if new_time:
                if "-" in new_time:
                    start, end = [part.strip() for part in new_time.split("-", 1)]
                    target["start_time"] = start
                    target["end_time"] = end
                else:
                    target["start_time"] = new_time
            if new_location:
                target["location_area"] = new_location
            target["notes"] = f"{target.get('notes','')} | {proposed_change}".strip(" |")
        elif change_type == "cancel" and target:
            target["activity_type"] = "Cancelled"
            target["notes"] = f"{target.get('notes','')} | {proposed_change}".strip(" |")
        elif change_type == "add":
            rows.append(
                {
                    "day": change.get("itinerary_day", ""),
                    "date": change.get("date", ""),
                    "start_time": new_time or "",
                    "end_time": "",
                    "city": change.get("location", ""),
                    "location_area": new_location or "",
                    "activity_type": "Added",
                    "activity_description": title or proposed_change,
                    "notes": rationale,
                }
            )

    return rows


def write_updated_itinerary(rows: List[Dict[str, str]], output_path: str) -> None:
    df = pd.DataFrame(rows)
    df.to_excel(output_path, index=False)
