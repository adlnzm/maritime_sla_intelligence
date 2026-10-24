"""Offline validation runner; all product writes must use pytest temporary roots."""
import json
import os
import socket
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT / "src"))


def deny_network(*args, **kwargs):
    raise RuntimeError("External network disabled during code integration validation")


socket.create_connection = deny_network
original_connect = socket.socket.connect


def connect(self, address):
    # asyncio on Windows uses a loopback socketpair internally.
    if isinstance(address, tuple) and address[0] in {"127.0.0.1", "::1"}:
        return original_connect(self, address)
    return deny_network()


socket.socket.connect = connect
for name in list(os.environ):
    if name.startswith(("AZURE_", "MARITIME_", "APPLICATIONINSIGHTS_", "OTEL_")):
        os.environ.pop(name)
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
sys.dont_write_bytecode = True
if __name__ == "__main__":
    import pytest

    print(json.dumps({"network": "external sockets denied", "python": sys.version}))
    raise SystemExit(pytest.main(sys.argv[1:]))
