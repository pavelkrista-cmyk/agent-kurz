"""
A01 — RSS Reader / RSS Parser
==============================
Základ mediálního monitoringu: čtení, parsování a filtrování RSS feedů.
Foundation of media monitoring: reading, parsing, and filtering RSS feeds.

Spuštění / Run:
    python rss_reader.py

Závislosti / Dependencies:
    pip install feedparser
"""

import feedparser
from datetime import datetime

# ─── Konfigurace feedů / Feed configuration ──────────────────────────────────
# Přidej nebo odeber feedy podle potřeby / Add or remove feeds as needed
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
    """
    Extrahuje autora z různých RSS tagů.
    Extracts author from various RSS tags.

    RSS feedy používají různé tagy pro autora:
      - <author> (standard RSS 2.0)
      - <dc:creator> (Dublin Core extension)
    feedparser mapuje oba na entry.author, ale ne vždy.
    """
    # Zkus standardní 'author' atribut
    author = getattr(entry, "author", None)
    if author and author.strip():
        return author.strip()

    # Zkus Dublin Core creator (někdy v entry.tags nebo author_detail)
    author_detail = getattr(entry, "author_detail", None)
    if author_detail:
        name = author_detail.get("name", "")
        if name:
            return name.strip()

    return "Neznámý autor / Unknown author"


def get_published(entry) -> str:
    """
    Vrátí datum vydání jako čitelný řetězec YYYY-MM-DD HH:MM.
    Returns publication date as readable YYYY-MM-DD HH:MM string.

    feedparser parsuje datum do structured time tuple (published_parsed).
    Pokud chybí, vrátíme fallback string.
    """
    parsed = getattr(entry, "published_parsed", None)
    if parsed:
        try:
            dt = datetime(*parsed[:6])
            return dt.strftime("%Y-%m-%d %H:%M")
        except Exception:
            pass

    # Fallback: surový string z RSS (neformátovaný)
    raw = getattr(entry, "published", None)
    if raw:
        return raw[:25]  # zkrátíme

    return "Datum neznámé / Date unknown"


def contains_keyword(entry: dict, keyword: str) -> bool:
    """
    Zkontroluje, zda článek obsahuje klíčové slovo v titulku nebo perexi.
    Checks if article contains keyword in title or summary (case-insensitive).
    """
    keyword_lower = keyword.lower()
    title   = entry.get("title", "").lower()
    summary = entry.get("summary", "").lower()
    return keyword_lower in title or keyword_lower in summary


def parse_feed(source: dict) -> list:
    """
    Stáhne a naparsuje jeden RSS feed, vrátí seznam article dictů.
    Downloads and parses one RSS feed, returns list of article dicts.

    Každý dict obsahuje / Each dict contains:
        title, link, author, published, summary, source

    Při chybě vrátí prázdný seznam (nevyhodí výjimku).
    On error returns empty list (does not raise exception).
    """
    print(f"  Čtu feed: {source['name']} ...")

    try:
        feed = feedparser.parse(source["url"])
    except Exception as e:
        print(f"  ⚠  Chyba při stahování {source['name']}: {e}")
        return []

    # feedparser nastaví bozo=True pokud XML není perfektně validní,
    # ale stále ho zvládne naparsovat — bezpečné ignorovat
    if getattr(feed, "bozo", False):
        bozo_exc = getattr(feed, "bozo_exception", None)
        if bozo_exc:
            print(f"  ℹ  {source['name']}: drobná XML chyba (bozo), pokračuji. ({type(bozo_exc).__name__})")

    if not feed.entries:
        print(f"  ⚠  Feed {source['name']} neobsahuje žádné články (prázdný nebo nedostupný).")
        return []

    articles = []
    for entry in feed.entries:
        articles.append({
            "title":     entry.get("title", "Bez titulku / No title"),
            "link":      entry.get("link", ""),
            "author":    get_author(entry),
            "published": get_published(entry),
            # summary může obsahovat HTML tagy — pro teď je necháme
            "summary":   entry.get("summary", "")[:400],
            "source":    source["name"],
        })

    print(f"  ✓  {source['name']}: {len(articles)} článků načteno.")
    return articles


def print_article(article: dict, index: int):
    """Vytiskne článek čitelně do terminálu. / Prints article readably to terminal."""
    print(f"\n  [{index:2d}]  {article['title']}")
    print(f"        Autor: {article['author']}")
    print(f"        Datum: {article['published']}  |  Zdroj: {article['source']}")
    print(f"        URL:   {article['link']}")
    if article['summary'].strip():
        # Odstraníme HTML tagy jednoduše, zkrátíme
        import re
        clean_summary = re.sub(r"<[^>]+>", "", article["summary"])
        short = clean_summary.strip()[:150].replace("\n", " ")
        print(f"        Perex: {short}…")


# ─── Hlavní program / Main program ───────────────────────────────────────────

def main():
    print("=" * 60)
    print("  A01 — RSS Reader / RSS Parser")
    print("  Mediální monitoring — základ / Media monitoring — foundation")
    print("=" * 60)

    keyword = input("\nZadej klíčové slovo pro filtrování (Enter = zobraz vše): ").strip()

    print(f"\nNačítám {len(RSS_FEEDS)} RSS feedy...\n")

    all_articles = []
    errors = 0

    for source in RSS_FEEDS:
        articles = parse_feed(source)
        if not articles:
            errors += 1
        all_articles.extend(articles)

    print(f"\nCelkem načteno: {len(all_articles)} článků ze {len(RSS_FEEDS)} zdrojů.")
    if errors:
        print(f"Varování: {errors} zdroj(ů) vrátil chybu nebo byl prázdný.")

    # ── Filtrování / Filtering ────────────────────────────────────────────────
    if keyword:
        filtered = [a for a in all_articles if contains_keyword(a, keyword)]
        print(f"Filtrováno dle '{keyword}': {len(filtered)} shod z {len(all_articles)}.")
    else:
        filtered = all_articles
        print("Bez filtru — zobrazuji vše.")

    if not filtered:
        print("\nŽádné výsledky nenalezeny. / No results found.")
        print("Tip: zkus kratší nebo anglické klíčové slovo.")
        return

    # ── Výpis výsledků / Print results ───────────────────────────────────────
    display_limit = 20
    print(f"\n{'=' * 60}")
    if keyword:
        print(f"  VÝSLEDKY pro '{keyword}' ({min(len(filtered), display_limit)} z {len(filtered)})")
    else:
        print(f"  VÝSLEDKY — všechny články ({min(len(filtered), display_limit)} z {len(filtered)})")
    print(f"{'=' * 60}")

    for i, article in enumerate(filtered[:display_limit], 1):
        print_article(article, i)

    if len(filtered) > display_limit:
        print(f"\n  … a dalších {len(filtered) - display_limit} článků (zobrazeno {display_limit}).")

    print(f"\n{'=' * 60}")
    print("  Hotovo. / Done.")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
