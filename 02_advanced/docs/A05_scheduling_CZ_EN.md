# Scheduling / Scheduling
> Krok / Step: A05 | Modul / Module: Advanced | Datum / Date: 2026-04-24

---

## Co je scheduling a proč ho potřebujeme / What is Scheduling and Why We Need It

Dosud jsme agenta spouštěli ručně — otevřeli PowerShell, napsali `python media_agent_v3.py`,
zadali téma. To funguje pro testování, ale mediální monitoring má smysl jen pokud běží
**každý den automaticky** — ideálně ráno, než si sedneš ke kafé.

Scheduling = plánované automatické spouštění skriptu bez zásahu člověka.

Na Windows k tomu slouží **Task Scheduler** (Plánovač úloh) — vestavěný nástroj,
který umí spustit libovolný program v nastavený čas.

*Scheduling = running a script automatically at a set time without human intervention.
On Windows, Task Scheduler is the built-in tool for this.*

---

## Dva problémy k vyřešení / Two Problems to Solve

Než nastavíme Task Scheduler, musíme vyřešit dva problémy:

**Problém 1: `input()` čeká na klávesnici**
`media_agent_v3.py` obsahuje `input("Zadej téma...")` — při automatickém spuštění
nikdo klávesnici neobsluhuje, skript by čekal věčně.

**Problém 2: Kde se výstup zobrazí?**
Bez otevřeného terminálu nevidíme co agent dělá. Potřebujeme výstup zapsat do log souboru.

Řešení: vytvoříme nový soubor `scheduled_runner.py` — obal kolem agenta,
který tyto dva problémy řeší.

---

## scheduled_runner.py — non-interaktivní wrapper

Tento skript:
- Volá agenta přímo (bez `input()`) s přednastavenými tématy
- Přesměruje výstup do log souboru s datem
- Zachytí chyby — pokud agent selže, zapíše chybu do logu a skončí čistě

```python
# Témata pro monitoring — uprav dle svých zájmů
TOPICS = ["AI", "cybersecurity", "Python"]

# Spustí agenta pro každé téma
for topic in TOPICS:
    run_agent(topic)   # volá funkci z media_agent_v3
```

Logování funguje přesměrováním `sys.stdout` do souboru:

```python
log_path = os.path.join(LOGS_DIR, f"agent_log_{date.today()}.txt")
with open(log_path, "w", encoding="utf-8") as log_file:
    sys.stdout = log_file
    run_agent("AI")
    sys.stdout = sys.__stdout__  # obnov původní výstup
```

Po každém spuštění najdeš soubor `logs/agent_log_2026-04-24.txt` s celým výpisem.

---

## run_agent.bat — spouštěcí soubor pro Task Scheduler

Task Scheduler potřebuje spustit `.bat` soubor (Windows dávkový příkaz),
ne přímo Python. `.bat` soubor zajistí správnou cestu k Pythonu a ke skriptu.

```bat
@echo off
REM Spustí scheduled_runner.py s absolutními cestami
python "C:\Users\pavel\OneDrive\Dokumenty\Claude\Agenti\How to\Lektor - Agenti\02_advanced\code\scheduled_runner.py"
```

`@echo off` = nevypisuj příkazy, jen výsledky (čistší log).

---

## Nastavení Windows Task Scheduler / Setting Up Windows Task Scheduler

Postup krok za krokem:

**1.** Stiskni `Win + S`, napiš `Task Scheduler`, otevři.

**2.** V pravém panelu klikni na **Create Basic Task...**

**3.** Vyplň:
- Name: `Media Monitoring Agent`
- Description: `Denní spuštění AI monitoringu`
- Klikni Next

**4.** Trigger (kdy spustit):
- Vyber **Daily**
- Klikni Next
- Nastav čas: `07:00:00` (nebo kdy chceš)
- Klikni Next

**5.** Action (co spustit):
- Vyber **Start a program**
- Klikni Next
- Program/script: vlož celou cestu k `.bat` souboru:
  ```
  C:\Users\pavel\OneDrive\Dokumenty\Claude\Agenti\How to\Lektor - Agenti\02_advanced\code\run_agent.bat
  ```
- Klikni Next

**6.** Zkontroluj nastavení, klikni **Finish**.

**7.** Ověření — klikni pravým tlačítkem na nově vytvořenou úlohu → **Run**.
   Zkontroluj log soubor v `02_advanced/code/logs/`.

---

## Struktura souborů po A05 / File Structure After A05

```
02_advanced/code/
├── media_agent_v3.py       ← hlavní agent (nezměněno)
├── scheduled_runner.py     ← nový: spouští agenta bez input()
├── run_agent.bat           ← nový: spouštěcí soubor pro Task Scheduler
├── agent_state.json        ← stav agenta (seen_urls)
├── digest_2026-04-24.md    ← vygenerovaný digest
└── logs/
    └── agent_log_2026-04-24.txt  ← výpis každého běhu
```

---

## Co se stane každý den / What Happens Every Day

```
07:00 — Task Scheduler spustí run_agent.bat
          ↓
        run_agent.bat spustí scheduled_runner.py
          ↓
        scheduled_runner.py otevře log soubor
          ↓
        Pro každé téma v TOPICS:
          search_rss → filtruje seen_urls → nové články
          create_digest → uloží digest_YYYY-MM-DD.md
          save_state → aktualizuje agent_state.json
          ↓
        Log soubor uložen: logs/agent_log_2026-04-24.txt
07:02 — Hotovo. Digest čeká ve složce.
```

Celý proces trvá přibližně 1–2 minuty, počítač to zvládne na pozadí.

---

## Mini-úkol / Mini Task

1. Spusť `scheduled_runner.py` ručně — ověř že funguje bez `input()`
2. Otevři `logs/agent_log_*.txt` — vidíš celý výpis agenta?
3. Nastav Task Scheduler na čas, kdy jsi u počítače — otestuj automatické spuštění

> **Otázka: Co se stane, když počítač v 07:00 spí?**
> *(Tip: v Task Scheduler nastavení hledej "Run task as soon as possible after
> a scheduled start is missed")*

---

## Náklady / API Cost

Jedno automatické spuštění pro 3 témata = 3× ~$0.003 = **~$0.009 denně**.
Za měsíc = ~$0.27. Za rok = ~$3.30 — v limitu kurzu $5 i s vývojem.

*One scheduled run for 3 topics = ~$0.009/day. Monthly = ~$0.27. Well within budget.*

---

*Další krok / Next step: A06 — Error handling — co když zdroj není dostupný*
