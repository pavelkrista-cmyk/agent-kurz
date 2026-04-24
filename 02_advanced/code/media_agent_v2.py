"""
A03 — Media Monitoring Agent v2 — s pamětí / with memory
==========================================================
Rozšíření A02 o agent state: pamatujeme si již zpracované články (seen_urls).
Extension of A02 with agent state: we remember already-processed articles (seen_urls).

Nové oproti A02 / New compared to A02:
  - load_state() / save_state() — perzistentní JSON soubor
  - filter_new_articles()       — vyřadí již viděné URL
  - agent_state.json            — soubor se stavem agenta

Spuštění / Run:
    python media_agent_v2.py

Závislosti / Dependencies:
    pip install anthropic python-dotenv feedparser
"""

import os
import json
import re
from datetime import date, datetime
from dotenv import load_dotenv
import anthropic
import feedparser

load_dotenv()
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# ─── Konfigurace / Configuration ─────────────────────────────────────────────
MODEL      = "claude-haiku-4-5-20251001"
OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(OUTPUT_DIR, "agent_state.json")

RSS_FEEDS = [
    {"name": "TechCrunch", "url": "https://techcrunch.com/feed/"},
    {"name": "Lupa.cz",    "url": "https://www.lupa.cz/rss/clanky/"},
    {"name": "Root.cz",    "url": "https://www.root.cz/rss/clanky/"},
]

# ─── Systémový prompt / System prompt ────────────────────────────────────────
SYSTEM_PROMPT = f"""Jsi mediální monitoring agent specializovaný na technologické zprávy.
Dnešní datum: {date.today().strftime('%Y-%m-%d')}

Když dostaneš téma:
1. Zavolej search_rss s tímto tématem — to je vždy první krok.
2. Pokud JSON obsahuje "new: 0" nebo zprávu o žádných nových článcích, informuj uživatele
   a NEVOLEJ save_to_file. Digest se generuje jen pro nové články.
3. Pokud jsou nové články, vyber 3–8 nejrelevantnějších.
4. Pro každý vybraný článek napiš 2–3 věté shrnutí v češtině.
5. Sestav Markdown digest v tomto formátu:

# Mediální monitoring: {{téma}}
_Datum: {date.today().strftime('%Y-%m-%d')}_

## Přehled
[1–2 věty o celkovém obrazu tématu]

## Články

### [Přesný titulek článku]
**Zdroj:** [název zdroje] | **Autor:** [autor] | **Datum:** [datum]
**URL:** [odkaz]

[2–3 věté shrnutí česky]

---

6. Zavolej save_to_file s názvem digest_{date.today().strftime('%Y-%m-%d')}.md
7. Odpověz stručnou zprávou: kolik nových článků, kde je soubor.

Pravidla:
- Shrnutí piš česky, technické termíny anglicky
- Pokud autor obsahuje email, zobraz jen jméno za závorkou
- search_rss vrátí v JSON pole 'new' — kolik článků je skutečně nových"""

# ─── State management ────────────────────────────────────────────────────────

def load_state() -> dict:
    """
    Načte agent state ze souboru.
    Loads agent state from file.
    Pokud soubor neexistuje, vrátí prázdný state — první spuštění.
    If file doesn't exist, returns empty state — first run.
    """
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"  ⚠ Chyba čtení state, začínám od nuly: {e}")
    return {
        "seen_urls":       [],
        "last_run":        None,
        "total_processed": 0
    }


def save_state(state: dict, new_urls: list):
    """
    Přidá nové URL do state a uloží na disk.
    Adds new URLs to state and saves to disk.
    """
    seen_set = set(state["seen_urls"])
    added = 0
    for url in new_urls:
        if url and url not in seen_set:
            state["seen_urls"].append(url)
            seen_set.add(url)
            added += 1

    state["last_run"]        = datetime.now().strftime("%Y-%m-%d %H:%M")
    state["total_processed"] = state.get("total_processed", 0) + added

    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

    print(f"  💾 State uložen: {added} nových URL přidáno (celkem {len(state['seen_urls'])})")


def filter_new_articles(articles: list, seen_urls: set) -> list:
    """
    Vrátí jen články, jejichž URL ještě nebylo zpracováno.
    Returns only articles whose URL has not yet been processed.
    """
    return [a for a in articles if a.get("link", "") not in seen_urls]

# ─── Globální state — načteme jednou při startu / Global state loaded at startup
state = load_state()

# ─── Python implementace nástrojů / Python tool implementations ──────────────

def get_author_clean(entry) -> str:
    """Extrahuje čisté jméno autora — odstraní email prefix."""
    author = getattr(entry, "author", None) or ""
    match = re.search(r"\((?:[^:]+:\s*)?([^)]+)\)", author)
    if match:
        return match.group(1).strip()
    if author and "@" not in author:
        return author.strip()
    return "Neznámý autor"


def get_published(entry) -> str:
    """Vrátí datum vydání jako YYYY-MM-DD HH:MM."""
    parsed = getattr(entry, "published_parsed", None)
    if parsed:
        try:
            return datetime(*parsed[:6]).strftime("%Y-%m-%d %H:%M")
        except Exception:
            pass
    raw = getattr(entry, "published", "")
    return raw[:16] if raw else "Datum neznámé"


