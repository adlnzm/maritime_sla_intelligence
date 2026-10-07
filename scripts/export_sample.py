"""Export only actual retained observations for a portable replay, with source hashes."""
import argparse
import json
from pathlib import Path

from maritime.store import Store

parser = argparse.ArgumentParser()
parser.add_argument("--data-dir", default="data")
parser.add_argument("--output", default="tests/data/portwatch_sample.json")
args = parser.parse_args()
store = Store(args.data_dir)
report = store.latest_report()
if not report or report["status"] != "SUCCESS":
    raise SystemExit("A successful public run is required before exporting a replay sample")
ports, activity = store.read("ports"), store.read("activity")
for rows in (ports, activity):
    for row in rows:
        row.pop("run_id", None)
        if row["classification"] != "OBSERVED":
            raise ValueError("Only real observed public records may be exported here")
events = [{k: v for k, v in event.items() if k != "raw_path"} for event in report["source_status"]]
bundle = {"as_of": report["as_of"], "ports": ports, "activity": activity, "source_status": events,
          "description": "Unmodified normalized public PortWatch observations. Source hashes identify raw retained responses. Replay is historical, not a live freshness claim."}
path = Path(args.output)
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(bundle, indent=2), encoding="utf-8")
print(f"Exported {len(ports)} ports and {len(activity)} observed activity rows to {path}")
