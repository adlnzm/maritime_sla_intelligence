"""Verify reused evidence and preserve the source baseline; no network or ingestion."""
import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

from maritime.release_evidence import source_snapshot

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
OLD = ROOT / 'evidence/official-source-assessment-20261017'


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def write(name, value):
    (HERE / name).write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


baseline = read(HERE / 'source-before.json')
assert source_snapshot() == baseline, 'Source changed during assessment'
assert read(ROOT / 'configs/governance.json')['freshness_days'] == 10
assert read(ROOT / 'evidence/local-release-20261017-freshness-01/result.json')['source'] == baseline
captures = read(OLD / 'international-access.json')
for capture in captures:
    path = OLD / (capture['name'] + '.response')
    body = path.read_bytes()
    assert hashlib.sha256(body).hexdigest() == capture['sha256'], path
    assert len(body) == capture['bytes'], path
    capture['retained_path'] = path.relative_to(ROOT).as_posix()
    capture['checksum_verified'] = True
annual = read(OLD / 'comtrade-annual-retry.response')
assert annual['count'] == len(annual['data']) == 1 and not annual['error']
row = annual['data'][0]
assert (row['period'], row['freqCode'], row['reporterCode']) == ('2025', 'A', 702)
assert row['isAggregate'] and not row['isReported']
assert read(OLD / 'comtrade-preview.response')['count'] == 0
write('sample-verification.json', captures)
suite = ET.parse(HERE / 'tests-authorized.xml').getroot().find('testsuite')
totals = {key: int(suite.attrib[key]) for key in ('tests', 'failures', 'errors', 'skipped')}
assert totals == {'tests': 28, 'failures': 0, 'errors': 0, 'skipped': 0}
assert (HERE / 'tests-authorized.exitcode').read_text(encoding='utf-8-sig').strip() == '0'
status = subprocess.run(['git', 'status', '--porcelain=v1', '-uall'], capture_output=True, check=True).stdout.decode('utf-8')
(HERE / 'git-status-after.txt').write_text(status, encoding='utf-8')
before = (HERE / 'git-status-before.txt').read_text(encoding='utf-8-sig').splitlines()
assert set(before).issubset(set(status.splitlines())), 'Existing Git status entries disappeared'
write('verification.json', {
    'status': 'PASS', 'provider_integrated': False,
    'source_files_unchanged': len(baseline), 'matches_completed_release_source': True,
    'freshness_days': 10, 'retained_http_bodies_verified': len(captures),
    'tests': totals, 'warnings': 1,
    'commands': [
        {'command': '.venv/Scripts/python.exe -m pytest tests/test_source_contracts.py tests/test_governance.py -q --junitxml=evidence/trade-qualification-20261017-160824/tests.xml', 'exit_code': 1, 'result': 'Sandbox attempt stalled without output; interrupted, not a passing test run'},
        {'command': '.venv/Scripts/python.exe -m pytest tests/test_source_contracts.py tests/test_governance.py -q --junitxml=evidence/trade-qualification-20261017-160824/tests-authorized.xml', 'exit_code': 0, 'result': '28 passed; 1 Starlette/httpx deprecation warning'},
        {'command': '.venv/Scripts/python.exe evidence/trade-qualification-20261017-160824/verify.py', 'result': 'Assertions complete; actual process exit captured in verify.exitcode'}
    ],
    'blockers': ['UN Comtrade mixed/external product redistribution applicability unresolved', 'WTO authorized usable sample and product-specific rights unverified', 'Trade publication/revision metadata, units and broader country coverage not fully qualified'],
    'release_claim': 'Assessment only; no new deployment or release-readiness claim'
})
manifest = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in HERE.iterdir() if p.is_file() and p.name not in ('manifest.json', 'verify.log', 'verify.exitcode')}
write('manifest.json', manifest)
assert all(hashlib.sha256((HERE / name).read_bytes()).hexdigest() == digest for name, digest in manifest.items())
print(json.dumps({'status': 'PASS', 'source_files_unchanged': len(baseline), 'http_bodies_verified': len(captures), 'manifest_files_verified': len(manifest), 'tests': totals}))
