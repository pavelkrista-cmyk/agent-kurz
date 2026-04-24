"""
A06 — Media Monitoring Agent v4 — error handling
=================================================
Nové oproti v3 / New compared to v3:
  - Defensivní RSS parsing: feed.bozo check, per-feed try/except
  - Retry logika pro Anthropic API (overloaded_error, max 3 pokusy)
  - Robustní fallback pro chybějící pole (autor, datum, summary)
  - Přehledné error reporty v logu — agent nepadne, jen zapíše varování

Spuštění / Run:
    python media_agent_v4.py

Závislosti / Dependencies:
    pip install anthropic python-dotenv feedparser
"""

import os
import json
import re
import time
from datetime import date, datetime
from dotenv import load_dotenv
import anthropic
import feedparser

load_dotenv()
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

MODEL      = "claude-haiku-4-5-20251001"
OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(OUTPUT_DIR, "agent_state.json")

RSS_FEEDS = [
    {"name": "TechCrunch", "url": "https://techcrunch.com/feed/"},
    {"name": "Lupa.cz",    "url": "https://www.lupa.cz/rss/clanky/"},
    {"name": "Root.cz",    "url": "https://www.root.cz/rss/clanky/"},
]

TODAY = date.today().strftime("%Y-%m-%d")

SYSTEM_PROMPT = f"""Jsi mediální monitoring agent specializovaný na technologické zprávy.
Dnešní datum: {TODAY}

Postup:
1. Zavolej search_rss s daným tématem — vždy jako první krok.
2. Pokud JSON obsahuje 'new: 0', informuj uživatele a skonči. Nevolej create_digest.
3. Pokud jsou nové články, vyber 4–8 nejrelevantnějších.
4. Zavolej create_digest s vyplněnou strukturou:
   - topic: téma monitoringu
   - date: dnešní datum ({TODAY})
   - overview: 2-3 věty o celkovém obrazu tématu v češtině
   - articles: seznam vybraných článků, každý s:
       title, source, author, published, url,
       summary_cs (2-3 věté shrnutí česky),
       relevance (celé číslo 1-10 dle důležitosti pro téma)
5. Odpověz stručně: kolik článků, jaká průměrná relevance.

Pravidla:
- summary_cs vždy česky, technické termíny anglicky
- relevance: 10 = přelomová zpráva, 7-9 = důležité, 4-6 = zajímavé, 1-3 = okrajové
- Pokud autor obsahuje email, zobraz jen jméno
- Pokud pole chybí, použij rozumnou náhradu (např. autor = 'Redakce')"""

# ─── State management ────────────────────────────────────────────────────────

def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"  ⚠ Chyba čtení state: {e} — začínám s prázdným statem.")
    return {"seen_urls": [], "last_run": None, "total_processed": 0}


def save_state(state: dict, new_urls: list):
    seen_set = set(state["seen_urls"])
    added = 0
    for url in new_urls:
        if url and url not in seen_set:
            state["seen_urls"].append(url)
            seen_set.add(url)
            added += 1
    state["last_run"]        = datetime.now().strftime("%Y-%m-%d %H:%M")
    state["total_processed"] = state.get("total_processed", 0) + added
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        if added:
            print(f"  💾 State: {added} nových URL přidáno (celkem {len(state['seen_urls'])})")
    except Exception as e:
        print(f"  ✗ Nelze uložit state: {e}")


def filter_new_articles(articles: list, seen_urls: set) -> list:
    return [a for a in articles if a.get("link", "") not in seen_urls]


state = load_state()

# ─── Pomocné funkce ───────────────────────────────────────────────────────────

def get_author_clean(entry) -> str:
    """Extrahuje čisté jméno autora — ošetří email prefix, prázdné pole."""
    author = getattr(entry, "author", None) or ""
    match = re.search(r"\((?:[^:]+:\s*)?([^)]+)\)", author)
    if match:
        return match.group(1).strip()
    if author and "@" not in author:
        return author.strip()
    return "Redakce"  # v3 používal "Neznámý autor" — Redakce je přesnější


