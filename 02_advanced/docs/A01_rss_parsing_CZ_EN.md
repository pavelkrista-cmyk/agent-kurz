# RSS Parsing / RSS Parsing
> Krok / Step: A01 | Modul / Module: Advanced | Datum / Date: 2026-04-24

---

## Co je RSS a proč ho používáme / What is RSS and Why We Use It

RSS (Really Simple Syndication) je standardizovaný formát pro distribuci obsahu na webu.
Každý zpravodajský web, blog nebo podcast publikuje RSS **feed** — XML soubor, který se
automaticky aktualizuje při každém novém článku.

Pro agenta monitorujícího média je RSS ideální vstupní zdroj:
- **Strukturovaný formát** — titulek, autor, datum, odkaz, popis jsou vždy na stejném místě
- **Bez scrapingu** — nepotřebujeme parsovat HTML, RSS je čisté XML
- **Rychlá aktualizace** — feed se mění v řádu minut od vydání článku

*RSS (Really Simple Syndication) is a standardized format for distributing web content.
Every news site, blog, or podcast publishes an RSS feed — an XML file that updates
automatically with every new article. For a media monitoring agent, RSS is the ideal
input: structured format, no scraping needed, and updates within minutes of publication.*

---

## Struktura RSS feedu / RSS Feed Structure

Typický RSS feed vypadá takto (zjednodušeno):

```xml
<rss version="2.0">
  <channel>
    <title>BBC News - Technology</title>
    <link>https://www.bbc.co.uk/news/technology</link>
    <description>Technology news from BBC</description>

    <item>
      <title>AI model breaks new record on benchmark</title>
      <link>https://www.bbc.co.uk/news/articles/abc123</link>
      <author>jane.smith@bbc.co.uk (Jane Smith)</author>
      <pubDate>Wed, 24 Apr 2026 09:00:00 GMT</pubDate>
      <description>A new AI model has surpassed previous records...</description>
    </item>

    <item>
      <!-- další článek / next article -->
    </item>
  </channel>
</rss>
```

Klíčové elementy každého `<item>` (článku):

| Element | Obsah | Vždy přítomen? |
|---|---|---|
| `<title>` | Titulek článku | Ano |
| `<link>` | URL článku | Ano |
| `<author>` | Autor (formát se liší) | Někdy |
| `<pubDate>` | Datum a čas vydání | Většinou |
| `<description>` | Perex / shrnutí | Většinou |
| `<dc:creator>` | Autor (alternativní tag) | Někdy |

*The key elements of each `<item>`: title, link, author (sometimes), pubDate, description.*

---

## feedparser — knihovna pro čtení RSS / feedparser — RSS Reading Library

Python knihovna `feedparser` (Universal Feed Parser) umí číst RSS, Atom i jiné feed formáty.
Stáhne URL feedu, naparsuje XML a vrátí čistý Python objekt.

*The `feedparser` Python library reads RSS, Atom, and other feed formats.
It downloads the feed URL, parses the XML, and returns a clean Python object.*

### Instalace / Installation

```bash
pip install feedparser
```

### Základní použití / Basic Usage

```python
import feedparser

# Stáhni a naparsuj feed
feed = feedparser.parse("https://feeds.feedburner.com/TechCrunch")

# Metadata feedu
print(feed.feed.title)        # "TechCrunch"
print(feed.feed.link)         # "https://techcrunch.com"

# Počet článků
print(len(feed.entries))      # např. 20

# První článek
entry = feed.entries[0]
print(entry.title)            # "OpenAI announces GPT-5"
print(entry.link)             # "https://techcrunch.com/..."
print(entry.published)        # "Wed, 24 Apr 2026 09:00:00 GMT"
print(entry.summary)          # Perex článku
```

---

## Klíčový koncept: Bezpečný přístup k polím / Key Concept: Safe Field Access

RSS feedy nejsou jednotné. Jeden zdroj má `author`, jiný `dc:creator`, třetí nemá autora vůbec.
Přímý přístup přes `entry.author` vyhodí `AttributeError` nebo `KeyError`, když pole chybí.

**Řešení: vždy používej `.get()` nebo `getattr()` s výchozí hodnotou.**

*RSS feeds are not uniform. One source has `author`, another `dc:creator`, a third has none.
Direct access via `entry.author` raises `AttributeError` when the field is missing.
Solution: always use `.get()` or `getattr()` with a default value.*

```python
# ❌ Špatně — vyhodí chybu pokud pole chybí
author = entry.author

# ✅ Správně — bezpečný přístup s fallback hodnotou
author = entry.get("author", "Autor neznámý")

# Alternativa pro vnořené objekty
author = getattr(entry, "author", "Autor neznámý")
```

