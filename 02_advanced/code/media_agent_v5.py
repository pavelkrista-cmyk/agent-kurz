"""
A08 — Media Monitoring Agent v5 — email delivery
=================================================
Nové oproti v4 / New compared to v4:
  - send_email_digest() — odešle HTML email přes Gmail SMTP
  - Markdown digest se převede na HTML (nadpisy, tučné, odkazy)
  - Konfigurace v .env: GMAIL_USER, GMAIL_APP_PASSWORD, EMAIL_TO

Spuštění / Run:
    python media_agent_v5.py

Závislosti / Dependencies:
    pip install anthropic python-dotenv feedparser
    (smtplib, email.mime — součást Python stdlib, nepotřebuje pip)
"""

import os
import json
import re
import time
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import date, datetime
from dotenv import load_dotenv
import anthropic
import feedparser

load_dotenv()
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

MODEL      = "claude-haiku-4-5-20251001"
OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(OUTPUT_DIR, "agent_state.json")

# ─── Email konfigurace / Email configuration ─────────────────────────────────
GMAIL_USER     = os.getenv("GMAIL_USER")
GMAIL_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")
EMAIL_TO       = os.getenv("EMAIL_TO", GMAIL_USER)  # výchozí: posílej sám sobě

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
    author = getattr(entry, "author", None) or ""
    match = re.search(r"\((?:[^:]+:\s*)?([^)]+)\)", author)
    if match:
        return match.group(1).strip()
    if author and "@" not in author:
        return author.strip()
    return "Redakce"


def get_published(entry) -> str:
    parsed = getattr(entry, "published_parsed", None)
    if parsed:
        try:
            return datetime(*parsed[:6]).strftime("%Y-%m-%d %H:%M")
        except Exception:
            pass
    raw = getattr(entry, "published", "") or ""
    return raw[:16] if raw else "Datum neznámé"

# ─── Retry wrapper ────────────────────────────────────────────────────────────

def call_api_with_retry(messages: list, max_retries: int = 3) -> object:
    wait_seconds = 10
    for attempt in range(max_retries):
        try:
            return client.messages.create(
                model=MODEL, max_tokens=4096,
                system=SYSTEM_PROMPT, tools=TOOLS, messages=messages
            )
        except anthropic.APIStatusError as e:
            if "overloaded" in str(e).lower() and attempt < max_retries - 1:
                print(f"  ⚠ API přetíženo — čekám {wait_seconds}s (pokus {attempt+1}/3)...")
                time.sleep(wait_seconds)
                wait_seconds *= 2
            else:
                raise
        except anthropic.APIConnectionError as e:
            if attempt < max_retries - 1:
                print(f"  ⚠ Síťová chyba — čekám {wait_seconds}s (pokus {attempt+1}/3)...")
                time.sleep(wait_seconds)
                wait_seconds *= 2
            else:
                raise

# ─── Email funkce / Email functions ──────────────────────────────────────────

def md_to_html(md_text: str) -> str:
    """
    Jednoduchý Markdown → HTML převodník pro digest.
    Simple Markdown → HTML converter for digest emails.
    Pokrývá: # nadpisy, **tučné**, [text](url), --- oddělovač, odrážky.
    """
    lines   = md_text.split("\n")
    html    = []
    in_list = False

    for line in lines:
        # Oddělovač
        if line.strip() == "---":
            if in_list:
                html.append("</ul>"); in_list = False
            html.append("<hr style='border:none;border-top:1px solid #eee;margin:12px 0'>")
            continue

        # Nadpisy
        if line.startswith("### "):
            if in_list: html.append("</ul>"); in_list = False
            html.append(f"<h3 style='color:#1a73e8;margin:16px 0 4px'>{line[4:]}</h3>")
            continue
        if line.startswith("## "):
            if in_list: html.append("</ul>"); in_list = False
            html.append(f"<h2 style='color:#1f1f1f;border-bottom:2px solid #1a73e8;padding-bottom:4px'>{line[3:]}</h2>")
            continue
        if line.startswith("# "):
            if in_list: html.append("</ul>"); in_list = False
            html.append(f"<h1 style='color:#1a73e8'>{line[2:]}</h1>")
            continue

        # Odrážky
        if line.startswith("- "):
            if not in_list:
                html.append("<ul style='margin:4px 0;padding-left:20px'>"); in_list = True
            html.append(f"<li>{line[2:]}</li>")
            continue
        else:
            if in_list:
                html.append("</ul>"); in_list = False

        # Prázdný řádek
        if not line.strip():
            html.append("<br>")
            continue

        # Inline formátování: **tučné**, [text](url), `kód`
        processed = line
        processed = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", processed)
        processed = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2" style="color:#1a73e8">\1</a>', processed)
        processed = re.sub(r"`([^`]+)`", r"<code style='background:#f3f4f6;padding:1px 4px;border-radius:3px'>\1</code>", processed)

        html.append(f"<p style='margin:4px 0'>{processed}</p>")

    if in_list:
        html.append("</ul>")

    return "\n".join(html)


