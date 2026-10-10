import ast
import json
from pathlib import Path


def test_notebooks_are_connected_to_runtime_and_parameterized():
    for stage in ("bronze", "silver", "gold", "acceptance"):
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