---

## Filtrování článků / Filtering Articles

Základní filtrování: hledáme klíčové slovo v titulku nebo perexi.

*Basic filtering: search for a keyword in the title or summary.*

```python
def contains_keyword(entry, keyword: str) -> bool:
    """Vrátí True pokud článek obsahuje klíčové slovo v titulku nebo perexi."""
    keyword_lower = keyword.lower()
    title = entry.get("title", "").lower()
    summary = entry.get("summary", "").lower()
    return keyword_lower in title or keyword_lower in summary
```

---

## Celý A01 skript / Full A01 Script

Tento skript je základ pro Advanced agenta. Nestará se ještě o plánování ani o paměť
(to přijde v A03 a A05). Teď se učíme číst a filtrovat.

*This script is the foundation for the Advanced agent. It doesn't yet handle scheduling
or memory (that comes in A03 and A05). Here we learn to read and filter.*

```python
"""
A01 — RSS Reader / RSS Parser
Základ mediálního monitoringu: čtení, parsování a filtrování RSS feedů.
Foundation of media monitoring: reading, parsing, and filtering RSS feeds.
"""

import feedparser
from datetime import datetime

# ─── Konfigurace feedů / Feed configuration ──────────────────────────────────
RSS_FEEDS = [
    {
        "name": "TechCrunch",
        "url": "https://techcrunch.com/feed/",
        "language": "en"
    },
    {
        "name": "Lupa.cz",
        "url": "https://www.lupa.cz/rss/clanky/",
        "language": "cs"
    },
    {
        "name": "Root.cz",
        "url": "https://www.root.cz/rss/clanky/",
        "language": "cs"
    },
]

# ─── Pomocné funkce / Helper functions ───────────────────────────────────────

def get_author(entry) -> str:
    """Extrahuje autora z různých RSS tagů. / Extracts author from various RSS tags."""
    # Zkus standardní 'author' tag
    if hasattr(entry, "author") and entry.author:
        return entry.author
    # Zkus Dublin Core 'creator' tag (alternativní standard)
    if hasattr(entry, "tags"):
        for tag in entry.tags:
            if "creator" in tag.get("term", ""):
                return tag.get("term", "Neznámý autor")
    return "Neznámý autor / Unknown author"


def get_published(entry) -> str:
    """Vrátí datum vydání jako čitelný řetězec. / Returns publication date as readable string."""
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        dt = datetime(*entry.published_parsed[:6])
        return dt.strftime("%Y-%m-%d %H:%M")
    return "Datum neznámé / Date unknown"


def contains_keyword(entry, keyword: str) -> bool:
    """Zkontroluje, zda článek obsahuje klíčové slovo. / Checks if article contains keyword."""
    keyword_lower = keyword.lower()
    title = entry.get("title", "").lower()
    summary = entry.get("summary", "").lower()
    return keyword_lower in title or keyword_lower in summary


def parse_feed(source: dict) -> list[dict]:
    """
    Stáhne a naparsuje jeden RSS feed.
    Downloads and parses one RSS feed.
    
    Returns: list of article dicts with keys: title, link, author, published, summary, source
    """
    print(f"  Čtu feed: {source['name']} ...")
    
    try:
        feed = feedparser.parse(source["url"])
    except Exception as e:
        print(f"  ⚠ Chyba při čtení {source['name']}: {e}")
        return []
    
    # Zkontroluj, zda feed vrátil články
    if not feed.entries:
        print(f"  ⚠ Feed {source['name']} neobsahuje žádné články.")
        return []
    
    articles = []
    for entry in feed.entries:
        articles.append({
            "title":     entry.get("title", "Bez titulku"),
            "link":      entry.get("link", ""),
            "author":    get_author(entry),
            "published": get_published(entry),
            "summary":   entry.get("summary", "")[:300],  # max 300 znaků perexi
            "source":    source["name"],
        })
    
    print(f"  ✓ {source['name']}: {len(articles)} článků načteno.")
    return articles


def print_article(article: dict, index: int):
    """Vytiskne článek čitelně do terminálu. / Prints article readably to terminal."""
    print(f"\n[{index}] {article['title']}")
    print(f"    Autor: {article['author']}  |  {article['published']}  |  {article['source']}")
    print(f"    URL: {article['link']}")
    if article['summary']:
        # Zkrátíme perex pro přehlednost
        summary_short = article['summary'][:120].replace("\n", " ")
        print(f"    Perex: {summary_short}...")


# ─── Hlavní program / Main program ───────────────────────────────────────────

def main():
    keyword = input("Zadej klíčové slovo pro filtrování (Enter = zobraz vše): ").strip()
    
    print(f"\nNačítám RSS feedy...")
    
    all_articles = []
    for source in RSS_FEEDS:
        articles = parse_feed(source)
        all_articles.extend(articles)
    
    print(f"\nCelkem načteno: {len(all_articles)} článků ze {len(RSS_FEEDS)} zdrojů.")
    
    # Filtrování
    if keyword:
        filtered = [a for a in all_articles if contains_keyword(a, keyword)]
        print(f"Filtrováno dle '{keyword}': {len(filtered)} shod.")
    else:
        filtered = all_articles
    
    if not filtered:
        print("Žádné výsledky nenalezeny. / No results found.")
        return
    
    print(f"\n{'='*60}")
    print(f"VÝSLEDKY / RESULTS ({len(filtered)} článků)")
    print(f"{'='*60}")
    
    for i, article in enumerate(filtered[:20], 1):   # max 20 výsledků
        print_article(article, i)
    
    print(f"\n{'='*60}")
    print("Hotovo. / Done.")


if __name__ == "__main__":
    main()
```

