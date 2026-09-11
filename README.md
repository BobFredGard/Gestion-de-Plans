# Gestion-de-Plans (NumPlans)

Application interne JUSTET : gestion de la numérotation des plans Clients → Projets → Plans,
avec fichiers associés (PDF / STEP / DXF), visionneuse 3D (STEP → GLTF via FreeCAD),
auth multi-rôles, exports ZIP et notifications de révisions.

## Interface Graphique
<img width="1415" height="584" alt="image" src="https://github.com/user-attachments/assets/3cf1fe15-dba0-4770-a77d-7e4fb1cd5050" />
<img width="1422" height="806" alt="image" src="https://github.com/user-attachments/assets/15a69fe1-ca51-4af9-88ca-5ae2e802d296" />

## Stack
- Backend : `server.py` — Python stdlib `http.server` + `sqlite3` + `bcrypt`, port 3000
- Frontend : `index.html` — un seul fichier (~218 Ko), HTML/CSS/JS vanilla, Three.js local (`threejs/`)
- DB : SQLite `numplans.db` (tables `clients`, `projects`, `plans`, `users`, `sessions`, `counters`, `revision_changes`, `file_changes`)
- 3D : conversion STEP → GLTF via FreeCAD headless, cache dans `GLTF/` (voir section dédiée)
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

## Visionneuse 3D : génération des GLTF

Les navigateurs ne savent pas afficher le STEP natif : le serveur convertit
chaque STEP en **glTF** (.gltf + .bin), format affichable en WebGL via Three.js.

### Outil de conversion : FreeCAD (headless)
- Binaire configuré par `FREECAD_PATH` en haut de `server.py`
  (défaut : `C:/Program Files/FreeCAD 1.1/bin/freecadcmd.exe`) — à ajuster selon la version installée.
- `step_to_gltf()` génère un script Python temporaire qui, dans FreeCAD sans interface :
  1. crée un document et importe le STEP (`Import.insert`, `mergeCompound=True`),
  2. ne garde que les objets avec des solides (`Shape.Solids`),
  3. tesselle chaque solide (précision `0.1`),
  4. exporte le tout en glTF (`Import.export`) → produit `<NUMPLAN>.gltf` + `<NUMPLAN>.bin`.
- Conversion lancée en sous-processus avec **timeout de 300 s** ; chaque étape est
  tracée dans `GLTF/gltf_conversion.log` (préfixe `[GLTF]` aussi en console).

### Cache et régénération
- Cache : `GLTF/<NUMPLAN>.gltf` + `GLTF/<NUMPLAN>.bin`, où `<NUMPLAN>` =
  `CLIENT-PROJET-PLAN[-REV]` (ex. `MERLIN-21-000-A`) — régénérable à tout moment, jamais versionné.
- `needs_gltf_regeneration()` compare les dates : si le `.stp`/`.step` de `Plans/`
  est **plus récent** que le cache (ou cache manquant), reconversion automatique.
- Endpoints :
  - `GET /gltf/<NUMPLAN>.gltf` / `.bin` — conversion paresseuse à la demande (503 si pas prêt),
  - `GET /api/gltf/<NUMPLAN>` et `/api/gltf-bin/<NUMPLAN>` — lecture du cache,
  - `GET /api/step/<NUMPLAN>` — téléchargement du STEP source,
  - `DELETE /api/gltf-delete/<NUMPLAN>` — purge du cache (autorisé même en lecture seule locale).
- Côté frontend : la modale 3D (`viewer-3d-modal`) charge le `.gltf` avec
  `three.min.js` + `GLTFLoader.js`, navigation orbitale via `OrbitControls.js`
  (fichiers servis localement depuis `threejs/`, aucune dépendance CDN pour la 3D).

### Maintenance
- `cleanup_gltf.py` : supprime les `.gltf`/`.bin` sans plan correspondant en base (orphelins).
- Fichiers STEP surveillés toutes les 60 s (`scan_step_changes`) : toute modification
  de mtime crée une notification « STEP modifié » (table `file_changes`).

## Dossiers runtime (non versionnés, voir `.gitignore`)
- `Plans/` — PDF/STEP/DXF nommés `CLIENT-PROJET-PLAN[-REV].ext`
- `GLTF/` — cache généré (`.gltf` + `.bin` + `gltf_conversion.log`)
- `backups/` — copies auto à chaque `save_data` (rétention 100/ext)
- `numplans.db`, `*.pem`, `__pycache__/` — ignorés

## Sécurité
Ne committer jamais : `numplans.db`, `*.pem`, `backups/`.
Auth : Basic + cookie `session` (30 j), CSRF (`csrf_token` + `X-CSRF-Token`),
bcrypt (migration auto depuis legacy SHA-256), mode lecture seule en local sans login admin.

## Pour voir un rendu réel
- https://plans.justet.com/
- Login : TEST
- Pass : TEST
