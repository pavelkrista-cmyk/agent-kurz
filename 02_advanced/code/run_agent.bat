@echo off
REM ============================================================
REM  run_agent.bat
REM  Spouštěcí soubor pro Windows Task Scheduler
REM  Launcher for Windows Task Scheduler
REM
REM  Nastavení / Setup:
REM  1. Otevři Task Scheduler (Win+S -> "Task Scheduler")
REM  2. Create Basic Task -> Daily -> 07:00
REM  3. Action: Start a program
REM  4. Program: cesta k tomuto .bat souboru
REM ============================================================

python "C:\Users\pavel\OneDrive\Dokumenty\Claude\Agenti\How to\Lektor - Agenti\02_advanced\code\scheduled_runner.py"
