import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import httpx

out = Path(__file__).resolve().parent
sources = {s['source_id']: s for s in json.loads(Path('configs/sources.json').read_text())['sources']}
queries = []
with httpx.Client(timeout=45, follow_redirects=True) as client:
    def query(name, source, params):
        url = sources[source]['source_url'] + '/query'
        params = {'f': 'json', **params}
        response = client.get(url, params=params)
        at = datetime.now(timezone.utc).isoformat()
        response.raise_for_status()
        (out / (name + '.json')).write_bytes(response.content)
        queries.append({'name': name, 'url': str(response.url), 'parameters': params, 'retrieved_at': at, 'sha256': hashlib.sha256(response.content).hexdigest()})
        (out / 'canonical-queries.json').write_text(json.dumps(queries, indent=2))
        body = response.json()
        if 'error' in body:
            raise ValueError(body['error'])
        return body
    body = query('hamad-reference', 'portwatch_ports', {'where': "UPPER(country) LIKE '%QATAR%' OR UPPER(portname) LIKE '%HAMAD%' OR UPPER(portname) LIKE '%DOHA%' OR LOCODE = 'QAHMD'", 'outFields': '*', 'returnGeometry': 'false'})
    print(json.dumps(body, indent=2))
