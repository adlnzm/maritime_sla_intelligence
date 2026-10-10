import argparse
import json
import logging
import os
from datetime import date
from pathlib import Path

from maritime.pipeline import load_json, run, write_json
from maritime.store import Store


def main():
    parser = argparse.ArgumentParser(description="Maritime intelligence pipeline")
    sub = parser.add_subparsers(dest="command", required=True)
    pipeline = sub.add_parser("run")
    pipeline.add_argument("--data-dir", default=os.getenv("MARITIME_DATA_DIR", "data"))
    pipeline.add_argument("--config", default="configs/pipeline.json")
    pipeline.add_argument("--registry", default="configs/sources.json")
    pipeline.add_argument("--fixture")
    pipeline.add_argument("--as-of", type=date.fromisoformat)
    pipeline.add_argument("--ml-backend", choices=["local", "azure_ml"], default="local")
    report = sub.add_parser("report")
    report.add_argument("--data-dir", default="data")
    serve = sub.add_parser("serve")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    extract = sub.add_parser("extract-evidence")
    extract.add_argument("--input", required=True)
    extract.add_argument("--source", required=True)
    extract.add_argument("--data-dir", default="data")
    imported = sub.add_parser("import-gold")
    imported.add_argument("--folder", required=True, help="Exported Gold run folder")
    imported.add_argument("--report", required=True, help="Verified run report JSON")
    imported.add_argument("--data-dir", default="data")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if args.command == "run":
        result = run(
            args.data_dir,
            args.config,
            args.registry,
            args.fixture,
            args.as_of,
            ml_backend=args.ml_backend,
        )
        print(
            json.dumps(
                {"run_id": result["run_id"], "status": result["status"], "gates": result["gates"]},
                indent=2,
            )
        )
    elif args.command == "report":
        print(json.dumps(Store(args.data_dir).latest_report(), indent=2))
    elif args.command == "serve":
        import uvicorn

        uvicorn.run("maritime.api:create_app", factory=True, host=args.host, port=args.port)
    elif args.command == "extract-evidence":
        from maritime.genai import extract
        from maritime.models import stable_id, utcnow

        text = Path(args.input).read_text(encoding="utf-8")
        retrieved_at = utcnow()
        store = Store(args.data_dir)
        evidence_id = stable_id(text, args.source)
        write_json(
            store.root / "bronze" / "external_evidence" / (evidence_id + ".json"),
            {"text": text, "source_url": args.source, "retrieved_at": retrieved_at},
        )
        signals, metrics = extract(text, args.source, retrieved_at)
        if os.getenv("MARITIME_STORAGE_BACKEND") == "azure_blob":
            from maritime.azure_store import AzureStore

            store = AzureStore()
        audit_id = store.audit(
            "extraction", {"signals": signals, "metrics": metrics, "evidence_id": evidence_id}
        )
        print(json.dumps({"audit_id": audit_id, "signals": signals, "metrics": metrics}, indent=2))
    elif args.command == "import-gold":
        report = load_json(args.report)
        if report["status"] != "SUCCESS" or report["data_quality"]["status"] != "PASS":
            raise ValueError("Only a successfully validated run can be imported")
        store = Store(args.data_dir)
        folder = Path(args.folder)
        required = {
            "ports",
            "activity",
            "congestion",
            "network",
            "scenarios",
            "sla_risk",
            "interventions",
            "decisions",
            "lineage",
            "data_quality",
        }
        found = {file.stem for file in folder.glob("*.json")}
        if required - found:
            raise ValueError(f"Missing required products: {required - found}")
        for file in folder.glob("*.json"):
            rows = load_json(file)
            if any(row.get("run_id") != report["run_id"] for row in rows):
                raise ValueError("Gold run ID mismatch")
            store.write(report["run_id"], file.stem, rows)
        store.run(report)
        store.set_metadata("published_run", report["run_id"])
        print(json.dumps({"status": "IMPORTED", "run_id": report["run_id"]}))


if __name__ == "__main__":
    main()
