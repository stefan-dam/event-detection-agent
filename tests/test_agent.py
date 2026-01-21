from types import SimpleNamespace

from src.agent import _collect_tool_usage, _filter_opportunities, _is_iso_date
from src.models import Event, EventList, Source


def test_is_iso_date() -> None:
    assert _is_iso_date("2026-02-03") is True
    assert _is_iso_date("Feb 3 2026") is False


def test_collect_tool_usage_order() -> None:
    steps = [
        (SimpleNamespace(tool="web_search", tool_input="query"), ""),
        (SimpleNamespace(tool="web_scrape", tool_input="https://example.com"), ""),
    ]
    usage = _collect_tool_usage(steps)
    assert usage["order"][0] == "web_search"
    assert usage["searches"] == ["query"]
    assert usage["scrapes"] == ["https://example.com"]


def test_filter_opportunities_requires_snippet() -> None:
    event_with_snippet = Event(
        id="evt_1",
        category="opportunity",
        title="Test event",
        location="Tokyo",
        date="2026-02-03",
        time_window=None,
        description="Test",
        rationale="Test",
        recommendation="Test",
        proposed_change="Test",
        sources=[Source(title="Source", url="https://example.com", snippet="Text")],
        confidence=0.5,
    )
    event_without_snippet = Event(
        id="evt_2",
        category="opportunity",
        title="Test event 2",
        location="Tokyo",
        date="2026-02-03",
        time_window=None,
        description="Test",
        rationale="Test",
        recommendation="Test",
        proposed_change="Test",
        sources=[Source(title="Source", url="https://example.com", snippet="")],
        confidence=0.5,
    )
    events = EventList(events=[event_with_snippet, event_without_snippet])
    _filter_opportunities(events, ["Tokyo"])
    assert len(events.events) == 1
