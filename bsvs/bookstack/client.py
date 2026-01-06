"""BookStack API client for permission validation."""

import logging
from dataclasses import dataclass
from typing import Any

import httpx

from bsvs.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class BookStackPage:
    """BookStack page data."""
    id: int
    name: str
    slug: str
    book_id: int
    chapter_id: int | None
    created_by: int
    updated_by: int


@dataclass
class BookStackUser:
    """BookStack user data."""
    id: int
    name: str
    email: str


class BookStackClient:
    """Client for BookStack API interactions."""

    def __init__(
        self,
        base_url: str | None = None,
        token_id: str | None = None,
        token_secret: str | None = None,
    ):
        """
        Initialize BookStack client.

        Args:
            base_url: BookStack instance URL (defaults to settings)
            token_id: API token ID (defaults to settings)
            token_secret: API token secret (defaults to settings)
        """
        settings = get_settings()
        self.base_url = (base_url or settings.bookstack_url or "").rstrip("/")
        self.token_id = token_id or settings.bookstack_token_id
        self.token_secret = token_secret or settings.bookstack_token_secret

        if not self.base_url:
            logger.warning("BookStack URL not configured")

    @property
    def is_configured(self) -> bool:
        """Check if BookStack integration is configured."""
        return bool(self.base_url and self.token_id and self.token_secret)

    def _get_headers(self) -> dict[str, str]:
        """Get authentication headers for API requests."""
        return {
            "Authorization": f"Token {self.token_id}:{self.token_secret}",
            "Content-Type": "application/json",
        }

    async def _request(
        self,
        method: str,
        endpoint: str,
        **kwargs,
    ) -> dict[str, Any]:
        """Make an authenticated request to BookStack API."""
        if not self.is_configured:
            raise ValueError("BookStack client not configured")

        url = f"{self.base_url}/api/{endpoint.lstrip('/')}"
        headers = self._get_headers()

        async with httpx.AsyncClient() as client:
            response = await client.request(
                method,
                url,
                headers=headers,
                timeout=10.0,
                **kwargs,
            )
            response.raise_for_status()
            return response.json()

    async def get_page(self, page_id: int) -> BookStackPage:
        """
        Get page details by ID.

        Args:
            page_id: The BookStack page ID

        Returns:
            BookStackPage with page details
        """
        data = await self._request("GET", f"pages/{page_id}")
        return BookStackPage(
            id=data["id"],
            name=data["name"],
            slug=data["slug"],
            book_id=data["book_id"],
            chapter_id=data.get("chapter_id"),
            created_by=data["created_by"],
            updated_by=data["updated_by"],
        )

    async def check_page_access(self, page_id: int) -> bool:
        """
        Check if the configured API user can access a page.

        This is a simple check - if we can fetch the page, we have access.
        For user-specific access, use validate_user_page_access.

        Args:
            page_id: The BookStack page ID

        Returns:
            True if page is accessible, False otherwise
        """
        try:
            await self.get_page(page_id)
            return True
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (403, 404):
                return False
            raise

    async def get_current_user(self) -> BookStackUser:
        """Get the current API user's details."""
        data = await self._request("GET", "users/me")
        return BookStackUser(
            id=data["id"],
            name=data["name"],
            email=data["email"],
        )

    async def search_pages(self, query: str, count: int = 10) -> list[dict]:
        """
        Search for pages.

        Args:
            query: Search query
            count: Maximum results to return

        Returns:
            List of matching page data
        """
        data = await self._request(
            "GET",
            "search",
            params={"query": query, "count": count},
        )
        return [
            item for item in data.get("data", [])
            if item.get("type") == "page"
        ]


# Singleton client instance
_client: BookStackClient | None = None


def get_bookstack_client() -> BookStackClient:
    """Get or create the BookStack client singleton."""
    global _client
    if _client is None:
        _client = BookStackClient()
    return _client
