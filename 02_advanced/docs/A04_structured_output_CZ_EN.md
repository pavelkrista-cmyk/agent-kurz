# Structured Output / Structured Output
> Krok / Step: A04 | Modul / Module: Advanced | Datum / Date: 2026-04-24

---

## Problém s volným textem / The Problem with Free Text

V A02 a A03 Claude píše Markdown digest jako volný text. Funguje to — ale má to slabiny:

- Formát se může lišit běh od běhu (Claude je kreativní)
- Nemůžeš snadno extrahovat data strojově (počet článků, autory, zdroje)
- Přidání nového pole (např. skóre relevance) vyžaduje přepsání systémového promptu
  a doufání, že Claude ho správně zformátuje

Structured output řeší všechny tři problémy najednou.

*In A02/A03 Claude writes a free-text Markdown digest. It works, but the format can vary
between runs, data extraction is hard, and adding new fields requires prompt rewriting.
Structured output solves all three problems at once.*

---

## Co je structured output / What is Structured Output

Místo aby Claude psal volný text, **vyplní předdefinovanou JSON strukturu**.
Ty mu dáš schéma (co pole existují, jakého jsou typu), on je vyplní daty.

```
Bez structured output:                 Se structured output:
─────────────────────────────          ─────────────────────────────
Claude píše:                           Claude vyplní:
"# Mediální monitoring: AI             {
_Datum: 2026-04-24_                      "topic": "AI",
                                         "date": "2026-04-24",
## Přehled                               "overview": "AI dominuje...",
AI dominuje zpravodajství...             "articles": [
                                           {
### OpenAI GPT-5.5                           "title": "OpenAI GPT-5.5",
**Zdroj:** TechCrunch...                     "source": "TechCrunch",
..."                                         "author": "Lucas Ropek",
                                             "relevance": 9,
                                             "summary_cs": "..."
                                           }
                                         ]
                                       }
                                       
                                       Python převede JSON → Markdown
```

---

## Jak to implementujeme / How We Implement It

Přidáme třetí nástroj: `create_digest`. Claude ho zavolá místo `save_to_file` —
"vyplní" strukturu jako by volal funkci s pojmenovanými parametry.

```python
{
    "name": "create_digest",
    "description": "Vytvoří strukturovaný digest ze zpracovaných článků. ...",
    "input_schema": {
        "type": "object",
        "properties": {
            "topic":    {"type": "string"},
            "date":     {"type": "string"},
            "overview": {"type": "string", "description": "2-3 věty o celkovém obrazu"},
            "articles": {
                "type": "array",
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
        "required": ["topic", "date", "overview", "articles"]
    }
}
```

Claude musí vyplnit všechna `required` pole — jinak API vrátí chybu.
Tím garantujeme, že digest bude vždy mít přehled, každý článek bude mít URL a shrnutí.

*Claude must fill all `required` fields — otherwise the API returns an error.
This guarantees the digest always has an overview and every article has a URL and summary.*

---

## Python: z JSON struktury do Markdownu / Python: from JSON Structure to Markdown

Když Claude zavolá `create_digest`, dostaneme čistý Python dict.
Python funkce ho převede na Markdown a uloží:

```python
def create_digest(topic: str, date: str, overview: str, articles: list) -> str:
    """Převede strukturovaná data na Markdown digest a uloží do souboru."""

    # Seřaď články podle relevance (nejdůležitější první)
    articles_sorted = sorted(articles, key=lambda a: a.get("relevance", 0), reverse=True)

    lines = [
        f"# Mediální monitoring: {topic}",
        f"_Datum: {date}_",
        "",
        "## Přehled",
        overview,
        "",
        "## Články",
        "",
    ]

    for art in articles_sorted:
        relevance = art.get("relevance", "?")
        lines += [
            f"### {art['title']}",
            f"**Zdroj:** {art['source']} | "
            f"**Autor:** {art.get('author', 'Neznámý')} | "
            f"**Datum:** {art.get('published', '?')} | "
            f"**Relevance:** {relevance}/10",
            f"**URL:** {art['url']}",
            "",
            art['summary_cs'],
            "",
            "---",
            "",
        ]

    content = "\n".join(lines)
    filename = f"digest_{date}.md"
    filepath = os.path.join(OUTPUT_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    # Ulož URL do state
    urls = [a["url"] for a in articles]
    save_state(state, urls)

    return f"✓ Digest uložen: {filepath} ({len(articles)} článků, seřazeno dle relevance)"
```

---

## Co se změnilo v agentic loop / What Changed in the Agentic Loop

Sekvence volání je teď:

```
1. search_rss("AI")          ← načte a filtruje RSS (stejné jako A03)
2. create_digest(            ← strukturovaná data místo volného textu
     topic="AI",
     date="2026-04-24",
     overview="...",
     articles=[{...}, {...}]
   )
3. end_turn → krátká zpráva
```

`save_to_file` už nepotřebujeme — `create_digest` ukládá sám.

---

## Klíčová výhoda: pole `relevance` / Key Benefit: the `relevance` Field

Přidali jsme pole `relevance` (celé číslo 1–10) do schématu.
Claude ho vyplní — nemusíme ho žádat v systémovém promptu.

Díky tomu můžeme v Pythonu:

```python
# Seřadit podle relevance
articles_sorted = sorted(articles, key=lambda a: a["relevance"], reverse=True)

# Filtrovat jen vysoce relevantní
top_articles = [a for a in articles if a["relevance"] >= 7]

# Spočítat průměr
avg = sum(a["relevance"] for a in articles) / len(articles)
```

Žádný z těchto výpočtů by nebyl možný, kdyby Claude psal volný Markdown text.

*None of these calculations would be possible if Claude wrote free Markdown text.*

---

## Kdy použít structured output / When to Use Structured Output

| Situace | Doporučení |
|---|---|
| Jednorázový výstup pro čtení | Volný text stačí |
| Výstup se opakuje (denní digest) | Structured output |
| Výstup vstupuje do dalšího systému | Structured output vždy |
| Chceš strojově zpracovat pole | Structured output vždy |
| Jednoduchý chatbot | Volný text stačí |

---

## Mini-úkol / Mini Task

1. Spusť `python media_agent_v3.py` — zadej téma `AI`
2. Otevři vygenerovaný digest — jsou články seřazeny podle relevance?
3. Otevři `agent_state.json` — přibyly nové URL?

> **Otázka: Jaké relevance skóre dal Claude nejdůležitějšímu článku?
> Souhlasíš s jeho hodnocením?**

---

*Další krok / Next step: A05 — Scheduling — automatické spouštění agenta každý den*
