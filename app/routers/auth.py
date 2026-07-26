"""
Auth router.

Auth endpoints:
  POST /auth/token  —  Issues access_token + refresh_token to the client
"""

import logging
from uuid import uuid4

from fastapi import HTTPException, APIRouter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Authentication"])