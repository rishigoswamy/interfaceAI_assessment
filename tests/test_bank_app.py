"""
tests/test_bank_app.py
Unit tests for FastAPI Bank Application endpoints.
"""

import pytest
import httpx
from bank_app.server import app


@pytest.mark.asyncio
async def test_bank_app_endpoints():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        # 1. Health check
        res = await client.get("/health")
        assert res.status_code == 200
        assert res.json()["status"] == "ok"

        # 2. Portal HTML index
        res = await client.get("/?tenant=horizon")
        assert res.status_code == 200
        assert "Horizon Financial FCU" in res.text

        # 3. Member lookup existing
        res = await client.get("/api/members/MBR-1092")
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["data"]["id"] == "MBR-1092"

        # 4. Member lookup not found
        res = await client.get("/api/members/MBR-UNKNOWN-99")
        assert res.status_code == 404
        assert res.json()["error_code"] == "MEMBER_NOT_FOUND"

        # 5. Open sub-account
        open_payload = {
            "member_id": "MBR-3041",
            "product_type": "Money Market Special",
            "initial_deposit": 750.0
        }
        res = await client.post("/api/accounts/open", json=open_payload)
        assert res.status_code == 200
        acc_data = res.json()
        assert acc_data["success"] is True
        assert "SUB-" in acc_data["data"]["account_number"]

        # 6. Open sub-account invalid member
        res = await client.post("/api/accounts/open", json={"member_id": "NONEXISTENT", "product_type": "Savings", "initial_deposit": 100})
        assert res.status_code == 404
