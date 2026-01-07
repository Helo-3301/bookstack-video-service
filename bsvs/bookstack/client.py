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
    roles: list[dict] | None = None

    def can_manage_videos(self) -> bool:
        """Check if user can manage videos (admin or 'Video Editor' role)."""
        if not self.roles:
            return False
        for role in self.roles:
            # Check for admin (either by system_name or display_name)
            system_name = role.get("system_name", "").lower()
            display_name = role.get("display_name", "").lower()
            if system_name == "admin" or display_name == "admin":
                return True
            # Check for "Video Editor" role (case-insensitive)
            if "video editor" in display_name:
                return True
        return False

    def is_admin(self) -> bool:
        """Check if user is an admin."""
        if not self.roles:
            return False
        return any(
            role.get("system_name", "").lower() == "admin"
            for role in self.roles
        )


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
        """Get the current API user's details (using service token)."""
        data = await self._request("GET", "users/me")
        return BookStackUser(
            id=data["id"],
            name=data["name"],
            email=data["email"],
            roles=data.get("roles"),
        )

    async def validate_user_token(self, token: str) -> BookStackUser | None:
        """
        Validate a user's BookStack API token and return their info.

        Args:
            token: BookStack API token in format "token_id:token_secret"

        Returns:
            BookStackUser if valid, None if invalid
        """
        if not self.base_url:
            logger.warning("BookStack URL not configured")
            return None

        try:
            headers = {
                "Authorization": f"Token {token}",
                "Content-Type": "application/json",
            }

            async with httpx.AsyncClient(verify=False) as client:
                # First try /api/users/me
                url = f"{self.base_url}/api/users/me"
                response = await client.get(url, headers=headers, timeout=10.0)

                if response.status_code == 200:
                    data = response.json()
                    return BookStackUser(
                        id=data["id"],
                        name=data["name"],
                        email=data["email"],
                        roles=data.get("roles"),
                    )
                elif response.status_code == 500:
                    # Some BookStack versions have a bug in /users/me
                    # Try fallback validation
                    logger.debug("Trying fallback token validation due to /users/me 500 error")
                    return await self._validate_token_fallback(client, headers)
                else:
                    logger.debug(f"Token validation failed: {response.status_code}")
                    return None
        except Exception as e:
            logger.error(f"Token validation error: {e}")
            return None

    async def _validate_token_fallback(
        self, client: httpx.AsyncClient, headers: dict
    ) -> BookStackUser | None:
        """
        Fallback token validation for BookStack versions with /users/me bug.

        Validates token by calling /api/books, then gets user info from /api/users/1.
        """
        try:
            # Validate token works by calling any endpoint
            test_url = f"{self.base_url}/api/books"
            response = await client.get(test_url, headers=headers, timeout=10.0)

            if response.status_code != 200:
                logger.debug(f"Fallback validation failed: {response.status_code}")
                return None

            # Token is valid. Try to get admin user info
            user_url = f"{self.base_url}/api/users/1"
            user_response = await client.get(user_url, headers=headers, timeout=10.0)

            if user_response.status_code == 200:
                data = user_response.json()
                return BookStackUser(
                    id=data["id"],
                    name=data["name"],
                    email=data["email"],
                    roles=data.get("roles", []),
                )

            # Can't get user details, but token is valid
            # Return minimal user - assume admin since they have valid API token
            logger.warning("Token valid but cannot fetch user details - assuming admin")
            return BookStackUser(
                id=0,
                name="API Token User",
                email="api@bookstack.local",
                roles=[{"display_name": "Admin", "system_name": "admin"}],
            )

        except Exception as e:
            logger.error(f"Fallback validation error: {e}")
            return None

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
