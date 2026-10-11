@echo off
cd /d "C:\Users\derek\Desktop\syndicate_staging"
python pipeline_worker.py >> pipeline_cron.log 2>&1
