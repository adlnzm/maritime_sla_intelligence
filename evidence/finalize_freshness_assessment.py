"""Verify the new campaign and seal this investigation's separate research evidence."""
import hashlib
import json
import zipfile
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

from maritime.release_evidence import verify_source

campaign = Path('evidence/local-release-20261017-freshness-01')
research = Path('evidence/official-source-assessment-20261017')
diagnosis = Path('evidence/freshness-diagnosis-20261017-131acd0c')
result = json.loads((campaign / 'result.json').read_text())
manifest = json.loads((campaign / 'evidence-manifest.json').read_text())
assert manifest['release'] == result
verify_source(result['source'])
with zipfile.ZipFile(str(campaign) + '.zip') as archive:
    assert archive.testzip() is None
    for name, digest in manifest['files'].items():
        assert hashlib.sha256((campaign / name).read_bytes()).hexdigest() == digest
        assert hashlib.sha256(archive.read(name)).hexdigest() == digest
    assert archive.read('evidence-manifest.json') == (campaign / 'evidence-manifest.json').read_bytes()
assert json.loads(Path('configs/pipeline.json').read_text())['freshness_days'] == 10
assert json.loads(Path('configs/governance.json').read_text())['freshness_days'] == 10
assert next(s for s in json.loads(Path('configs/sources.json').read_text())['sources'] if s['source_id']=='portwatch_activity')['freshness_days'] == 10
suite = ET.parse(campaign / 'tests.xml').getroot().find('testsuite').attrib
live = json.loads((campaign / 'live/release-validation.json').read_text())
docker = json.loads(next((campaign / 'docker').glob('*/result.json')).read_text())
ready = (result['status']=='LOCAL_READY' and result['source_integrity']=='PASS'
         and all(c['exit_code']==0 for c in result['commands'])
         and live.get('campaign',{}).get('status')=='PASS' and docker['status']=='PASS')
latest = {}
if (campaign / 'live/release-manifest.json').exists():
    latest = json.loads((campaign / 'live/release-manifest.json').read_text())['source_latest_by_port']
probe = json.loads((diagnosis / 'diagnosis.json').read_text())
ports = [{**p, 'campaign_observation_date':latest.get(p['port_id']),
          'campaign_age_days':(date(2026,10,17)-date.fromisoformat(latest[p['port_id']])).days if p['port_id'] in latest else None}
         for p in probe['live_ports']]
if ready:
    assert len(ports)==len(latest)==6 and all(0<=p['campaign_age_days']<=10 for p in ports)
summary = {'LOCAL_RELEASE_READY':'YES' if ready else 'NO', 'PRODUCTION_READY':'NO',
           'git_revision':result['git_revision'], 'working_tree':'DIRTY; prior work retained; no commit/reset',
           'campaign':str(campaign), 'campaign_status':result['status'], 'tests':suite,
           'source_files_verified':len(result['source']), 'evidence_files_verified':len(manifest['files']),
           'source_integrity':'PASS', 'evidence_integrity':'PASS', 'freshness_days':10,
           'independent_probe_freshness':'PASS' if probe['freshness_pass'] else 'FAIL',
           'ports':ports, 'docker':docker['status'], 'live_campaign':live.get('campaign',{}),
           'archive_sha256':hashlib.sha256(Path(str(campaign)+'.zip').read_bytes()).hexdigest(),
           'commands':result['commands']}
