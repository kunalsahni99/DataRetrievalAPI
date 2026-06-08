"""
License subscription models.

Tables:
  SubscribedSku — tenant-level license pools from Graph /subscribedSkus
                  (how many seats purchased vs consumed)
"""

from typing import Optional

from sqlmodel import Field

from app.models.base import SyncBase


class SubscribedSku(SyncBase, table=True):
    """
    Tenant-level license subscription from Graph /subscribedSkus.

    Key fields for the Analysis Agent:
      sku_part_number  — human-readable name (e.g. "ENTERPRISEPACK" = E3, "SPE_E5" = E5)
      consumed_units   — currently assigned to users
      enabled_units    — total purchased seats
      enabled_units - consumed_units = unassigned (waste) seats
    """
    __tablename__ = "subscribed_skus"

    sku_id: str = Field(primary_key=True)
    sku_part_number: str                            # e.g. "ENTERPRISEPACK"
    consumed_units: int = 0
    enabled_units: int = 0                          # prepaidUnits.enabled
    suspended_units: int = 0                        # prepaidUnits.suspended
    warning_units: int = 0                          # prepaidUnits.warning
    applies_to: Optional[str] = None                # "User" or "Company"

    @property
    def unassigned_units(self) -> int:
        """Seats purchased but not assigned to any user — the primary waste metric."""
        return max(0, self.enabled_units - self.consumed_units)
