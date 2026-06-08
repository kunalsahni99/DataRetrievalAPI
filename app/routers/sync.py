"""
Sync router.

  POST /sync/all — triggers users + licenses sync in one call.

When new M365 data sources are added (SharePoint, Teams, OneDrive, Exchange),
import their sync function here and call it from sync_all().
"""

import logging

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.db.session import get_session
from app.routers.licenses import sync_licenses
from app.routers.users import sync_users

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sync", tags=["Sync"])


@router.post("/all", summary="Sync all M365 data sources")
def sync_all(session: Session = Depends(get_session)) -> dict:
    """
    Runs all sync operations in sequence and returns a combined summary.

    The LangGraph Data Retrieval Node should call this endpoint, then
    pass the result downstream — no Graph API calls happen in the agent.

    Sequence (extend as new sources are added):
      1. Users + license assignments  ← POST /users/sync
      2. License SKUs                 ← POST /licenses/sync
      3. SharePoint sites           ← POST /sharepoint/sync  (future)
      4. Teams channels             ← POST /teams/sync       (future)
    """
    logger.info("Starting full M365 sync")

    users_result = sync_users(session=session)
    license_result = sync_licenses(session=session)

    return {
        "status": "complete",
        "results": {
            "users": users_result,
            "licenses": license_result,
        },
    }
