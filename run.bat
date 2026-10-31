@echo off
title AI-Assisted Software Testing Agent
cd /d "%~dp0"

echo.
echo ========================================
echo  AI-Assisted Software Testing Agent v2
echo ========================================
echo.
echo Closing any previous stuck Streamlit instances...
taskkill /f /fi "WINDOWTITLE eq streamlit*" 2>nul
echo Starting application fresh...
echo App will open at http://localhost:8501
echo.

"C:\Users\aksha\AppData\Local\Programs\Python\Python312\python.exe" -m streamlit run main.py

pause
