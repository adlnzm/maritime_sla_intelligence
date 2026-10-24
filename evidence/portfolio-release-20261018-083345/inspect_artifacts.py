"""Read-only bounded screening; outputs paths/categories, never matched values."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import zipfile

ROOT = Path.cwd()
OUT = Path(__file__).resolve().parent
LIMIT = 5_000_000
patterns = {
    'private_key_marker': rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
    'provider_token_candidate': rb'(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|AKIA[A-Z0-9]{16}|sk-[A-Za-z0-9_-]{30,})',
    'jwt_candidate': rb'eyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}',
    'credential_assignment_review': rb'(?i)(?:api[_-]?key|client[_-]?secret|password|accountkey|operator[_-]?key)\s*[=:]\s*[\x22\x27]?[A-Za-z0-9/+_-]{12,}',
    'connection_or_signed_url_review': rb'(?i)(?:AccountKey=|SharedAccessSignature=|[?&]sig=|https?://[^\s/:]+:[^\s/@]+@)',
    'local_identity_metadata': rb'(?i)(?:[A-Z]:[\\/]+Users[\\/]|/home/[^/\s]+/|hostname[\x22\x27]?\s*[:=])',
    'email_review': rb'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}',
    'private_network_reference': rb'(?i)(?:privatelink\.|https?://(?:10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|172\.(?:1[6-9]|2\d|3[01])\.\d+\.\d+))',
}
hits = []
inventory = []
skipped = []

def scan(label, body, scope):
    if b'\x00' in body[:4096]:
        skipped.append({'path': label, 'scope': scope, 'reason': 'binary; not decoded'})
        return
    for category, pattern in patterns.items():
        matches = list(re.finditer(pattern, body))
        if matches:
            hits.append({'path': label, 'scope': scope, 'category': category,
                         'count': len(matches), 'first_line': body[:matches[0].start()].count(b'\n') + 1})

def archive(label, body_or_path, scope):
    import io
    with zipfile.ZipFile(io.BytesIO(body_or_path) if isinstance(body_or_path, bytes) else body_or_path) as z:
        total = 0
        for info in z.infolist():
            if info.is_dir():
                continue
            item = label + '!' + info.filename
            if info.file_size > LIMIT or total + info.file_size > 100_000_000:
                skipped.append({'path': item, 'scope': scope, 'reason': 'archive size bound'})
                continue
            if info.flag_bits & 1:
                skipped.append({'path': item, 'scope': scope, 'reason': 'encrypted'})
                continue
            total += info.file_size
            scan(item, z.read(info), scope + '-archive')

for base, dirs, names in os.walk(ROOT):
    dirs[:] = [d for d in dirs if d not in ('.git', '.venv', '__pycache__', '.pytest_cache', '.ruff_cache', 'node_modules') and not d.startswith('release-environment-') and Path(base, d).resolve() != OUT]
    for name in names:
        path = Path(base, name)
        rel = path.relative_to(ROOT).as_posix()
        size = path.stat().st_size
        inventory.append({'path': rel, 'bytes': size})
        if path.suffix.lower() in ('.zip', '.whl'):
            try:
                archive(rel, path, 'working-tree')
            except Exception as exc:
                skipped.append({'path': rel, 'reason': type(exc).__name__})
        elif size <= LIMIT:
            scan(rel, path.read_bytes(), 'working-tree')
        else:
            skipped.append({'path': rel, 'reason': 'file size bound'})

objects = subprocess.check_output(['git', 'rev-list', '--objects', '--all']).splitlines()
blobs = 0
object_names = {line.partition(b' ')[0]: line.partition(b' ')[2] for line in objects}
metadata_lines = subprocess.run(['git', 'cat-file', '--batch-check'], input=b'\n'.join(object_names) + b'\n', capture_output=True, check=True).stdout.splitlines()
eligible = []
for metadata_line in metadata_lines:
    oid, kind, size_raw = metadata_line.split()
    name = object_names[oid]
    if kind != b'blob':
        continue
    blobs += 1
    label = oid.decode() + ':' + name.decode('utf-8', errors='replace')
    size = int(size_raw)
    if size > LIMIT:
        skipped.append({'path': label, 'scope': 'git-history', 'reason': 'blob size bound'})
        continue
    eligible.append((oid, name, size, label))
batch = subprocess.run(['git', 'cat-file', '--batch'], input=b'\n'.join(x[0] for x in eligible) + b'\n', capture_output=True, check=True).stdout
offset = 0
for oid, name, size, label in eligible:
    header_end = batch.index(b'\n', offset)
    body = batch[header_end + 1:header_end + 1 + size]
    offset = header_end + 1 + size + 1
    if name.lower().endswith((b'.zip', b'.whl')):
        try:
            archive(label, body, 'git-history')
        except Exception as exc:
            skipped.append({'path': label, 'reason': type(exc).__name__})
    else:
        scan(label, body, 'git-history')

# Inspect author/committer metadata without publishing identities.
metadata = subprocess.check_output(['git', 'log', '--all', '--format=%H%x09%an%x09%ae%x09%cn%x09%ce'])
scan('git log --all author/committer metadata (identities withheld)', metadata, 'git-metadata')
source = json.loads((ROOT / 'evidence/local-release-20261017-freshness-01/result.json').read_text())['source']
changed = [p for p, digest in source.items() if hashlib.sha256((ROOT / p).read_bytes()).hexdigest() != digest]
result = {'findings': hits, 'inventory': inventory, 'not_content_assessed': skipped,
          'reachable_history_blobs': blobs, 'reachable_commits': int(subprocess.check_output(['git', 'rev-list', '--count', '--all'])),
          'source_hashes_checked': len(source), 'changed_source_paths': changed,
          'exclusions': ['.git internals except reachable Git blobs and author/committer metadata', '.venv', 'release-environment-*', 'node_modules', 'Python/tool caches', 'this new evidence directory'],
          'limits': {'file_bytes': LIMIT, 'archive_total_bytes': 100_000_000},
          'warning': 'Heuristic screening is not a secret-free certification; binary bodies and all recorded exclusions remain unassessed. No matched values are emitted.'}
(OUT / 'artifact-screening.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps({'files_inventoried': len(inventory), 'history_blobs': blobs, 'findings': len(hits), 'not_content_assessed': len(skipped), 'changed_source_paths': changed}))
