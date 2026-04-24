"""
A02 — Media Monitoring Agent / Mediální monitoring agent
=========================================================
Multi-tool agent: kombinuje RSS čtení (search_rss) a ukládání výstupu (save_to_file).
Multi-tool agent: combines RSS reading (search_rss) and file saving (save_to_file).

Spuštění / Run:
    python media_agent.py

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
MODEL = "claude-haiku-4-5-20251001"

# Kde se ukládají digesty / Where digests are saved
OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))

RSS_FEEDS = [
    {"name": "TechCrunch", "url": "https://techcrunch.com/feed/"},
    {"name": "Lupa.cz",    "url": "https://www.lupa.cz/rss/clanky/"},
    {"name": "Root.cz",    "url": "https://www.root.cz/rss/clanky/"},
]

# ─── Systémový prompt / System prompt ────────────────────────────────────────
SYSTEM_PROMPT = """Jsi mediální monitoring agent specializovaný na technologické zprávy.

Když dostaneš téma:
1. Zavolej search_rss s tímto tématem jako keyword — to je vždy první krok.
2. Z vrácených článků vyber 3–5 nejrelevantnějších k tématu.
3. Pro každý vybraný článek napiš 2–3 věté shrnutí v češtině.
4. Sestav Markdown digest přesně v tomto formátu:

# Mediální monitoring: {téma}
_Datum: {dnešní datum}_

## Přehled
[1–2 věty o celkovém obrazu tématu na základě nalezených článků]

## Články

### [Přesný titulek článku]
**Zdroj:** [název zdroje] | **Autor:** [autor] | **Datum:** [datum]
**URL:** [odkaz]

[2–3 věté shrnutí česky]

---

[opakuj pro každý článek]

5. Zavolej save_to_file s tímto digestem. Filename: digest_{dnešní datum YYYY-MM-DD}.md
6. Odpověz stručnou zprávou: co jsi našel, kolik článků, kde je soubor uložen.

Pravidla:
- Shrnutí piš česky, technické termíny ponechej anglicky
- Pokud autor obsahuje email (např. redakce@lupa.cz), zobraz jen jméno za závorkou
- Vybírej jen skutečně relevantní články — raději méně a kvalitní než více a vágní"""

# ─── Python implementace nástrojů / Python tool implementations ──────────────

def get_author_clean(entry) -> str:
    """Extrahuje čisté jméno autora — odstraní email prefix."""
    author = getattr(entry, "author", None) or ""

    # Formát "redakce@lupa.cz (Lupa.cz: Jan Sedlák)" → "Jan Sedlák"
    match = re.search(r"\((?:[^:]+:\s*)?([^)]+)\)", author)
    if match:
        return match.group(1).strip()

    # Čisté jméno (TechCrunch style) → vrátíme přímo
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


def search_rss(keyword: str, max_results: int = 10) -> str:
    """
    Tool implementace: stáhne RSS feedy, filtruje dle keyword, vrátí JSON.
    Tool implementation: downloads RSS feeds, filters by keyword, returns JSON.
    """
    keyword_lower = keyword.lower()
    all_articles = []

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
            # Chyba jednoho feedu neukončí celé vyhledávání
            all_articles.append({"error": f"{source['name']}: {e}"})

    # Omez počet výsledků
    results = all_articles[:max_results]

    if not results:
        return json.dumps({"message": f"Žádné články pro '{keyword}' nenalezeny."}, ensure_ascii=False)

    return json.dumps({
        "keyword":      keyword,
        "total_found":  len(all_articles),
        "returned":     len(results),
        "articles":     results
    }, ensure_ascii=False, indent=2)


def save_to_file(content: str, filename: str) -> str:
    """
    Tool implementace: uloží content do souboru OUTPUT_DIR/filename.
    Tool implementation: saves content to OUTPUT_DIR/filename.
    """
    # Bezpečnostní kontrola: jen .md soubory, žádné cesty s lomítkem
    if "/" in filename or "\\" in filename:
        return "✗ Chyba: filename nesmí obsahovat lomítka."
    if not filename.endswith(".md"):
        filename += ".md"

    filepath = os.path.join(OUTPUT_DIR, filename)
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        return f"✓ Digest uložen: {filepath} ({len(content)} znaků)"
    except Exception as e:
        return f"✗ Chyba při ukládání: {e}"


# ─── Definice nástrojů pro Claudea / Tool definitions for Claude ─────────────

TOOLS = [
    {
        "name": "search_rss",
        "description": (
            "Vyhledá aktuální články v RSS feedech dle klíčového slova. "
            "Vrátí seznam článků jako JSON: title, link, author, published, summary, source. "
            "Použij jako první krok při každém monitoringu tématu."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "keyword": {
                    "type": "string",
                    "description": "Klíčové slovo pro filtrování článků (case-insensitive)"
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximální počet článků k vrácení (default 10, max 20)",
                    "default": 10
                }
            },
            "required": ["keyword"]
        }
    },
    {
        "name": "save_to_file",
        "description": (
            "Uloží textový obsah (Markdown) do souboru na disku. "
            "Použij pro uložení finálního digestu poté, co ho sestavíš. "
            "Filename formát: digest_YYYY-MM-DD.md"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "Obsah souboru — Markdown text digestu"
                },
                "filename": {
                    "type": "string",
                    "description": "Název souboru, např. digest_2026-04-24.md"
                }
            },
            "required": ["content", "filename"]
        }
    }
]

# ─── Agentic loop / Agentic loop ─────────────────────────────────────────────

def run_agent(topic: str):
    """
    Spustí media monitoring agenta pro zadané téma.
    Runs the media monitoring agent for the given topic.
    """
    print(f"\n{'='*60}")
    print(f"  Spouštím agenta pro téma: '{topic}'")
    print(f"  Datum: {date.today()}")
    print(f"{'='*60}\n")

    messages = [
        {"role": "user", "content": f"Sleduj téma: {topic}"}
    ]

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

        # Přidej odpověď Claudea do konverzace
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            # Claude skončil — vytiskni finální odpověď
            for block in response.content:
                if hasattr(block, "text"):
                    print(f"\n{'='*60}")
                    print("  AGENT DOKONČIL / AGENT DONE")
                    print(f"{'='*60}")
                    print(block.text)
            break

        elif response.stop_reason == "tool_use":
            # Claude chce zavolat nástroj (nebo více nástrojů najednou)
            tool_results = []

            for block in response.content:
                if block.type != "tool_use":
                    continue

                print(f"  → Claude volá: {block.name}({json.dumps(block.input, ensure_ascii=False)[:80]}...)")

                # Dispatch — zavolej správnou Python funkci
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

            # Přidej výsledky nástrojů do konverzace
            messages.append({"role": "user", "content": tool_results})

        else:
            # Neočekávaný stop_reason — pro debugování
            print(f"  ⚠ Neočekávaný stop_reason: {response.stop_reason}")
            break

    print(f"\n  Celkem inferencí: {inference_count}")
    print(f"{'='*60}\n")


# ─── Hlavní program / Main program ───────────────────────────────────────────

def main():
    print("=" * 60)
    print("  A02 — Media Monitoring Agent")
    print("  Multi-tool: search_rss + save_to_file")
    print("=" * 60)

    topic = input("\nZadej téma pro monitoring (Enter = 'AI'): ").strip()
    if not topic:
        topic = "AI"

    run_agent(topic)


if __name__ == "__main__":
    main()
