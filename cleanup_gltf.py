import os
import sqlite3
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, 'numplans.db')
GLTF_DIR = os.path.join(BASE_DIR, 'GLTF')

def get_expected_plans():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    plans = set()
    c.execute('SELECT number, revisionLetters FROM clients')
    for client in c.fetchall():
        client_num = client['number']
        rev_letters = client['revisionLetters']
        c2 = conn.cursor()
        c2.execute('SELECT number FROM projects WHERE client_id IN (SELECT id FROM clients WHERE number = ?)', (client_num,))
        for project in c2.fetchall():
            proj_num = project['number'].replace('PR-', '')
            c3 = conn.cursor()
            c3.execute('SELECT number, revision FROM plans WHERE project_id IN (SELECT id FROM projects WHERE number = ? AND client_id IN (SELECT id FROM clients WHERE number = ?))', (project['number'], client_num))
            for plan in c3.fetchall():
                plan_num = plan['number'].replace('PL-', '')
                revision = plan['revision']
                base = f"{client_num}-{proj_num}-{plan_num}"
                rev_suffix = ''
                if revision and revision != '0':
                    if rev_letters:
                        num_rev = int(revision)
                        if 1 <= num_rev <= 26:
                            rev_suffix = '-' + chr(64 + num_rev)
                        elif num_rev > 26:
                            first = (num_rev - 27) // 26
                            second = ((num_rev - 27) % 26) + 1
                            rev_suffix = '-' + chr(64 + first + 1) + chr(64 + second)
                    else:
                        rev_suffix = '-' + revision
                plans.add(f"{base}{rev_suffix}")
    conn.close()
    return plans

def cleanup():
    expected = get_expected_plans()
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] GLTF cleanup - {len(expected)} plans actifs")
    if not os.path.isdir(GLTF_DIR):
        print(f"  GLTF_DIR {GLTF_DIR} n'existe pas")
        return
    deleted = 0
    kept = 0
    for f in os.listdir(GLTF_DIR):
        if not (f.endswith('.gltf') or f.endswith('.bin')):
            continue
        name = f.rsplit('.', 1)[0]
        if name not in expected:
            path = os.path.join(GLTF_DIR, f)
            try:
                os.remove(path)
                deleted += 1
            except Exception as e:
                print(f"  Erreur suppression {f}: {e}")
        else:
            kept += 1
    print(f"  Supprimés: {deleted}, Gardés: {kept}")

if __name__ == '__main__':
    cleanup()
