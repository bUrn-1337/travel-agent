"""
LLM Generator — the G in RAG.

Supports:
  1. Groq  (free, fast — llama-3.1-8b-instant)  set GROQ_API_KEY
  2. Google Gemini (free tier)                    set GEMINI_API_KEY
  3. No-LLM fallback: formats retrieved chunks into a readable plan

Streaming (SSE) path:   generate_plan()    → Generator[str]
Structured JSON path:   generate_plan_json() → dict
"""
import os
import json
import logging
from typing import Generator

import httpx

logger = logging.getLogger(__name__)

GROQ_URL   = "https://api.groq.com/openai/v1/chat/completions"
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-1.5-flash:streamGenerateContent?alt=sse&key={key}"
)

GROQ_MODEL   = "llama-3.1-8b-instant"
GEMINI_MODEL = "gemini-1.5-flash"


# ── Prompt builder ───────────────────────────────────────────────────────────

def build_prompt(
    destination_name: str,
    state: str,
    chunks: list[dict],
    days: int,
    budget_per_day: float,
    group_type: str,
    vibes: list[str],
    extra_query: str = "",
    live_snippets: list[dict] = None,
) -> str:
    context_parts = []
    seen_sections: set[str] = set()

    for c in chunks:
        sec = c.get("section_type", "general")
        # Allow max 2 chunks per section type to avoid repetition
        key = f"{sec}"
        count = sum(1 for k in seen_sections if k.startswith(key))
        if count >= 2:
            continue
        seen_sections.add(f"{key}_{count}")
        context_parts.append(f"[{sec.upper()}]\n{c['text']}")

    context = "\n\n---\n\n".join(context_parts)

    vibe_str  = ", ".join(vibes) if vibes else "general sightseeing"
    budget_str = f"₹{int(budget_per_day):,}" if budget_per_day else "flexible"
    extra_str  = f"\nUser's specific request: \"{extra_query}\"" if extra_query else ""

    # Live web snippets block (Google Search results)
    live_block = ""
    if live_snippets:
        lines = []
        for i, s in enumerate(live_snippets, 1):
            lines.append(f"{i}. {s.get('title', '')}")
            lines.append(f"   {s.get('snippet', '')}")
        live_block = "\n\nLIVE WEB CONTEXT (Google Search — current info):\n" + "\n".join(lines)

    prompt = f"""You are an experienced Indian travel expert. Use the information provided below to create a travel plan. Prefer the Live Web Context for current prices, tips, and conditions. Use the Knowledge Base for factual details about highlights, food, and transport.

DESTINATION: {destination_name}, {state}
TRIP DETAILS:
- Duration: {days} days
- Budget: {budget_str} per person per day
- Group type: {group_type}
- Travel vibe: {vibe_str}{extra_str}

RETRIEVED KNOWLEDGE BASE:
{context}{live_block}

---

Based on the above information, provide a detailed and practical travel plan with these sections:

## Day-by-Day Itinerary
(Specific activities for each of the {days} days, using the highlights provided)

## Food Guide
(Must-try local dishes and where to find them)

## Getting There & Local Transport
(How to reach {destination_name} and move around)

## Accommodation Guide
(Best options for a {group_type}, price range)

## Budget Estimate
(Realistic daily cost breakdown for a {group_type} with {budget_str}/day budget)

## Travel Tips
(Best time, what to pack, important cautions)

Be specific, practical, and concise. Format using markdown."""

    return prompt


# ── Groq streaming ───────────────────────────────────────────────────────────

def _stream_groq(prompt: str, api_key: str) -> Generator[str, None, None]:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a concise, expert Indian travel planner. "
                    "Respond in clean markdown. Use only the provided context."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "stream": True,
        "temperature": 0.4,
        "max_tokens": 1800,
    }

    with httpx.Client(timeout=60) as client:
        with client.stream("POST", GROQ_URL, headers=headers,
                           json=payload) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line or line == "data: [DONE]":
                    continue
                if line.startswith("data: "):
                    try:
                        data  = json.loads(line[6:])
                        delta = data["choices"][0]["delta"].get("content", "")
                        if delta:
                            yield delta
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue


# ── Gemini streaming ─────────────────────────────────────────────────────────

def _stream_gemini(prompt: str, api_key: str) -> Generator[str, None, None]:
    url     = GEMINI_URL.format(key=api_key)
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.4, "maxOutputTokens": 1800},
    }

    with httpx.Client(timeout=60) as client:
        with client.stream("POST", url, json=payload) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line or not line.startswith("data: "):
                    continue
                try:
                    data = json.loads(line[6:])
                    parts = (
                        data.get("candidates", [{}])[0]
                            .get("content", {})
                            .get("parts", [])
                    )
                    for part in parts:
                        text = part.get("text", "")
                        if text:
                            yield text
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue


