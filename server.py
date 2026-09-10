# NumPLans Server with SQLite
# Lancez ce script sur le PC "serveur" puis accédez depuis les autres PCs via http://IP:3000

import http.server
import socketserver
import json
import os
import base64
import hashlib
import secrets
import io
import zipfile
import urllib.parse
import sqlite3
import subprocess
import bcrypt
import time
from datetime import datetime

PORT = 3000
BASE_DIR = "D:/ServerFolders/NumPlans"
FILES_DIR = BASE_DIR + "/Plans"
DB_FILE = BASE_DIR + "/numplans.db"

FREECAD_PATH = "C:/Program Files/FreeCAD 1.1/bin/freecadcmd.exe"

GLTF_DIR = BASE_DIR + "/GLTF"
os.makedirs(GLTF_DIR, exist_ok=True)

BACKUP_DIR = BASE_DIR + "/backups"
os.makedirs(BACKUP_DIR, exist_ok=True)
MAX_BACKUPS = 100

def backup_db():
    import shutil
    from datetime import datetime
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{BACKUP_DIR}/numplans_{ts}.db"
    try:
        shutil.copy2(DB_FILE, backup_path)
    except Exception as e:
        print(f"[BACKUP] DB copy failed: {e}")
        return

    exclude_endings = ('.db', '.db-journal', '.db-wal', '.db-shm')
    for fname in os.listdir(BASE_DIR):
        src = os.path.join(BASE_DIR, fname)
        if not os.path.isfile(src) or fname.endswith(exclude_endings):
            continue
        base, ext = os.path.splitext(fname)
        dst = f"{BACKUP_DIR}/{base}_{ts}{ext}"
        try:
            with open(src, 'rb') as fr:
                with open(dst, 'wb') as fw:
                    fw.write(fr.read())
        except Exception as e:
            print(f"[BACKUP] {fname} copy failed: {e}")

    # Retention par extension : garder les MAX_BACKUPS plus récents
    for ext in set(os.path.splitext(f)[1] for f in os.listdir(BACKUP_DIR) if os.path.isfile(os.path.join(BACKUP_DIR, f))):
        old = sorted(
            [f for f in os.listdir(BACKUP_DIR) if f.endswith(ext)],
            reverse=True
        )
        for f in old[MAX_BACKUPS:]:
            try:
                os.remove(f"{BACKUP_DIR}/{f}")
            except:
                pass
    print(f"[BACKUP] Saved to {backup_path}")
LOG_FILE = os.path.join(GLTF_DIR, "gltf_conversion.log")

def step_to_gltf(step_path, gltf_path):
    """Convert STEP file to GLTF using FreeCADcmd - proper GLTF export"""
    import tempfile
    import time
    import subprocess as sp

    def log(msg):
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        log_msg = f"[{timestamp}] {msg}"
        print(log_msg)
        try:
            with open(LOG_FILE, 'a') as f:
                f.write(log_msg + '\n')
        except:
            pass

    # Remove old files if they exist
    bin_path = gltf_path.replace('.gltf', '.bin')
    if os.path.exists(gltf_path):
        os.remove(gltf_path)
    if os.path.exists(bin_path):
        os.remove(bin_path)

    # Build script with proper escaping
    step_escaped = step_path.replace('\\', '\\\\').replace('"', '\\"')
    gltf_escaped = gltf_path.replace('\\', '\\\\').replace('"', '\\"')

    script = f'''
import FreeCAD
import Import
import os

step_path = "{step_escaped}"
gltf_path = "{gltf_escaped}"

print("Loading STEP:", step_path)

doc = FreeCAD.newDocument()
Import.mergeCompound = True
Import.importVisible = True
Import.useNameOfInstance = False
Import.insert(step_path, doc.Name)
doc.recompute()

print("Objects:", len(doc.Objects))

# Filter: only objects with Shape.Solids
export_objects = [obj for obj in doc.Objects if hasattr(obj, "Shape") and obj.Shape.Solids]
print("Objects with solids:", len(export_objects))

# Also add mesh representation for each
mesh_added = False
for obj in export_objects:
    try:
        mesh = obj.Shape.tessellate(0.1)
        print("Mesh for", obj.Label + ":", len(mesh), "facets")
        mesh_added = True
    except Exception as e:
        print("Tessellate error for", obj.Label + ":", e)

if export_objects:
    print("Exporting to GLTF:", gltf_path)
    Import.export(export_objects, gltf_path)
    print("Export done")
else:
    print("No objects to export!")

FreeCAD.closeDocument(doc.Name)
print("DONE")
'''
    script_path = os.path.join(tempfile.gettempdir(), "_step_gltf.py")
    with open(script_path, 'w', encoding='utf-8') as f:
        f.write(script)

    log(f"Starting FreeCAD conversion: {step_path}")

    process = sp.Popen(
        [FREECAD_PATH, script_path],
        stdout=sp.PIPE,
        stderr=sp.PIPE,
        text=True
    )

    try:
        stdout, stderr = process.communicate(timeout=300)
        log(f"stdout: {stdout}")
        if stderr:
            log(f"stderr (last 500): {stderr[-500:]}")

        time.sleep(0.5)

        gltf_exists = os.path.exists(gltf_path)
        bin_exists = os.path.exists(bin_path)
        log(f"Result - GLTF: {gltf_exists}, BIN: {bin_exists}")

        return gltf_exists and bin_exists
    except sp.TimeoutExpired:
        log("ERROR: Timeout!")
        process.kill()
        return False
    except Exception as e:
        log(f"ERROR: {e}")
        return False
    finally:
        if os.path.exists(script_path):
            os.remove(script_path)

def needs_gltf_regeneration(num_plan, gltf_file):
    """Check if GLTF needs regeneration because STEP is newer"""
    bin_file = gltf_file.replace('.gltf', '.bin')
    if not os.path.exists(gltf_file) or not os.path.exists(bin_file):
        return True
    gltf_mtime = os.path.getmtime(gltf_file)
    step_file_stp = f"{FILES_DIR}/{num_plan}.stp"
    step_file_step = f"{FILES_DIR}/{num_plan}.step"
    for f in (step_file_stp, step_file_step):
        if os.path.exists(f) and os.path.getmtime(f) > gltf_mtime:
            return True
    return False

def clear_gltf_cache(num_plan):
    """Delete GLTF and BIN files for a given num_plan"""
    for f in (f"{GLTF_DIR}/{num_plan}.gltf", f"{GLTF_DIR}/{num_plan}.bin"):
        if os.path.exists(f):
            os.remove(f)