---

## Co se děje krok za krokem / Step by Step

Spustíš `rss_reader.py`, zadáš klíčové slovo (např. `"AI"`) a sleduj výpis:

1. Skript postupně stahuje každý RSS feed (HTTP GET request na URL)
2. `feedparser` naparsuje XML → Python objekt `feed.entries`
3. Pro každý `entry` extrahujeme pět polí: `title`, `link`, `author`, `published`, `summary`
4. Funkce `contains_keyword()` projde titulky a perexy — vrátí `True`/`False`
5. Filtrované výsledky se vypíší do terminálu, max. 20 položek

Celý proces běží bez Claude API — žádné API náklady, jen HTTP request na RSS URL.

*The script downloads each RSS feed, feedparser parses the XML into a Python object,
we extract five fields from each entry, filter by keyword, and print results.
No Claude API involved — zero cost.*

---

## Proč je to důležité pro agenta / Why This Matters for the Agent

Tato vrstva (RSS → filtrovaný seznam článků) bude vstupem pro agenta v A02.
Agent dostane seznam článků a použije Claude API k jejich hlubší analýze —
shrnutí, hodnocení relevance, extrakce autora z textu (pokud RSS autor chybí).

Bez solidního RSS parseru by agent zpracovával nekvalitní nebo neúplná data.

*This layer (RSS → filtered article list) will be the input for the agent in A02.
The agent will receive the article list and use Claude API for deeper analysis —
summarization, relevance scoring, author extraction from text.
Without a solid RSS parser, the agent would work with incomplete data.*

---

## Časté problémy a řešení / Common Problems and Solutions

| Problém | Příčina | Řešení |
|---|---|---|
| `AttributeError: entry has no attribute 'author'` | Pole v RSS chybí | Použij `entry.get("author", "Neznámý")` |
| Feed vrátí 0 článků | URL feedu se změnila | Ověř URL v prohlížeči, najdi nový feed |
| `bozo: True` v feedparser | Feed není validní XML | feedparser zvládne i "bozo" feedy, ignoruj |
| Špatné kódování znaků | Feed v ISO-8859-2 | feedparser řeší kódování automaticky |
| `urllib.error.URLError` | Síťová chyba / timeout | Ošetři try/except (viz kód výše) |

*Common problems: missing author field → use `.get()` with default; feed returns 0 entries
→ verify URL; `bozo: True` → safe to ignore; encoding issues → feedparser handles automatically;
`URLError` → wrap in try/except.*

---

## Mini-úkol / Mini Task

1. Nainstaluj feedparser: `pip install feedparser`
2. Spusť `rss_reader.py` (najdeš v `02_advanced/code/`)
3. Zkus různá klíčová slova: `"AI"`, `"Python"`, `"bezpečnost"`
4. Podívej se na výpis pole `author` — jak se liší mezi zdroji?

> **Otázka: Kolik článků vrátil TechCrunch? Byl u nich vždy vyplněný autor?**

*(Odpověz než přejdeš na A02.)*

---

## Náklady na API / API Cost

A01 nepoužívá Claude API vůbec. Náklady = **$0.00**.
feedparser dělá přímé HTTP requesty na RSS URL — bez tokenů, bez inference.

*A01 uses no Claude API. Cost = $0.00.*

---

*Další krok / Next step: A02 — Multi-tool agent — agent dostane RSS výstup a zavolá Claude pro analýzu*
