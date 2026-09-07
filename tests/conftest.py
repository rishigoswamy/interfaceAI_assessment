"""
tests/conftest.py
Global pytest fixtures.
"""

import pytest
import threading
import time
import httpx
from bank_app.data import reset_db
from bank_app.server import run_server


@pytest.fixture(scope="session", autouse=True)
def shared_bank_server():
    """Starts the OmniCore Banking mock server if not already running."""
    server_running = False
    try:
        r = httpx.get("http://127.0.0.1:8000/health", timeout=1.0)
        if r.status_code == 200:
            server_running = True
    except Exception:
        pass

    if not server_running:
        t = threading.Thread(target=run_server, kwargs={"host": "127.0.0.1", "port": 8000}, daemon=True)
        t.start()
        # Wait until server responds
        for _ in range(20):
            time.sleep(0.2)
            try:
                r = httpx.get("http://127.0.0.1:8000/health", timeout=0.5)
                if r.status_code == 200:
                    break
            except Exception:
                continue

    yield


@pytest.fixture(autouse=True)
def reset_database_state():
    """Resets the mock in-memory bank database before each test run."""
    reset_db()
    yield
    reset_db()
