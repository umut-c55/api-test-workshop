"""Gemeinsame Fixtures.

Konfiguration über Umgebungsvariablen, damit lokal und in CI dasselbe läuft:
  API_BASE_URL  Basis-URL des SUT   (Standard: http://localhost:8000)
  DB_PATH       Pfad zur SQLite-DB  (Standard: sut/data/app.db)
"""
import os
import sqlite3
import time
from pathlib import Path

import httpx
import pytest

BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")
DB_PATH = Path(os.environ.get("DB_PATH", "sut/data/app.db"))
SCHEMAS = Path(__file__).resolve().parent.parent / "schemas"


@pytest.fixture(scope="session")
def base_url() -> str:
    return BASE_URL


@pytest.fixture(scope="session")
def schemas_dir() -> Path:
    return SCHEMAS


@pytest.fixture(scope="session", autouse=True)
def sut_ready(base_url):
    """Wartet, bis das SUT antwortet (max. 30 s)."""
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            httpx.get(f"{base_url}/docs", timeout=1)
            return
        except httpx.HTTPError:
            time.sleep(0.5)
    pytest.exit(f"SUT unter {base_url} nicht erreichbar", returncode=2)


@pytest.fixture
def client(base_url):
    with httpx.Client(base_url=base_url, timeout=5) as c:
        yield c


@pytest.fixture
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    yield conn
    conn.close()


# TODO: Fixture für frische Datenbank pro Testlauf (Tabellen leeren oder
# DB neu anlegen) und Factory-Fixtures für Defekte/Testdaten ergänzen,
# sobald das SUT-Schema steht.