# ── No-LLM fallback ──────────────────────────────────────────────────────────

def _format_chunks_fallback(
    chunks: list[dict],
    destination_name: str,
    days: int,
    group_type: str,
) -> Generator[str, None, None]:
    """
    When no LLM API key is set, format the retrieved chunks directly.
    Groups chunks by section_type and produces clean markdown.
    """
    grouped: dict[str, list[str]] = {}
    for c in chunks:
        sec = c.get("section_type", "general")
        grouped.setdefault(sec, []).append(c["text"])

    SECTION_LABELS = {
        "itinerary":     "Itinerary",
        "highlights":    "Highlights & Attractions",
        "overview":      "About",
        "food":          "Food & Cuisine",
        "transport":     "Getting There & Transport",
        "accommodation": "Accommodation",
        "season":        "Best Time to Visit",
        "suitability":   "Who Should Visit",
        "budget":        "Budget Guide",
        "general":       "General Info",
    }

    header = (
        f"# Travel Plan: {destination_name}\n"
        f"*{days}-day trip for {group_type}*\n\n"
        f"> **Note:** LLM generation is disabled (no API key set). "
        f"Showing retrieved knowledge base content.\n\n"
    )
    yield header

    ordered = ["itinerary", "highlights", "overview", "food",
               "transport", "accommodation", "season", "budget", "general"]

    for sec in ordered:
        if sec not in grouped:
            continue
        label = SECTION_LABELS.get(sec, sec.title())
        yield f"## {label}\n\n"
        for text in grouped[sec]:
            yield text + "\n\n"


# ── Public interface ─────────────────────────────────────────────────────────

def generate_plan(
    destination_name: str,
    state: str,
    chunks: list[dict],
    days: int,
    budget_per_day: float,
    group_type: str,
    vibes: list[str],
    extra_query: str = "",
    live_snippets: list[dict] = None,
) -> Generator[str, None, None]:
    """
    Entry point for generation. Picks provider based on env vars.
    Yields string tokens suitable for SSE streaming.
    live_snippets: Google Search results to inject as live context.
    """
    groq_key   = os.getenv("GROQ_API_KEY", "").strip()
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()

    if not chunks:
        yield (
            f"# {destination_name}\n\n"
            f"No knowledge base chunks found for this destination. "
            f"Please run `python3 ingest.py` first to build the RAG index.\n"
        )
        return

    prompt = build_prompt(destination_name, state, chunks, days,
                          budget_per_day, group_type, vibes, extra_query,
                          live_snippets)

    if groq_key:
        try:
            logger.info(f"Generating with Groq ({GROQ_MODEL})")
            yield from _stream_groq(prompt, groq_key)
            return
        except Exception as e:
            logger.warning(f"Groq failed ({e}), trying fallback")

    if gemini_key:
        try:
            logger.info(f"Generating with Gemini ({GEMINI_MODEL})")
            yield from _stream_gemini(prompt, gemini_key)
            return
        except Exception as e:
            logger.warning(f"Gemini failed ({e}), using chunk fallback")

    logger.info("Using chunk-format fallback")
    yield from _format_chunks_fallback(chunks, destination_name, days, group_type)


# ── Packing list ─────────────────────────────────────────────────────────────

def _build_packing_prompt(
    destination_name: str,
    state: str,
    days: int,
    group_type: str,
    vibes: list[str],
    travel_month: int,
) -> str:
    from datetime import datetime
    MONTHS = ["","January","February","March","April","May","June",
              "July","August","September","October","November","December"]
    month_name = MONTHS[travel_month] if 1 <= travel_month <= 12 else MONTHS[datetime.now().month]
    vibe_str = ", ".join(vibes) if vibes else "general sightseeing"

    return f"""You are an expert Indian travel packer. Generate a practical packing list for this trip.

TRIP:
- Destination: {destination_name}, {state}
- Duration: {days} days
- Travel month: {month_name}
- Group: {group_type}
- Vibes: {vibe_str}

Generate a concise packing list with these sections. Each item should be on its own line with a checkbox (- [ ]).
Tailor items specifically to the destination climate, activities, and season.

## 👗 Clothing
(season-appropriate, activity-specific)

## 🪪 Documents & Money
(IDs, bookings, cards)

## 🎒 Gear & Accessories
(destination/vibe specific — e.g. trekking poles for mountains, snorkel for beach)

## 🧴 Toiletries & Health
(essentials + destination-specific, e.g. altitude sickness pills for mountains)

## 📱 Electronics
(power banks, adapters, offline maps)

## 🍫 Snacks & Extras
(travel snacks, misc)

Keep each section tight — 6–10 items max. Skip generic obvious items. Be specific to {destination_name} in {month_name}."""