(research / 'verification.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
lines = ['# Final freshness and source assessment — 17 October 2026', '',
         f"**LOCAL_RELEASE_READY = {summary['LOCAL_RELEASE_READY']}**  ", '**PRODUCTION_READY = NO**', '',
         'The original failure and the current success are separate: retained October 14 responses genuinely ended October 2 (age 12); fresh October 17 requests now end October 9 (age 8). The source advanced. No date was rewritten and all three configured freshness limits remain 10.', '',
         'The narrow parser fix rejects malformed suffixes and ambiguous timestamps, and converts explicit timezone offsets to UTC before extracting the date. It fixes a reproduced acceptance/boundary defect, but did not cause PortWatch to publish newer data. Only `src/maritime/sources.py` and `tests/test_source_contracts.py` changed in application/test code for this workstream. Earlier dirty changes were preserved.', '',
         'Detailed diagnosis: [FINDINGS](../freshness-diagnosis-20261017-131acd0c/FINDINGS.md), [raw-probe manifest](../freshness-diagnosis-20261017-131acd0c/diagnosis.json). Source strategy: [comparison and recommendation](ASSESSMENT.md), [port/government details](ports.md), [international sources](international.md).', '',
         '| Port | ID | Current direct-source observation | Age on Oct 17 | Full campaign observation / age |',
         '|---|---|---|---:|---|']
for port in ports:
    lines.append(f"| {port['name']} | {port['port_id']} | {port['source_observation_date']} | {port['age_days']} | {port['campaign_observation_date']} / {port['campaign_age_days']} |")
lines += ['', f"Focused verification: 31 passed, zero failures. Full suite: {suite['tests']} tests, {suite['failures']} failures, {suite['errors']} errors, {suite['skipped']} skipped. One Starlette/httpx deprecation warning. Full campaign scope includes real Docker startup/auth/security/outage/restart/recovery, actual backup/restore, source and governance regression, publication concurrency, model contracts, lint/format/package build, dependency audit, Bicep and PBIR static validation, and live acquisition/replay/failure accounting.", '',
          f"Git revision `{result['git_revision']}` with dirty working tree. New campaign `{campaign}` status `{result['status']}`. Independently verified {len(result['source'])} source hashes and {len(manifest['files'])} evidence hashes in both directory and ZIP. Command arrays/timestamps/exits are in `verification.json` and the campaign manifest.", '',
          '| Campaign command | Exit code | Log |', '|---|---:|---|']
for command in result['commands']:
    lines.append(f"| {command['name']} | {command['exit_code']} | `{campaign / (command['name']+'.log')}` |")
lines += ['', 'Read-only official-source capture scripts exited 0 after retaining per-request results; HTTP outcomes include usable 200 data, 200 empty records, 200 rejection HTML, 401, 403 and 429. A capture-script success is not a provider acceptance. Exact request URLs, timestamps and body hashes are in the separate access manifests. The original diagnostic helper failed once because it assumed numeric dates; it was corrected to inspect actual date-only values, then completed with exit 0.', '',
          'No alternative provider was integrated. Retain PortWatch primary for the existing activity metric; propose a separate rights-reviewed LA operational corroboration pilot and approved Singapore/Rotterdam event-feed samples. Trade/tariff/throughput series belong in contextual tables, not fresh port-call or waiting-time fields. The exact previously recommended World Trade Center source remains ambiguous; WTCA GATRI was identified but is not assumed to be that recommendation.', '',
          'Production remains blocked by actual cloud/workspace deployment, identity and effective permissions, provider reuse rights, Power BI rendering/refresh, approved retention/locking, named owners and alert routing, and production backup/failover/SLO evidence. Shipment-SLA ML remains deferred. No new image-generation services/dependencies were introduced.', '',
          'Freshness is time-dependent: October 9 observations become eleven days old on October 20; absent newer data, the unchanged gate must block again. Full local acceptance does not establish sustained upstream timeliness, production deployment, or commercial shipment prediction accuracy.']
(research / 'FINAL_REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
for folder in (research, diagnosis):
    hashes = {p.relative_to(folder).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
              for p in folder.rglob('*') if p.is_file() and p.name!='assessment-checksums.json'}
    (folder / 'assessment-checksums.json').write_text(json.dumps(hashes,indent=2),encoding='utf-8')
print(json.dumps({key:summary[key] for key in ('LOCAL_RELEASE_READY','PRODUCTION_READY','campaign_status','tests','source_files_verified','evidence_files_verified')},indent=2))
