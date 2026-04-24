# Multi-tool Agent / Multi-tool Agent
> Krok / Step: A02 | Modul / Module: Advanced | Datum / Date: 2026-04-24

---

## Co je multi-tool agent / What is a Multi-tool Agent

V B01 a B02 měl agent jeden nástroj — `search_web`. Rozhodování bylo jednoduché:
buď zavolat ten jeden nástroj, nebo odpovědět přímo.

Multi-tool agent má **více nástrojů** a Claude sám rozhoduje:
- **Který nástroj zavolat** (a ve kterém pořadí)
- **S jakými parametry**
- **Jestli zavolat více nástrojů za sebou**
- **Kdy přestat volat nástroje a napsat finální odpověď**

Toto rozhodování se děje uvnitř LLM inference — Claude čte popis každého nástroje
a na základě systémového promptu a kontextu konverzace vybírá nejlepší akci.

*In B01/B02 the agent had one tool — `search_web`. With a multi-tool agent, Claude
decides which tool to call, in what order, with what parameters, and when to stop
calling tools and write the final answer — all based on tool descriptions and context.*

---

## Architektura A02 agenta / A02 Agent Architecture

Náš media monitoring agent má **dva nástroje**:

```
┌─────────────────────────────────────────────────────────┐
│              MEDIA MONITORING AGENT                     │
│                                                         │
│  System prompt:                                         │
│  "Jsi novinářský monitor. Načti RSS články,            │
│   analyzuj je a ulož digest do souboru."               │
│                                                         │
│  Tool 1: search_rss(keyword, max_results)              │
│    → stáhne RSS feedy, filtruje, vrátí JSON            │
│                                                         │
│  Tool 2: save_to_file(content, filename)               │
│    → uloží text do souboru na disku                    │
│                                                         │
│  Typická sekvence volání:                               │
│    1. search_rss("AI", 10)                             │
│    2. [Claude analyzuje výsledky a sestaví digest]     │
│    3. save_to_file(digest, "digest_2026-04-24.md")     │
│    4. end_turn → "Digest uložen."                      │
└─────────────────────────────────────────────────────────┘
```

Klíčový bod: **nikdo Claudovi neřekl "zavolej nejdřív search_rss, pak save_to_file"**.
Claude to vyvodil sám z popisu nástrojů a systémového promptu.

*Key point: nobody told Claude "first call search_rss, then save_to_file". Claude
inferred this from the tool descriptions and system prompt.*

---

## Nový tool: save_to_file / New Tool: save_to_file

V A01 jsme uměli číst RSS. Teď přidáme druhý nástroj — uložení výstupu do souboru.

```python
def save_to_file(content: str, filename: str) -> str:
    """
    Uloží obsah do souboru. Vrátí potvrzení nebo chybovou zprávu.
    Saves content to a file. Returns confirmation or error message.
    """
    try:
        filepath = os.path.join(OUTPUT_DIR, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        return f"✓ Soubor uložen: {filepath}"
    except Exception as e:
        return f"✗ Chyba při ukládání: {e}"
```

A jeho definice pro Claudea (co Claude vidí):

```python
{
    "name": "save_to_file",
    "description": (
        "Uloží textový obsah do souboru na disku. "
        "Použij pro uložení finálního digestu. "
        "Filename musí mít formát: digest_YYYY-MM-DD.md"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "content":  {"type": "string", "description": "Obsah souboru (Markdown text)"},
            "filename": {"type": "string", "description": "Název souboru, např. digest_2026-04-24.md"}
        },
        "required": ["content", "filename"]
    }
}
```

---

## Systémový prompt pro media agenta / System Prompt for Media Agent

Systémový prompt je instruktáž agenta. Musí být konkrétní — říct Claudovi:
- **Co má udělat** (načíst, analyzovat, uložit)
- **Jaký formát výstupu** očekáváme
- **Jaké nástroje má k dispozici a k čemu**