def generate_packing_list(
    destination_name: str,
    state: str,
    days: int,
    group_type: str,
    vibes: list[str],
    travel_month: int = 0,
) -> Generator[str, None, None]:
    """Stream a packing list for the given destination and trip details."""
    groq_key   = os.getenv("GROQ_API_KEY", "").strip()
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()

    prompt = _build_packing_prompt(destination_name, state, days, group_type, vibes, travel_month)

    if groq_key:
        try:
            yield from _stream_groq(prompt, groq_key)
            return
        except Exception as e:
            logger.warning(f"Groq failed for packing list ({e}), trying Gemini")

    if gemini_key:
        try:
            yield from _stream_gemini(prompt, gemini_key)
            return
        except Exception as e:
            logger.warning(f"Gemini failed for packing list ({e})")

    # Minimal static fallback
    yield f"# Packing List — {destination_name}\n\n"
    yield "## 👗 Clothing\n- [ ] Comfortable walking shoes\n- [ ] Weather-appropriate layers\n\n"
    yield "## 🪪 Documents\n- [ ] ID / Passport\n- [ ] Hotel bookings\n- [ ] Travel insurance\n\n"
    yield "## 🎒 Gear\n- [ ] Backpack\n- [ ] Water bottle\n- [ ] Sunscreen\n\n"


# ── JSON prompt builder ──────────────────────────────────────────────────────

def _build_json_prompt(
    destination_name: str,
    state: str,
    chunks: list[dict],
    days: int,
    budget_per_day: float,
    group_type: str,
    vibes: list[str],
    extra_query: str = "",
    live_snippets: list[dict] = None,
) -> str:
    context_parts = []
    seen: set[str] = set()
    for c in chunks:
        sec = c.get("section_type", "general")
        count = sum(1 for k in seen if k.startswith(sec))
        if count >= 2:
            continue
        seen.add(f"{sec}_{count}")
        context_parts.append(f"[{sec.upper()}]\n{c['text']}")
    context = "\n\n---\n\n".join(context_parts)

    vibe_str   = ", ".join(vibes) if vibes else "general sightseeing"
    budget_str = f"₹{int(budget_per_day):,}" if budget_per_day else "flexible"
    extra_str  = f'\nUser request: "{extra_query}"' if extra_query else ""

    live_block = ""
    if live_snippets:
        lines = []
        for i, s in enumerate(live_snippets, 1):
            lines.append(f"{i}. {s.get('title', '')}: {s.get('snippet', '')}")
        live_block = "\n\nLIVE WEB CONTEXT:\n" + "\n".join(lines)

    return f"""You are an expert Indian travel planner. Based on the knowledge below, produce a structured travel plan as valid JSON (no markdown, no backticks — raw JSON only).

DESTINATION: {destination_name}, {state}
DETAILS: {days} days | {budget_str}/person/day | {group_type} | vibes: {vibe_str}{extra_str}

KNOWLEDGE BASE:
{context}{live_block}

Return ONLY this JSON structure (fill every field, be specific and practical):
{{
  "summary": "One engaging sentence describing this trip.",
  "itinerary": [
    {{"day": 1, "title": "Short day theme", "morning": "Activity detail", "afternoon": "Activity detail", "evening": "Activity detail", "highlight": "The best moment of the day"}}
  ],
  "food_guide": [
    {{"dish": "Dish name", "description": "Brief description", "where": "Restaurant/area name", "approx_cost_inr": 200}}
  ],
  "transport": {{
    "options": [
      {{"mode": "Train/Flight/Bus/Drive", "route": "Route description", "duration": "e.g. 6h", "est_cost_inr": 500}}
    ],
    "local": "How to get around locally (autos, cabs, walking, etc.)"
  }},
  "accommodation": [
    {{"type": "Hotel/Hostel/Homestay/Resort", "area": "Best area to stay", "price_range": "₹X–Y/night", "best_for": "Who this suits"}}
  ],
  "tips": ["Practical tip 1", "Practical tip 2", "Practical tip 3"]
}}

Generate exactly {days} day entries in itinerary. Ensure costs are realistic INR amounts for {group_type} travel in India."""


# ── Non-streaming JSON callers ───────────────────────────────────────────────

