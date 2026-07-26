"""
Base Microsoft Graph API client.

Handles:
  - Auth via MSAL client credentials (MSAL caches tokens internally)
  - Automatic pagination via @odata.nextLink
  - Retry with backoff on 429 (Graph throttling), respecting Retry-After header

Extending to a new M365 data source (SharePoint, Teams, OneDrive, Exchange):
  1. Create a new router in app/routers/
  2. Create the corresponding SQLModel in app/models/
  3. Call self.get_all("<graph-endpoint>", params={...}) — no changes needed here
"""

import logging
import time
from typing import Optional

import httpx
import msal

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class GraphClient:
    def __init__(self) -> None:
        settings = get_settings()
        self._settings = settings
        self._msal_app = msal.ConfidentialClientApplication(
            settings.AZURE_CLIENT_ID,
            authority=f"https://login.microsoftonline.com/{settings.AZURE_TENANT_ID}",
            client_credential=settings.AZURE_CLIENT_SECRET,
        )

    # ── Auth ──────────────────────────────────────────────────────────────────

    def _acquire_token(self) -> str:
        """
        Acquire access token via client credentials flow.
        MSAL handles caching and silent refresh automatically.
        """
        result = self._msal_app.acquire_token_for_client(
            scopes=self._settings.GRAPH_SCOPES
        )
        if "access_token" not in result:
            error = result.get("error_description") or result.get("error", "unknown")
            raise RuntimeError(f"Token acquisition failed: {error}")
        return result["access_token"]

    def _auth_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._acquire_token()}",
            "Accept": "application/json",
        }

    # ── HTTP ──────────────────────────────────────────────────────────────────

    def _get_with_retry(
        self,
        url: str,
        params: Optional[dict] = None,
        attempt: int = 0,
    ) -> dict:
        """
        Single GET with exponential backoff on 429.
        Respects the Retry-After response header when present.
        """
        with httpx.Client(timeout=30) as client:
            response = client.get(url, headers=self._auth_headers(), params=params)

        if response.status_code == 429:
            if attempt >= self._settings.GRAPH_MAX_RETRIES:
                raise RuntimeError(
                    f"Max retries ({self._settings.GRAPH_MAX_RETRIES}) exceeded for {url}"
                )
            backoff = self._settings.GRAPH_RETRY_BACKOFF_BASE * (2 ** attempt)
            retry_after = int(response.headers.get("Retry-After", backoff))
            logger.warning(
                "Graph API rate limit hit. Waiting %ds before retry %d/%d. URL: %s",
                retry_after, attempt + 1, self._settings.GRAPH_MAX_RETRIES, url,
            )
            time.sleep(retry_after)
            return self._get_with_retry(url, params, attempt + 1)

        response.raise_for_status()
        return response.json()

    # ── Public interface ──────────────────────────────────────────────────────

    def get(self, endpoint: str, params: Optional[dict] = None) -> dict:
        """Single GET. Returns raw response dict (no pagination)."""
        url = f"{self._settings.GRAPH_BASE_URL}/{endpoint.lstrip('/')}"
        return self._get_with_retry(url, params)

    def get_all(self, endpoint: str, params: Optional[dict] = None) -> list[dict]:
        """
        Paginated GET. Follows @odata.nextLink until all pages are fetched.
        Returns a flat list of all records across all pages.

        Graph API returns up to `$top` records per page (max 999 for /users).
        For large tenants this can span many pages — all handled transparently.
        """
        url = f"{self._settings.GRAPH_BASE_URL}/{endpoint.lstrip('/')}"
        current_params = params
        results: list[dict] = []
        page = 1

        while url:
            data = self._get_with_retry(url, current_params)
            batch = data.get("value", [])
            results.extend(batch)
            url = data.get("@odata.nextLink")   # None on last page
            current_params = None               # nextLink already encodes original params
            logger.info(
                "Fetched page %d (%d records, %d total) from /%s",
                page, len(batch), len(results), endpoint,
            )
            page += 1

        return results
    
    async def assign_license(self, user_id: str, sku_id:str) -> dict:
        """Assigns a M365 license to a user"""

        token = self._acquire_token()

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self._settings.GRAPH_BASE_URL}/users/{user_id}/assignLicense",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "addLicenses": [{"disabledPlans": [], "skuId": sku_id}],
                    "removeLicenses": []
                },
                timeout=300
            )

            if response.status_code != 200:
                error = response.json().get("error", {}).get("message", response.text)
                raise ValueError(f"License assignment failed: {error}")
            
            return response.json()
        

    async def revoke_license(self, user_id: str, sku_id:str) -> dict:
        """Revokes a M365 license to a user"""

        token = self._acquire_token()

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self._settings.GRAPH_BASE_URL}/users/{user_id}/assignLicense",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "addLicenses": [],
                    "removeLicenses": [sku_id]
                },
                timeout=300
            )

            if response.status_code != 200:
                error = response.json().get("error", {}).get("message", response.text)
                raise ValueError(f"License revocation failed: {error}")
            
            return response.json()