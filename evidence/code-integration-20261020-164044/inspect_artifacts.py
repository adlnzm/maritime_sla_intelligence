"""Read-only import/build/source inspection; never initialize application state."""
import ast
import hashlib
import importlib
import importlib.metadata
import json
import sys
import tarfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
sys.dont_write_bytecode = True
files = [
    path
    for folder in ("src", "tests", "scripts", "configs", "azure", "fabric", "sql", "docker", ".github")
    for path in (ROOT / folder).rglob("*")
    if path.is_file() and "__pycache__" not in path.parts
]
files += [ROOT / name for name in ("pyproject.toml", "uv.lock")]
hashes = {
    path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
    for path in files
}
(EVIDENCE / "source-hashes.json").write_text(json.dumps(hashes, indent=2), encoding="utf-8")
modules = []
for path in sorted((ROOT / "src/maritime").glob("*.py")):
    name = "maritime" if path.stem == "__init__" else "maritime." + path.stem
    importlib.import_module(name)
    modules.append(name)
python_files = [p for p in files if p.suffix == ".py"]
for path in python_files:
    ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
build = EVIDENCE / "verified-build"
with tarfile.open(next(build.glob("*.tar.gz"))) as archive:
    names = archive.getnames()
    assert not any("/evidence/" in n or "/.venv/" in n for n in names)
    assert any(n.endswith("/configs/governance.json") for n in names)
with zipfile.ZipFile(next(build.glob("*.whl"))) as wheel:
    assert wheel.read("maritime/governance_contract.json") == (
        ROOT / "configs/governance.json"
    ).read_bytes()
    for name in modules:
        relative = name.replace(".", "/") + ".py"
        if name == "maritime":
            relative = "maritime/__init__.py"
        assert wheel.read(relative) == (ROOT / "src" / relative).read_bytes()
result = {
    "status": "PASS",
    "imported_modules": modules,
    "parsed_python_files": len(python_files),
    "sdist_entries": len(names),
    "wheel_source_and_governance_match": True,
    "static_type_checker": "NOT_CONFIGURED",
    "no_runtime_started": True,
    "dependencies": {
        d.metadata["Name"]: d.version for d in importlib.metadata.distributions()
        if d.metadata.get("Name")
    },
}
(EVIDENCE / "artifact-inspection.json").write_text(
    json.dumps(result, indent=2), encoding="utf-8"
)
print(json.dumps({k: v for k, v in result.items() if k != "dependencies"}, indent=2))
