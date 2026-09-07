"""
bank_app/server.py
FastAPI server serving the OmniCore Banking Back-Office Application.
"""

import os
from typing import Optional
from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import uvicorn

from bank_app.data import MEMBERS_DB

app = FastAPI(title="OmniCore Banking Back-Office Console", version="4.2.0")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")

templates = Jinja2Templates(directory=TEMPLATES_DIR)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

TENANTS = {
    "default": "Apex Credit Union",
    "horizon": "Horizon Financial FCU",
    "summit": "Summit National Bank"
}


class OpenAccountRequest(BaseModel):
    member_id: str
    product_type: str
    initial_deposit: float


@app.get("/", response_class=HTMLResponse)
async def serve_portal(
    request: Request,
    tenant: str = Query("default"),
    show_interstitial: bool = Query(False)
):
    tenant_name = TENANTS.get(tenant, "Apex Credit Union")
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "tenant_id": tenant,
            "tenant_name": tenant_name,
            "show_interstitial": show_interstitial
        }
    )


@app.get("/api/members/{member_id}")
async def get_member(member_id: str, force_unlock: bool = False):
    member = MEMBERS_DB.get(member_id.strip())
    if not member:
        return JSONResponse(
            status_code=404,
            content={
                "success": False,
                "error_code": "MEMBER_NOT_FOUND",
                "message": f"Member record '{member_id}' not found in active ledger"
            }
        )

    if member.get("security_lock") and not force_unlock:
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "data": {
                    "id": member["id"],
                    "security_lock": True,
                    "status": "SECURITY_HOLD",
                    "message": "Supervisory intervention lock is active."
                }
            }
        )

    return {
        "success": True,
        "data": member
    }


@app.post("/api/accounts/open")
async def open_account(payload: OpenAccountRequest):
    member = MEMBERS_DB.get(payload.member_id)
    if not member:
        raise HTTPException(status_code=404, detail="Target member not found")

    new_acc_num = f"SUB-{abs(hash(payload.product_type + payload.member_id)) % 900000 + 100000}"
    new_account = {
        "account_number": new_acc_num,
        "type": payload.product_type,
        "balance": f"${payload.initial_deposit:,.2f}",
        "available": f"${payload.initial_deposit:,.2f}",
        "status": "OPEN"
    }
    member["accounts"].append(new_account)

    return {
        "success": True,
        "data": new_account,
        "message": f"Successfully created sub-account {new_acc_num}"
    }


@app.get("/health")
async def health_check():
    return {"status": "ok", "app": "OmniCore Banking v4.2"}


def run_server(host: str = "127.0.0.1", port: int = 8000):
    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    run_server()