def get_published(entry) -> str:
    """Vrátí datum publikace ve formátu YYYY-MM-DD HH:MM nebo 'Datum neznámé'."""
    parsed = getattr(entry, "published_parsed", None)
    if parsed:
        try:
            return datetime(*parsed[:6]).strftime("%Y-%m-%d %H:%M")
        except Exception:
            pass
    raw = getattr(entry, "published", "") or ""
    return raw[:16] if raw else "Datum neznámé"

# ─── Retry wrapper pro Anthropic API ─────────────────────────────────────────

def call_api_with_retry(messages: list, max_retries: int = 3) -> object:
    """
    Volá Anthropic API s automatickým opakováním při přetížení serveru.
    Calls Anthropic API with automatic retry on server overload.

    Při 'overloaded_error' čeká exponenciálně: 10s, 20s, 40s.
    On 'overloaded_error' waits exponentially: 10s, 20s, 40s.
    """
    wait_seconds = 10
    for attempt in range(max_retries):
        try:
            return client.messages.create(
                model=MODEL, max_tokens=4096,
                system=SYSTEM_PROMPT, tools=TOOLS, messages=messages
            )
        except anthropic.APIStatusError as e:
            if "overloaded" in str(e).lower() and attempt < max_retries - 1:
                print(f"  ⚠ API přetíženo — čekám {wait_seconds}s a zkouším znovu "
                      f"(pokus {attempt + 1}/{max_retries})...")
                time.sleep(wait_seconds)
                wait_seconds *= 2  # exponential backoff: 10 → 20 → 40
            else:
                raise  # jiná chyba nebo vyčerpané pokusy — předej výše
        except anthropic.APIConnectionError as e:
            if attempt < max_retries - 1:
                print(f"  ⚠ Síťová chyba — čekám {wait_seconds}s a zkouším znovu "
                      f"(pokus {attempt + 1}/{max_retries})...")
                time.sleep(wait_seconds)
                wait_seconds *= 2
            else:
                raise

# ─── Tool implementace ───────────────────────────────────────────────────────

def search_rss(keyword: str, max_results: int = 15) -> str:
    """
    Stáhne RSS, filtruje dle keyword, odstraní viděné URL.
    Downloads RSS, filters by keyword, removes seen URLs.

    A06: každý feed zpracujeme odděleně — chyba jednoho feedu
    neovlivní ostatní. feed.bozo signalizuje malformovaný XML.
    """
    keyword_lower = keyword.lower()
    all_articles  = []
    seen_set      = set(state["seen_urls"])
    feed_errors   = []

    for source in RSS_FEEDS:
        try:
            feed = feedparser.parse(source["url"])

            # feed.bozo == True: feedparser detekoval problém s XML
            # (ale data jsou obvykle stále k dispozici — jen varujeme)
            if feed.bozo:
                bozo_msg = str(getattr(feed, "bozo_exception", "neznámá chyba"))
                print(f"  ⚠ Feed '{source['name']}' má XML problém: {bozo_msg[:80]}")
                # Nepřeskakujeme — feedparser obvykle data načte i z vadného XML

            if not feed.entries:
                print(f"  ⚠ Feed '{source['name']}' vrátil prázdný seznam článků.")
                continue

            for entry in feed.entries:
                title   = entry.get("title", "") or ""
                summary = entry.get("summary", "") or ""
                if keyword_lower in title.lower() or keyword_lower in summary.lower():
                    all_articles.append({
                        "title":     title,
                        "link":      entry.get("link", ""),
                        "author":    get_author_clean(entry),
                        "published": get_published(entry),
                        "summary":   re.sub(r"<[^>]+>", "", summary)[:300],
                        "source":    source["name"],
                    })

        except Exception as e:
            # Síťová chyba, timeout, DNS selhání...
            msg = f"Feed '{source['name']}' selhal: {type(e).__name__}: {e}"
            print(f"  ✗ {msg}")
            feed_errors.append(msg)
            # continue — zpracujeme další feedy

    new_articles = filter_new_articles(all_articles, seen_set)
    print(f"  📰 Celkem: {len(all_articles)} | Nových: {len(new_articles)} | "
          f"Viděno: {len(all_articles) - len(new_articles)}"
          + (f" | Chyby feedů: {len(feed_errors)}" if feed_errors else ""))

    if not new_articles:
        result = {"message": f"Žádné nové články pro '{keyword}'.", "new": 0}
        if feed_errors:
            result["feed_errors"] = feed_errors
        return json.dumps(result, ensure_ascii=False)

    results = new_articles[:max_results]
    output  = {
        "keyword": keyword, "total_found": len(all_articles),
        "new": len(new_articles), "returned": len(results), "articles": results
    }
    if feed_errors:
        output["feed_errors"] = feed_errors  # Claude to uvidí v tool_result
    return json.dumps(output, ensure_ascii=False, indent=2)