def send_email_digest(topic: str, digest_path: str) -> str:
    """
    Přečte MD digest, převede na HTML a odešle přes Gmail SMTP.
    Reads MD digest, converts to HTML and sends via Gmail SMTP.
    """
    if not GMAIL_USER or not GMAIL_PASSWORD:
        return "⚠ Email nekonfigurován — chybí GMAIL_USER nebo GMAIL_APP_PASSWORD v .env"

    if not os.path.exists(digest_path):
        return f"✗ Digest soubor nenalezen: {digest_path}"

    try:
        with open(digest_path, "r", encoding="utf-8") as f:
            md_content = f.read()
    except Exception as e:
        return f"✗ Nelze přečíst digest: {e}"

    # Sestavení emailu
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"📰 Mediální monitoring: {topic} — {TODAY}"
    msg["From"]    = GMAIL_USER
    msg["To"]      = EMAIL_TO

    # Plain text verze (fallback pro staré email klienty)
    plain_text = md_content

    # HTML verze
    html_body = f"""
    <html><body style="font-family:Arial,sans-serif;max-width:700px;margin:auto;padding:20px;color:#1f1f1f">
    <div style="background:#1a73e8;color:white;padding:16px 20px;border-radius:8px 8px 0 0">
        <h1 style="margin:0;font-size:20px">📰 Mediální monitoring</h1>
        <p style="margin:4px 0 0;opacity:0.85">{topic} — {TODAY}</p>
    </div>
    <div style="border:1px solid #e0e0e0;border-top:none;padding:20px;border-radius:0 0 8px 8px">
    {md_to_html(md_content)}
    </div>
    <p style="color:#999;font-size:11px;margin-top:12px">
        Generováno automaticky — Media Monitoring Agent v5
    </p>
    </body></html>
    """

    msg.attach(MIMEText(plain_text, "plain", "utf-8"))
    msg.attach(MIMEText(html_body,  "html",  "utf-8"))

    # Odeslání přes Gmail SMTP
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_USER, GMAIL_PASSWORD)
            server.sendmail(GMAIL_USER, EMAIL_TO, msg.as_string())
        return f"✉ Email odeslán na {EMAIL_TO}"
    except smtplib.SMTPAuthenticationError:
        return "✗ SMTP chyba: špatné přihlašovací údaje — zkontroluj GMAIL_APP_PASSWORD v .env"
    except Exception as e:
        return f"✗ SMTP chyba: {type(e).__name__}: {e}"

# ─── Tool implementace ───────────────────────────────────────────────────────

def search_rss(keyword: str, max_results: int = 15) -> str:
    keyword_lower = keyword.lower()
    all_articles  = []
    seen_set      = set(state["seen_urls"])
    feed_errors   = []

    for source in RSS_FEEDS:
        try:
            feed = feedparser.parse(source["url"])
            if feed.bozo:
                bozo_msg = str(getattr(feed, "bozo_exception", "neznámá chyba"))
                print(f"  ⚠ Feed '{source['name']}' má XML problém: {bozo_msg[:80]}")
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
            msg = f"Feed '{source['name']}' selhal: {type(e).__name__}: {e}"
            print(f"  ✗ {msg}")
            feed_errors.append(msg)

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
        output["feed_errors"] = feed_errors
    return json.dumps(output, ensure_ascii=False, indent=2)


def create_digest(topic: str, date_str: str, overview: str, articles: list) -> str:
    for art in articles:
        art.setdefault("title",      "Bez titulku")
        art.setdefault("source",     "Neznámý zdroj")
        art.setdefault("author",     "Redakce")
        art.setdefault("published",  "Datum neznámé")
        art.setdefault("url",        "")
        art.setdefault("summary_cs", "Shrnutí není k dispozici.")
        art.setdefault("relevance",  5)

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
            f"**URL:** [{art['title']}]({art['url']})",
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

    # Automaticky odešli email po uložení digestu
    email_result = send_email_digest(topic, filepath)
    print(f"  {email_result}")

    return (
        f"✓ Digest uložen: {filepath} | "
        f"{len(articles)} článků | "
        f"Průměrná relevance: {avg_relevance:.1f}/10 | "
        f"Top článek: '{articles_sorted[0]['title']}' ({articles_sorted[0].get('relevance','?')}/10) | "
        f"{email_result}"
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
    print(f"  A08 — Media Agent v5 | Téma: '{topic}' | {TODAY}")
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
    print("  A08 — Media Monitoring Agent v5")
    print("  Email delivery: HTML digest → Gmail SMTP")
    print("=" * 60)

    topic = input("\nZadej téma pro monitoring (Enter = 'AI'): ").strip() or "AI"
    run_agent(topic)


if __name__ == "__main__":
    main()
