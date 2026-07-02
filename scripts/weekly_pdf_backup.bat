@echo off
chcp 65001 >nul
cd /d C:\Users\User\code\ems-literature
git pull --quiet
python scripts\download_pdfs.py --max 300 >> "G:\我的雲端硬碟\EMS文獻庫\下載紀錄.log" 2>&1
