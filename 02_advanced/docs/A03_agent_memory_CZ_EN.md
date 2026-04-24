# Agent Memory / State — Agent Memory / State
> Krok / Step: A03 | Modul / Module: Advanced | Datum / Date: 2026-04-24

---

## Problém bez paměti / The Problem Without Memory

Spusť `media_agent.py` dvakrát za sebou se stejným tématem. Co se stane?

Agent vygeneruje dvě téměř identická shrnutí — stejné články, stejný obsah.
Pro denní monitoring je to zbytečné: chceme vidět jen **nové** články, ne opakovat včerejší.

Agent bez paměti neví, co už zpracoval. Každý běh začíná od nuly.

*Run `media_agent.py` twice with the same topic. The agent generates two nearly identical
digests — same articles, same content. For daily monitoring we want only new articles.
An agent without memory starts from scratch every run.*

---

## Co je agent state / What is Agent State

**Agent state** je informace, která přetrvává mezi jednotlivými běhy agenta.

Klíčové rozlišení — state není v context window:

```
Context window (dočasný / temporary):
  ┌────────────────────────────────────┐
  │  system prompt                     │
  │  user: "Sleduj téma: AI"           │
  │  assistant: tool_use search_rss    │
  │  user: [výsledky RSS]              │
  │  assistant: tool_use save_to_file  │
  │  ...                               │
  └────────────────────────────────────┘
  Po skončení běhu → vše zapomenuto

Agent state (perzistentní / persistent):
  ┌────────────────────────────────────┐
  │  state.json na disku               │
  │  {"seen_urls": ["url1", "url2"]}   │
  └────────────────────────────────────┘
  Přetrvává mezi běhy → základ paměti
```

Ukládáme state do souboru na disku, ne do Claude. Proč?
- Context window má limit tokenů — tisíce URL by ho zahlcovaly
- Claude API je placené — posílat stovky URL při každém volání zbytečně prodražuje
- Soubor je čitelný, verzovatelný, opravitelný

*Agent state is information that persists between agent runs. We store state in a file
on disk, NOT in the Claude context window — because the context window is limited,
expensive, and temporary.*

---

## Náš state: seznam viděných URL / Our State: List of Seen URLs

Nejjednodušší a nejrobustnější přístup: pamatujeme si URL každého zpracovaného článku.

```json
{
  "seen_urls": [
    "https://techcrunch.com/2026/04/23/openai-gpt-5-5/",
    "https://www.lupa.cz/aktuality/nvidia-rubin/",
    "https://techcrunch.com/2026/04/23/era-computer/"
  ],
  "last_run": "2026-04-24 08:00",
  "total_processed": 3
}
```

Proč URL a ne titulek? URL je jednoznačný identifikátor — titulek se může změnit
(editace po publikaci), URL zůstává stejné.

*Why URL and not title? URL is a unique identifier — titles can be edited after
publication, URLs stay the same.*

---

## Tři nové funkce / Three New Functions

```python
STATE_FILE = os.path.join(OUTPUT_DIR, "agent_state.json")

def load_state() -> dict:
    """Načte state ze souboru. Pokud neexistuje, vrátí prázdný state."""
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"seen_urls": [], "last_run": None, "total_processed": 0}


def save_state(state: dict):
    """Uloží aktuální state do souboru."""
    state["last_run"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def filter_new_articles(articles: list, seen_urls: set) -> list:
    """Vrátí jen články, jejichž URL jsme ještě neviděli."""
    return [a for a in articles if a.get("link", "") not in seen_urls]
```

---

## Jak state vstupuje do agentic loop / How State Enters the Agentic Loop

State není součástí Claude API volání. Je to Python logika kolem agenta:

