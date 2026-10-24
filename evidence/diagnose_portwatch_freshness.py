"""Read retained evidence and query source maxima independently of application caches."""
import hashlib
import json
import sqlite3
import subprocess
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

import httpx

from maritime.sources import normalize_activity

root = Path('evidence') / ('freshness-diagnosis-20261017-' + uuid.uuid4().hex[:8])
root.mkdir()
old = Path('evidence/local-release-20261014-final')
report = json.loads(next((old / 'live/failed-reports').glob('*/report.json')).read_text())
registry = json.loads(Path('configs/sources.json').read_text())
endpoint = next(s['source_url'] for s in registry['sources'] if s['source_id']=='portwatch_activity')
as_of = date(2026, 10, 14)
ports, rows, events = {}, [], []
for event in report['source_status']:
    if event.get('source_id') not in {'portwatch_ports', 'portwatch_activity'} or 'checksum' not in event:
        continue
    raw = old / 'live/failed-bronze' / event['source_id'] / (event['checksum'] + '.raw')
    assert hashlib.sha256(raw.read_bytes()).hexdigest() == event['checksum']
    body = json.loads(raw.read_bytes())
    events.append({key:event.get(key) for key in ('source_id','source_url','retrieved_at','checksum','request_parameters','record_count','expected_extract_count')})
    for feature in body.get('features', []):
        row = feature['attributes']
        if event['source_id'] == 'portwatch_ports':
            ports[row['portid']] = row['portname']
        else:
            rows.append({**row, '_metadata':event})
normalized = normalize_activity(rows)
retained = []
for port, name in sorted(ports.items()):
    raw_max = max((r for r in rows if r['portid']==port), key=lambda r:r['date'])
    stamp = datetime.fromisoformat(raw_max['date']).replace(tzinfo=timezone.utc) if isinstance(raw_max['date'], str) else datetime.fromtimestamp(raw_max['date']/1000, timezone.utc)
    canonical = max(r['date'] for r in normalized if r['port_id']==port)
    assert stamp.date().isoformat() == canonical == report['data_quality']['latest_by_port'][port]
    retained.append({'port_id':port, 'name':name, 'raw_date':raw_max['date'], 'source_observation_date':stamp.date().isoformat(), 'canonical_date':canonical, 'age_days':(as_of-stamp.date()).days, 'retrieved_at':raw_max['_metadata']['retrieved_at'], 'source_url':raw_max['_metadata']['source_url']})
campaign = json.loads((old / 'result.json').read_text())
cmd = next(c['command'] for c in campaign['commands'] if c['name']=='live')
db = Path(cmd[cmd.index('--root')+1]) / 'maritime.db'
with sqlite3.connect(db.resolve().as_uri()+'?mode=ro', uri=True) as con:
    metadata = [r[0] for r in con.execute('SELECT key FROM metadata')]
    persisted_dq = json.loads(con.execute("SELECT payload FROM products WHERE product='data_quality'").fetchone()[0])
assert persisted_dq['latest_by_port'] == report['data_quality']['latest_by_port']
assert not any(key.startswith('activity_cache:') or key=='published_run' for key in metadata)
summary = {'as_of':str(as_of), 'live_as_of':'2026-10-17', 'freshness_days':10, 'retained':retained, 'retained_events':events,
           'retained_rows':len(rows), 'no_persisted_checkpoint_or_publication':True,
           'git_revision':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(), 'probes':[]}
(root / 'retained-analysis.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
with httpx.Client(timeout=60, follow_redirects=True, headers={'Cache-Control':'no-cache'}) as client:
    def probe(name, url, params):
        at = datetime.now(timezone.utc).isoformat()
        response = client.get(url, params=params)
        (root / (name+'.json')).write_bytes(response.content)
        record = {'name':name, 'url':str(response.url), 'retrieved_at':at, 'http_status':response.status_code,
                  'sha256':hashlib.sha256(response.content).hexdigest(),
                  'headers':{k:v for k,v in response.headers.items() if k.lower() in {'date','age','last-modified','etag','cache-control'}}}
        summary['probes'].append(record)
        (root / 'diagnosis.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
        response.raise_for_status()
        body = response.json()
        if 'error' in body:
            raise ValueError(body['error'])
        return body
    layer = probe('layer-metadata', endpoint, {'f':'json'})
    summary['layer_identity'] = {k:layer.get(k) for k in ('name','serviceItemId','dateFieldsTimeReference','editingInfo','maxRecordCount','advancedQueryCapabilities')}
    summary['live_ports'] = []
    for port, name in sorted(ports.items()):
        latest = probe('latest-'+port, endpoint+'/query', {'f':'json','where':f"portid = '{port}'", 'outFields':'portid,date,portcalls', 'orderByFields':'date DESC', 'resultRecordCount':1,'returnGeometry':'false'})
        recent = probe('recent-count-'+port, endpoint+'/query', {'f':'json','where':f"portid = '{port}' AND date >= DATE '2026-10-07' AND date <= DATE '2026-10-17'",'returnCountOnly':'true'})
        row = latest['features'][0]['attributes']
        stamp = datetime.fromisoformat(row['date']).replace(tzinfo=timezone.utc) if isinstance(row['date'], str) else datetime.fromtimestamp(row['date']/1000, timezone.utc)
        summary['live_ports'].append({'port_id':port,'name':name,'source_observation_date':stamp.date().isoformat(),'age_days':(date(2026,10,17)-stamp.date()).days,'fresh_window_count':recent['count'],'raw_date':row['date']})
    item_id = layer.get('serviceItemId')
    if item_id:
        probe('arcgis-item',f'https://www.arcgis.com/sharing/rest/content/items/{item_id}',{'f':'json'})
summary['freshness_pass'] = all(0<=p['age_days']<=10 and p['fresh_window_count']>0 for p in summary['live_ports'])
(root / 'diagnosis.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
print(json.dumps({'output':str(root),'retained':retained,'live_ports':summary['live_ports'],'freshness_pass':summary['freshness_pass']},indent=2))
