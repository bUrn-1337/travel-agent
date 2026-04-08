"""
Re-enriches destinations that still have generic template descriptions.
Strategy:
  1. Try Groq (llama-3.1-8b-instant) with 2s delay + exponential backoff on 429
  2. Fall back to Gemini 1.5 Flash if Groq fails 3 times in a row
  3. Save after every successful enrichment so progress is never lost

Usage:
  python3 scripts/enrich_descriptions.py
  python3 scripts/enrich_descriptions.py --batch 10   # do only 10 destinations
"""
import json, os, sys, time, argparse, logging
from pathlib import Path
import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger()

DATA_PATH  = Path(__file__).parent.parent / "data" / "destinations.json"
GROQ_URL   = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.1-8b-instant"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={key}"

SCHEMA = '{"description":"2-3 vivid sentences about the destination","highlights":["specific attraction 1","specific attraction 2","specific attraction 3","specific attraction 4","specific attraction 5"],"food_specialties":["local dish 1","local dish 2","local dish 3","local dish 4"],"accommodation":["type1","type2","type3"]}'

SYSTEM = "You are an expert Indian travel writer. Return ONLY valid JSON — no markdown, no explanation, no extra text."


def build_prompt(dest: dict) -> str:
    return (
        f"Destination: {dest['name']}, {dest['state']}\n"
        f"Region: {dest['region']}\n"
        f"Travel vibes: {', '.join(dest.get('vibes', []))}\n"
        f"Primary vibe: {dest.get('primary_vibe', '')}\n\n"
        f"Write real, accurate, specific information for this Indian destination.\n"
        f"Return ONLY this JSON:\n{SCHEMA}"
    )


def needs_enrich(dest: dict) -> bool:
    desc  = dest.get("description", "")
    highs = dest.get("highlights", [""])
    first = (highs[0] if highs else "")
    return (
        "Known for its" in desc
        or "experiences centred around" in desc
        or first.startswith("Explore ")
        or first in ("Local markets", "Main attractions", "Local sights")
    )


def call_groq(prompt: str, api_key: str) -> dict:
    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user",   "content": prompt},
        ],
        "temperature": 0.4,
        "max_tokens":  700,
        "response_format": {"type": "json_object"},
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    with httpx.Client(timeout=30) as c:
        r = c.post(GROQ_URL, headers=headers, json=payload)
        r.raise_for_status()
        return json.loads(r.json()["choices"][0]["message"]["content"])


def call_gemini(prompt: str, api_key: str) -> dict:
    url = GEMINI_URL.format(key=api_key)
    payload = {
        "contents": [{"parts": [{"text": SYSTEM + "\n\n" + prompt}]}],
        "generationConfig": {
            "temperature": 0.4,
            "maxOutputTokens": 700,
            "responseMimeType": "application/json",
        },
    }
    with httpx.Client(timeout=30) as c:
        r = c.post(url, json=payload)
        r.raise_for_status()
        text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        return json.loads(text)


def enrich_one(dest: dict, groq_key: str, gemini_key: str) -> dict | None:
    """Try Groq up to 3 times with backoff, then Gemini, then return None."""
    prompt = build_prompt(dest)

    if groq_key:
        for attempt in range(3):
            try:
                data = call_groq(prompt, groq_key)
                return data
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    wait = 2 ** (attempt + 2)   # 4s, 8s, 16s
                    log.warning(f"  Groq 429 — waiting {wait}s (attempt {attempt+1}/3)")
                    time.sleep(wait)
                else:
                    log.warning(f"  Groq error {e.response.status_code}: {e}")
                    break
            except Exception as e:
                log.warning(f"  Groq exception: {e}")
                break

    if gemini_key:
        try:
            data = call_gemini(prompt, gemini_key)
            return data
        except Exception as e:
            log.warning(f"  Gemini failed: {e}")

    return None


def apply_fill(dest: dict, fill: dict) -> None:
    if fill.get("description"):
        dest["description"] = fill["description"]
    if fill.get("highlights") and len(fill["highlights"]) >= 3:
        dest["highlights"] = fill["highlights"]
    if fill.get("food_specialties") and len(fill["food_specialties"]) >= 2:
        dest["food_specialties"] = fill["food_specialties"]
    if fill.get("accommodation") and len(fill["accommodation"]) >= 1:
        dest["accommodation"] = fill["accommodation"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", type=int, default=0,
                        help="Max destinations to process (0 = all)")
    args = parser.parse_args()

    groq_key   = os.getenv("GROQ_API_KEY",   "").strip()
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()

    if not groq_key and not gemini_key:
        log.error("Set GROQ_API_KEY or GEMINI_API_KEY before running.")
        sys.exit(1)

    with open(DATA_PATH) as f:
        dests = json.load(f)

    todo = [d for d in dests if needs_enrich(d)]
    if args.batch:
        todo = todo[:args.batch]

    log.info(f"{len(todo)} destinations need enrichment")
    if not todo:
        log.info("Nothing to do.")
        return

    ok = skip = 0
    for i, dest in enumerate(todo, 1):
        log.info(f"[{i}/{len(todo)}] {dest['name']}, {dest['state']}")
        fill = enrich_one(dest, groq_key, gemini_key)
        if fill:
            apply_fill(dest, fill)
            ok += 1
            # Save after every success so progress is never lost
            with open(DATA_PATH, "w", encoding="utf-8") as f:
                json.dump(dests, f, indent=2, ensure_ascii=False)
        else:
            log.warning(f"  SKIPPED (all providers failed)")
            skip += 1

        # Polite delay between calls
        if i < len(todo):
            time.sleep(2.0)

    log.info(f"\nDone. Enriched: {ok} | Skipped: {skip}")
    log.info(f"Next: restart the backend + run python3 ingest.py --dest <ids> to re-index changed destinations")


if __name__ == "__main__":
    main()
