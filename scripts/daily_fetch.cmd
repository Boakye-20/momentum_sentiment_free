@echo off
rem Wrapper for Windows Task Scheduler — see scripts/daily_fetch.py.
cd /d "C:\Users\PKwarts\Documents\momentum_sentiment_free"
"C:\Users\PKwarts\AppData\Local\Programs\Python\Python313\python.exe" scripts\daily_fetch.py >> outputs\daily_fetch.log 2>&1
