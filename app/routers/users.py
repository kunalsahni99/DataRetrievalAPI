"""
Users router.

Sync endpoints  (write):
  POST /users/sync           — fetch from Graph /users, upsert to DB

Query endpoints (read):
  GET  /users/               — all users (current state)
  GET  /users/with-licenses  — users joined with their SKU names [primary agent input]
  GET  /users/{user_id}      — single user record
"""

import logging
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from app.core.graph_client import GraphClient
from app.db.session import get_session
from app.models.license import SubscribedSku
from app.models.user import (
    USER_SELECT_FIELDS,
    User,
    UserAssignedLicense,
    UserWithLicenses,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/users", tags=["Users"])

def _parse_dt(value: str | None) -> datetime | None:
    """Parse Graph API ISO 8601 datetime string to Python datetime."""
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


# ── Sync ──────────────────────────────────────────────────────────────────────

@router.post("/sync", summary="Sync users from Graph API")
def sync_users(session: Session = Depends(get_session)) -> dict:
    """
    Fetches all users from Graph /users and persists them to the DB.

    Strategy:
      - Users table:           merge on id (upsert — always current state)
      - UserAssignedLicense:   delete-all + re-insert (clean snapshot of assignments)

    Returns a sync summary including sync_run_id for traceability.

    TODO (production): wrap in BackgroundTasks + return 202 Accepted
    for large tenants where this can take several minutes.
    """
    client = GraphClient()
    sync_run_id = str(uuid.uuid4())
    now = datetime.now()

    logger.info("Starting user sync (run: %s)", sync_run_id)

    raw_users = client.get_all(
        "users",
        params={
            "$select": USER_SELECT_FIELDS,
            "$top": 999,
        },
    )

    # Clear existing license rows — they'll be re-inserted fresh below.
    # This keeps UserAssignedLicense as a clean current-state snapshot.
    existing_licenses = session.exec(select(UserAssignedLicense)).all()
    for row in existing_licenses:
        session.delete(row)
    session.flush()

    license_rows = 0
    for raw in raw_users:
        user = User(
            id=raw["id"],
            display_name=raw.get("displayName"),
            user_principal_name=raw.get("userPrincipalName", ""),
            account_enabled=raw.get("accountEnabled"),
            department=raw.get("department"),
            job_title=raw.get("jobTitle"),
            mail=raw.get("mail"),
            usage_location=raw.get("usageLocation"),
            created_datetime=_parse_dt(raw.get("createdDateTime")),
            fetched_at=now,
            sync_run_id=sync_run_id,
        )
        session.merge(user)

        for lic in raw.get("assignedLicenses", []):
            session.add(UserAssignedLicense(
                user_id=raw["id"],
                sku_id=lic.get("skuId", ""),
                fetched_at=now,
                sync_run_id=sync_run_id,
            ))
            license_rows += 1

    session.commit()
    logger.info(
        "User sync complete: %d users, %d license rows (run: %s)",
        len(raw_users), license_rows, sync_run_id,
    )

    return {
        "sync_run_id": sync_run_id,
        "users_synced": len(raw_users),
        "license_rows_synced": license_rows,
        "fetched_at": now.isoformat(),
    }


# ── Query ─────────────────────────────────────────────────────────────────────

@router.get(
    "/with-licenses",
    response_model=list[UserWithLicenses],
    summary="Users with their assigned SKU names [primary agent endpoint]",
)
def list_users_with_licenses(
    account_enabled: Optional[bool] = Query(default=None, description="Filter by account status"),
    session: Session = Depends(get_session),
) -> list[UserWithLicenses]:
    """
    Returns all users joined with their human-readable license SKU names.
    This is the primary read endpoint for the Segmentation Agent.

    Optional filters let the pipeline or a human narrow the dataset before
    passing it downstream (e.g. only enabled accounts).
    """
    # Build user query with optional filters
    query = select(User)
    if account_enabled is not None:
        query = query.where(User.account_enabled == account_enabled)

    users = session.exec(query).all()
    if not users:
        return []

    # Build sku_id → sku_part_number lookup from subscribed SKUs
    sku_lookup: dict[str, str] = {
        s.sku_id: s.sku_part_number
        for s in session.exec(select(SubscribedSku)).all()
    }

    # Group license assignments by user_id
    license_rows = session.exec(select(UserAssignedLicense)).all()
    user_skus: dict[str, list[str]] = {}
    for row in license_rows:
        sku_name = sku_lookup.get(row.sku_id, row.sku_id)  # fallback to raw ID
        user_skus.setdefault(row.user_id, []).append(sku_name)

    return [
        UserWithLicenses(
            id=u.id,
            display_name=u.display_name,
            user_principal_name=u.user_principal_name,
            account_enabled=u.account_enabled,
            department=u.department,
            job_title=u.job_title,
            mail=u.mail,
            usage_location=u.usage_location,
            assigned_skus=user_skus.get(u.id, []),
        )
        for u in users
    ]


@router.get("/", response_model=list[User], summary="List all users (current state)")
def list_users(
    account_enabled: Optional[bool] = Query(default=None),
    session: Session = Depends(get_session),
) -> list[User]:
    query = select(User)
    if account_enabled is not None:
        query = query.where(User.account_enabled == account_enabled)
    return session.exec(query).all()


@router.get("/{user_id}", response_model=User, summary="Get a single user by Azure AD object ID")
def get_user(user_id: str, session: Session = Depends(get_session)) -> User:
    user = session.get(User, user_id)

    if not user:
        raise HTTPException(status_code=404, detail=f"User '{user_id}' not found.")
    return user

@router.get("/upn/{user_principal_name}", response_model=User, summary="Get a single user by UPN")
def get_user_by_upn(user_principal_name: str, session: Session = Depends(get_session)) -> User:
    user = session.exec(
        select(User).where(User.user_principal_name == user_principal_name)
    ).first()

    if not user:
        raise HTTPException(status_code=404, detail=f"User '{user_principal_name}' not found.")
    return user