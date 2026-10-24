"""Six read-only one-record official queries, no retries or ingestion."""
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import time
import urllib.error
import urllib.parse
import urllib.request

OUT = Path(__file__).resolve().parent
prior = json.loads(Path('evidence/freshness-diagnosis-20261017-131acd0c/diagnosis.json').read_text())
base = 'https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/Daily_Ports_Data/FeatureServer/0/query'
results = []
for port in prior['live_ports']:
    query = urllib.parse.urlencode({'f': 'json', 'where': "portid='" + port['port_id'] + "'", 'outFields': 'portid,date,portcalls', 'returnGeometry': 'false', 'orderByFields': 'date DESC', 'resultRecordCount': 1})
    item = {'port_id': port['port_id'], 'name': port['name'], 'url': base + '?' + query,
            'retrieved_at': datetime.now(timezone.utc).isoformat(), 'as_of': '2026-10-18',
            'prior_source_date': port['source_observation_date'], 'freshness_days': 10}
    try:
        with urllib.request.urlopen(item['url'], timeout=20) as response:
            body = response.read(65537)
            item['http_status'] = response.status
        if len(body) > 65536:
            raise ValueError('Response exceeds bounded sample')
        raw = OUT / ('latest-' + port['port_id'] + '.json')
        raw.write_bytes(body)
        item['raw_file'] = raw.name
        item['sha256'] = hashlib.sha256(body).hexdigest()
        value = json.loads(body)
        assert 'error' not in value and len(value['features']) == 1
        attrs = value['features'][0]['attributes']
        assert attrs['portid'] == port['port_id']
        observed = date.fromisoformat(attrs['date'])
        item['source_observation_date'] = attrs['date']
        item['age_days'] = (date(2026, 10, 18) - observed).days
        item['freshness_pass'] = 0 <= item['age_days'] <= 10
    except Exception as exc:
        item['error_category'] = type(exc).__name__
        if isinstance(exc, urllib.error.HTTPError):
            item['http_status'] = exc.code
        item['freshness_pass'] = None
    results.append(item)
    time.sleep(1)
report = {'as_of': '2026-10-18', 'freshness_days': 10, 'ports': results,
          'all_six_fresh': all(x['freshness_pass'] is True for x in results),
          'scope': 'Latest-observation freshness only; not a full ingestion or release campaign. Retrieval timestamps are separate; dates are native source date-only fields.'}
(OUT / 'freshness.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(report, indent=2))
raise SystemExit(0 if report['all_six_fresh'] else 1)
