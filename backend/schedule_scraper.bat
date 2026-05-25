@echo off
:: MomentumQuest — Weekly Job Scraper
:: Import this file into Windows Task Scheduler for automated weekly runs.
::
:: Task Scheduler setup:
::   Action  : Start a program
::   Program : D:\momentumQuest\backend\schedule_scraper.bat
::   Trigger : Weekly, choose day + time (e.g. Monday 02:00 AM)
::   Start in: D:\momentumQuest\backend

cd /d D:\momentumQuest\backend

echo [%DATE% %TIME%] Starting MomentumQuest scraper... >> logs\scraper.log

call venv\Scripts\activate

python manage.py scrape_jobs --max-pages 3 --max-jobs 20 >> logs\scraper.log 2>&1

echo [%DATE% %TIME%] Scraper finished. >> logs\scraper.log