def search_rss(keyword: str, max_results: int = 15) -> str:
    """
    Tool: stáhne RSS, filtruje dle keyword, ODSTRANÍ již viděné URL.
    Tool: downloads RSS, filters by keyword, REMOVES already-seen URLs.
    """
    keyword_lower = keyword.lower()
    all_articles  = []
    seen_set      = set(state["seen_urls"])  # set pro rychlé vyhledávání O(1)

    for source in RSS_FEEDS:
        try:
            feed = feedparser.parse(source["url"])
            for entry in feed.entries:
                title   = entry.get("title", "")
                summary = entry.get("summary", "")
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
            print(f"  ⚠ Chyba feedu {source['name']}: {e}")

    # Filtruj nové články
    new_articles = filter_new_articles(all_articles, seen_set)

    print(f"  📰 Nalezeno celkem: {len(all_articles)} | Nových: {len(new_articles)} | Viděno dříve: {len(all_articles) - len(new_articles)}")

    if not new_articles:
        return json.dumps({
            "message":     f"Žádné nové články pro '{keyword}'. Vše již bylo zpracováno.",
            "total_found": len(all_articles),
            "new":         0
        }, ensure_ascii=False)

    results = new_articles[:max_results]
    return json.dumps({
        "keyword":     keyword,
        "total_found": len(all_articles),
        "new":         len(new_articles),
        "returned":    len(results),
        "articles":    results
    }, ensure_ascii=False, indent=2)


def save_to_file(content: str, filename: str) -> str:
    """Tool: uloží digest do souboru a zaznamená URL zpracovaných článků."""
    if "/" in filename or "\\" in filename:
        return "✗ Chyba: filename nesmí obsahovat lomítka."
    if not filename.endswith(".md"):
        filename += ".md"

    filepath = os.path.join(OUTPUT_DIR, filename)
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

        # Extrahuj URL z digestu a ulož do state
        urls = re.findall(r'\*\*URL:\*\*\s*(https?://\S+)', content)
        save_state(state, urls)

        return f"✓ Digest uložen: {filepath} ({len(content)} znaků, {len(urls)} článků zaznamenáno do state)"
    except Exception as e:
        return f"✗ Chyba při ukládání: {e}"


# ─── Tool definice / Tool definitions ────────────────────────────────────────

TOOLS = [
    {
        "name": "search_rss",
        "description": (
            "Vyhledá NOVÉ články v RSS feedech dle klíčového slova. "
            "Automaticky filtruje již zpracované články (agent si pamatuje seen_urls). "
            "Vrátí JSON s poli: total_found, new, returned, articles. "
            "Použij jako první krok. Pokud 'new' == 0, nové články nejsou — nepiš digest."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "keyword":     {"type": "string",  "description": "Klíčové slovo pro filtrování"},
                "max_results": {"type": "integer", "description": "Max počet článků (default 15)", "default": 15}
            },
            "required": ["keyword"]
        }
    },
    {
        "name": "save_to_file",
        "description": (
            "Uloží Markdown digest do souboru a zaznamená zpracované URL do paměti agenta. "
            f"Filename formát: digest_{date.today().strftime('%Y-%m-%d')}.md"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "content":  {"type": "string", "description": "Markdown text digestu"},
                "filename": {"type": "string", "description": "Název souboru"}
            },
            "required": ["content", "filename"]
        }
    }
]

# ─── Agentic loop ─────────────────────────────────────────────────────────────

def run_agent(topic: str):
    print(f"\n{'='*60}")
    print(f"  Spouštím agenta pro téma: '{topic}'")
    print(f"  Datum: {date.today()}")
    if state["last_run"]:
        print(f"  Poslední běh: {state['last_run']} | Celkem zpracováno: {state['total_processed']} URL")
    else:
        print(f"  První spuštění — state prázdný.")
    print(f"{'='*60}\n")

    messages = [{"role": "user", "content": f"Sleduj téma: {topic}"}]
    inference_count = 0

    while True:
        inference_count += 1
        print(f"[Inference #{inference_count}] Claude přemýšlí...")

        response = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages
        )

        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            for block in response.content:
                if hasattr(block, "text"):
                    print(f"\n{'='*60}")
                    print("  AGENT DOKONČIL / AGENT DONE")
                    print(f"{'='*60}")
                    print(block.text)
            break

        elif response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                print(f"  → Claude volá: {block.name}({json.dumps(block.input, ensure_ascii=False)[:80]}...)")

                if block.name == "search_rss":
                    result = search_rss(**block.input)
                elif block.name == "save_to_file":
                    result = save_to_file(**block.input)
                    print(f"  {result}")
                else:
                    result = f"Neznámý nástroj: {block.name}"

                tool_results.append({
                    "type":        "tool_result",
                    "tool_use_id": block.id,
                    "content":     result
                })
            messages.append({"role": "user", "content": tool_results})

        else:
            print(f"  ⚠ Neočekávaný stop_reason: {response.stop_reason}")
            break

    print(f"\n  Celkem inferencí: {inference_count}")
    print(f"{'='*60}\n")


# ─── Hlavní program ───────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  A03 — Media Monitoring Agent v2 — s pamětí")
    print("  State soubor:", STATE_FILE)
    print("=" * 60)

    topic = input("\nZadej téma pro monitoring (Enter = 'AI'): ").strip()
    if not topic:
        topic = "AI"

    run_agent(topic)


if __name__ == "__main__":
    main()
