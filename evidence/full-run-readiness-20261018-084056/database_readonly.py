"""Read immutable main files only when WAL absent/empty; never call Store."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3

out = Path(__file__).resolve().parent
rows = []
for original in json.loads((out / 'preflight.json').read_text())['databases']:
    p = Path(original['path'])
    wal = Path(str(p) + '-wal')
    if wal.exists() and wal.stat().st_size:
        continue
    before = hashlib.sha256(p.read_bytes()).hexdigest()
    item = {'path': p.as_posix(), 'observed_at': datetime.now(timezone.utc).isoformat()}
    try:
        con = sqlite3.connect(p.resolve().as_uri() + '?mode=ro&immutable=1', uri=True)
        con.execute('PRAGMA query_only=ON')
        item['user_version'] = con.execute('PRAGMA user_version').fetchone()[0]
        item['quick_check'] = con.execute('PRAGMA quick_check').fetchone()[0]
        item['tables'] = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        item['runs'] = dict(con.execute('SELECT status,count(*) FROM runs GROUP BY status'))
        item['checkpoints'] = []
        for key, value in con.execute('SELECT key,value FROM metadata'):
            if key == 'published_run':
                item['published_run'] = json.loads(value)
            elif key.startswith('activity_cache:'):
                values = json.loads(value)
                item['checkpoints'].append({'key': key, 'rows': len(values), 'latest_date': max((r['date'] for r in values), default=None), 'duplicates': len(values) - len({(r['port_id'], r['date']) for r in values})})
        if 'audit_chain' in item['tables']:
            item['unchained_audits'] = con.execute('SELECT count(*) FROM audit WHERE id NOT IN (SELECT audit_id FROM audit_chain)').fetchone()[0]
            item['orphan_chain_rows'] = con.execute('SELECT count(*) FROM audit_chain WHERE audit_id NOT IN (SELECT id FROM audit)').fetchone()[0]
        con.close()
        item['stable_main_hash'] = before == hashlib.sha256(p.read_bytes()).hexdigest()
        item['wal_still_empty'] = not wal.exists() or wal.stat().st_size == 0
    except Exception as exc:
        item['error_category'] = type(exc).__name__
    rows.append(item)
(out / 'database-readonly.json').write_text(json.dumps(rows, indent=2))
print(json.dumps(rows, indent=2))
