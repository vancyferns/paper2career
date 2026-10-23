@echo off
rem Paper2Career daily local ingestion runner
setlocal enabledelayedexpansion
cd /d "%~dp0\.."

if not exist ".venv\Scripts\python.exe" (
    echo Virtual environment not found in .venv.
    exit /b 1
)

echo Starting Paper2Career daily ingestion (auto-publish mode)...
.venv\Scripts\python.exe -m paper2career --local run --auto-publish --trigger "scheduled_local"
if errorlevel 1 (
    echo Ingestion failed.
    exit /b 1
)

echo Exporting latest data to frontend...
.venv\Scripts\python.exe -m paper2career --local export-demo

echo Daily ingestion finished.
