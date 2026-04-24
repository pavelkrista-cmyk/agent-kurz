# Stav projektu / Project Progress
> Poslední aktualizace / Last updated: 2026-04-24 (A07 done — Advanced modul kompletní)

---

## Jak číst tento soubor / How to read this file

- `[ ]` pending — krok ještě nezačal
- `[~]` in progress — krok probíhá
- `[x]` done — krok dokončen a otestován

---

## Modul 1 — BASIC: Denní přehled zpráv / Daily News Briefing

### Setup / Environment
- [x] B00-1 Nainstalovat Git lokálně a propojit s GitHub účtem
- [x] B00-2 Vytvořit GitHub repozitář `agent-kurz`
- [x] B00-3 Zaregistrovat Tavily API (free tier), uložit klíč do `.env`
- [x] B00-4 Zaregistrovat Anthropic API, uložit klíč do `.env`, nastavit spending limit $5
- [x] B00-5 Nainstalovat závislosti: `pip install anthropic python-dotenv`

### Teorie / Theory
- [x] B01 Agentic loop — co se děje uvnitř agenta (studijní materiál)
- [x] B02 Tool use — jak agent volá nástroje (studijní materiál)

### Praxe / Practice
- [x] B03 Uložení výstupu do souboru s datem v názvu
- [x] B04 První Tool — Tavily search_web tool
- [x] B05 Propojit tool s agentem — základní agentic loop
- [x] B06 Strukturovaný výstup — Markdown digest se zdroji
- [x] B07 Git commit a push hotového agenta

### Acceptance check
- [x] B08 Agent projde všemi acceptance criteria (viz CLAUDE.md sekce 4)

---

## Modul 2 — ADVANCED: Monitoring médií / Media Monitoring Agent

- [x] A01 RSS parsing — číst a filtrovat RSS zdroje
- [x] A02 Multi-tool agent — více nástrojů v jednom agentu
- [x] A03 Agent memory / state — pamatovat si, co už bylo zpracováno
- [x] A04 Structured output — JSON schéma pro digest
- [x] A05 Scheduling — automatické spouštění (cron / Task Scheduler)
- [x] A06 Error handling — co když zdroj není dostupný
- [x] A07 Acceptance check

---

## Modul 3 — HOME-PROFI: Job Search Assistant

- [ ] P01 MCP setup — nastavení MCP serveru pro file access
- [ ] P02 PDF parsing — extrakce textu z CV a LinkedIn exportu
- [ ] P03 Job search tool — vyhledávání inzerátů
- [ ] P04 Matching engine — porovnání požadavků s profilem
- [ ] P05 Cover letter generator — structured output
- [ ] P06 CV diff — návrhy konkrétních úprav
- [ ] P07 Orchestrator pattern — agent řídí subagenty
- [ ] P08 Acceptance check

---

## Poznámky / Notes

<!-- Sem si piš poznámky, co funguje, co ne, na co nezapomenout -->