```
┌─────────────────────────────────────────────────────────────┐
│  SPUŠTĚNÍ AGENTA / AGENT START                              │
│                                                             │
│  1. load_state()          ← načti seen_urls ze souboru      │
│  2. search_rss(keyword)   ← stáhni nové články              │
│  3. filter_new_articles() ← vyřaď již viděné                │
│  4. Claude analyzuje      ← jen nové články do context      │
│  5. save_to_file()        ← ulož digest                     │
│  6. save_state()          ← přidej nové URL do state        │
│                                                             │
│  Příští běh: state.seen_urls je o 5 URL delší               │
└─────────────────────────────────────────────────────────────┘
```

Klíčový moment: **filtrování probíhá v Pythonu, ne v Claude**.
Claude dostane do context window jen nové články — nikdy nevidí celý seznam seen_urls.

*The filtering happens in Python, not in Claude. Claude only receives new articles
in its context window — it never sees the full list of seen URLs.*

---

## Modifikovaný search_rss s filtrováním / Modified search_rss with Filtering

Oproti A02 přibyl jeden parametr `seen_urls` a filtrování:

```python
def search_rss(keyword: str, max_results: int = 10) -> str:
    """Stáhne RSS, filtruje dle keyword A dle seen_urls."""
    # ... (stejné stahování jako v A02) ...

    # NOVÉ: filtruj již viděné články
    new_articles = filter_new_articles(all_articles, state["seen_urls"])

    if not new_articles:
        return json.dumps({
            "message": f"Žádné nové články pro '{keyword}'. Vše již bylo zpracováno.",
            "total_found": len(all_articles),
            "new": 0
        }, ensure_ascii=False)

    results = new_articles[:max_results]
    return json.dumps({
        "keyword":     keyword,
        "total_found": len(all_articles),
        "new":         len(new_articles),
        "returned":    len(results),
        "articles":    results
    }, ensure_ascii=False, indent=2)
```

Všimni si: JSON vrácený Claudovi teď obsahuje i pole `new` — Claude vidí,
kolik článků je skutečně nových, a může to zmínit v digestu.

---

## State roste v čase / State Grows Over Time

Po prvním běhu:
```json
{"seen_urls": ["url_A", "url_B", "url_C"], "total_processed": 3}
```

Po druhém běhu (druhý den):
```json
{"seen_urls": ["url_A", "url_B", "url_C", "url_D", "url_E"], "total_processed": 5}
```

Po týdnu: `seen_urls` může mít 30–50 URL. To je v pořádku — JSON soubor s 50 URL
má velikost asi 5 KB. Pokud chceš, můžeš přidat čištění: mazat URL starší než 30 dní.
To přidáme v A06 jako součást error handling.

---

## Celý kód / Full Code

Viz soubor `02_advanced/code/media_agent_v2.py`.

Co je nové oproti `media_agent.py` (A02):
- `load_state()` a `save_state()` — perzistentní paměť
- `filter_new_articles()` — deduplication
- `state` je globální proměnná přístupná z `search_rss`
- Po každém úspěšném běhu se URL nových článků přidají do state
- Výpis ukazuje kolik článků bylo nových vs. celkem

---

## Mini-úkol / Mini Task

1. Spusť `media_agent_v2.py` — první běh zpracuje všechny nové články
2. Spusť ho znovu ihned — co se stane? Kolik nových článků najde?
3. Najdi soubor `agent_state.json` — otevři ho a podívej se na `seen_urls`

> **Otázka: Co Claude odpověděl ve druhém běhu, když nenašel žádné nové články?**

---

## Náklady s pamětí / Cost with Memory

Druhý a každý další běh (bez nových článků): Claude dostane zprávu
`"Žádné nové články"` a odpoví přímo bez dalšího tool volání.

| Scénář | Inference | Náklady |
|---|---|---|
| 1. běh — 5 nových článků | 3 inference | ~$0.003 |
| 2. běh — 0 nových článků | 1 inference | ~$0.0001 |
| 2. běh — 2 nové články | 3 inference | ~$0.002 |

Paměť šetří API náklady — zbytečně nezpracováváme stejný obsah.

*Memory saves API costs — we don't reprocess the same content unnecessarily.*

---

*Další krok / Next step: A04 — Structured output — JSON schéma pro konzistentní formát digestu*
