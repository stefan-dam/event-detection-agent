"""LangChain agent orchestration and validation logic."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Dict, List
from urllib.parse import parse_qs, unquote, urlparse

from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import BaseTool
from langchain_groq import ChatGroq

from .models import EventList
from .tools import OFFICIAL_DOMAINS


def _build_prompt() -> ChatPromptTemplate:
    return ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are an AI Event Detection Agent. Use the tools to gather "
                "fresh evidence. You MUST call web_search at least once and "
                "web_scrape for every URL you reference in sources. "
                "For hazards, use official_hazard_search and "
                "official_hazard_scrape for authoritative sources. "
                "Only suggest events that match the itinerary dates/locations "
                "and the user's preferences. Ensure hazards are time-sensitive "
                "and opportunities are temporally relevant. "
                "Return JSON only following the provided schema.",
            ),
            (
                "human",
                "User preferences:\n{preferences}\n\n"
                "Itinerary rows:\n{itinerary}\n\n"
                "Itinerary context:\n{context}\n\n"
                "Priority web queries (use as guidance):\n{queries}\n\n"
                "Memory summary:\n{memory}\n\n"
                "Blocked events (recently rejected):\n{blocked}\n\n"
                "For each event, include itinerary_day, itinerary_row_id, "
                "change_type, and any new_time/new_location if applicable.\n\n"
                "Event dates MUST be ISO format YYYY-MM-DD.\n\n"
                "{format_instructions}",
            ),
        ]
    )


def build_agent(tools: List[BaseTool], model: str) -> AgentExecutor:
    llm = ChatGroq(model=model, temperature=0.2)
    parser = PydanticOutputParser(pydantic_object=EventList)
    prompt = _build_prompt()
    agent = create_tool_calling_agent(llm=llm, tools=tools, prompt=prompt)
    return AgentExecutor(
        agent=agent,
        tools=tools,
        return_intermediate_steps=True,
        verbose=False,
        handle_parsing_errors=True,
    )


def _normalize_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.netloc.endswith("duckduckgo.com") and parsed.path.startswith("/l/"):
        query = parse_qs(parsed.query)
        target = query.get("uddg", [""])[0]
        return unquote(target)
    return url


def _collect_tool_usage(intermediate_steps: List) -> Dict[str, List[str]]:
    searches: List[str] = []
    scrapes: List[str] = []
    official_searches: List[str] = []
    official_scrapes: List[str] = []
    order: List[str] = []
    for action, _ in intermediate_steps:
        tool_name = getattr(action, "tool", "")
        if tool_name:
            order.append(tool_name)
        tool_input = getattr(action, "tool_input", "")
        if isinstance(tool_input, dict):
            tool_input = tool_input.get("query") or tool_input.get("url") or ""
        if tool_name == "web_search":
            searches.append(str(tool_input))
        if tool_name == "web_scrape":
            scrapes.append(_normalize_url(str(tool_input)))
        if tool_name == "official_hazard_search":
            official_searches.append(str(tool_input))
        if tool_name == "official_hazard_scrape":
            official_scrapes.append(_normalize_url(str(tool_input)))
    return {
        "searches": searches,
        "scrapes": scrapes,
        "official_searches": official_searches,
        "official_scrapes": official_scrapes,
        "order": order,
    }


def _extract_source_urls(events: EventList) -> List[str]:
    urls = []
    for event in events.events:
        for source in event.sources:
            if source.url:
                urls.append(_normalize_url(source.url))
    return urls


def _assign_event_ids(events: EventList) -> None:
    for event in events.events:
        key = "|".join(
            [
                event.category,
                event.date or "",
                event.location or "",
                event.title or "",
                event.proposed_change or "",
            ]
        )
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]
        event.id = f"evt_{digest}"


def _parse_event_date(value: str) -> datetime | None:
    if not value:
        return None
    match = re.search(r"\d{4}-\d{2}-\d{2}", value)
    if not match:
        return None
    try:
        return datetime.strptime(match.group(0), "%Y-%m-%d")
    except ValueError:
        return None


def _is_iso_date(value: str) -> bool:
    return bool(re.match(r"^\d{4}-\d{2}-\d{2}$", value or ""))


def _filter_hazards(events: EventList) -> None:
    hazard_keywords = {
        "storm",
        "snow",
        "wind",
        "strike",
        "closure",
        "warning",
        "advisory",
        "security",
        "travel advisory",
        "civil unrest",
        "demonstration",
        "terrorism",
        "crime",
        "warning level",
    }
    severity_cues = {
        "severe",
        "heavy",
        "major",
        "warning",
        "alert",
        "advisory",
        "cancel",
        "high",
        "elevated",
        "level",
    }
    official_domains = set(OFFICIAL_DOMAINS)
    filtered = []
    for event in events.events:
        if event.category != "hazard":
            filtered.append(event)
            continue
        text = f"{event.description} {event.rationale} {event.recommendation}".lower()
        source_text = " ".join(
            [source.snippet for source in event.sources if source.snippet]
        ).lower()
        has_keyword = any(keyword in text or keyword in source_text for keyword in hazard_keywords)
        has_severity = any(cue in text or cue in source_text for cue in severity_cues)
        has_source_snippet = any(source.snippet for source in event.sources)
        if official_domains:
            has_official_source = any(
                any(domain in (source.url or "") for domain in official_domains)
                for source in event.sources
            )
        else:
            has_official_source = True
        is_mofa_advisory = any("mofa.go.jp" in (source.url or "") for source in event.sources)
        if (has_keyword and has_severity and has_source_snippet and has_official_source) or (
            is_mofa_advisory and has_source_snippet
        ):
            filtered.append(event)
    events.events = filtered


def _filter_opportunities(events: EventList, allowed_terms: List[str]) -> None:
    filtered = []
    for event in events.events:
        if event.category != "opportunity":
            filtered.append(event)
            continue
        has_source_snippet = any(source.snippet for source in event.sources)
        location_text = (event.location or "").lower()
        matches_location = True
        if allowed_terms:
            matches_location = any(term.lower() in location_text for term in allowed_terms)
        if has_source_snippet and matches_location:
            filtered.append(event)
    events.events = filtered


def _filter_solution_quality(events: EventList, min_length: int = 20) -> bool:
    filtered = []
    removed = False
    for event in events.events:
        if len(event.recommendation.strip()) < min_length:
            removed = True
            continue
        if len(event.proposed_change.strip()) < min_length:
            removed = True
            continue
        filtered.append(event)
    events.events = filtered
    return removed


def detect_events(
    agent: AgentExecutor,
    preferences: str,
    itinerary: str,
    memory_events: List[Dict[str, str]],
    memory_summary: str,
    blocked_event_ids: List[str],
    queries: List[str],
    context: Dict[str, str | List[str]],
    required_categories: List[str],
    max_events: int = 8,
) -> EventList:
    """Run the agent and enforce tool usage, date formats, and evidence rules."""
    parser = PydanticOutputParser(pydantic_object=EventList)
    memory_blob = json.dumps(memory_events, ensure_ascii=False)
    blocked = json.dumps(blocked_event_ids)
    context_blob = json.dumps(context, ensure_ascii=False)
    queries_blob = "\n".join(queries)

    last_events: EventList | None = None
    for attempt in range(2):
        result = agent.invoke(
            {
                "preferences": preferences,
                "itinerary": itinerary,
                "context": context_blob,
                "queries": queries_blob,
                "memory": memory_summary + "\nRaw events: " + memory_blob,
                "blocked": blocked,
                "format_instructions": parser.get_format_instructions()
                + "\nReturn at least one hazard and one opportunity if evidence is available.",
            }
        )

        output = result.get("output")
        if isinstance(output, EventList):
            events = output
        else:
            events = parser.parse(output)

        _assign_event_ids(events)
        _filter_hazards(events)
        allowed_terms = list(context.get("cities", [])) + list(context.get("locations", []))
        _filter_opportunities(events, allowed_terms)
        solutions_filtered = _filter_solution_quality(events)

        usage = _collect_tool_usage(result.get("intermediate_steps", []))
        source_urls = _extract_source_urls(events)
        scraped_urls = set(usage["scrapes"]) | set(usage["official_scrapes"])
        missing_sources = [url for url in source_urls if url and url not in scraped_urls]
        invalid_dates = [event for event in events.events if not _is_iso_date(event.date)]

        has_required_tools = bool(usage["searches"]) and bool(usage["scrapes"])
        if usage["order"]:
            first_tool = usage["order"][0]
            has_required_tools = has_required_tools and first_tool == "web_search"
        hazard_events = [event for event in events.events if event.category == "hazard"]
        if hazard_events and OFFICIAL_DOMAINS:
            has_required_tools = (
                has_required_tools
                and bool(usage["official_searches"])
                and bool(usage["official_scrapes"])
            )
        has_required_categories = all(
            any(event.category == category for event in events.events)
            for category in required_categories
        )

        if (
            has_required_tools
            and not missing_sources
            and has_required_categories
            and not invalid_dates
            and not solutions_filtered
        ):
            last_events = events
            break

        last_events = events
        queries_blob = (
            queries_blob
            + "\nIMPORTANT: You must use web_search first, then web_scrape each source URL."
        )
        if missing_sources:
            queries_blob += "\nScrape these URLs: " + ", ".join(missing_sources)
        if invalid_dates:
            queries_blob += "\nUse ISO dates only (YYYY-MM-DD) for event.date."
        if solutions_filtered:
            queries_blob += "\nProvide concrete recommendation and proposed_change with at least 20 characters."

    events = last_events or EventList()
    _assign_event_ids(events)
    _filter_hazards(events)
    allowed_terms = list(context.get("cities", [])) + list(context.get("locations", []))
    _filter_opportunities(events, allowed_terms)
    _filter_solution_quality(events)

    # Filter by itinerary date range if possible
    date_min = context.get("date_min", "")
    date_max = context.get("date_max", "")
    parsed_min = _parse_event_date(date_min) if date_min else None
    parsed_max = _parse_event_date(date_max) if date_max else None
    if parsed_min and parsed_max:
        filtered = []
        for event in events.events:
            event_date = _parse_event_date(event.date)
            if event_date and parsed_min <= event_date <= parsed_max:
                filtered.append(event)
        events.events = filtered

    events.events = [e for e in events.events if e.id not in blocked_event_ids]
    events.events = events.events[:max_events]
    return events
