import base64
import hashlib
import json
import secrets
import tempfile
import webbrowser
from pathlib import Path
from urllib.parse import urlencode
from typing import Optional, Dict, Any
import httpx

from settings import AUTH_BASE_AUTHORIZE, AUTH_BASE_TOKEN, CLIENT_ID, REDIRECT_URI, SCOPES
from storage import TokenStorage

class OAuthManager:
    """OAuth PKCE flow implementation (plan.md section 3)"""

    def __init__(self):
        self.storage = TokenStorage()
        self.code_verifier: Optional[str] = None
        self.state: Optional[str] = None
        self.pkce_file = Path(tempfile.gettempdir()) / "anthropic_oauth_pkce.json"

    def _save_pkce(self):
        """Save PKCE values temporarily"""
        self.pkce_file.write_text(json.dumps({
            "code_verifier": self.code_verifier,
            "state": self.state
        }))

    def _load_pkce(self):
        """Load saved PKCE values"""
        if self.pkce_file.exists():
            try:
                data = json.loads(self.pkce_file.read_text())
                return data.get("code_verifier"), data.get("state")
            except (json.JSONDecodeError, IOError):
                pass
        return None, None

    def _clear_pkce(self):
        """Clear PKCE values after use"""
        if self.pkce_file.exists():
            self.pkce_file.unlink()

    def generate_pkce(self) -> tuple[str, str]:
        """Generate PKCE code verifier and challenge (plan.md section 3.1)"""
        # Generate high-entropy code_verifier (43-128 chars)
        code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode('utf-8').rstrip('=')

        # Create code_challenge using SHA-256
        challenge_bytes = hashlib.sha256(code_verifier.encode('utf-8')).digest()
        code_challenge = base64.urlsafe_b64encode(challenge_bytes).decode('utf-8').rstrip('=')

        return code_verifier, code_challenge

    def get_authorize_url(self) -> str:
        """Construct OAuth authorize URL with PKCE (plan.md section 3.2)"""
        self.code_verifier, code_challenge = self.generate_pkce()
        # OpenCode uses the verifier as the state
        self.state = self.code_verifier

        # Save PKCE values for later use
        self._save_pkce()

        params = {
            "code": "true",  # Critical parameter from OpenCode
            "client_id": CLIENT_ID,
            "response_type": "code",
            "redirect_uri": REDIRECT_URI,
            "scope": SCOPES,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "state": self.state
        }

        # Use claude.ai for authorization (Claude Pro/Max)
        return f"{AUTH_BASE_AUTHORIZE}/oauth/authorize?{urlencode(params)}"

    def start_login_flow(self) -> str:
        """Start the OAuth login flow by opening browser (plan.md section 3.3)"""
        auth_url = self.get_authorize_url()

        # Open the authorization URL in the default browser
        webbrowser.open(auth_url)

        return auth_url

    async def exchange_code(self, code: str) -> Dict[str, Any]:
        """Exchange authorization code for tokens (plan.md section 3.4)"""
        # Split the code and state (they come as "code#state")
        parts = code.split("#")
        actual_code = parts[0]
        state = parts[1] if len(parts) > 1 else None

        # Load saved PKCE verifier if not already loaded
        if not self.code_verifier:
            self.code_verifier, self.state = self._load_pkce()

        if not self.code_verifier:
            raise ValueError("No PKCE verifier found. Start login flow first.")

        # Use the state from the code if available, otherwise use saved state
        if not state:
            state = self.state

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{AUTH_BASE_TOKEN}/v1/oauth/token",
                json={
                    "code": actual_code,
                    "state": state,
                    "grant_type": "authorization_code",
                    "client_id": CLIENT_ID,
                    "redirect_uri": REDIRECT_URI,
                    "code_verifier": self.code_verifier
                },
                headers={"Content-Type": "application/json"}
            )

        if response.status_code != 200:
            error_detail = response.text
            raise Exception(f"Token exchange failed: {response.status_code} - {error_detail}")

        token_data = response.json()

        # Store tokens securely
        self.storage.save_tokens(
            access_token=token_data["access_token"],
            refresh_token=token_data["refresh_token"],
            expires_in=token_data.get("expires_in", 3600)
        )

        # Clear PKCE values after successful exchange
        self._clear_pkce()
        self.code_verifier = None
        self.state = None

        return {"status": "success", "message": "Tokens obtained successfully"}

    async def refresh_tokens(self) -> bool:
        """Refresh expired tokens (plan.md section 3.5)"""
        import logging
        logger = logging.getLogger(__name__)

        refresh_token = self.storage.get_refresh_token()
        if not refresh_token:
            logger.warning("No refresh token available for refresh")
            return False

        logger.info("Attempting to refresh OAuth tokens...")
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{AUTH_BASE_TOKEN}/v1/oauth/token",
                    json={
                        "grant_type": "refresh_token",
                        "refresh_token": refresh_token,
                        "client_id": CLIENT_ID
                    },
                    headers={"Content-Type": "application/json"}
                )

                if response.status_code != 200:
                    logger.error(f"Token refresh failed with status {response.status_code}: {response.text}")
                    return False

                token_data = response.json()

                # Update stored tokens
                self.storage.save_tokens(
                    access_token=token_data["access_token"],
                    refresh_token=token_data["refresh_token"],
                    expires_in=token_data.get("expires_in", 3600)
                )

                logger.info("Successfully refreshed OAuth tokens")
                return True
            except Exception as e:
                logger.error(f"Token refresh failed with exception: {e}")
                return False

    async def get_valid_token_async(self) -> Optional[str]:
        """Get a valid access token, refreshing if necessary (async version for FastAPI)"""
        import logging
        logger = logging.getLogger(__name__)

        if not self.storage.is_token_expired():
            return self.storage.get_access_token()

        logger.info("Token expired, attempting automatic refresh...")
        # Try to refresh
        if await self.refresh_tokens():
            return self.storage.get_access_token()

        logger.error("Failed to refresh token automatically")
        return None

    def get_valid_token(self) -> Optional[str]:
        """Get a valid access token, refreshing if necessary (sync version for CLI)"""
        if not self.storage.is_token_expired():
            return self.storage.get_access_token()

        # Try to refresh - only use asyncio.run if not in an event loop
        import asyncio
        try:
            loop = asyncio.get_running_loop()
            # We're in an async context, can't use asyncio.run
            return None
        except RuntimeError:
            # No event loop running, safe to use asyncio.run
            if asyncio.run(self.refresh_tokens()):
                return self.storage.get_access_token()

        return None