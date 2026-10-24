import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import httpx

out = Path(__file__).resolve().parent
reference = json.loads((out / 'hamad-reference.json').read_text())['features']
matches = [f['attributes'] for f in reference if (f['attributes'].get('LOCODE') or '').replace(' ', '') == 'QAHMD' and f['attributes']['country'] == 'Qatar']
assert len(matches) == 1
port = matches[0]
sources = {s['source_id']: s for s in json.loads(Path('configs/sources.json').read_text())['sources']}
url = sources['portwatch_activity']['source_url'] + '/query'
queries = json.loads((out / 'canonical-queries.json').read_text())
with httpx.Client(timeout=45) as client:
    for name, extra in [
        ('hamad-activity-range', {'outStatistics': json.dumps([{'statisticType': kind, 'onStatisticField': field, 'outStatisticFieldName': alias} for kind,field,alias in [('min','date','first_date'),('max','date','latest_date'),('count','date','observations')]])}),
        ('hamad-activity-latest', {'outFields': '*', 'orderByFields': 'date DESC', 'resultRecordCount': 14, 'returnGeometry': 'false'}),
    ]:
        params = {'f':'json', 'where': "portid = '" + port['portid'] + "'", **extra}
        response = client.get(url, params=params)
        response.raise_for_status()
        (out / (name + '.json')).write_bytes(response.content)
        queries.append({'name': name, 'url': str(response.url), 'parameters':params,'retrieved_at':datetime.now(timezone.utc).isoformat(),'sha256':hashlib.sha256(response.content).hexdigest()})
        body = response.json()
        assert 'error' not in body, body
        print(name, json.dumps(body['features'][:2]))
(out / 'canonical-queries.json').write_text(json.dumps(queries, indent=2))
