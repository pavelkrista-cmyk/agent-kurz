# Error Handling / Error Handling
> Krok / Step: A06 | Modul / Module: Advanced | Datum / Date: 2026-04-24

---

## Co je error handling a proč ho potřebujeme / What is Error Handling and Why We Need It

Agent běžící automaticky ve 07:00 nesmí padnout jen proto, že jeden RSS feed vrátí
prázdnou odpověď nebo Anthropic API je momentálně přetížené. Uživatel nic nevidí —
skript buď tiše selže, nebo se zablokuje navždy.

Error handling = proaktivní ošetření očekávatelných selhání tak, aby agent:
- **pokračoval** tam, kde je to možné (skipne vadný feed, zkusí API znovu)
- **zaznamenal** co se stalo (log soubor pro diagnostiku)
- **nepadl celý** kvůli jedné drobné chybě

*Error handling = proactively dealing with expected failures so the agent continues where
possible, records what happened, and doesn't crash entirely due to one minor error.*

---

## Tři kategorie chyb / Three Categories of Errors

**1. RSS chyby** — zdroj nedostupný, vadný XML, prázdný feed
**2. API chyby** — Anthropic server přetížen (`overloaded_error`), výpadek sítě
**3. Datové chyby** — RSS článek bez autora, bez data, bez URL

Každou kategorii ošetříme jinak.

---

## RSS chyby — feed.bozo a per-feed try/except

feedparser má vestavěný indikátor problémů: `feed.bozo == True` znamená,
že XML byl malformovaný — ale feedparser **obvykle data načte i tak**.
Nestačí proto na `bozo` reagovat přeskočením; stačí varovat.

Druhá úroveň: každý feed obalíme vlastním `try/except`. Síťová chyba
(`ConnectionError`, DNS selhání) je zachycena, uložena do `feed_errors` a zpracování
pokračuje s dalšími feedy.

```python
for source in RSS_FEEDS:
    try:
        feed = feedparser.parse(source["url"])
        if feed.bozo:
            print(f"  ⚠ Feed '{source['name']}' má XML problém")
            # Nepřeskakujeme — data jsou obvykle k dispozici
        if not feed.entries:
            print(f"  ⚠ Feed '{source['name']}' vrátil prázdný seznam")
            continue
        # ... normální zpracování článků
    except Exception as e:
        print(f"  ✗ Feed '{source['name']}' selhal: {e}")
        # continue — zkusíme další feedy
```

*feedparser has a built-in problem indicator: `feed.bozo == True` means malformed XML —
but feedparser usually still parses data. Wrap each feed in its own try/except so a
network error on one feed doesn't stop the others.*

---

## API chyby — retry s exponential backoff

Anthropic API vrátí `overloaded_error` při dočasném přetížení serveru — nejedná se
o chybu v kódu. Správná reakce: počkej a zkus znovu.

**Exponential backoff** = každý pokus čeká déle než předchozí:
- Pokus 1 selže → čekej 10 sekund
- Pokus 2 selže → čekej 20 sekund
- Pokus 3 selže → vzdej to a vyhoď chybu

Proč exponenciálně? Pokud je server přetížený, příliš rychlé opakování ho zatíží víc.

```python
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
                print(f"  ⚠ API přetíženo — čekám {wait_seconds}s (pokus {attempt+1}/3)")
                time.sleep(wait_seconds)
                wait_seconds *= 2      # 10 → 20 → 40
            else:
                raise                  # jiná chyba — předej výše
```

*Exponential backoff: each retry waits longer than the previous one. Avoids hammering an
already-overloaded server.*

---

## Datové chyby — field defaults v create_digest

RSS standardy jsou laxní — článek může chybět autor, datum, nebo summary.
Místo aby kód vyhazoval `KeyError`, nastavíme výchozí hodnoty:

```python
for art in articles:
    art.setdefault("title",      "Bez titulku")
    art.setdefault("source",     "Neznámý zdroj")
    art.setdefault("author",     "Redakce")
    art.setdefault("published",  "Datum neznámé")
    art.setdefault("url",        "")
    art.setdefault("summary_cs", "Shrnutí není k dispozici.")
    art.setdefault("relevance",  5)
```

`dict.setdefault(key, value)` nastaví hodnotu pouze pokud klíč neexistuje —
existující hodnoty zůstanou beze změny.

*RSS standards are loose — articles can be missing author, date, or summary. Use
`dict.setdefault()` to fill in defaults without overwriting existing values.*

---

## Tool chyby — try/except v agentic loop

I samotný tool může selhat (chyba disku, neočekávaný formát dat...). Obalíme každé
volání toolu tak, aby chyba vrátila smysluplnou zprávu Claudovi místo pádu agenta:

```python
try:
    if block.name == "search_rss":
        result = search_rss(**block.input)
    elif block.name == "create_digest":
        result = create_digest(**block.input)
except Exception as e:
    result = json.dumps({"error": f"Tool {block.name} selhal: {type(e).__name__}: {e}"})
    print(f"  ✗ Tool chyba: {e}")
```

Claude dostane JSON s `"error"` polem a může zareagovat rozumně (informovat uživatele,
zkusit jinak) místo aby dostal prázdnou odpověď.

---

## Co se změnilo mezi v3 a v4 / What Changed Between v3 and v4

| Oblast | v3 | v4 |
|---|---|---|
| RSS parsing | Jeden try/except pro celý loop | Per-feed try/except + bozo check |
| API volání | `client.messages.create()` přímo | `call_api_with_retry()` — 3 pokusy |
| Chybějící pole | `KeyError` by způsobil pád | `setdefault()` — výchozí hodnoty |
| Tool chyby | Nekryté — agent by padl | Try/except vrátí chybu Claudovi |
| Fallback autor | "Neznámý autor" | "Redakce" — přesnější pro tisk |

---

## Struktura souborů po A06 / File Structure After A06

```
02_advanced/code/
├── rss_reader.py           ← A01: standalone RSS test
├── media_agent.py          ← A02: základní agent
├── media_agent_v2.py       ← A03: + state/memory
├── media_agent_v3.py       ← A04: + structured output
├── media_agent_v4.py       ← A06: + error handling  ← NOVÉ
├── scheduled_runner.py     ← A05: non-interactive runner
├── run_agent.bat           ← A05: Task Scheduler launcher
├── agent_state.json        ← stav agenta
└── logs/
    └── agent_log_*.txt
```

*V produkci bys `scheduled_runner.py` upravil, aby importoval `media_agent_v4`
místo `media_agent_v3`.*

---

## Mini-úkol / Mini Task

1. Spusť `python media_agent_v4.py` — ověř, že výstup je stejný jako u v3
2. Najdi v kódu funkci `call_api_with_retry` — kolik sekund čeká při druhém pokusu?
3. **Bonusová otázka:** Co se stane, pokud všechny tři RSS feedy selžou najednou?
   Vrátí agent chybu nebo tiché `new: 0`?

---

## Náklady / API Cost

Retry logika přidává náklady pouze při skutečném přetížení — za normálních podmínek
nula extra volání. V kurzu k tomu prakticky nedojde.

*Retry logic adds cost only during actual overload — zero extra calls under normal
conditions.*

---

*Další krok / Next step: A07 — Acceptance check — finální ověření celého Advanced modulu*
