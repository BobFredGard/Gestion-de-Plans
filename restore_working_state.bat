@echo off
echo Restauration de l'etat fonctionnel (2026-08-28 08:21:23)...
copy /Y "D:\ServerFolders\NumPLans\backups\server_20260828_082123.py" "D:\ServerFolders\NumPLans\server.py"
copy /Y "D:\ServerFolders\NumPLans\backups\index_20260828_082123.html" "D:\ServerFolders\NumPLans\index.html"
echo Fichiers restaures. Redemarrez le serveur.
pause
