"""Resolve LAESim-owned assets and its original Python client."""

import importlib
import os
import sys
from pathlib import Path


def repository_root() -> Path:
    configured = os.environ.get("LAESIM_ROOT")
    candidates = [Path(configured)] if configured else list(Path(__file__).resolve().parents)
    for root in candidates:
        if (root / "PythonClient/airsim/client.py").is_file() and (root / "AirLib/include").is_dir():
            return root.resolve()
    raise RuntimeError("LAESim source checkout not found. Install from its root or set LAESIM_ROOT.")


def load_laesim_client():
    client_root = repository_root() / "PythonClient"
    if str(client_root) not in sys.path:
        sys.path.insert(0, str(client_root))
    client = importlib.import_module("airsim")
    if client_root not in Path(client.__file__).resolve().parents:
        raise RuntimeError("A different AirSim package is already loaded; start with LAESim's PythonClient.")
    return client


def editor_project(root: Path) -> Path:
    configured = os.environ.get("LAESIM_UE_PROJECT")
    project = Path(configured).expanduser() if configured else root / "Unreal/Environments/SceneGen/WirelessCityFactory.uproject"
    return project.resolve()
