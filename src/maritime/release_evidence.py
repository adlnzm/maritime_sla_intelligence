"""Bind verification to the source actually executed, not a later working tree."""

import hashlib
from pathlib import Path


def source_snapshot():
    files = {}
    for folder in (
        "src",
        "configs",
        "scripts",
        "tests",
        "docker",
        "azure",
        "fabric",
        ".github",
        "docs",
        "sql",
    ):
        for path in sorted(Path(folder).rglob("*")):
            if (
                path.is_file()
                and "__pycache__" not in path.parts
                and path.name != "deployment.json"
            ):
                files[path.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    for name in (
        "pyproject.toml",
        "uv.lock",
        "README.md",
        ".env.example",
        "compose.demo.yml",
        "docker-compose.yml",
        ".dockerignore",
        ".gitattributes",
        ".gitignore",
        ".amlignore",
    ):
        files[name] = hashlib.sha256(Path(name).read_bytes()).hexdigest()
    return files


def verify_source(expected):
    if source_snapshot() != expected:
        raise ValueError("Source changed since validation; rerun the complete release suite")