def create_digest(topic: str, date_str: str, overview: str, articles: list) -> str:
    """
    Převede strukturovaná JSON data na Markdown digest a uloží soubor.
    Converts structured JSON data to Markdown digest and saves to file.

    A06: ošetřuje chybějící pole v každém článku (title, url, summary_cs...).
    """
    # Robustní fallback pro chybějící pole
    for art in articles:
        art.setdefault("title",      "Bez titulku")
        art.setdefault("source",     "Neznámý zdroj")
        art.setdefault("author",     "Redakce")
        art.setdefault("published",  "Datum neznámé")
        art.setdefault("url",        "")
        art.setdefault("summary_cs", "Shrnutí není k dispozici.")
        art.setdefault("relevance",  5)  # výchozí střední relevance

    articles_sorted = sorted(articles, key=lambda a: a.get("relevance", 0), reverse=True)
    avg_relevance   = (
        sum(a.get("relevance", 0) for a in articles) / len(articles)
        if articles else 0
    )

    lines = [
        f"# Mediální monitoring: {topic}",
        f"_Datum: {date_str} | Článků: {len(articles)} | Průměrná relevance: {avg_relevance:.1f}/10_",
        "",
        "## Přehled",
        overview,
        "",
        "## Články _(seřazeno dle relevance)_",
        "",
    ]

    for art in articles_sorted:
        rel = art.get("relevance", "?")
        bar = ("█" * rel + "░" * (10 - rel)) if isinstance(rel, int) else ""
        lines += [
            f"### {art['title']}",
            f"**Zdroj:** {art['source']} | "
            f"**Autor:** {art['author']} | "
            f"**Datum:** {art['published']}",
            f"**Relevance:** {rel}/10  `{bar}`",
            f"**URL:** {art['url']}",
            "",
            art["summary_cs"],
            "",
            "---",
            "",
        ]

    content  = "\n".join(lines)
    filename = f"digest_{date_str}.md"
    filepath = os.path.join(OUTPUT_DIR, filename)

    try:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception as e:
        return f"✗ Nelze uložit digest: {e}"

    urls = [a.get("url", "") for a in articles if a.get("url")]
    save_state(state, urls)

    return (
        f"✓ Digest uložen: {filepath} | "
        f"{len(articles)} článků | "
        f"Průměrná relevance: {avg_relevance:.1f}/10 | "
        f"Top článek: '{articles_sorted[0]['title']}' ({articles_sorted[0].get('relevance', '?')}/10)"
    )

# ─── Tool definice ────────────────────────────────────────────────────────────

