"""Shared query builder for CLI and API."""

from __future__ import annotations

from typing import List, Optional


def _infer_language(preferences: Optional[str]) -> str:
    if not preferences:
        return "local"
    lowered = preferences.lower()
    if "japanese" in lowered:
        return "Japanese"
    if "portuguese" in lowered:
        return "Portuguese"
    if "spanish" in lowered:
        return "Spanish"
    if "french" in lowered:
        return "French"
    return "local"


def build_queries(context: dict, preferences: Optional[str] = None) -> List[str]:
    date_min = context.get("date_min", "")
    date_max = context.get("date_max", "")
    dates = context.get("dates", [])
    cities = context.get("cities", [])
    locations = context.get("locations", [])
    queries: List[str] = []

    for city in cities:
        queries.append(f"weather forecast {city} {date_min} {date_max}")
        queries.append(f"travel advisory {city} {date_min} {date_max}")
        queries.append(f"public transport strike {city} {date_min} {date_max}")
        queries.append(f"festival events {city} {date_min} {date_max}")
        queries.append(f"museum deals {city} {date_min} {date_max}")
        queries.append(f"family-friendly events near {city} {date_min} {date_max}")

        for date in dates:
            queries.append(f"events {city} {date}")

    for location in locations:
        lower = location.lower()
        if "airport" in lower:
            queries.append(f"airport closure {location} {date_min} {date_max}")
        if "station" in lower:
            queries.append(f"train station disruption {location} {date_min} {date_max}")

    # Phrase opportunities
    language = _infer_language(preferences)
    if preferences:
        lowered = preferences.lower()
        if any(keyword in lowered for keyword in ["language", "phrase", "word", "japanese"]):
            for city in cities:
                queries.append(f"useful local phrase {city} {date_min} {date_max}")
                queries.append(f"common {language} phrase to use at restaurant {city}")

    return queries
