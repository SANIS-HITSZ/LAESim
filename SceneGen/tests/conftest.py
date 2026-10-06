"""Keep relative fixture references local to the scene module."""

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def scene_fixture_root(monkeypatch):
    monkeypatch.chdir(Path(__file__).resolve().parents[1])
