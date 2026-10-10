"""Public adapters retain exact HTTP responses; failed requests never return fake records."""

import csv
import hashlib
import io
import time
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx

from maritime.models import stable_id, utcnow


class SourceError(RuntimeError):
    """Source unavailable or source contract violated."""


class Fetcher:
    def __init__(self, root, client=None, sleep=time.sleep):
        self.root = Path(root)
        self.client = client or httpx.Client(timeout=45, follow_redirects=True)
        self.sleep = sleep
        self.events = []
        self.retries = 0
        self.timeouts = 0
        self.open_circuits = set()

    def get(self, source_id, url, params=None):
        if source_id in self.open_circuits:
            raise SourceError(f"{source_id}: circuit open for this run after retry exhaustion")
        started = time.perf_counter()
        for attempt in range(4):
            try:
                response = self.client.get(url, params=params)
                if response.status_code == 429 or response.status_code >= 500:
                    response.raise_for_status()
                response.raise_for_status()
                checksum = hashlib.sha256(response.content).hexdigest()
                folder = self.root / "bronze" / source_id
                folder.mkdir(parents=True, exist_ok=True)
                path = folder / (checksum + ".raw")
                duplicate = path.exists()
                if duplicate and hashlib.sha256(path.read_bytes()).hexdigest() != checksum:
                    raise SourceError("Existing Bronze content was modified")
                if not duplicate:
                    path.write_bytes(response.content)
                event = {
                    "acquisition_id": stable_id(source_id, utcnow(), params),
                    "request_parameters": params or {},
                    "response_status": response.status_code,
                    "duplicate_payload": duplicate,
                    "source_timestamp": response.headers.get("Last-Modified"),
                    "source_id": source_id,
                    "source_url": str(response.url),
                    "retrieved_at": utcnow(),
                    "checksum": checksum,
                    "raw_path": str(path),
                    "bytes": len(response.content),
                    "duration_seconds": time.perf_counter() - started,
                    "retries": attempt,
                    "status": "SUCCESS",
                    "dataset_version": response.headers.get("etag"),
                }
                self.events.append(event)
                return response, event
            except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                if isinstance(exc, httpx.TimeoutException):
                    self.timeouts += 1
                retryable = (
                    isinstance(exc, httpx.TransportError)
                    or exc.response.status_code == 429
                    or exc.response.status_code >= 500
                )
                if attempt == 3 or not retryable:
                    self.open_circuits.add(source_id)
                    self.events.append(
                        {
                            "source_id": source_id,
                            "source_url": url,
                            "retrieved_at": utcnow(),
                            "status": "FAILED",
                            "error": type(exc).__name__,
                            "retries": attempt,
                            "duration_seconds": time.perf_counter() - started,
                        }
                    )
                    raise SourceError(f"{source_id}: {type(exc).__name__}") from exc
                self.retries += 1
                retry_after = (
                    exc.response.headers.get("Retry-After", "")
                    if isinstance(exc, httpx.HTTPStatusError)
                    else ""
                )
                self.sleep(min(60, float(retry_after)) if retry_after.isdigit() else 2**attempt)

    def arcgis(self, source, where, fields="*", order="ObjectId"):
        rows = []
        expected = None
        if source.get("reconcile_count"):
            response, event = self.get(
                source["source_id"],
                source["source_url"] + "/query",
                {"f": "json", "where": where, "returnCountOnly": "true"},
            )
            body = response.json()
            if not isinstance(body.get("count"), int) or body["count"] < 0:
                raise SourceError("Source count query failed")
            expected = body["count"]
            event["record_count"] = 0
            event["expected_extract_count"] = expected
        seen_pages = set()
        offset = 0
        while True:
            response, event = self.get(
                source["source_id"],
                source["source_url"] + "/query",
                {
                    "f": "json",
                    "where": where,
                    "outFields": fields,
                    "returnGeometry": "false",
                    "orderByFields": order,
                    "resultOffset": offset,
                    "resultRecordCount": 1000,
                },
            )
            body = response.json()
            if "error" in body or "features" not in body:
                raise SourceError(
                    f"{source['source_id']}: ArcGIS contract error: {body.get('error')}"
                )
            page = [f["attributes"] for f in body["features"]]
            page_hash = stable_id(page)
            if page and page_hash in seen_pages:
                raise SourceError("Repeated pagination page")
            seen_pages.add(page_hash)
            if len(seen_pages) > 10000:
                raise SourceError("Pagination bound exceeded")
            for row in page:
                missing = set(source["required_fields"]) - row.keys()
                if missing:
                    raise SourceError(f"{source['source_id']}: missing fields {missing}")
                row["_metadata"] = event
            rows.extend(page)
            event["record_count"] = len(page)
            if not body.get("exceededTransferLimit"):
                break
            if not page:
                raise SourceError("Pagination did not advance")
            offset += len(page)
        if expected is not None and len(rows) != expected:
            raise SourceError(f"Partial extract: expected {expected}, received {len(rows)}")
        return rows


