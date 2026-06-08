"""
User-related models.

Tables:
  User                — core user record from Graph /users
  UserAssignedLicense — per-user license assignments (one row per user+SKU)

Response models (not tables):
  UserWithLicenses    — User + human-readable SKU names; used by the segmentation agent
"""

from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel

from app.models.base import SyncBase

# ── Graph $select fields ──────────────────────────────────────────────────────
# Add fields here + in the User model below as the pipeline needs more data.

USER_SELECT_FIELDS = ",".join([
    "id",
    "displayName",
    "userPrincipalName",
    "accountEnabled",
    "department",
    "jobTitle",
    "mail",
    "usageLocation",
    "createdDateTime",
    "assignedLicenses",
    # "signInActivity",
])


# ── Tables ────────────────────────────────────────────────────────────────────

class User(SyncBase, table=True):
    """
    Core user record synced from Graph /users.
    Primary key is the Azure AD object ID — immutable, unlike UPN.
    On each sync, existing rows are merged (overwritten) in place.
    """
    __tablename__ = "users"

    id: str = Field(primary_key=True)
    display_name: Optional[str] = None
    user_principal_name: str = Field(index=True)
    account_enabled: Optional[bool] = None
    department: Optional[str] = Field(default=None, index=True)
    job_title: Optional[str] = None
    mail: Optional[str] = None
    usage_location: Optional[str] = Field(default=None, index=True)
    created_datetime: Optional[datetime] = None


class UserAssignedLicense(SyncBase, table=True):
    """
    License assignments per user, extracted from the assignedLicenses
    array nested in each /users response object.

    One row per (user, SKU). The table is fully replaced on each sync
    (delete-all + re-insert) so it always reflects current state.
    """
    __tablename__ = "user_assigned_licenses"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: str = Field(index=True, foreign_key="users.id")
    sku_id: str = Field(index=True)  # joins to SubscribedSku.sku_id


# ── Response models (not DB tables) ──────────────────────────────────────────

class UserWithLicenses(SQLModel):
    """
    Flat read model combining a user's attributes with their assigned
    SKU part numbers (human-readable, e.g. "ENTERPRISEPACK").

    This is the primary input for the Segmentation Agent — it has everything
    needed to group users by license type, department, and activity.
    """
    id: str
    display_name: Optional[str] = None
    user_principal_name: str
    account_enabled: Optional[bool] = None
    department: Optional[str] = None
    job_title: Optional[str] = None
    mail: Optional[str] = None
    usage_location: Optional[str] = None
    assigned_skus: list[str] = []
