@echo off
echo Creating NumPLans Server scheduled task...
schtasks /create /tn "NumPLansServer" /tr "\"C:\Users\Fred\AppData\Local\Programs\Python\Python313\python.exe\" \"D:\ServerFolders\NumPLans\server.py\"" /sc onlogon /rl HIGHEST /f
echo.
echo Task created. Check with: schtasks /query /tn "NumPLansServer"
echo.
pause
