import argparse
import json
import logging
import os
from datetime import date

from maritime.pipeline import run
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
    report = sub.add_parser("report")
    report.add_argument("--data-dir", default="data")
    serve = sub.add_parser("serve")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if args.command == "run":
        result = run(args.data_dir, args.config, args.registry, args.fixture, args.as_of)
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


if __name__ == "__main__":
    main()
