"""Export an authenticated operations snapshot for the existing Power BI report."""

import argparse
import json
import os
from pathlib import Path
from urllib.parse import urlparse

import httpx


def export(client, output):
    response = client.get("/operations/reporting")
    response.raise_for_status()
    packet = response.json()
    if packet.get("schema_version") != "1.0":
        raise ValueError("Unsupported operations reporting contract")
    for table in (
        "fact_port_weeks",
        "fact_review_queue",
        "fact_hamad_port_weeks",
        "fact_review_history",
        "fact_escalations",
    ):
        if not isinstance(packet.get(table), list):
            raise ValueError("Missing reporting table: " + table)
    # Never replace an earlier snapshot; the caller selects an explicit new file.
    with Path(output).open("x", encoding="utf-8") as target:
        json.dump(packet, target, indent=2, allow_nan=False)
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-url", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    address = urlparse(args.api_url)
    if address.scheme != "https" or not address.hostname or address.username or address.password:
        raise ValueError("An authenticated HTTPS API endpoint is required")
    token = os.environ["MARITIME_EXPORT_ACCESS_TOKEN"]
    with httpx.Client(
        base_url=args.api_url,
        headers={"Authorization": "Bearer " + token},
        timeout=30,
        follow_redirects=False,
    ) as client:
        export(client, args.output)