```python
SYSTEM_PROMPT = """Jsi mediální monitoring agent specializovaný na technologické zprávy.

Když dostaneš téma:
1. Zavolej search_rss s tímto tématem jako keyword
2. Z vrácených článků vyber 3–5 nejrelevantnějších
3. Pro každý vybraný článek napiš 2–3 větové shrnutí v češtině
4. Sestav Markdown digest v tomto formátu:

# Mediální monitoring: {téma}
_Datum: {dnešní datum}_

## Přehled / Summary
[1–2 věty o celkovém obrazu tématu]

## Články / Articles

### [Titulek článku]
**Zdroj:** [název zdroje] | **Autor:** [autor] | **Datum:** [datum]
**URL:** [odkaz]

[2–3 věté shrnutí]

---

5. Ulož digest pomocí save_to_file s názvem digest_YYYY-MM-DD.md
6. Odpověz uživateli krátkou zprávou, co jsi našel a kde je digest uložen.

Piš shrnutí česky. Technické termíny ponechej v angličtině."""
```

---

## Proč je popis nástroje tak důležitý / Why Tool Description Matters

Podívej se na popis `search_rss`:

```
"Vyhledá aktuální články v RSS feedech dle klíčového slova.
 Vrátí seznam článků jako JSON: title, link, author, published, summary, source.
 Použij jako první krok při každém monitoringu."
```

Poslední věta `"Použij jako první krok"` je instrukce přímo v popisu nástroje.
Claude ji čte a respektuje — voláme nástroj správně, bez explicitního příkazu v chatu.

*The last sentence "Use as first step" is an instruction embedded in the tool description.
Claude reads it and follows it — the tool gets called correctly without an explicit command.*

---

## Celý kód / Full Code

Viz soubor `02_advanced/code/media_agent.py` — komentáře vysvětlují každý krok.

Klíčové části, které jsou nové oproti B02:

**1. Registrace dvou nástrojů místo jednoho:**
```python
tools = [search_rss_tool, save_to_file_tool]  # seznam, ne jeden tool
```

**2. Dispatch více nástrojů:**
```python
elif response.stop_reason == "tool_use":
    tool_results = []
    for block in response.content:
        if block.type == "tool_use":
            if block.name == "search_rss":
                result = search_rss(**block.input)
            elif block.name == "save_to_file":
                result = save_to_file(**block.input)
            else:
                result = f"Neznámý tool: {block.name}"
            tool_results.append({
                "type": "tool_use_id": block.id,
                "content": result
            })
```

**3. Výsledek:** soubor `digest_2026-04-24.md` v aktuální složce.

---

## Co Claude udělá uvnitř / What Claude Does Internally

Tady je co se děje krok za krokem — pro debugování je užitečné to vědět:

```
Inference #1:
  Claude dostane: user zprávu "Sleduj téma: AI"
  Claude přemýšlí: "Potřebuji data → zavolám search_rss"
  stop_reason: tool_use → search_rss("AI", 10)

Inference #2:
  Claude dostane: výsledky search_rss (JSON s 10 články)
  Claude přemýšlí: "Mám data, vyberu 3–5 nejlepších, napíšu shrnutí,
                    pak musím uložit → zavolám save_to_file"
  stop_reason: tool_use → save_to_file(digest_text, "digest_2026-04-24.md")

Inference #3:
  Claude dostane: "✓ Soubor uložen: digest_2026-04-24.md"
  Claude přemýšlí: "Hotovo, mohu odpovědět uživateli"
  stop_reason: end_turn → finální zpráva
```

Celkem **3 inference** = 3 volání Claude API. Každé stojí tokeny.

*Total 3 inferences = 3 Claude API calls. Each costs tokens.*

---

## Náklady na API / API Cost

| Krok | Tokeny (odhad) | Náklady (haiku) |
|---|---|---|
| Inference #1 (rozhodnutí) | ~500 input | ~$0.0003 |
| Inference #2 (analýza + digest) | ~2 000 input + ~800 output | ~$0.002 |
| Inference #3 (potvrzení) | ~200 input | ~$0.0001 |
| **Celkem / Total** | **~3 500 tokenů** | **~$0.003** |

Jeden běh agenta = přibližně **$0.003** = **0,07 Kč**. Za měsíc denních spuštění = ~$0.09.

*One agent run ≈ $0.003. Daily runs for a month ≈ $0.09.*

---

## Mini-úkol / Mini Task

1. Spusť `media_agent.py`
2. Zadej téma: `AI`
3. Najdi vygenerovaný soubor `digest_*.md` ve složce `02_advanced/code/`
4. Otevři ho v VS Code — vypadá digest jak jsi čekal?

> **Otázka: Kolik inferencí proběhlo? Podívej se na výpis v terminálu —
> kolikrát se Claude vrátil s `tool_use`?**

---

*Další krok / Next step: A03 — Agent memory / state — agent si pamatuje, co už zpracoval*
