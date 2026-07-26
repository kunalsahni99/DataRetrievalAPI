"""
Licenses router.

Sync endpoints  (write):
  POST /licenses/sync  — fetch from Graph /subscribedSkus, upsert to DB

Query endpoints (read):
  GET  /licenses/skus  — all tenant SKUs with seat counts
"""

import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.core.graph_client import GraphClient
from app.db.session import get_session
from app.models.license import SubscribedSku
from app.models.user import UserAssignedLicense
from app.schemas import LicenseOperationRequest, LicenseOperationResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/licenses", tags=["Licenses"])


# ── Sync ──────────────────────────────────────────────────────────────────────

@router.post("/sync", summary="Sync tenant license SKUs from Graph API")
def sync_licenses(session: Session = Depends(get_session)) -> dict:
    """
    Fetches all license subscriptions from Graph /subscribedSkus and
    merges them into the DB (upsert on sku_id).

    The unassigned seat count (enabled - consumed) is the key metric
    the Analysis Agent uses to identify waste.
    """
    client = GraphClient()
    sync_run_id = str(uuid.uuid4())
    now = datetime.now()

    logger.info("Starting license SKU sync (run: %s)", sync_run_id)

    raw_skus = client.get_all("subscribedSkus")

    for raw in raw_skus:
        prepaid = raw.get("prepaidUnits", {})
        sku = SubscribedSku(
            sku_id=raw["skuId"],
            sku_part_number=raw.get("skuPartNumber", ""),
            consumed_units=raw.get("consumedUnits", 0),
            enabled_units=prepaid.get("enabled", 0),
            suspended_units=prepaid.get("suspended", 0),
            warning_units=prepaid.get("warning", 0),
            applies_to=raw.get("appliesTo"),
            fetched_at=now,
            sync_run_id=sync_run_id,
        )
        session.merge(sku)

    session.commit()
    logger.info("License sync complete: %d SKUs (run: %s)", len(raw_skus), sync_run_id)

    return {
        "sync_run_id": sync_run_id,
        "skus_synced": len(raw_skus),
        "fetched_at": now.isoformat(),
    }


# ── Query ─────────────────────────────────────────────────────────────────────

@router.get("/skus", response_model=list[SubscribedSku], summary="List all tenant license SKUs")
def list_skus(session: Session = Depends(get_session)) -> list[SubscribedSku]:
    """
    Returns all license SKUs in the tenant with seat counts.
    Use enabled_units - consumed_units to see unassigned (wasted) seats per SKU.
    """
    skus = session.exec(select(SubscribedSku)).all()
    if not skus:
        raise HTTPException(
            status_code=404,
            detail="No license data found. Run POST /licenses/sync first.",
        )
    return skus


@router.get("/skus/{sku_id}", response_model=SubscribedSku, summary="Get a single SKU by ID")
def get_sku(sku_id: str, session: Session = Depends(get_session)) -> SubscribedSku:
    sku = session.get(SubscribedSku, sku_id)
    if not sku:
        raise HTTPException(status_code=404, detail=f"SKU '{sku_id}' not found.")
    return sku


# ── Write ─────────────────────────────────────────────────────────────────────
@router.post("/assign", response_model=LicenseOperationResponse)
async def assign_license(req: LicenseOperationRequest, session: Session = Depends(get_session)):
    client = GraphClient()

    try:
        await client.assign_license(req.user_id, req.sku_id)

        existing_user = session.exec(
            select(UserAssignedLicense).where(
                UserAssignedLicense.user_id == req.user_id,
                UserAssignedLicense.sku_id == req.sku_id
            )
        ).first()

        if not existing_user:
            session.add(UserAssignedLicense(user_id=req.user_id, sku_id=req.sku_id))
            session.commit()

        return LicenseOperationResponse(
            success = True,
            message = f"License {req.sku_id} assigned to {req.user_id}",
            user_id = req.user_id,
            sku_id = req.sku_id
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e}")
    
@router.post("/revoke", response_model=LicenseOperationResponse)
async def revoke_license(req: LicenseOperationRequest, session: Session = Depends(get_session)):
    client = GraphClient()

    try:
        await client.revoke_license(req.user_id, req.sku_id)

        assignment = session.exec(
            select(UserAssignedLicense).where(
                UserAssignedLicense.user_id == req.user_id,
                UserAssignedLicense.sku_id == req.sku_id
            )
        ).first()

        if assignment:
            session.delete(assignment)
            session.commit()

        return LicenseOperationResponse(
            success = True,
            message = f"License {req.sku_id} revoked from {req.user_id}",
            user_id = req.user_id,
            sku_id = req.sku_id
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e}")