def get_gltf_path(num_plan):
    """Get or create GLTF for a given num_plan"""
    gltf_file = f"{GLTF_DIR}/{num_plan}.gltf"

    if needs_gltf_regeneration(num_plan, gltf_file):
        clear_gltf_cache(num_plan)
        step_file_stp = f"{FILES_DIR}/{num_plan}.stp"
        step_file_step = f"{FILES_DIR}/{num_plan}.step"

        source_step = None
        if os.path.exists(step_file_stp):
            source_step = step_file_stp
        elif os.path.exists(step_file_step):
            source_step = step_file_step

        if source_step:
            print(f"Converting STEP to GLTF: {source_step}")
            if step_to_gltf(source_step, gltf_file):
                return gltf_file

    return gltf_file if os.path.exists(gltf_file) else None

def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS clients (
            id TEXT PRIMARY KEY,
            number TEXT NOT NULL,
            name TEXT,
            revisionLetters INTEGER DEFAULT 0,
            createdAt TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            number TEXT NOT NULL,
            name TEXT,
            createdAt TEXT,
            client_id TEXT,
            FOREIGN KEY (client_id) REFERENCES clients(id)
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS plans (
            id TEXT PRIMARY KEY,
            number TEXT NOT NULL,
            name TEXT,
            software TEXT,
            createdAt TEXT,
            project_id TEXT,
            FOREIGN KEY (project_id) REFERENCES projects(id)
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS counters (
            name TEXT PRIMARY KEY,
            value INTEGER
        )
    ''')
    c.execute("PRAGMA table_info(plans)")
    columns = [col[1] for col in c.fetchall()]
    if 'revision' not in columns:
        c.execute("ALTER TABLE plans ADD COLUMN revision TEXT DEFAULT '0'")
    if 'observations' not in columns:
        c.execute("ALTER TABLE plans ADD COLUMN observations TEXT DEFAULT ''")
    if 'is_ensemble' not in columns:
        c.execute("ALTER TABLE plans ADD COLUMN is_ensemble INTEGER DEFAULT 0")
        c.execute("UPDATE plans SET is_ensemble = 1 WHERE number = 'PL-000'")
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password_salt TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'client',
            client_id TEXT,
            createdAt TEXT,
            FOREIGN KEY (client_id) REFERENCES clients(id)
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')
    # Clean expired sessions
    c.execute("DELETE FROM sessions WHERE expires_at < datetime('now')")
    c.execute("PRAGMA table_info(clients)")
    client_columns = [col[1] for col in c.fetchall()]
    if 'revisionLetters' not in client_columns:
        c.execute("ALTER TABLE clients ADD COLUMN revisionLetters INTEGER DEFAULT 0")
    if 'hidden' not in client_columns:
        c.execute("ALTER TABLE clients ADD COLUMN hidden INTEGER DEFAULT 0")
    c.execute('''
        CREATE TABLE IF NOT EXISTS revision_changes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            client_id TEXT NOT NULL,
            plan_number TEXT NOT NULL,
            old_revision TEXT NOT NULL,
            new_revision TEXT NOT NULL,
            created_at TEXT NOT NULL,
            read_by_client INTEGER DEFAULT 0
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS file_changes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_name TEXT NOT NULL UNIQUE,
            last_known_mtime TEXT NOT NULL,
            detected_at TEXT NOT NULL,
            read_by_client INTEGER DEFAULT 0
        )
    ''')
    # Seed admin if no users exist
    c.execute('SELECT COUNT(*) FROM users')
    if c.fetchone()[0] == 0:
        pwd_hash = hash_password('admin')
        c.execute('INSERT INTO users (id, username, password_salt, password_hash, role, createdAt) VALUES (?, ?, ?, ?, ?, ?)',
                  ('admin', 'admin', '', pwd_hash, 'admin', datetime.now().isoformat()))
        print("[INIT] User admin created (password: admin)")
    # Seed base TEST si aucun client (installation fraiche)
    c.execute('SELECT COUNT(*) FROM clients')
    if c.fetchone()[0] == 0:
        seed_ts = datetime.now().isoformat()
        seed_client = '-'.join(secrets.token_hex(2) for _ in range(3))
        seed_project = '-'.join(secrets.token_hex(2) for _ in range(3))
        seed_plan = '-'.join(secrets.token_hex(2) for _ in range(3))
        c.execute('INSERT INTO clients (id, number, name, revisionLetters, hidden, createdAt) VALUES (?, ?, ?, ?, ?, ?)',
                  (seed_client, 'TEST', 'TEST', 0, 0, seed_ts))
        c.execute('INSERT INTO projects (id, number, name, createdAt, client_id) VALUES (?, ?, ?, ?, ?)',
                  (seed_project, 'PR-01', 'TEST Projet', seed_ts, seed_client))
        c.execute('INSERT INTO plans (id, number, name, software, revision, observations, is_ensemble, createdAt, project_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
                  (seed_plan, 'PL-000', 'Test Plan', '', '0', '', 0, seed_ts, seed_project))
        c.execute("INSERT OR REPLACE INTO counters (name, value) VALUES ('projectsByClient', ?)",
                  (json.dumps({seed_client: 1}),))
        print("[INIT] Base TEST initiale creee (TEST / PR-01 / PL-000)")
    conn.commit()
    conn.close()

def load_data(client_id=None, user=None):
    conn = get_db()
    c = conn.cursor()
    
    if client_id:
        c.execute('SELECT * FROM clients WHERE id = ? ORDER BY createdAt DESC', (client_id,))
    else:
        c.execute('SELECT * FROM clients ORDER BY createdAt DESC')
    client_rows = c.fetchall()
    clients = []
    for row in client_rows:
        client = dict(row)
        # Filtrer les clients cachés pour les non-admin
        if not client_id and client.get('hidden') and user and user.get('role') != 'admin':
            # Visible si le nom d'utilisateur correspond au nom du client
            if not (user.get('username') and user['username'] == client.get('name')):
                continue
        c.execute('SELECT * FROM projects WHERE client_id = ? ORDER BY createdAt DESC', (client['id'],))
        project_rows = c.fetchall()
        projects = []
        for prow in project_rows:
            project = dict(prow)
            c.execute('SELECT * FROM plans WHERE project_id = ? ORDER BY createdAt', (project['id'],))
            plan_rows = c.fetchall()
            project['plans'] = [dict(plan) for plan in plan_rows]
            projects.append(project)
        client['projects'] = projects
        clients.append(client)
    
    c.execute('SELECT value FROM counters WHERE name = ?', ('client',))
    row = c.fetchone()
    client_counter = row['value'] if row else 0
    
    c.execute('SELECT value FROM counters WHERE name = ?', ('projectsByClient',))
    rows = c.fetchall()
    projects_by_client = {}
    for r in rows:
        data = json.loads(r['value']) if r['value'] else {}
        projects_by_client.update(data)
    
    conn.close()
    return {
        'clients': clients,
        'counters': {
            'client': client_counter,
            'projectsByClient': projects_by_client
        }
    }

def save_data(data):
    backup_db()
    conn = get_db()
    try:
        conn.execute('BEGIN IMMEDIATE')
        c = conn.cursor()

        # Snapshot old revisions before overwrite
        c.execute('SELECT id, revision FROM plans')
        old_revisions = {row[0]: row[1] for row in c.fetchall()}

        c.execute('DELETE FROM plans')
        c.execute('DELETE FROM projects')
        c.execute('DELETE FROM clients')

        for client in data.get('clients', []):
            c.execute(
                'INSERT INTO clients (id, number, name, revisionLetters, hidden, createdAt) VALUES (?, ?, ?, ?, ?, ?)',
                (client['id'], client['number'], client['name'], 1 if client.get('revisionLetters') else 0, 1 if client.get('hidden') else 0, client.get('createdAt'))
            )
            for project in client.get('projects', []):
                c.execute(
                    'INSERT INTO projects (id, number, name, createdAt, client_id) VALUES (?, ?, ?, ?, ?)',
                    (project['id'], project['number'], project['name'], project.get('createdAt'), client['id'])
                )
                for plan in project.get('plans', []):
                    c.execute(
                        'INSERT INTO plans (id, number, name, software, revision, observations, is_ensemble, createdAt, project_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
                        (plan['id'], plan['number'], plan.get('name'), plan.get('software'), plan.get('revision', '0'), plan.get('observations', ''), 1 if plan.get('is_ensemble') else 0, plan.get('createdAt'), project['id'])
                    )
                    new_rev = plan.get('revision', '0')
                    old_rev = old_revisions.get(plan['id'])
                    if old_rev is not None and old_rev != new_rev:
                        c.execute(
                            'INSERT INTO revision_changes (plan_id, project_id, client_id, plan_number, old_revision, new_revision, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)',
                            (plan['id'], project['id'], client['id'], plan['number'], old_rev, new_rev, datetime.now().isoformat())
                        )

        c.execute('INSERT OR REPLACE INTO counters (name, value) VALUES (?, ?)',
                  ('client', data.get('counters', {}).get('client', 0)))

        projects_by_client = data.get('counters', {}).get('projectsByClient', {})
        c.execute('INSERT OR REPLACE INTO counters (name, value) VALUES (?, ?)',
                  ('projectsByClient', json.dumps(projects_by_client)))

        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"[SAVE] Transaction failed, rolled back: {e}")
        raise
    finally:
        conn.close()

def hash_password(password):
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()

def check_password(password, stored_hash, stored_salt=None):
    try:
        if stored_hash.startswith('$2b$'):
            return bcrypt.checkpw(password.encode(), stored_hash.encode())
    except:
        pass
    # Legacy SHA-256 fallback
    if stored_salt:
        expected = hashlib.sha256((stored_salt + password).encode()).hexdigest()
        return expected == stored_hash
    return False

SESSION_DURATION_DAYS = 30

def create_session(user_id):
    conn = get_db()
    c = conn.cursor()
    token = secrets.token_hex(32)
    c.execute('INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, datetime("now", ?))',
              (token, user_id, f'+{SESSION_DURATION_DAYS} days'))
    conn.commit()
    conn.close()
    return token

def get_user_from_session(token):
    conn = get_db()
    c = conn.cursor()
    c.execute('''SELECT u.id, u.username, u.role, u.client_id FROM sessions s
                 JOIN users u ON u.id = s.user_id
                 WHERE s.token = ? AND s.expires_at > datetime("now")''', (token,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def check_auth(auth_header, headers=None):
    if not auth_header and headers:
        cookies = headers.get('Cookie', '')
        for c in cookies.split(';'):
            c = c.strip()
            if c.startswith('session='):
                user = get_user_from_session(c[8:])
                if user:
                    return user
    if not auth_header:
        return None
    try:
        encoded = auth_header.split(' ')[1]
        decoded = base64.b64decode(encoded).decode('utf-8')
        username, password = decoded.split(':', 1)
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT id, username, password_salt, password_hash, role, client_id FROM users WHERE username = ?', (username,))
        row = c.fetchone()
        if row:
            user = dict(row)
            if check_password(password, user['password_hash'], user['password_salt']):
                # Migrate legacy SHA-256 to bcrypt on successful login
                if not user['password_hash'].startswith('$2b$'):
                    new_hash = hash_password(password)
                    c.execute('UPDATE users SET password_hash = ?, password_salt = ? WHERE id = ?', (new_hash, '', user['id']))
                    conn.commit()
                conn.close()
                return {'id': user['id'], 'username': user['username'], 'role': user['role'], 'client_id': user['client_id']}
            else:
                print(f"[AUTH] Failed login attempt for user: {username}")
        conn.close()
    except:
        pass
    return None

import re
LOCAL_IP_RE = re.compile(r'^(127\.|192\.168\.|10\.|172\.(1[6-9]|2[0-9]|3[01])\.|::1)')

def generate_csrf_token():
    return secrets.token_hex(32)

def get_csrf_token_from_cookies(headers):
    cookies = headers.get('Cookie', '')
    for c in cookies.split(';'):
        c = c.strip()
        if c.startswith('csrf_token='):
            return c[11:]
    return None

def check_csrf(handler):
    cookie_token = get_csrf_token_from_cookies(handler.headers)
    header_token = handler.headers.get('X-CSRF-Token', '')
    if not cookie_token or not header_token or cookie_token != header_token:
        return False
    return True

def is_local(request_handler):
    host = request_handler.headers.get('Host', '')
    # If X-Forwarded-Proto is 'https', it came through Cloudflare tunnel → not local
    if request_handler.headers.get('X-Forwarded-Proto') == 'https':
        return False
    # If no X-Forwarded-Proto at all, it's a direct connection → could be local
    # Check if host is a local IP
    if LOCAL_IP_RE.match(host):
        return True
    # Also treat localhost as local
    if host.startswith('localhost') or host == '127.0.0.1:3000':
        return True
    return False

def get_all_files_status(client_id=None, user=None):
    data = load_data(client_id, user)
    files = {}
    for client in data.get('clients', []):
        client_num = client.get('number', '')
        revision_letters = client.get('revisionLetters', False)
        for project in client.get('projects', []):
            proj_num = project.get('number', '').replace('PR-', '')
            for plan in project.get('plans', []):
                plan_num = plan.get('number', '').replace('PL-', '')
                revision = plan.get('revision', '0')
                if revision_letters and revision != '0':
                    num_rev = int(revision)
                    if 1 <= num_rev <= 26:
                        rev_suffix = '-' + chr(64 + num_rev)
                    elif num_rev > 26:
                        first = (num_rev - 27) // 26
                        second = ((num_rev - 27) % 26) + 1
                        rev_suffix = '-' + chr(64 + first + 1) + chr(64 + second)
                    else:
                        rev_suffix = ''
                elif not revision_letters and revision != '0':
                    rev_suffix = '-' + revision
                else:
                    rev_suffix = ''
                num_plan = f"{client_num}-{proj_num}-{plan_num}{rev_suffix}"
                files[num_plan] = {
                    'pdf': os.path.exists(f"{FILES_DIR}/{num_plan}.pdf"),
                    'step': os.path.exists(f"{FILES_DIR}/{num_plan}.stp") or os.path.exists(f"{FILES_DIR}/{num_plan}.step"),
                    'dxf': os.path.exists(f"{FILES_DIR}/{num_plan}.dxf")
                }

    for f in os.listdir(FILES_DIR):
        if f.endswith('.pdf') or f.endswith('.stp') or f.endswith('.step') or f.endswith('.dxf'):
            base = f.rsplit('.', 1)[0]
            if base not in files:
                files[base] = {
                    'pdf': os.path.exists(f"{FILES_DIR}/{base}.pdf"),
                    'step': os.path.exists(f"{FILES_DIR}/{base}.stp") or os.path.exists(f"{FILES_DIR}/{base}.step"),
                    'dxf': os.path.exists(f"{FILES_DIR}/{base}.dxf")
                }
    return files

def sanitize_filename(name):
    name = name.replace(' ', '_')
    name = ''.join(c for c in name if c.isalnum() or c in ('_', '-', '.'))
    return name

def find_plan_by_id(plan_id):
    data = load_data()
    for client in data.get('clients', []):
        for project in client.get('projects', []):
            for plan in project.get('plans', []):
                if plan.get('id') == plan_id:
                    return client, project, plan
    return None, None, None

def find_client_by_id(client_id):
    data = load_data()
    for client in data.get('clients', []):
        if client.get('id') == client_id:
            return client
    return None

def find_project_by_id(project_id):
    data = load_data()
    for client in data.get('clients', []):
        for project in client.get('projects', []):
            if project.get('id') == project_id:
                return client, project
    return None, None

def get_zip_name(plan_num, plan_name, client_number):
    if client_number == 'MERLIN':
        return plan_name
    return f"{plan_num} - {plan_name}"

def get_revision_suffix(revision, revision_letters):
    if not revision or revision == '0':
        return ''
    if revision_letters:
        num = int(revision)
        if num >= 1 and num <= 26:
            return '-' + chr(64 + num)
        if num > 26:
            first = (num - 27) // 26 + 1
            second = (num - 27) % 26 + 1
            return '-' + chr(64 + first) + chr(64 + second)
    return '-' + revision

def delete_plan_files(client, project, plan):
    deleted = []
    client_num = client.get('number', '')
    proj_num = project.get('number', '').replace('PR-', '')
    plan_num = plan.get('number', '').replace('PL-', '')
    base_plan = f"{client_num}-{proj_num}-{plan_num}"

    def match_plan(name):
        n = name.rsplit('.', 1)[0]
        return n == base_plan or n.startswith(base_plan + '-')

    for f in os.listdir(FILES_DIR):
        if match_plan(f):
            filepath = f"{FILES_DIR}/{f}"
            try:
                os.remove(filepath)
                deleted.append(filepath)
            except Exception:
                pass

    for f in os.listdir(GLTF_DIR):
        if match_plan(f):
            filepath = f"{GLTF_DIR}/{f}"
            try:
                os.remove(filepath)
                deleted.append(filepath)
            except Exception:
                pass

    return deleted

def delete_project_files(client, project):
    deleted = []
    client_num = client.get('number', '')
    proj_num = project.get('number', '').replace('PR-', '')
    base_project = f"{client_num}-{proj_num}"

    def match_project(name):
        n = name.rsplit('.', 1)[0]
        return n.startswith(base_project + '-') or n == base_project

    for f in os.listdir(FILES_DIR):
        if match_project(f):
            filepath = f"{FILES_DIR}/{f}"
            try:
                os.remove(filepath)
                deleted.append(filepath)
            except Exception:
                pass

    for f in os.listdir(GLTF_DIR):
        if match_project(f):
            filepath = f"{GLTF_DIR}/{f}"
            try:
                os.remove(filepath)
                deleted.append(filepath)
            except Exception:
                pass

    return deleted

def delete_client_files(client):
    deleted = []
    client_num = client.get('number', '')

    for f in os.listdir(FILES_DIR):
        if f.startswith(client_num + '-'):
            filepath = f"{FILES_DIR}/{f}"
            try:
                os.remove(filepath)
                deleted.append(filepath)
            except Exception:
                pass

    for f in os.listdir(GLTF_DIR):
        if f.startswith(client_num + '-'):
            filepath = f"{GLTF_DIR}/{f}"
            try:
                os.remove(filepath)
                deleted.append(filepath)
            except Exception:
                pass

    return deleted

def get_num_plan_with_revision(client_num, proj_num, plan_num, revision, revision_letters):
    base = f"{client_num}-{proj_num}-{plan_num}"
    suffix = get_revision_suffix(revision, revision_letters)
    return base + suffix

def create_single_plan_zip(client, project, plan):
    plan_num = plan.get('number', '').replace('PL-', '')
    plan_name = plan.get('name', 'Plan_ensemble') or 'Plan_ensemble'
    client_num = client.get('number', '')
    proj_num = project.get('number', '').replace('PR-', '')
    revision = plan.get('revision', '0')
    revision_letters = client.get('revisionLetters', False)
    zip_name = get_zip_name(plan_num, plan_name, client_num)

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
        num_plan = get_num_plan_with_revision(client_num, proj_num, plan_num, revision, revision_letters)
        if os.path.exists(f"{FILES_DIR}/{num_plan}.pdf"):
            with open(f"{FILES_DIR}/{num_plan}.pdf", 'rb') as f:
                zipf.writestr(f"{zip_name}.pdf", f.read())
        step_file = f"{FILES_DIR}/{num_plan}.stp" if os.path.exists(f"{FILES_DIR}/{num_plan}.stp") else f"{FILES_DIR}/{num_plan}.step"
        if os.path.exists(step_file):
            ext = 'stp' if step_file.endswith('.stp') else 'step'
            with open(step_file, 'rb') as f:
                zipf.writestr(f"{zip_name}.{ext}", f.read())
        if os.path.exists(f"{FILES_DIR}/{num_plan}.dxf"):
            with open(f"{FILES_DIR}/{num_plan}.dxf", 'rb') as f:
                zipf.writestr(f"{zip_name}.dxf", f.read())
    
    zip_buffer.seek(0)
    return zip_buffer.getvalue(), zip_name

def create_project_zip(client, project):
    project_name = project.get('name', 'Project') or 'Project'
    base_name = project_name
    client_num = client.get('number', '')
    proj_num = project.get('number', '').replace('PR-', '')
    revision_letters = client.get('revisionLetters', False)

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for plan in project.get('plans', []):
            plan_num = plan.get('number', '').replace('PL-', '')
            revision = plan.get('revision', '0')
            num_plan = get_num_plan_with_revision(client_num, proj_num, plan_num, revision, revision_letters)
            plan_name = plan.get('name', 'Plan_ensemble') or 'Plan_ensemble'
            zip_name = get_zip_name(plan_num, plan_name, client_num)

            if os.path.exists(f"{FILES_DIR}/{num_plan}.pdf"):
                with open(f"{FILES_DIR}/{num_plan}.pdf", 'rb') as f:
                    zipf.writestr(f"{zip_name}.pdf", f.read())
            step_file = f"{FILES_DIR}/{num_plan}.stp" if os.path.exists(f"{FILES_DIR}/{num_plan}.stp") else f"{FILES_DIR}/{num_plan}.step"
            if os.path.exists(step_file):
                ext = 'stp' if step_file.endswith('.stp') else 'step'
                with open(step_file, 'rb') as f:
                    zipf.writestr(f"{zip_name}.{ext}", f.read())
            if os.path.exists(f"{FILES_DIR}/{num_plan}.dxf"):
                with open(f"{FILES_DIR}/{num_plan}.dxf", 'rb') as f:
                    zipf.writestr(f"{zip_name}.dxf", f.read())

    zip_buffer.seek(0)
    return zip_buffer.getvalue(), base_name

def create_client_zip(client):
    client_name = client.get('name', 'Client') or 'Client'
    client_number = client.get('number', '')
    base_name = f"{client_number}_{client_name}"
    revision_letters = client.get('revisionLetters', False)

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for project in client.get('projects', []):
            project_name = project.get('name', 'Project') or 'Project'
            project_number = project.get('number', '').replace('PR-', '')
            project_folder = f"{project_number}_{project_name}"

            for plan in project.get('plans', []):
                plan_num = plan.get('number', '').replace('PL-', '')
                revision = plan.get('revision', '0')
                num_plan = get_num_plan_with_revision(client_number, project_number, plan_num, revision, revision_letters)
                plan_name = plan.get('name', 'Plan_ensemble') or 'Plan_ensemble'
                zip_name = get_zip_name(plan_num, plan_name, client_number)

                if os.path.exists(f"{FILES_DIR}/{num_plan}.pdf"):
                    with open(f"{FILES_DIR}/{num_plan}.pdf", 'rb') as f:
                        zipf.writestr(f"{project_folder}/{zip_name}.pdf", f.read())
                step_file = f"{FILES_DIR}/{num_plan}.stp" if os.path.exists(f"{FILES_DIR}/{num_plan}.stp") else f"{FILES_DIR}/{num_plan}.step"
                if os.path.exists(step_file):
                    ext = 'stp' if step_file.endswith('.stp') else 'step'
                    with open(step_file, 'rb') as f:
                        zipf.writestr(f"{project_folder}/{zip_name}.{ext}", f.read())
                if os.path.exists(f"{FILES_DIR}/{num_plan}.dxf"):
                    with open(f"{FILES_DIR}/{num_plan}.dxf", 'rb') as f:
                        zipf.writestr(f"{project_folder}/{zip_name}.dxf", f.read())

    zip_buffer.seek(0)
    return zip_buffer.getvalue(), base_name

def scan_step_changes():
    """Scan the Plans directory for STEP files and detect modification time changes."""
    plans_dir = FILES_DIR
    if not os.path.isdir(plans_dir):
        return
    try:
        conn = get_db()
        c = conn.cursor()
        known = {}
        c.execute('SELECT file_name, last_known_mtime FROM file_changes')
        for row in c.fetchall():
            known[row['file_name']] = row['last_known_mtime']
        for fname in os.listdir(plans_dir):
            if not fname.lower().endswith('.step'):
                continue
            fpath = os.path.join(plans_dir, fname)
            if not os.path.isfile(fpath):
                continue
            mtime = os.path.getmtime(fpath)
            mtime_str = str(mtime)
            if fname in known:
                if known[fname] != mtime_str:
                    c.execute('UPDATE file_changes SET last_known_mtime = ?, detected_at = ?, read_by_client = 0 WHERE file_name = ?',
                              (mtime_str, datetime.now().isoformat(), fname))
            else:
                c.execute('INSERT OR IGNORE INTO file_changes (file_name, last_known_mtime, detected_at, read_by_client) VALUES (?, ?, ?, 1)',
                          (fname, mtime_str, datetime.now().isoformat()))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[SCAN] Error scanning STEP files: {e}")

import threading

def start_file_scanner():
    """Start a background thread that scans STEP files every 60 seconds."""
    def scanner_loop():
        while True:
            time.sleep(60)
            scan_step_changes()
    t = threading.Thread(target=scanner_loop, daemon=True)
    t.start()
    print("[SCAN] STEP file scanner started (every 60s)")

class NumPlansHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        local = is_local(self)
        if local:
            authed = check_auth(self.headers.get('Authorization'), self.headers)
            if authed:
                user = authed
            else:
                user = {'role': 'local', 'client_id': None, 'username': 'local'}
        else:
            user = check_auth(self.headers.get('Authorization'), self.headers)
        if self.path == '/api/data':
            if local and user['role'] == 'local':
                data = load_data(None, user)
                data['local'] = True
            elif not user:
                data = {'clients': [], 'counters': {'client': 0, 'projectsByClient': {}}}
            else:
                client_id = user['client_id'] if user['role'] == 'client' else None
                # Client lié à un client caché sans projet → mode viewer (voit tout sauf les cachés)
                if client_id:
                    conn = get_db()
                    c = conn.cursor()
                    c.execute('SELECT hidden, (SELECT COUNT(*) FROM projects WHERE client_id = ?) AS nb FROM clients WHERE id = ?', (client_id, client_id))
                    row = c.fetchone()
                    conn.close()
                    if row and row[0] and row[1] == 0:
                        client_id = None
                data = load_data(client_id, user)
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(data).encode())
        elif self.path == '/api/files-status':
            if local and user['role'] == 'local':
                files_status = get_all_files_status(None, user)
            elif not user:
                files_status = {}
            else:
                client_id = user['client_id'] if user['role'] == 'client' else None
                if client_id:
                    conn = get_db()
                    c = conn.cursor()
                    c.execute('SELECT hidden, (SELECT COUNT(*) FROM projects WHERE client_id = ?) AS nb FROM clients WHERE id = ?', (client_id, client_id))
                    row = c.fetchone()
                    conn.close()
                    if row and row[0] and row[1] == 0:
                        client_id = None
                files_status = get_all_files_status(client_id, user)
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(files_status).encode())
        elif self.path.startswith('/api/export-plan/'):
            plan_id = self.path.split('/')[-1]
            client, project, plan = find_plan_by_id(plan_id)
            if not plan:
                self.send_error(404)
                return
            zip_data, base_name = create_single_plan_zip(client, project, plan)
            self.send_response(200)
            self.send_header('Content-Type', 'application/zip')
            self.send_header('Content-Disposition', f'attachment; filename="{base_name}"')
            self.send_header('Content-Length', str(len(zip_data)))
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(zip_data)
        elif self.path.startswith('/api/export-project/'):
            project_id = self.path.split('/')[-1]
            client, project = find_project_by_id(project_id)
            if not project:
                self.send_error(404)
                return
            zip_data, base_name = create_project_zip(client, project)
            self.send_response(200)
            self.send_header('Content-Type', 'application/zip')
            self.send_header('Content-Disposition', f'attachment; filename="{base_name}"')
            self.send_header('Content-Length', str(len(zip_data)))
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(zip_data)
        elif self.path.startswith('/api/export-client/'):
            client_id = self.path.split('/')[-1]
            client = find_client_by_id(client_id)
            if not client:
                self.send_error(404)
                return
            zip_data, base_name = create_client_zip(client)
            self.send_response(200)
            self.send_header('Content-Type', 'application/zip')
            self.send_header('Content-Disposition', f'attachment; filename="{base_name}"')
            self.send_header('Content-Length', str(len(zip_data)))
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(zip_data)
        elif self.path.startswith('/api/gltf/'):
            num_plan = self.path.split('/')[-1]
            gltf_path = get_gltf_path(num_plan)
            if gltf_path and os.path.exists(gltf_path):
                self.send_response(200)
                self.send_header('Content-Type', 'model/gltf+json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                with open(gltf_path, 'rb') as f:
                    self.wfile.write(f.read())
            else:
                self.send_error(404)
        elif self.path.startswith('/api/gltf-bin/'):
            num_plan = self.path.split('/')[-1]
            bin_path = f"{GLTF_DIR}/{num_plan}.bin"
            if os.path.exists(bin_path):
                self.send_response(200)
                self.send_header('Content-Type', 'application/octet-stream')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                with open(bin_path, 'rb') as f:
                    self.wfile.write(f.read())
            else:
                self.send_error(404)
        elif self.path.startswith('/api/step/'):
            num_plan = self.path.split('/')[-1]
            step_file_stp = f"{FILES_DIR}/{num_plan}.stp"
            step_file_step = f"{FILES_DIR}/{num_plan}.step"
            source_step = None
            if os.path.exists(step_file_stp):
                source_step = step_file_stp
            elif os.path.exists(step_file_step):
                source_step = step_file_step
            if source_step and os.path.exists(source_step):
                self.send_response(200)
                self.send_header('Content-Type', 'application/octet-stream')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                with open(source_step, 'rb') as f:
                    self.wfile.write(f.read())
            else:
                self.send_error(404)
        elif self.path.startswith('/gltf/'):
            filename = os.path.basename(self.path)
            num_plan = filename.replace('.gltf', '').replace('.bin', '')
            gltf_path = f"{GLTF_DIR}/{num_plan}.gltf"
            bin_path = f"{GLTF_DIR}/{num_plan}.bin"

            if self.path.endswith('.gltf'):
                if needs_gltf_regeneration(num_plan, gltf_path):
                    clear_gltf_cache(num_plan)
                    step_file_stp = f"{FILES_DIR}/{num_plan}.stp"
                    step_file_step = f"{FILES_DIR}/{num_plan}.step"
                    source_step = None
                    if os.path.exists(step_file_stp):
                        source_step = step_file_stp
                    elif os.path.exists(step_file_step):
                        source_step = step_file_step

                    if source_step:
                        print(f"[GLTF] Creating GLTF for {num_plan}...")
                        success = step_to_gltf(source_step, gltf_path)
                        if success:
                            print(f"[GLTF] Successfully created {gltf_path}")
                        else:
                            print(f"[GLTF] Failed to create {gltf_path}")
                    else:
                        print(f"[GLTF] No STEP file found for {num_plan}")
                        self.send_error(404)
                        return

                if os.path.exists(gltf_path) and os.path.exists(bin_path):
                    self.send_response(200)
                    self.send_header('Content-Type', 'model/gltf+json')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    with open(gltf_path, 'rb') as f:
                        self.wfile.write(f.read())
                else:
                    print(f"[GLTF] File not ready: {gltf_path} exists={os.path.exists(gltf_path)}, bin={os.path.exists(bin_path)}")
                    self.send_error(503)
            # If requesting .bin, serve it directly
            elif self.path.endswith('.bin'):
                if os.path.exists(bin_path):
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/octet-stream')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    with open(bin_path, 'rb') as f:
                        self.wfile.write(f.read())
                else:
                    print(f"[GLTF] BIN not found: {bin_path}")
                    self.send_error(404)
        elif self.path.startswith('/threejs/'):
            file_path = BASE_DIR + self.path
            if os.path.exists(file_path):
                self.send_response(200)
                if file_path.endswith('.js'):
                    self.send_header('Content-Type', 'application/javascript')
                else:
                    self.send_header('Content-Type', 'text/plain')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                with open(file_path, 'rb') as f:
                    self.wfile.write(f.read())
            else:
                self.send_error(404)
        elif self.path.startswith('/PDF/') or self.path.startswith('/STEP/') or self.path.startswith('/DXF/'):
            original_path = urllib.parse.unquote(self.path.split('?')[0])
            file_path = FILES_DIR + original_path.replace('/PDF/', '/').replace('/STEP/', '/').replace('/DXF/', '/')
            if os.path.exists(file_path):
                self.send_response(200)
                if original_path.endswith('.pdf'):
                    self.send_header('Content-Type', 'application/pdf')
                else:
                    self.send_header('Content-Type', 'application/octet-stream')

                if original_path.endswith('.pdf'):
                    self.send_header('Content-Disposition', 'inline')
                elif 'filename=' in self.path:
                    filename = self.path.split('filename=')[1].split('&')[0]
                    filename = urllib.parse.unquote(filename)
                    self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
                elif self.path.startswith('/PDF/'):
                    filename = os.path.basename(file_path)
                    self.send_header('Content-Disposition', f'inline; filename="{filename}"')
                
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                with open(file_path, 'rb') as f:
                    self.wfile.write(f.read())
            else:
                self.send_error(404)
        elif self.path == '/api/users':
            if not user or user['role'] != 'admin':
                self.send_error(401)
                return
            conn = get_db()
            c = conn.cursor()
            c.execute('SELECT id, username, role, client_id, createdAt FROM users')
            rows = c.fetchall()
            conn.close()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps([dict(r) for r in rows]).encode())
        elif self.path == '/api/revision-changes':
            if not user:
                self.send_response(401)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(b'{"error":"Not authenticated"}')
                return
            conn = get_db()
            c = conn.cursor()
            if user['role'] == 'admin':
                c.execute('SELECT * FROM revision_changes WHERE read_by_client = 0 ORDER BY created_at DESC LIMIT 50')
            else:
                c.execute('SELECT * FROM revision_changes WHERE client_id = ? AND read_by_client = 0 ORDER BY created_at DESC LIMIT 50',
                          (user['client_id'],))
            rows = [dict(r) for r in c.fetchall()]
            conn.close()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(rows).encode())
        elif self.path == '/api/file-changes':
            conn = get_db()
            c = conn.cursor()
            c.execute('SELECT * FROM file_changes WHERE read_by_client = 0 ORDER BY detected_at DESC LIMIT 50')
            rows = [dict(r) for r in c.fetchall()]
            conn.close()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(rows).encode())
        elif self.path.startswith('/favicon.'):
            filename = self.path.split('?')[0].split('/')[-1]
            file_path = os.path.join(BASE_DIR, filename)
            if os.path.exists(file_path):
                self.send_response(200)
                self.send_header('Cache-Control', 'public, max-age=86400')
                if file_path.endswith('.ico'):
                    self.send_header('Content-Type', 'image/x-icon')
                elif file_path.endswith('.svg'):
                    self.send_header('Content-Type', 'image/svg+xml')
                else:
                    self.send_header('Content-Type', 'image/png')
                self.end_headers()
                with open(file_path, 'rb') as f:
                    self.wfile.write(f.read())
            else:
                self.send_error(404)
        else:
            if self.path in ('/', '/index.html'):
                csrf_token = generate_csrf_token()
                self.send_response(200)
                self.send_header('Set-Cookie', f'csrf_token={csrf_token}; Path=/; SameSite=Strict; Max-Age=86400')
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.end_headers()
                file_path = BASE_DIR + '/index.html'
                with open(file_path, 'rb') as f:
                    self.wfile.write(f.read())
            else:
                super().do_GET()

    def do_POST(self):
        local = is_local(self)
        if local:
            authed = check_auth(self.headers.get('Authorization'), self.headers)
            user = authed or {'role': 'local', 'client_id': None, 'username': 'local'}
        else:
            user = check_auth(self.headers.get('Authorization'), self.headers)
        if self.path == '/api/data':
            if not local and (not user or user['role'] != 'admin'):
                self.send_response(403)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(b'{"error":"Unauthorized"}')
                return
            if not check_csrf(self):
                self.send_response(403)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(b'{"error":"CSRF token missing or invalid"}')
                return
            if local and user['role'] == 'local':
                self.send_response(403)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(b'{"error":"Read-only mode"}')
                return
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            json_data = json.loads(post_data.decode('utf-8'))
            save_data(json_data)
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(b'{"success":true}')
        elif self.path == '/api/login':
            # Extract form data if present (for browser password save flow)
            redirect_target = None
            form_user = None
            if self.headers.get('Content-Type', '').startswith('application/x-www-form-urlencoded'):
                content_length = int(self.headers['Content-Length'])
                post_data = self.rfile.read(content_length).decode('utf-8')
                params = urllib.parse.parse_qs(post_data)
                redirect_target = params.get('redirect', [None])[0]
                username = params.get('username', [None])[0]
                password = params.get('password', [None])[0]
                if username and password:
                    encoded = base64.b64encode(f"{username}:{password}".encode()).decode()
                    form_user = check_auth(f"Basic {encoded}")
            # If it's a form submission with redirect, always redirect (browser save flow)
            if redirect_target:
                if form_user:
                    session_token = create_session(form_user['id'])
                    self.send_response(302)
                    self.send_header('Set-Cookie', f'session={session_token}; Path=/; Max-Age=86400; SameSite=Lax')
                    self.send_header('Location', redirect_target + ('?' if '?' not in redirect_target else '&') + 'session=1')
                    self.end_headers()
                else:
                    self.send_response(302)
                    self.send_header('Location', redirect_target + ('?' if '?' not in redirect_target else '&') + 'login_error=1')
                    self.end_headers()
                return
            # Normal API JSON response (for AJAX fetch)
            if local and not form_user and user['role'] == 'local':
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'loggedin': True,
                    'role': 'local',
                    'client_id': None,
                    'client': None
                }).encode())
                return
            user = form_user or user
            if user:
                client_info = None
                if user['role'] == 'client' and user['client_id']:
                    conn = get_db()
                    c = conn.cursor()
                    c.execute('SELECT number, name FROM clients WHERE id = ?', (user['client_id'],))
                    row = c.fetchone()
                    conn.close()
                    if row:
                        client_info = {'number': row['number'], 'name': row['name']}
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'loggedin': True,
                    'username': user['username'],
                    'role': user['role'],
                    'client_id': user['client_id'],
                    'client': client_info
                }).encode())
            else:
                self.send_response(403)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(b'{"loggedin":false}')
        elif self.path == '/api/create-user':
            if local and user['role'] == 'local':
                self.send_response(403)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(b'{"error":"Read-only mode"}')
                return
            if not user or user['role'] != 'admin':
                self.send_error(401)
                return
            if not check_csrf(self):
                self.send_response(403)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(b'{"error":"CSRF token missing or invalid"}')
                return
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            body = json.loads(post_data.decode('utf-8'))
            uid = secrets.token_hex(8)
            pwd_hash = hash_password(body['password'])
            conn = get_db()
            c = conn.cursor()
            try:
                c.execute('INSERT INTO users (id, username, password_salt, password_hash, role, client_id, createdAt) VALUES (?, ?, ?, ?, ?, ?, ?)',
                          (uid, body['username'], '', pwd_hash, body.get('role', 'client'), body.get('client_id'), datetime.now().isoformat()))
                conn.commit()
                conn.close()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({'success': True, 'id': uid}).encode())
            except sqlite3.IntegrityError:
                conn.close()
                self.send_response(400)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({'error': 'Username already exists'}).encode())
        elif self.path == '/api/change-password':
            if local and user['role'] == 'local':
                self.send_response(403)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(b'{"error":"Read-only mode"}')
                return
            if not user:
                self.send_error(401)
                return
            if not check_csrf(self):
                self.send_response(403)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(b'{"error":"CSRF token missing or invalid"}')
                return
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            body = json.loads(post_data.decode('utf-8'))
            target_id = body.get('user_id', user['id'])
            if target_id != user['id'] and user['role'] != 'admin':
                self.send_error(401)
                return
            pwd_hash = hash_password(body['password'])
            conn = get_db()
            c = conn.cursor()
            c.execute('UPDATE users SET password_salt = ?, password_hash = ? WHERE id = ?', ('', pwd_hash, target_id))
            conn.commit()
            conn.close()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({'success': True}).encode())
        elif self.path == '/api/logout':
            # Clear the session cookie and delete session from DB
            cookies = self.headers.get('Cookie', '')
            for c in cookies.split(';'):
                c = c.strip()
                if c.startswith('session='):
                    token = c[8:]
                    conn = get_db()
                    conn.execute('DELETE FROM sessions WHERE token = ?', (token,))
                    conn.commit()
                    conn.close()
                    break
            self.send_response(200)
            self.send_header('Set-Cookie', 'session=; Path=/; Max-Age=0')
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(b'{"loggedout":true}')
        elif self.path == '/api/revision-change-read':
            if not user:
                self.send_response(401)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(b'{"error":"Not authenticated"}')
                return
            if not check_csrf(self):
                self.send_response(403)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(b'{"error":"CSRF token missing or invalid"}')
                return
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            body = json.loads(post_data.decode('utf-8'))
            change_id = body.get('change_id')
            if not change_id:
                self.send_response(400)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(b'{"error":"Missing change_id"}')
                return
            conn = get_db()
            c = conn.cursor()
            if user['role'] == 'admin':
                c.execute('UPDATE revision_changes SET read_by_client = 1 WHERE id = ?', (change_id,))
            else:
                c.execute('UPDATE revision_changes SET read_by_client = 1 WHERE id = ? AND client_id = ?',
                          (change_id, user['client_id']))
            conn.commit()
            conn.close()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(b'{"success":true}')
        elif self.path == '/api/file-change-read':
            if not user:
                self.send_response(401)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(b'{"error":"Not authenticated"}')
                return
            if not check_csrf(self):
                self.send_response(403)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(b'{"error":"CSRF token missing or invalid"}')
                return
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            body = json.loads(post_data.decode('utf-8'))
            change_id = body.get('change_id')
            if not change_id:
                self.send_response(400)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(b'{"error":"Missing change_id"}')
                return
            conn = get_db()
            c = conn.cursor()
            c.execute('UPDATE file_changes SET read_by_client = 1 WHERE id = ?', (change_id,))
            conn.commit()
            conn.close()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(b'{"success":true}')
        else:
            self.send_error(404)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        self.end_headers()

    def do_DELETE(self):
        # GLTF cache deletion is allowed even in local read-only mode
        if self.path.startswith('/api/gltf-delete/'):
            num_plan = self.path.split('/')[-1]
            gltf_path = GLTF_DIR + '/' + num_plan + '.gltf'
            bin_path = GLTF_DIR + '/' + num_plan + '.bin'
            deleted = False
            try:
                if os.path.exists(gltf_path):
                    os.remove(gltf_path)
                    deleted = True
                if os.path.exists(bin_path):
                    os.remove(bin_path)
                    deleted = True
            except Exception:
                pass
            if deleted:
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(b'{"deleted":true}')
            else:
                self.send_error(404)
            return
        local = is_local(self)
        if local:
            authed = check_auth(self.headers.get('Authorization'), self.headers)
            if not authed or authed['role'] != 'admin':
                self.send_response(403)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(b'{"error":"Read-only mode"}')
                return
            user = authed
        else:
            user = check_auth(self.headers.get('Authorization'), self.headers)
        if self.path.startswith('/api/delete-user/'):
            if not user or user['role'] != 'admin':
                self.send_error(401)
                return
            if not check_csrf(self):
                self.send_response(403)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(b'{"error":"CSRF token missing or invalid"}')
                return
            target_id = self.path.split('/')[-1]
            if target_id == user['id']:
                self.send_response(400)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({'error': 'Cannot delete yourself'}).encode())
                return
            conn = get_db()
            c = conn.cursor()
            c.execute('DELETE FROM users WHERE id = ?', (target_id,))
            conn.commit()
            conn.close()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({'deleted': True}).encode())
        elif self.path.startswith('/api/delete-plan/'):
            if not check_csrf(self):
                self.send_response(403)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(b'{"error":"CSRF token missing or invalid"}')
                return
            plan_id = self.path.split('/')[-1]
            client, project, plan = find_plan_by_id(plan_id)
            if not plan:
                self.send_error(404)
                return
            deleted_files = delete_plan_files(client, project, plan)
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({'deleted': deleted_files}).encode())
        elif self.path.startswith('/api/delete-project/'):
            if not check_csrf(self):
                self.send_response(403)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(b'{"error":"CSRF token missing or invalid"}')
                return
            project_id = self.path.split('/')[-1]
            client, project = find_project_by_id(project_id)
            if not project:
                self.send_error(404)
                return
            deleted_files = delete_project_files(client, project)
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({'deleted': deleted_files}).encode())
        elif self.path.startswith('/api/delete-client/'):
            if not check_csrf(self):
                self.send_response(403)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(b'{"error":"CSRF token missing or invalid"}')
                return
            client_id = self.path.split('/')[-1]
            client = find_client_by_id(client_id)
            if not client:
                self.send_error(404)
                return
            deleted_files = delete_client_files(client)
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({'deleted': deleted_files}).encode())
        else:
            self.send_error(405)

init_db()
scan_step_changes()
start_file_scanner()

os.chdir(BASE_DIR)
class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    request_queue_size = 15

with ThreadedTCPServer(("", PORT), NumPlansHandler) as httpd:
    print(f"NumPLans Server running at http://localhost:{PORT}")
    print(f"Base directory: {BASE_DIR}")
    print(f"Database file: {os.path.abspath(DB_FILE)}")
    print(f"Access from other PCs: http://192.168.x.x:{PORT}")
    print(f"Default login: admin / admin")
    print(f"Check files status: http://localhost:{PORT}/api/files-status")
    httpd.serve_forever()