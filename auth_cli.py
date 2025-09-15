import webbrowser
from typing import Optional
from rich.console import Console
from rich.prompt import Prompt

from oauth import OAuthManager
from storage import TokenStorage

console = Console()

class CLIAuthFlow:
    """Handle OAuth authentication flow in CLI"""

    def __init__(self):
        self.oauth = OAuthManager()
        self.storage = TokenStorage()

    async def authenticate(self) -> bool:
        """
        Run the OAuth authentication flow
        Returns True if successful, False otherwise
        """
        try:
            # Step 1: Generate auth URL and open browser
            console.print("\n[bold]Step 1:[/bold] Opening browser for authentication...")
            auth_url = self.oauth.get_authorize_url()

            # Try to open browser
            if webbrowser.open(auth_url):
                console.print("[green][OK][/green] Browser opened successfully")
            else:
                console.print("[yellow]Could not open browser automatically[/yellow]")
                console.print(f"Please open this URL manually:\n{auth_url}")

            # Step 2: Instructions
            console.print("\n[bold]Step 2:[/bold] Complete the login process in your browser")
            console.print("  1. Login to your Claude Pro/Max account if prompted")
            console.print("  2. Authorize the application")
            console.print("  3. You will see an authorization code on the Anthropic page")

            # Step 3: Get code from user
            console.print("\n[bold]Step 3:[/bold] Paste the authorization code below")
            console.print("[dim]The code should look like: CODE#STATE[/dim]\n")

            # Use simple input to avoid event loop conflicts
            try:
                code = input("Authorization code: ")
            except KeyboardInterrupt:
                console.print("\n[yellow]Authentication cancelled by user[/yellow]")
                return False

            if not code or len(code.strip()) < 10:
                console.print("[red]Invalid or missing code. Please paste the complete code from the browser.[/red]")
                return False

            # Step 4: Exchange code for tokens
            console.print("\n[bold]Step 4:[/bold] Exchanging code for tokens...")

            result = await self.oauth.exchange_code(code.strip())

            if result and result.get("status") == "success":
                console.print("[green][OK][/green] Tokens obtained successfully")

                # Show token status
                status = self.storage.get_status()
                if status["expires_at"]:
                    console.print(f"Token expires at: {status['expires_at']}")

                return True
            else:
                console.print("[red][ERROR][/red] Failed to exchange code for tokens")
                return False

        except Exception as e:
            console.print(f"[red][ERROR][/red] Authentication failed: {e}")

            # Offer retry
            retry = Prompt.ask("\nWould you like to try again?", choices=["y", "n"], default="n")
            if retry.lower() == "y":
                return await self.authenticate()

            return False

    async def refresh_token(self) -> bool:
        """
        Attempt to refresh the access token
        Returns True if successful, False otherwise
        """
        try:
            console.print("Refreshing access token...")

            success = await self.oauth.refresh_tokens()

            if success:
                console.print("[green][OK][/green] Token refreshed successfully")

                # Show new expiry
                status = self.storage.get_status()
                if status["expires_at"]:
                    console.print(f"New expiry: {status['expires_at']}")

                return True
            else:
                console.print("[red][ERROR][/red] Token refresh failed")
                console.print("You may need to login again")
                return False

        except Exception as e:
            console.print(f"[red][ERROR][/red] Refresh failed: {e}")
            return False