def _call_groq_json(prompt: str, api_key: str) -> dict:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type":  "application/json",
    }
    payload = {
        "model":           GROQ_MODEL,
        "messages":        [
            {"role": "system",
             "content": "You are a JSON-only travel planner. Output valid JSON, no markdown, no extra text."},
            {"role": "user", "content": prompt},
        ],
        "temperature":     0.3,
        "max_tokens":      2500,
        "response_format": {"type": "json_object"},
    }
    with httpx.Client(timeout=60) as client:
        resp = client.post(GROQ_URL, headers=headers, json=payload)
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        return json.loads(content)


def _call_gemini_json(prompt: str, api_key: str) -> dict:
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-1.5-flash:generateContent?key={api_key}"
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature":    0.3,
            "maxOutputTokens": 2500,
            "responseMimeType": "application/json",
        },
    }
    with httpx.Client(timeout=60) as client:
        resp = client.post(url, json=payload)
        resp.raise_for_status()
        text = (resp.json()["candidates"][0]["content"]["parts"][0]["text"])
        return json.loads(text)


def _fallback_json(
    chunks: list[dict],
    destination_name: str,
    state: str,
    days: int,
    group_type: str,
    vibes: list[str],
) -> dict:
    """Build a structured dict from retrieved chunks (no LLM)."""
    grouped: dict[str, list[str]] = {}
    for c in chunks:
        grouped.setdefault(c.get("section_type", "general"), []).append(c["text"])

    itinerary = []
    for d in range(1, days + 1):
        itinerary.append({
            "day":       d,
            "title":     f"Day {d} in {destination_name}",
            "morning":   "Explore local attractions",
            "afternoon": "Visit key sights",
            "evening":   "Local cuisine and leisure",
            "highlight": "Immerse in local culture",
        })

    food_texts = grouped.get("food", [""])
    food_guide = [{"dish": "Local specialties", "description": food_texts[0][:200] if food_texts else "Ask locals",
                   "where": "Local markets and restaurants", "approx_cost_inr": 300}]

    transport_texts = grouped.get("transport", [""])
    accommodation   = [{"type": "Hotel / Guesthouse", "area": f"Near {destination_name} centre",
                        "price_range": "₹800–2500/night", "best_for": group_type}]

    return {
        "summary":       f"A {days}-day trip to {destination_name}, {state} for {group_type}.",
        "itinerary":     itinerary,
        "food_guide":    food_guide,
        "transport":     {
            "options": [{"mode": "Check transport options", "route": transport_texts[0][:150] if transport_texts else "",
                         "duration": "Varies", "est_cost_inr": 0}],
            "local":   "Use local autos, cabs, or hired vehicle.",
        },
        "accommodation": accommodation,
        "tips":          [
            "Book accommodation in advance during peak season.",
            "Carry cash — ATMs may be scarce in remote areas.",
            "Respect local customs and dress modestly at religious sites.",
        ],
        "_source": "fallback",
    }


# ── Public JSON interface ────────────────────────────────────────────────────

def generate_plan_json(
    destination_name: str,
    state: str,
    chunks: list[dict],
    days: int,
    budget_per_day: float,
    group_type: str,
    vibes: list[str],
    extra_query: str = "",
    live_snippets: list[dict] = None,
) -> dict:
    """
    Non-streaming structured JSON plan generator.
    Returns a dict matching the plan JSON schema.
    Falls back to chunk-formatted dict if no LLM key or on error.
    """
    groq_key   = os.getenv("GROQ_API_KEY",   "").strip()
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()

    if not chunks:
        return _fallback_json([], destination_name, state, days, group_type, vibes)

    prompt = _build_json_prompt(
        destination_name, state, chunks, days, budget_per_day,
        group_type, vibes, extra_query, live_snippets,
    )

    if groq_key:
        try:
            logger.info(f"JSON generation via Groq ({GROQ_MODEL})")
            plan = _call_groq_json(prompt, groq_key)
            plan["_source"] = "groq"
            return plan
        except Exception as e:
            logger.warning(f"Groq JSON failed: {e}; trying Gemini")

    if gemini_key:
        try:
            logger.info(f"JSON generation via Gemini ({GEMINI_MODEL})")
            plan = _call_gemini_json(prompt, gemini_key)
            plan["_source"] = "gemini"
            return plan
        except Exception as e:
            logger.warning(f"Gemini JSON failed: {e}; using fallback")

    logger.info("No LLM key or all failed — using structured fallback")
    return _fallback_json(chunks, destination_name, state, days, group_type, vibes)
