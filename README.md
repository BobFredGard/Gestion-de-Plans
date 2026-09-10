# Gestion-de-Plans (NumPlans)

Application interne JUSTET : gestion de la numérotation des plans Clients → Projets → Plans,
avec fichiers associés (PDF / STEP / DXF), visionneuse 3D (STEP → GLTF via FreeCAD),
auth multi-rôles, exports ZIP et notifications de révisions.

## Stack
- Backend : `server.py` — Python stdlib `http.server` + `sqlite3` + `bcrypt`, port 3000
- Frontend : `index.html` — un seul fichier (~218 Ko), HTML/CSS/JS vanilla, Three.js local (`threejs/`)
- DB : SQLite `numplans.db` (tables `clients`, `projects`, `plans`, `users`, `sessions`, `counters`, `revision_changes`, `file_changes`)
- 3D : `FREECAD_PATH` (`freecadcmd.exe`) → `GLTF/*.gltf` + `*.bin`, cache régénéré si STEP plus récent
- Scripts : `cleanup_gltf.py` (purge cache orphelin), `make_favicon.py`, `.bat` / `.cmd` (tâches planifiées, tunnel Cloudflare, restart)

## Lancement
```bat
go.good.bat
rem ou :
python server.py
```
Puis `http://localhost:3000` (admin/admin par défaut, à changer).
Depuis le LAN : `http://<IP-serveur>:3000`.

Au 1er lancement sur une base vide, `init_db()` crée automatiquement
le compte `admin` + la base TEST (client `TEST` / projet `PR-01` « TEST Projet »
/ plan `PL-000` « Test Plan », ensemble décoché). Si des clients existent déjà,
rien n'est ajouté (seed idempotent).

> `server.py` pointe par défaut sur `BASE_DIR = "D:/ServerFolders/NumPlans"`.
> Adaptez `BASE_DIR`, `FILES_DIR`, `DB_FILE`, `FREECAD_PATH` en haut du fichier
> ou copiez le dossier de prod vers ce chemin.

## Dossiers runtime (non versionnés, voir `.gitignore`)
- `Plans/` — PDF/STEP/DXF nommés `CLIENT-PROJET-PLAN[-REV].ext`
- `GLTF/` — cache généré (`.gltf` + `.bin`)
- `backups/` — copies auto à chaque `save_data` (rétention 100/ext)
- `numplans.db`, `*.pem`, `__pycache__/` — ignorés

## Sécurité
Ne committer jamais : `numplans.db`, `*.pem`, `backups/`.
Auth : Basic + cookie `session` (30 j), CSRF (`csrf_token` + `X-CSRF-Token`),
bcrypt (migration auto depuis legacy SHA-256), mode lecture seule en local sans login admin.
