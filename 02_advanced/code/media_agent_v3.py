"""
A04 — Media Monitoring Agent v3 — structured output
=====================================================
Nové oproti v2 / New compared to v2:
  - Nástroj create_digest() přijímá JSON schéma místo volného textu
  - Každý článek má pole 'relevance' (1-10) — Claude ho vyplní
  - Články jsou seřazeny dle relevance v digestu
  - Python garantuje konzistentní formát každého běhu

Spuštění / Run:
    python media_agent_v3.py

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
- Pokud autor obsahuje email, zobraz jen jméno"""

# ─── State management (stejné jako v A03) ────────────────────────────────────

def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"  ⚠ Chyba čtení state: {e}")
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
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    if added:
        print(f"  💾 State: {added} nových URL přidáno (celkem {len(state['seen_urls'])})")


def filter_new_articles(articles: list, seen_urls: set) -> list:
    return [a for a in articles if a.get("link", "") not in seen_urls]


state = load_state()

# ─── Pomocné funkce ───────────────────────────────────────────────────────────

def get_author_clean(entry) -> str:
    author = getattr(entry, "author", None) or ""
    match = re.search(r"\((?:[^:]+:\s*)?([^)]+)\)", author)
    if match:
        return match.group(1).strip()
    if author and "@" not in author:
        return author.strip()
    return "Neznámý autor"


def get_published(entry) -> str:
    parsed = getattr(entry, "published_parsed", None)
    if parsed:
        try:
            return datetime(*parsed[:6]).strftime("%Y-%m-%d %H:%M")
        except Exception:
            pass
    return getattr(entry, "published", "")[:16] or "Datum neznámé"

# ─── Tool implementace ───────────────────────────────────────────────────────

def search_rss(keyword: str, max_results: int = 15) -> str:
    """Stáhne RSS, filtruje dle keyword, odstraní viděné URL."""
    keyword_lower = keyword.lower()
    all_articles  = []
    seen_set      = set(state["seen_urls"])

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

    new_articles = filter_new_articles(all_articles, seen_set)
    print(f"  📰 Celkem: {len(all_articles)} | Nových: {len(new_articles)} | Viděno: {len(all_articles)-len(new_articles)}")

    if not new_articles:
        return json.dumps({"message": f"Žádné nové články pro '{keyword}'.", "new": 0}, ensure_ascii=False)

    results = new_articles[:max_results]
    return json.dumps({
        "keyword": keyword, "total_found": len(all_articles),
        "new": len(new_articles), "returned": len(results), "articles": results
    }, ensure_ascii=False, indent=2)


def create_digest(topic: str, date_str: str, overview: str, articles: list) -> str:
    """
    Převede strukturovaná JSON data na Markdown digest a uloží soubor.
    Converts structured JSON data to Markdown digest and saves to file.

    Články jsou seřazeny dle relevance (nejvyšší první).
    Articles are sorted by relevance (highest first).
    """
    # Seřaď dle relevance
    articles_sorted = sorted(articles, key=lambda a: a.get("relevance", 0), reverse=True)

    avg_relevance = (
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
        # Vizuální indikátor relevance
        if isinstance(rel, int):
            bar = "█" * rel + "░" * (10 - rel)
        else:
            bar = ""

        lines += [
            f"### {art.get('title', 'Bez titulku')}",
            f"**Zdroj:** {art.get('source', '?')} | "
            f"**Autor:** {art.get('author', 'Neznámý')} | "
            f"**Datum:** {art.get('published', '?')}",
            f"**Relevance:** {rel}/10  `{bar}`",
            f"**URL:** {art.get('url', '')}",
            "",
            art.get("summary_cs", ""),
            "",
            "---",
            "",
        ]

    content = "\n".join(lines)
    filename = f"digest_{date_str}.md"
    filepath = os.path.join(OUTPUT_DIR, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    # Zaznamenej URL do state
    urls = [a.get("url", "") for a in articles if a.get("url")]
    save_state(state, urls)

    return (
        f"✓ Digest uložen: {filepath} | "
        f"{len(articles)} článků | "
        f"Průměrná relevance: {avg_relevance:.1f}/10 | "
        f"Top článek: '{articles_sorted[0].get('title', '?')}' ({articles_sorted[0].get('relevance', '?')}/10)"
    )

# ─── Tool definice / Tool definitions ────────────────────────────────────────

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
    print(f"  A04 — Media Agent v3 | Téma: '{topic}' | {TODAY}")
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

        response = client.messages.create(
            model=MODEL, max_tokens=4096,
            system=SYSTEM_PROMPT, tools=TOOLS, messages=messages
        )
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

                if block.name == "search_rss":
                    result = search_rss(**block.input)
                elif block.name == "create_digest":
                    result = create_digest(**block.input)
                    print(f"  {result}")
                else:
                    result = f"Neznámý nástroj: {block.name}"

                tool_results.append({
                    "type": "tool_result", "tool_use_id": block.id, "content": result
                })
            messages.append({"role": "user", "content": tool_results})
        else:
            print(f"  ⚠ stop_reason: {response.stop_reason}")
            break

    print(f"\n  Celkem inferencí: {inference_cnt}\n{'='*60}\n")


def main():
    print("=" * 60)
    print("  A04 — Media Monitoring Agent v3")
    print("  Structured output: JSON schéma + relevance skóre")
    print("=" * 60)

    topic = input("\nZadej téma pro monitoring (Enter = 'AI'): ").strip() or "AI"
    run_agent(topic)


if __name__ == "__main__":
    main()
