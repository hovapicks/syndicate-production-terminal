@echo off
cd /d "C:\Users\derek\Desktop\syndicate_staging"
echo ======================================================== >> settlement_log.txt
echo [%date% %time%] Launching Autonomous Morning Cycle >> settlement_log.txt
echo ======================================================== >> settlement_log.txt

:: 1. Grade yesterday's tickets against ESPN final box scores
echo [*] Executing Ticket Settlement... >> settlement_log.txt
python settlement_auto.py >> settlement_log.txt 2>&1

:: 2. Pull fresh slate, compute EV, and stage recommendations
echo [*] Sweeping Slate and Generating Edges... >> settlement_log.txt
python pipeline_worker.py >> settlement_log.txt 2>&1

echo [%date% %time%] Morning Cycle Complete. >> settlement_log.txt
echo. >> settlement_log.txt