TOOLS = [
    {
        "name": "search_rss",
        "description": (
            "Vyhledá NOVÉ články v RSS feedech dle klíčového slova. "
            "Filtruje již zpracované (seen_urls). "
            "Vrátí JSON: total_found, new, returned, articles. "
            "Použij vždy jako první krok. Pokud new==0, nevolej create_digest."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "keyword":     {"type": "string",  "description": "Klíčové slovo"},
                "max_results": {"type": "integer", "description": "Max článků (default 15)", "default": 15}
            },
            "required": ["keyword"]
        }
    },
    {
        "name": "create_digest",
        "description": (
            "Vytvoří strukturovaný digest ze zpracovaných článků. "
            "Vyplň všechna pole přesně dle schématu. "
            "Relevance 1-10: 10=přelomové, 7-9=důležité, 4-6=zajímavé, 1-3=okrajové. "
            "Zavolej až po search_rss, když jsou nové články."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "topic":    {"type": "string", "description": "Téma monitoringu"},
                "date_str": {"type": "string", "description": f"Datum digestu, dnes: {TODAY}"},
                "overview": {"type": "string", "description": "2-3 věty o celkovém obrazu tématu česky"},
                "articles": {
                    "type": "array",
                    "description": "Seznam 4-8 nejrelevantnějších článků",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title":      {"type": "string"},
                            "source":     {"type": "string"},
                            "author":     {"type": "string"},
                            "published":  {"type": "string"},
                            "url":        {"type": "string"},
                            "summary_cs": {"type": "string", "description": "2-3 věté shrnutí česky"},
                            "relevance":  {"type": "integer", "description": "Skóre 1-10"}
                        },
                        "required": ["title", "source", "url", "summary_cs", "relevance"]
                    }
                }
            },
            "required": ["topic", "date_str", "overview", "articles"]
        }
    }
]

# ─── Agentic loop ─────────────────────────────────────────────────────────────

def run_agent(topic: str):
    print(f"\n{'='*60}")
    print(f"  A06 — Media Agent v4 | Téma: '{topic}' | {TODAY}")
    if state["last_run"]:
        print(f"  Poslední běh: {state['last_run']} | Zpracováno: {state['total_processed']} URL")
    else:
        print(f"  První spuštění — state prázdný.")
    print(f"{'='*60}\n")

    messages      = [{"role": "user", "content": f"Sleduj téma: {topic}"}]
    inference_cnt = 0

    while True:
        inference_cnt += 1
        print(f"[Inference #{inference_cnt}] Claude přemýšlí...")

        try:
            response = call_api_with_retry(messages)
        except anthropic.APIStatusError as e:
            print(f"\n  ✗ API chyba (vyčerpány pokusy): {e}")
            break
        except anthropic.APIConnectionError as e:
            print(f"\n  ✗ Síťová chyba (vyčerpány pokusy): {e}")
            break

        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            for block in response.content:
                if hasattr(block, "text"):
                    print(f"\n{'='*60}\n  HOTOVO\n{'='*60}")
                    print(block.text)
            break

        elif response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                args_preview = json.dumps(block.input, ensure_ascii=False)[:80]
                print(f"  → {block.name}({args_preview}...)")

                try:
                    if block.name == "search_rss":
                        result = search_rss(**block.input)
                    elif block.name == "create_digest":
                        result = create_digest(**block.input)
                        print(f"  {result}")
                    else:
                        result = f"Neznámý nástroj: {block.name}"
                except Exception as e:
                    # Tool selhal — vrátíme chybu Claudovi, nechceme aby agent padl
                    result = json.dumps({"error": f"Tool {block.name} selhal: {type(e).__name__}: {e}"})
                    print(f"  ✗ Tool chyba: {e}")

                tool_results.append({
                    "type": "tool_result", "tool_use_id": block.id, "content": result
                })
            messages.append({"role": "user", "content": tool_results})
        else:
            print(f"  ⚠ Neočekávaný stop_reason: {response.stop_reason}")
            break

    print(f"\n  Celkem inferencí: {inference_cnt}\n{'='*60}\n")


def main():
    print("=" * 60)
    print("  A06 — Media Monitoring Agent v4")
    print("  Error handling: retry, feed fallback, field defaults")
    print("=" * 60)

    topic = input("\nZadej téma pro monitoring (Enter = 'AI'): ").strip() or "AI"
    run_agent(topic)


if __name__ == "__main__":
    main()
