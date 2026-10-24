"""Create a separate auditable assessment; never modifies a sealed campaign."""
import hashlib
import json
import sqlite3
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

from maritime.release_evidence import verify_source

root = Path('evidence/local-release-20261014-final')
out = Path('evidence/acceptance-20261014')
out.mkdir(exist_ok=False)
result = json.loads((root / 'result.json').read_text())
manifest = json.loads((root / 'evidence-manifest.json').read_text())
assert manifest['release'] == result
assert result['source_integrity'] == 'PASS'
verify_source(result['source'])
with zipfile.ZipFile(str(root) + '.zip') as archive:
    assert archive.testzip() is None
    for name, digest in manifest['files'].items():
        assert hashlib.sha256((root / name).read_bytes()).hexdigest() == digest
        assert hashlib.sha256(archive.read(name)).hexdigest() == digest
    assert archive.read('evidence-manifest.json') == (root / 'evidence-manifest.json').read_bytes()
suite = ET.parse(root / 'tests.xml').getroot().find('testsuite').attrib
commands = {item['name']: item for item in result['commands']}
docker_path = next((root / 'docker').glob('*/result.json'))
docker = json.loads(docker_path.read_text())
audit = json.loads((root / 'dependency-audit.json').read_text())
vulnerabilities = sum(len(item.get('vulns', [])) for item in audit['dependencies'])
live = json.loads((root / 'live/release-validation.json').read_text())
failures = list((root / 'live/failed-reports').glob('*/report.json'))
dq = json.loads(failures[0].read_text())['data_quality'] if failures else {}
live_command = commands['live']['command']
live_root = Path(live_command[live_command.index('--root') + 1])
with sqlite3.connect((live_root / 'maritime.db').resolve().as_uri() + '?mode=ro', uri=True) as con:
    published = con.execute("SELECT value FROM metadata WHERE key='published_run'").fetchone()
