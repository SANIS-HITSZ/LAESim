from pathlib import Path
from types import SimpleNamespace

import pytest
from laesim_scene import repository


def test_default_root_has_native_client(monkeypatch):
    monkeypatch.delenv("LAESIM_ROOT", raising=False)
    root = repository.repository_root()
    assert (root / "PythonClient/airsim/client.py").is_file()
    assert repository.editor_project(root).is_file()


def test_configured_root_must_be_laesim(tmp_path, monkeypatch):
    monkeypatch.setenv("LAESIM_ROOT", str(tmp_path))
    with pytest.raises(RuntimeError, match="LAESim source checkout"):
        repository.repository_root()


def test_refuses_unrelated_airsim_module(monkeypatch):
    monkeypatch.setattr(repository.importlib, "import_module", lambda _: SimpleNamespace(__file__=str(Path.cwd() / "foreign/airsim/__init__.py")))
    with pytest.raises(RuntimeError, match="different AirSim"):
        repository.load_laesim_client()


def test_loads_native_client(monkeypatch):
    expected = repository.repository_root() / "PythonClient/airsim/__init__.py"
    module = SimpleNamespace(__file__=str(expected))
    monkeypatch.setattr(repository.importlib, "import_module", lambda _: module)
    assert repository.load_laesim_client() is module
