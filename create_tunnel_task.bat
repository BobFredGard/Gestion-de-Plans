@echo off
echo Creating Cloudflare Tunnel scheduled task...
schtasks /create /tn "CloudflareTunnel" /tr "C:\Users\Fred\AppData\Local\cloudflared\cloudflared.exe tunnel --config C:\ProgramData\Cloudflare\config.yml run" /sc onlogon /rl HIGHEST /f
echo.
echo Task created. Check with: schtasks /query /tn "CloudflareTunnel"
echo.
pause
