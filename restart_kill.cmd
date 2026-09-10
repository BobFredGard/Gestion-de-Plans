@echo off
taskkill /F /IM python.exe >nul 2>&1
ping -n 4 127.0.0.1 >nul
start /B python D:\ServerFolders\NumPlans\server.py
