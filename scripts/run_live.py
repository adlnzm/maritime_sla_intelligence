"""Run using the explicit UTC analysis date supplied at the command line."""

import argparse
import json
from datetime import date

from maritime.pipeline import run

parser = argparse.ArgumentParser()
parser.add_argument("--as-of", required=True, type=date.fromisoformat)
parser.add_argument("--data-dir", default="data")
args = parser.parse_args()
report = run(root=args.data_dir, as_of=args.as_of)
print(
    json.dumps(
        {
            k: report[k]
            for k in (
                "run_id",
                "status",
                "data",
                "congestion",
                "network",
                "scenarios",
                "sla",
                "decision",
                "ml",
                "gates",
            )
        },
        indent=2,
    )
)
