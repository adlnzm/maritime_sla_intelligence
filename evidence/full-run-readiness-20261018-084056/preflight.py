"""Read-only snapshot; never construct Store or open a writable DB."""
from datetime import datetime, timezone
import hashlib
import importlib.metadata as metadata
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys

OUT = Path(__file__).resolve().parent
result = {'observed_at': datetime.now(timezone.utc).isoformat(), 'python': sys.version, 'commands': [], 'databases': []}
commands = [
    ['docker', 'version', '--format', '{{json .Server}}'],
    ['docker', 'compose', 'ls', '--all', '--format', 'json'],
    ['docker', 'ps', '-a', '--format', '{{.ID}}\t{{.Names}}\t{{.Status}}\t{{.Ports}}'],
    ['docker', 'volume', 'ls', '--format', '{{.Name}}'],
    ['uv', 'pip', 'check', '--python', '.venv/Scripts/python.exe'],
]
for cmd in commands:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
        result['commands'].append({'command': cmd, 'exit_code': p.returncode, 'stdout': p.stdout, 'stderr': p.stderr})
    except Exception as exc:
        result['commands'].append({'command': cmd, 'error_category': type(exc).__name__, 'exit_code': None})
result['dependencies'] = {}
for name in ('maritime-sla-intelligence', 'fastapi', 'httpx', 'numpy', 'pandas', 'scikit-learn', 'uvicorn'):
    try:
        result['dependencies'][name] = metadata.version(name)
    except metadata.PackageNotFoundError:
        result['dependencies'][name] = 'MISSING'
result['candidate_roots'] = {'default_data': Path('data').exists(), 'documented_live_data': Path('data/live').exists()}
for path in Path('data').rglob('maritime.db'):
    entry = {'path': path.as_posix(), 'bytes': path.stat().st_size, 'wal_bytes': Path(str(path) + '-wal').stat().st_size if Path(str(path) + '-wal').exists() else 0,
             'lock_file_exists': (path.parent / '.pipeline.lock').exists()}
    if entry['wal_bytes']:
        entry['status'] = 'NOT_TESTED: WAL present; no unsafe immutable-main-only conclusion'
        result['databases'].append(entry)
        continue
    if entry['bytes'] > 100_000_000:
        entry['status'] = 'NOT_TESTED: bounded inspection size limit'
        result['databases'].append(entry)
        continue
    try:
        # Deserialize captured bytes into an in-memory DB: no source journal/SHM writes.
        before = hashlib.sha256(path.read_bytes()).hexdigest()
        con = sqlite3.connect(':memory:')
        con.deserialize(path.read_bytes())
        # WAL-format database images cannot always be deserialized; failure is retained.
        entry['user_version'] = con.execute('PRAGMA user_version').fetchone()[0]
        entry['integrity'] = con.execute('PRAGMA quick_check').fetchone()[0]
        entry['tables'] = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        entry['run_status_counts'] = dict(con.execute('SELECT status,count(*) FROM runs GROUP BY status'))
        entry['metadata_keys'] = [r[0] for r in con.execute('SELECT key FROM metadata')]
        entry['checkpoints'] = []
        for key, value in con.execute('SELECT key,value FROM metadata'):
            if key.startswith('activity_cache:'):
                rows = json.loads(value)
                entry['checkpoints'].append({'key': key, 'rows': len(rows), 'latest_date': max((r['date'] for r in rows), default=None), 'duplicate_keys': len(rows) - len({(r['port_id'], r['date']) for r in rows})})
            elif key == 'published_run':
                entry['published_run'] = json.loads(value)
        con.close()
        assert before == hashlib.sha256(path.read_bytes()).hexdigest()
        entry['status'] = 'READ_ONLY_SNAPSHOT'
    except Exception as exc:
        entry['error_category'] = type(exc).__name__
        entry['status'] = 'NOT_TESTED: in-memory image not readable; source untouched'
    result['databases'].append(entry)
source = json.loads(Path('evidence/local-release-20261017-freshness-01/result.json').read_text())['source']
result['source_mismatches'] = [p for p, digest in source.items() if hashlib.sha256(Path(p).read_bytes()).hexdigest() != digest]
result['source_hash_count'] = len(source)
result['free_bytes'] = shutil.disk_usage('.').free
(OUT / 'preflight.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps(result, indent=2))