def provenance(row, source_id, classification="OBSERVED"):
    meta = row["_metadata"]
    return {
        "source_id": source_id,
        "classification": classification,
        "retrieved_at": meta["retrieved_at"],
        "lineage_id": meta["checksum"],
    }


def normalize_ports(rows):
    return [
        {
            "port_id": r["portid"],
            "name": r["portname"],
            "country": r["country"],
            "latitude": r["lat"],
            "longitude": r["lon"],
            "unlocode": r.get("LOCODE"),
            **provenance(r, "portwatch_ports"),
        }
        for r in rows
    ]


def normalize_activity(rows):
    output = []
    for r in rows:
        value = r["date"]
        day = (
            datetime.fromtimestamp(value / 1000, timezone.utc).date().isoformat()
            if isinstance(value, (int, float))
            else str(value)[:10]
        )
        output.append(
            {
                "port_id": r["portid"],
                "date": day,
                "vessel_calls": r["portcalls"],
                **provenance(r, "portwatch_activity"),
            }
        )
    return output


def ingest_portwatch(fetcher, registry, config, store, as_of):
    sources = {s["source_id"]: s for s in registry["sources"]}
    names = config["port_names"]
    quoted_names = ",".join("'" + n.replace("'", "''") + "'" for n in names)
    raw_ports = fetcher.arcgis(sources["portwatch_ports"], f"portname IN ({quoted_names})")
    ports = normalize_ports(raw_ports)
    if not ports:
        raise SourceError("No ports matched configured names")
    found = {p["name"] for p in ports}
    if set(names) - found:
        raise SourceError(f"Configured ports missing: {set(names) - found}")
    scope = stable_id(sorted(p["port_id"] for p in ports))
    prior = store.metadata("activity_cache:" + scope, [])
    begin = as_of - timedelta(days=config["history_days"])
    if prior:
        watermark = max(date.fromisoformat(r["date"]) for r in prior)
        # Re-read recent days for publisher revisions. Explicit full refresh clears cache.
        begin = max(begin, watermark - timedelta(days=config["revision_overlap_days"]))
    ids = ",".join("'" + p["port_id"].replace("'", "''") + "'" for p in ports)
    where = f"portid IN ({ids}) AND date >= DATE '{begin}' AND date <= DATE '{as_of}'"
    raw = fetcher.arcgis(sources["portwatch_activity"], where)
    current = normalize_activity(raw)
    keys = [(r["port_id"], r["date"]) for r in current]
    if len(keys) != len(set(keys)):
        raise SourceError("Duplicate/conflicting activity records before cache merge")
    if not current:
        raise SourceError("Unexpected empty critical activity extract")
    if any(not begin.isoformat() <= r["date"] <= as_of.isoformat() for r in current):
        raise SourceError("Source returned records outside extraction window")
    if len(prior) != len({(r["port_id"], r["date"]) for r in prior}):
        raise SourceError("Duplicate checkpoint entities")
    # Replace queried window entirely so publisher deletions also propagate.
    merged = {(r["port_id"], r["date"]): r for r in prior if r["date"] < begin.isoformat()}
    merged.update({(r["port_id"], r["date"]): r for r in current})
    lower = (as_of - timedelta(days=config["history_days"])).isoformat()
    activity = sorted(
        [r for r in merged.values() if lower <= r["date"] <= as_of.isoformat()],
        key=lambda r: (r["port_id"], r["date"]),
    )
    replaced = sum(r["date"] >= begin.isoformat() for r in prior)
    expired = sum(
        r["date"] < begin.isoformat() and not lower <= r["date"] <= as_of.isoformat() for r in prior
    )
    if len(prior) + len(current) != len(activity) + replaced + expired:
        raise SourceError("Incremental accounting discrepancy")
    if hasattr(fetcher, "events"):
        fetcher.events.append(
            {
                "source_id": "portwatch_activity",
                "status": "CANONICALIZED",
                "retrieved_at": utcnow(),
                "record_count": len(activity),
                "accounting": {
                    "input": len(prior) + len(current),
                    "persisted_expected": len(activity),
                    "replaced_revision_window": replaced,
                    "filtered_expired": expired,
                    "balanced": True,
                },
            }
        )
    # Caller commits checkpoint only after DQ succeeds.
    return ports, activity, ("activity_cache:" + scope, activity)


