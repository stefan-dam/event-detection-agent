from pathlib import Path

import pandas as pd

from src.loaders import extract_itinerary_context, load_itinerary


def test_load_itinerary_table(tmp_path: Path) -> None:
    df = pd.DataFrame(
        [
            {
                "Day": "1",
                "Date": "2026-02-03",
                "Start Time": "10:00",
                "End Time": "12:00",
                "City": "Sapporo",
                "Location / Area": "Station",
            }
        ]
    )
    file_path = tmp_path / "itinerary.xlsx"
    df.to_excel(file_path, index=False)

    rows = load_itinerary(str(file_path))
    assert rows[0]["day"] == "1"
    assert rows[0]["row_id"] == "1"

    context = extract_itinerary_context(rows)
    assert context["date_min"] == "2026-02-03"
    assert "Sapporo" in context["cities"]


def test_load_itinerary_single_column(tmp_path: Path) -> None:
    df = pd.DataFrame(
        {
            "Day,Date,Start Time,End Time,City": [
                "1,2026-02-03,10:00,12:00,Sapporo",
            ]
        }
    )
    file_path = tmp_path / "itinerary.csv.xlsx"
    df.to_excel(file_path, index=False)

    rows = load_itinerary(str(file_path))
    assert rows[0]["city"] == "Sapporo"
    assert rows[0]["row_id"] == "1"
