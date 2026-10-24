"""Generate portable, parameterized notebook definitions from the packaged runtime."""

import json
from pathlib import Path


def build():
    output = Path("fabric/notebooks")
    output.mkdir(parents=True, exist_ok=True)
    for stage in (
        "bronze",
        "silver",
        "gold",
        "acceptance",
        "import_predictions",
        "import_feedback",
    ):
        cells = []

        def cell(source, metadata=None):
            cells.append(
                {
                    "cell_type": "code",
                    "execution_count": None,
                    "outputs": [],
                    "metadata": metadata or {},
                    "source": source.splitlines(keepends=True),
                }
            )

        cell('run_id = "manual-run"\nas_of = "2026-10-07"\n', {"tags": ["parameters"]})
        cell(
            "%pip install /lakehouse/default/Files/maritime/maritime_sla_intelligence-0.1.0-py3-none-any.whl\n"
        )
        cell(
            'from pathlib import Path\nimport zipfile\nimport tempfile\nimport re\nassert re.fullmatch(r"[A-Za-z0-9_-]+", run_id), "Invalid run_id"\nconfig_root = Path(tempfile.mkdtemp(prefix="maritime-config-"))\nwith zipfile.ZipFile("/lakehouse/default/Files/maritime/configs.zip") as archive:\n    archive.extractall(config_root)\nroot = "/lakehouse/default/Files/maritime"\nconfig_path = str(config_root / "configs/pipeline.json")\nregistry_path = str(config_root / "configs/sources.json")\n'
        )
        args = {
            "bronze": "spark, root, run_id, config_path, registry_path, as_of",
            "silver": "spark, root, run_id, config_path",
            "gold": "spark, root, run_id, config_path, registry_path",
            "acceptance": "spark, root, run_id",
            "import_predictions": "spark, root, run_id",
            "import_feedback": "spark, root, run_id",
        }[stage]
        cell(f"from maritime.fabric_runtime import {stage}\nresult = {stage}({args})\n")
        notebook = {
            "nbformat": 4,
            "nbformat_minor": 5,
            "metadata": {
                "kernelspec": {
                    "display_name": "Synapse PySpark",
                    "language": "python",
                    "name": "synapse_pyspark",
                },
                "language_info": {"name": "python"},
            },
            "cells": cells,
        }
        (output / f"{stage}.ipynb").write_text(json.dumps(notebook, indent=2), encoding="utf-8")


if __name__ == "__main__":
    build()
