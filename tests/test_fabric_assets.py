import ast
import json
import runpy
from pathlib import Path


def test_notebooks_are_connected_to_runtime_and_parameterized():
    for stage in (
        "bronze",
        "silver",
        "gold",
        "acceptance",
        "import_predictions",
        "import_feedback",
    ):
        notebook = json.loads(Path(f"fabric/notebooks/{stage}.ipynb").read_text())
        assert notebook["nbformat"] == 4
        assert notebook["cells"][0]["metadata"]["tags"] == ["parameters"]
        code = "\n".join(
            "".join(c["source"])
            for c in notebook["cells"]
            if not "".join(c["source"]).startswith("%")
        )
        ast.parse(code)
        assert f"from maritime.fabric_runtime import {stage}" in code


def test_generated_notebooks_match_retained_assets(tmp_path, monkeypatch):
    """Build in a disposable folder so existing notebooks are never overwritten."""
    original = Path("fabric/notebooks").resolve()
    builder = runpy.run_path("scripts/build_fabric_assets.py")["build"]
    monkeypatch.chdir(tmp_path)
    builder()
    for generated in Path("fabric/notebooks").glob("*.ipynb"):
        assert json.loads(generated.read_text()) == json.loads(
            (original / generated.name).read_text()
        )
