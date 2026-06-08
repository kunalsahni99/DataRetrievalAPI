"""
Shared base fields added to every synced table.

  fetched_at   — exact UTC time this record was written to the DB
  sync_run_id  — UUID shared by all records fetched in the same sync call;
                 useful for auditing and future historical snapshot queries
"""

import uuid
from datetime import datetime

from sqlmodel import Field, SQLModel


def _new_uuid() -> str:
    return str(uuid.uuid4())


class SyncBase(SQLModel):
    fetched_at: datetime = Field(default_factory=datetime.now)
    sync_run_id: str = Field(index=True, default_factory=_new_uuid)
