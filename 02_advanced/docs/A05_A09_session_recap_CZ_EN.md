# Session Recap — Kurz AI agentů
> 24. dubna 2026 · Modul 2: ADVANCED · Pavel Krista

---

## Přehled kroků / Steps Overview

| Krok | Téma | Stav |
|------|------|------|
| A05 | Scheduling — Task Scheduler | ✓ |
| A06 | Error handling — retry, fallback | ✓ |
| A07 | Acceptance check | ✓ |
| A08 | Email delivery — Gmail SMTP | ✓ |
| A09 | RSS feed — GitHub Pages | ✓ |

---

## A05 — Scheduling

- `scheduled_runner.py` — non-interaktivní obal kolem agenta (bez `input()`)
- `TeeOutput` — přesměruje výstup zároveň na obrazovku i do log souboru
- `run_agent.bat` — spouštěcí soubor pro Windows Task Scheduler
- Task Scheduler nastaven: každý den automatické spuštění
- `logs/agent_log_YYYY-MM-DD.txt` vzniká při každém běhu

---

## A06 — Error Handling

- **feed.bozo** — feedparser signalizuje vadný XML, ale data jsou obvykle k dispozici
- **Per-feed try/except** — chyba jednoho feedu nezastaví ostatní
- **Exponential backoff** — retry API volání: 10s → 20s → 40s
- **`dict.setdefault()`** — výchozí hodnoty pro chybějící pole (autor, datum, summary)
- **Tool error wrapper** — chyba toolu vrátí JSON error Claudovi místo pádu agenta

---

## A07 — Acceptance Check

Všechna 4 kritéria splněna:

- ✓ Agent proběhne automaticky (Task Scheduler + log soubor)
- ✓ Digest obsahuje název, autora, zdroj, shrnutí
- ✓ Soubor s datem v názvu (`digest_2026-04-24.md`)
- ✓ Agent nevyhodí chybu při nedostupném zdroji

---

## A08 — Email Delivery

- Gmail SMTP přes `smtplib` (součást Python stdlib — žádný pip)
- **App Password** ≠ tvoje Gmail heslo — speciální 16místný klíč pro aplikace
- `md_to_html()` — jednoduchý převodník Markdown → HTML pro email klienty
- Email obsahuje: nadpis, přehled, články s relevance bary, klikací URL
- Konfigurace v `.env`: `GMAIL_USER`, `GMAIL_APP_PASSWORD`, `EMAIL_TO`

---

## A09 — RSS Feed

- `create_rss_feed()` — generuje `feed.xml` ve standardu RSS 2.0
- Nové položky se přidávají na začátek, uchovává se max. 50 položek
- `xml.etree.ElementTree` — součást Python stdlib, žádný pip
- **GitHub Pages** — free hosting statických souborů z veřejného repozitáře
- Feed URL: `https://pavelkrista-cmyk.github.io/agent-kurz/02_advanced/code/feed.xml`

---

## Evoluce agenta / Agent Evolution

```
media_agent.py      ← A02: základní agentic loop
media_agent_v2.py   ← A03: + state/memory (seen_urls)
media_agent_v3.py   ← A04: + structured output (JSON schema, relevance)
media_agent_v4.py   ← A06: + error handling (retry, fallback)
media_agent_v5.py   ← A08: + email delivery (Gmail SMTP)
media_agent_v6.py   ← A09: + RSS feed (feed.xml → GitHub Pages)
```

Každý běh v6 produkuje tři výstupy:
```
digest_YYYY-MM-DD.md  →  soubor na disku
HTML email            →  Gmail inbox
feed.xml              →  GitHub Pages (RSS čtečky, budoucí web)
```

---

## 5 klíčových lekcí / 5 Key Lessons

**1. Non-interactive wrapper je nutnost.**
Agent spouštěný automaticky nesmí čekat na `input()`. Vždy připrav standalone runner.

**2. Exponential backoff, ne opakování v loop.**
Při API přetížení: počkej, zdvojnásob interval, zkus znovu. Rychlé opakování situaci zhorší.

**3. feed.bozo neznamená prázdná data.**
feedparser načte obsah i z vadného XML. Stačí varovat, nepřeskakovat celý feed.

**4. App Password ≠ Gmail heslo.**
Google pro aplikace vyžaduje speciální klíč. `.env` soubor nikdy na GitHub.

**5. RSS 2.0 je jen XML.**
Python stdlib (`xml.etree`) stačí. GitHub Pages = free hosting bez serveru.

---

## Co nás čeká / What's Next

**P01 — Home-profi: Job Search Assistant**
- MCP server pro přístup k souborům
- PDF parsing — čtení CV a LinkedIn exportu
- Job search tool — vyhledávání inzerátů
- Matching engine — porovnání s profilem
- Cover letter generator

---

*agent-kurz · github.com/pavelkrista-cmyk/agent-kurz · PROGRESS.md aktuální*