assert published is None, 'Failed fresh live campaign must not publish a run'
summary = {
    'LOCAL_RELEASE_READY': 'YES' if result['status'] == 'LOCAL_READY' else 'NO',
    'PRODUCTION_READY': 'NO', 'git_revision': result['git_revision'],
    'source_state': 'DIRTY: preserved tracked modifications and untracked implementation',
    'source_files_verified': len(result['source']), 'campaign': str(root),
    'campaign_status': result['status'], 'tests': suite,
    'vulnerabilities_reported': vulnerabilities,
    'docker_status': docker['status'], 'docker_checks': docker['checks'],
    'manifest_files_verified': len(manifest['files']),
    'archive_sha256': hashlib.sha256(Path(str(root)+'.zip').read_bytes()).hexdigest(),
    'source_integrity': 'PASS', 'evidence_integrity': 'PASS',
    'live_failure': live.get('mandatory_failed_controls', []),
    'latest_by_port': dq.get('latest_by_port'),
    'dependency_lock_sha256': result['source']['uv.lock'],
}
(out / 'verification.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
external = {
    'SRC-04': 'Optional approved source downloads/URLs absent; configure and execute WPI, UN/LOCODE and reference geometry.',
    'GOV-06': 'Owner-approved retention/lock and effective target permissions/expiry evidence required.',
    'SLA-02': 'Deferred by design: representative observed shipment outcomes and label approval unavailable.',
    'ML-04': 'Azure ML workspace, compute/quota, runner permissions and real jobs/registration/promotion required.',
    'ML-05': 'Local inference contracts passed; real prediction return and Fabric Delta readback still required.',
    'GEN-02': 'Authorized Azure OpenAI endpoint/deployment, identity, quota and real round trip required.',
    'LRN-02': 'Local transfer/replay passed; actual Fabric notebook and persisted readback require target access.',
    'FAB-01': 'Notebook generation/contracts passed; actual capacity, Spark and Delta execution required.',
    'FAB-02': 'Static orchestration contracts passed; actual deployment/job execution required.',
    'BI-02': '29 PBIR files/5 pages validated; Desktop rendering, real model binding, RLS and refresh/publish required.',
    'AZ-01': 'Bicep compiled; tenant/resources/identity/secrets/network and deployed authentication tests required.',
    'OPS-02': 'Named owners/contacts, approved targets, deployed alert rules and received notifications required.',
}
matrix = []
for item in json.loads(Path('docs/requirements/production_acceptance.json').read_text())['gaps']:
    code = item['id']
    status = 'BLOCKED' if code in external else 'PASS'
    detail = external.get(code, 'Local contract/algorithm scope only; see current tests and campaign logs. No cloud runtime claim.')
    evidence = str(root / 'tests.xml')
    if code == 'ARCH-02':
        status, detail = 'NOT RUN', 'PostgreSQL is not an implemented or selected backend; SQLite local and Azure Blob target remain the declared architecture.'
    if code == 'OPS-04':
        evidence, detail = str(docker_path), 'Real clean Compose build/start, HTTP, dependency failure/recovery, restart and persistent audits passed.'
    if code == 'PC-06':
        evidence, detail = str(out / 'verification.json'), 'Final source hashes, all manifest entries and ZIP bytes independently verified.'
    if code == 'SRC-05':
        evidence, detail = str(root / 'live/failed-reports'), 'Weather acquisition succeeded; the overall live publication failed activity freshness.'
    if code in external:
        evidence = 'evidence/deployment-preflight-20261014.json; docs/operations/deployment_acceptance.md'
    matrix.append({'id':code, 'requirement':item['requirement'], 'status':status, 'evidence':evidence, 'scope_or_remediation':detail})
matrix.append({'id':'LIVE-FRESHNESS', 'requirement':'Current public-data release campaign', 'status':'FAIL',
               'evidence':str(root / 'live/failed-reports'),
               'scope_or_remediation':'Latest PortWatch observations are 2026-10-02 for all six ports, 12 days old against the unchanged 10-day gate. Obtain fresher source data, then rerun the complete campaign; do not relabel replay as live.'})
matrix.extend([
    {'id':'LIVE-FOLLOWUP', 'requirement':'Post-publication live replay/failure campaign', 'status':'NOT RUN', 'evidence':str(root / 'live/release-validation.json'), 'scope_or_remediation':'Initial live DQ blocked publication before these steps. Restore fresh source input and rerun.'},
    {'id':'OFFSITE-DR', 'requirement':'Offsite backup/failover and approved production RPO/RTO', 'status':'BLOCKED', 'evidence':'docs/operations/deployment_acceptance.md', 'scope_or_remediation':'Owner, targets, offsite destination, recovery identity and target restore/failover execution required.'},
    {'id':'IMAGES', 'requirement':'Application independence from optional image generation', 'status':'PASS', 'evidence':str(docker_path), 'scope_or_remediation':'No images generated and no image-generation service/dependencies/assets added; clean build/runtime independent of such an environment.'},
    {'id':'OS-SCAN', 'requirement':'Container operating-system vulnerability scan', 'status':'NOT RUN', 'evidence':str(root / 'dependency-audit.log'), 'scope_or_remediation':'Existing repository audit covers Python dependencies. OS-layer scanning is not configured; do not infer an OS vulnerability pass.'},
    {'id':'TYPECHECK', 'requirement':'Dedicated static type checker', 'status':'NOT RUN', 'evidence':'pyproject.toml', 'scope_or_remediation':'No standalone type checker is configured; lint/build/runtime contracts were executed.'},
])
(out / 'acceptance-matrix.json').write_text(json.dumps(matrix, indent=2), encoding='utf-8')
lines = [
    '# Final acceptance — 14 October 2026', '',
    f"**LOCAL_RELEASE_READY = {summary['LOCAL_RELEASE_READY']}**  ", '**PRODUCTION_READY = NO**', '',
    'The full release is not accepted. Live acquisition returned stale PortWatch observations and correctly failed six freshness checks. All 50 automated tests and the Docker workflow passed, but those successes do not override the failed live campaign.', '',
    f"Git revision: `{result['git_revision']}`. Dirty source preserved; {len(result['source'])} source/configuration/documentation files hashed. No commit or reset was performed.",
    f"Campaign: `{root}`. Final status: `{result['status']}`. Source equality and {len(manifest['files'])} evidence-file hashes plus ZIP contents independently verified. See `verification.json` for lock/archive hashes.", '',
    f"Tests: {suite['tests']}; failures {suite['failures']}; errors {suite['errors']}; skipped {suite['skipped']}. One Starlette/httpx deprecation warning. Unit, local integration/E2E, concurrency/publication, security boundaries, governance, inference integrity and actual filesystem/SQLite recovery are covered; cloud contracts use test doubles and do not certify cloud execution.", '',
    '## Executed command gates', '', '| Gate | Exit | Evidence |', '|---|---:|---|',
]
for name, command in commands.items():
    lines.append(f"| {name} | {command['exit_code']} | `{root / (name+'.log')}` |")
lines += ['',
    f"Docker `{docker['project']}`: clean no-cache/pull build, seed completion ordering, health/readiness, real HTTP auth/roles/body boundaries, actual database outage (503) with liveness (200), dependency recovery, restart/run identity, audit persistence and backup/restore passed. Runtime UID 10001, zero effective capabilities, no-new-privileges, read-only root and 1 GiB/1 CPU/128 PID API limits verified. Containers are stopped; disposable volumes retained.", '',
    'Package consistency checked 112 installed packages. Python dependency audit reported zero known vulnerabilities, with two advisory no-deps/hash warnings. Lint, format, wheel/sdist build and generated notebooks passed. Bicep compilation completed without warnings. PBIR validation covered 29 files and five pages against vendored official schemas; Desktop/model/refresh remain blocked.', '',
    'Backup/restore used actual disposable data. SHA-256, SQLite integrity, approved products/publication and audit chains were validated. Tests reject existing/overlapping destinations and corrupt input before creating a restore destination. This is local functional recovery, not disaster recovery, offsite durability or production RPO/RTO.', '',
    'Root cause of the 11 October failure: missing Docker Desktop Linux engine pipe; no image build occurred. Cleanup then masked the original error and omitted Docker result evidence. Engine startup and evidence-finalization handling were corrected. Health now probes readiness, and logging no longer rereads a failed database or attributes an old response to a newly published run. Three concurrent publication regression cases use real SQLite publication and verify reads/review/outcome audit identities.', '',
    'Final live failure: all six ports latest 2 October versus requested 14 October, exceeding the unchanged 10-day freshness limit. Failed reports and raw responses are retained under live/failed-reports and live/failed-bronze. No stale run was published. Prior interim campaigns remain preserved and are not evidence of final-source acceptance.', '',
    '## Requirement acceptance matrix', '',
    'PASS below means only the stated executed local scope. BLOCKED cloud rows require target evidence before production acceptance.', '',
    '| ID | Requirement | Status | Evidence and remediation/scope |', '|---|---|---|---|',
]
for item in matrix:
    lines.append(f"| {item['id']} | {item['requirement']} | {item['status']} | `{item['evidence']}` — {item['scope_or_remediation']} |")
lines += ['', '## Deployment handoff and limitations', '',
    'Use `docs/operations/deployment_acceptance.md` in order for required values, least-privilege roles, owner actions, commands, expected evidence and rollback. Read-only preflight exited 1: Azure CLI and all required tenant/subscription/resource/Fabric/AML/OpenAI settings were absent. Install Azure CLI and configure/authenticate the approved target before running its preflight; process-local PowerShell execution may require `-ExecutionPolicy Bypass` under the local execution policy.', '',
    'All Azure deployment/Entra, Fabric, AML, Azure OpenAI, Power BI Desktop/service, locked retention/expiry, effective denial, alert delivery, offsite recovery/failover and SLO gates are BLOCKED — DEPLOYMENT ACTION REQUIRED. Network/private registry configuration and final report/model setup remain target configuration work. No retention approval, operational owner, production model approval, RPO/RTO or performance target has been invented.', '',
    'Shipment-SLA ML remains deferred. Port calls are activity proxies, not measured waiting/dwell times; reference geometry is not observed vessel traffic; simulated shipment losses/labels are not commercial outcomes. Port-call forecasts do not validate shipment-SLA prediction.', '',
    'To re-attempt acceptance: obtain fresh PortWatch input, keep the 10-day contract unchanged, and execute `python scripts/production_release.py --output evidence/<new-unique-directory> --live`. Require all gates, unchanged source and verified manifest before changing the local claim to YES. Production additionally requires every target gate and owner approval.',
]
(out / 'FINAL_ACCEPTANCE.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
(out / 'checksums.json').write_text(json.dumps({p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir() if p.is_file()}, indent=2), encoding='utf-8')
print(json.dumps(summary, indent=2))