def ingest_optional(fetcher, source, ports, as_of):
    adapter = source["adapter"]
    sid = source["source_id"]
    if adapter == "weather":
        rows = []
        for port in ports:
            response, meta = fetcher.get(
                sid,
                source["source_url"],
                {
                    "latitude": port["latitude"],
                    "longitude": port["longitude"],
                    "start_date": (as_of - timedelta(days=10)).isoformat(),
                    "end_date": (as_of - timedelta(days=5)).isoformat(),
                    "daily": "wind_speed_10m_max",
                    "timezone": "UTC",
                },
            )
            body = response.json()
            for day, wind in zip(
                body["daily"]["time"], body["daily"]["wind_speed_10m_max"], strict=True
            ):
                if wind is None:
                    raise SourceError("Missing weather reanalysis value")
                rows.append(
                    {
                        "port_id": port["port_id"],
                        "date": day,
                        "wind_kmh": wind,
                        **provenance({"_metadata": meta}, sid, "DERIVED"),
                    }
                )
        return rows
    url = source.get("download_url") or (
        source.get("source_url") if adapter == "route_geojson" else None
    )
    if not url:
        return None
    response, meta = fetcher.get(sid, url)
    origin = provenance({"_metadata": meta}, sid, source["classification"])
    if adapter == "wpi_csv":
        records = list(csv.DictReader(io.StringIO(response.content.decode("utf-8-sig"))))
        if not records or set(source["required_fields"]) - records[0].keys():
            raise SourceError("WPI header contract mismatch")
        return [
            {
                "reference_id": r["World Port Index Number"],
                "name": r["Main Port Name"],
                "latitude": float(r["Latitude"]),
                "longitude": float(r["Longitude"]),
                "unlocode": r["UN/LOCODE"].replace(" ", ""),
                **origin,
            }
            for r in records
        ]
    if adapter == "unlocode_zip":
        rows = []
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            for name in archive.namelist():
                if not name.lower().endswith(".csv") or "code" not in name.lower():
                    continue
                for r in csv.reader(
                    io.StringIO(archive.read(name).decode("utf-8-sig", errors="strict"))
                ):
                    if len(r) >= 12 and len(r[1]) == 2 and len(r[2]) == 3:
                        rows.append(
                            {"unlocode": r[1] + r[2], "name": r[3], "function": r[6], **origin}
                        )
        if not rows:
            raise SourceError("UN/LOCODE archive contains no recognized location rows")
        return rows
    if adapter == "route_geojson":
        body = response.json()
        if body.get("type") != "FeatureCollection":
            raise SourceError("Route source must be GeoJSON FeatureCollection")
        return [{**f["properties"], "geometry": f["geometry"], **origin} for f in body["features"]]
    raise SourceError(f"Unknown adapter {adapter}")
