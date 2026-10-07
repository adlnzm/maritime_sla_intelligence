"""Print public publisher names to resolve source configuration, no inferred aliases."""

import json

import httpx

url = "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/PortWatch_ports_database/FeatureServer/0/query"
response = httpx.get(
    url,
    params={
        "f": "json",
        "where": "portname LIKE '%Angeles%' OR portname LIKE '%York%' OR portname LIKE '%Long Beach%'",
        "outFields": "portid,portname,LOCODE",
        "returnGeometry": "false",
    },
    timeout=45,
)
response.raise_for_status()
print(json.dumps(response.json(), indent=2))
