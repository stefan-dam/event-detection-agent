"""File loaders and itinerary normalization utilities."""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
from docx import Document


def load_preferences(path: str) -> str:
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Preferences file not found: {path}")

    if file_path.suffix.lower() == ".docx":
        doc = Document(file_path)
        return "\n".join(p.text for p in doc.paragraphs).strip()

    return file_path.read_text(encoding="utf-8").strip()


def _normalize_columns(columns: List[str]) -> List[str]:
    normalized = []
    for col in columns:
        value = col.strip().lower()
        value = value.replace(" / ", "_").replace(" ", "_")
        value = value.replace("-", "_").replace("#", "")
        normalized.append(value)
    return normalized


def _apply_column_mapping(columns: List[str]) -> List[str]:
    aliases = {
        "daynumber": "day",
        "day_no": "day",
        "daynum": "day",
        "start": "start_time",
        "starttime": "start_time",
        "begin": "start_time",
        "from": "start_time",
        "depart": "start_time",
        "departure": "start_time",
        "start_time": "start_time",
        "end": "end_time",
        "endtime": "end_time",
        "finish": "end_time",
        "to": "end_time",
        "arrive": "end_time",
        "arrival": "end_time",
        "end_time": "end_time",
        "town": "city",
        "location_city": "city",
        "city_name": "city",
        "destination_city": "city",
        "destination": "city",
        "location": "location_area",
        "area": "location_area",
        "activity": "activity_description",
        "details": "activity_description",
        "desc": "activity_description",
        "description": "activity_description",
        "notes": "notes",
    }
    mapped = []
    for col in columns:
        mapped.append(aliases.get(col, col))
    return mapped


def _parse_single_column(df: pd.DataFrame) -> List[Dict[str, str]]:
    raw_header = df.columns[0]
    headers = [h.strip() for h in raw_header.split(",")]
    normalized = _normalize_columns(headers)
    normalized = _apply_column_mapping(normalized)
    _validate_columns(normalized)
    rows = []

    for idx, raw in enumerate(df.iloc[:, 0].fillna("").astype(str).tolist(), start=1):
        if not raw.strip():
            continue
        if raw.lower().startswith("day,"):
            continue
        fields = next(csv.reader([raw]))
        if len(fields) < len(normalized):
            fields = fields + [""] * (len(normalized) - len(fields))
        row = {normalized[i]: fields[i].strip() for i in range(len(normalized))}
        row.setdefault("row_id", str(idx))
        rows.append(row)

    return rows


def _parse_table(df: pd.DataFrame) -> List[Dict[str, str]]:
    normalized = _normalize_columns(df.columns.tolist())
    normalized = _apply_column_mapping(normalized)
    _validate_columns(normalized)
    df = df.copy()
    df.columns = normalized
    records = (
        df.fillna("")
        .astype(str)
        .to_dict(orient="records")
    )
    for idx, record in enumerate(records, start=1):
        record.setdefault("row_id", str(idx))
    return records


def _validate_columns(columns: List[str]) -> None:
    required = {"day", "date", "start_time", "end_time", "city"}
    missing = required.difference(columns)
    if missing:
        raise ValueError(
            f"Itinerary is missing required columns: {', '.join(sorted(missing))}"
        )


def _select_sheet(excel: pd.ExcelFile, required: List[str], sheet_name: Optional[str]) -> str:
    if sheet_name:
        return sheet_name
    for name in excel.sheet_names:
        df = excel.parse(name, nrows=1)
        columns = _normalize_columns(df.columns.tolist())
        if all(col in columns for col in required):
            return name
    return excel.sheet_names[0]


def load_itinerary(path: str, sheet_name: Optional[str] = None) -> List[Dict[str, str]]:
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Itinerary file not found: {path}")

    excel = pd.ExcelFile(file_path)
    required = ["day", "date", "start_time", "end_time", "city"]
    sheet = _select_sheet(excel, required, sheet_name)
    df = excel.parse(sheet, dtype=str)
    if df.shape[1] == 1:
        return _parse_single_column(df)

    return _parse_table(df)


def format_itinerary_rows(rows: List[Dict[str, str]]) -> str:
    lines = []
    for row in rows:
        lines.append(
            " | ".join(
                [
                    f"Day {row.get('day','')}",
                    row.get("date", ""),
                    f"{row.get('start_time','')}-{row.get('end_time','')}",
                    row.get("city", ""),
                    row.get("location_area", row.get("location__area", row.get("location", ""))),
                    row.get("activity_type", row.get("activity", "")),
                    row.get("activity_description", row.get("description", "")),
                    row.get("notes", ""),
                ]
            )
        )
    return "\n".join(lines)


def _parse_date(value: str) -> datetime | None:
    if not value:
        return None
    value = value.strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def extract_itinerary_context(rows: List[Dict[str, str]]) -> Dict[str, str | List[str]]:
    dates: List[datetime] = []
    cities = set()
    locations = set()

    for row in rows:
        date_value = row.get("date", "")
        parsed = _parse_date(date_value)
        if parsed:
            dates.append(parsed)
        city = row.get("city", "").strip()
        if city:
            cities.add(city)
        location = row.get("location_area", row.get("location__area", row.get("location", ""))).strip()
        if location:
            locations.add(location)

    dates_sorted = sorted(dates)
    date_min = dates_sorted[0].strftime("%Y-%m-%d") if dates_sorted else ""
    date_max = dates_sorted[-1].strftime("%Y-%m-%d") if dates_sorted else ""

    return {
        "date_min": date_min,
        "date_max": date_max,
        "dates": [d.strftime("%Y-%m-%d") for d in dates_sorted],
        "cities": sorted(cities),
        "locations": sorted(locations),
    }
