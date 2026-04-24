"""
A05 — Scheduled Runner / Plánovaný spouštěč
============================================
Non-interaktivní wrapper kolem media_agent_v3.
Určen pro automatické spouštění přes Windows Task Scheduler.

Non-interactive wrapper around media_agent_v3.
Designed for automatic execution via Windows Task Scheduler.

Spuštění ručně pro test / Run manually to test:
    python scheduled_runner.py

Automatické spuštění / Automatic execution:
    Přes run_agent.bat a Windows Task Scheduler (viz A05 studijní materiál)
"""

import os
import sys
from datetime import date, datetime

# ─── Konfigurace / Configuration ─────────────────────────────────────────────

# Témata ke sledování — uprav dle svých zájmů
# Topics to monitor — customize to your interests
TOPICS = [
    "AI",
    "cybersecurity",
]

# Složka pro logy — vytvoří se automaticky pokud neexistuje
CODE_DIR = os.path.dirname(os.path.abspath(__file__))
LOGS_DIR = os.path.join(CODE_DIR, "logs")
os.makedirs(LOGS_DIR, exist_ok=True)

# ─── Import agenta / Import agent ────────────────────────────────────────────
# Přidej složku s agentem do Python path a importuj run_agent funkci
sys.path.insert(0, CODE_DIR)

try:
    from media_agent_v3 import run_agent
except ImportError as e:
    print(f"CHYBA: Nelze importovat media_agent_v3: {e}")
    print("Ujisti se, že media_agent_v3.py je ve stejné složce.")
    sys.exit(1)

# ─── Logging helper ──────────────────────────────────────────────────────────

class TeeOutput:
    """
    Přesměruje výstup zároveň na obrazovku i do souboru.
    Redirects output to both screen and file simultaneously.
    """
    def __init__(self, file):
        self.file    = file
        self.console = sys.__stdout__

    def write(self, data):
        self.console.write(data)
        self.file.write(data)

    def flush(self):
        self.console.flush()
        self.file.flush()

# ─── Hlavní program / Main program ───────────────────────────────────────────

def main():
    today    = date.today().strftime("%Y-%m-%d")
    now      = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_path = os.path.join(LOGS_DIR, f"agent_log_{today}.txt")

    with open(log_path, "w", encoding="utf-8") as log_file:
        # Přesměruj výstup do souboru I na obrazovku
        sys.stdout = TeeOutput(log_file)

        print("=" * 60)
        print(f"  SCHEDULED RUN / PLÁNOVANÝ BĚH")
        print(f"  Čas spuštění: {now}")
        print(f"  Témata: {', '.join(TOPICS)}")
        print(f"  Log soubor: {log_path}")
        print("=" * 60)

        errors = []

        for topic in TOPICS:
            print(f"\n>>> Spouštím monitoring pro téma: '{topic}'")
            try:
                run_agent(topic)
            except Exception as e:
                # Chyba jednoho tématu neukončí zpracování ostatních
                # Error in one topic doesn't stop processing others
                msg = f"CHYBA při zpracování tématu '{topic}': {e}"
                print(f"\n⚠  {msg}")
                errors.append(msg)

        # Shrnutí běhu / Run summary
        print("\n" + "=" * 60)
        print(f"  SHRNUTÍ BĚHU / RUN SUMMARY")
        print(f"  Zpracovaná témata: {len(TOPICS)}")
        print(f"  Chyby: {len(errors)}")
        if errors:
            for err in errors:
                print(f"  ✗ {err}")
        else:
            print(f"  ✓ Vše proběhlo bez chyb.")
        print(f"  Log uložen: {log_path}")
        print("=" * 60)

        # Obnov původní stdout
        sys.stdout = sys.__stdout__

    print(f"\nScheduled run dokončen. Log: {log_path}")


if __name__ == "__main__":
    main()
