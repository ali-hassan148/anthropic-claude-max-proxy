import asyncio
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, Confirm
from rich import print as rprint

from storage import TokenStorage
from oauth import OAuthManager
from auth_cli import CLIAuthFlow
from proxy import ProxyServer

console = Console()

class AnthropicProxyCLI:
    """Main CLI interface for Anthropic Claude Max Proxy"""

    def __init__(self):
        self.storage = TokenStorage()
        self.oauth = OAuthManager()
        self.auth_flow = CLIAuthFlow()
        self.proxy_server = ProxyServer()
        self.server_thread: Optional[threading.Thread] = None
        self.server_running = False
        # Create a single event loop for the CLI session
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

    def clear_screen(self):
        """Clear the terminal screen"""
        console.clear()

    def display_header(self):
        """Display the application header"""
        console.print("=" * 50)
        console.print("    Anthropic Claude Max Proxy", style="bold")
        console.print("=" * 50)

    def get_auth_status(self) -> tuple[str, str]:
        """Get authentication status and expiry info"""
        status = self.storage.get_status()

        if not status["has_tokens"]:
            return "NO AUTH", "No tokens available"

        if status["is_expired"]:
            return "EXPIRED", f"Expired {status['time_until_expiry']}"

        # Calculate time remaining
        if status["expires_at"]:
            expires_dt = datetime.fromisoformat(status["expires_at"])
            now = datetime.now()
            delta = expires_dt - now

            if delta.total_seconds() < 0:
                return "EXPIRED", "Token expired"

            hours = int(delta.total_seconds() // 3600)
            minutes = int((delta.total_seconds() % 3600) // 60)

            if hours > 0:
                time_str = f"{hours}h {minutes}m"
            else:
                time_str = f"{minutes}m"

            return "VALID", f"Expires in {time_str}"

        return "UNKNOWN", "Unable to determine status"

    def display_menu(self):
        """Display the main menu"""
        auth_status, auth_detail = self.get_auth_status()

        # Status color based on state
        if auth_status == "VALID":
            status_style = "green"
        elif auth_status == "EXPIRED":
            status_style = "yellow"
        else:
            status_style = "red"

        console.print(f" Auth Status: [{status_style}]{auth_status}[/{status_style}] ({auth_detail})")

        if self.server_running:
            console.print(" Server Status: [green]RUNNING[/green] at http://127.0.0.1:8081")
        else:
            console.print(" Server Status: [dim]STOPPED[/dim]")

        console.print("-" * 50)

        # Menu options
        if self.server_running:
            console.print(" 1. Stop Proxy Server")
        else:
            console.print(" 1. Start Proxy Server")

        console.print(" 2. Login / Re-authenticate")
        console.print(" 3. Refresh Token")
        console.print(" 4. Show Token Status")
        console.print(" 5. Logout (Clear Tokens)")
        console.print(" 6. Exit")
        console.print("=" * 50)

    def show_token_status(self):
        """Display detailed token status"""
        status = self.storage.get_status()

        table = Table(title="Token Status Details")
        table.add_column("Property", style="cyan")
        table.add_column("Value")

        table.add_row("Has Tokens", "Yes" if status["has_tokens"] else "No")
        table.add_row("Is Expired", "Yes" if status["is_expired"] else "No")

        if status["expires_at"]:
            table.add_row("Expires At", status["expires_at"])
            table.add_row("Time Until Expiry", status["time_until_expiry"])

        table.add_row("Token File", str(self.storage.token_file))

        console.print(table)
        console.print("\nPress Enter to continue...")
        input()

    def start_proxy_server(self):
        """Start the proxy server in a background thread"""
        if self.server_running:
            console.print("[yellow]Server is already running[/yellow]")
            return

        # Check authentication first
        auth_status, _ = self.get_auth_status()
        if auth_status != "VALID":
            console.print("[red]ERROR:[/red] Valid authentication required to start server")
            console.print("Please login first (option 2)")
            console.print("\nPress Enter to continue...")
            input()
            return

        console.print("Starting proxy server...")

        try:
            # Start server in background thread
            self.server_thread = threading.Thread(target=self.proxy_server.run, daemon=True)
            self.server_thread.start()
            self.server_running = True

            # Wait a moment for server to start
            time.sleep(1)

            console.print("[green][OK][/green] Proxy running at http://127.0.0.1:8081")
            console.print("\nYou can now configure your OpenAI-compatible clients:")
            console.print("  Base URL: http://127.0.0.1:8081/v1")
            console.print("  API Key: any-placeholder-string")
            console.print("\nPress Enter to continue...")
            input()

        except Exception as e:
            console.print(f"[red]ERROR:[/red] Failed to start server: {e}")
            self.server_running = False
            console.print("\nPress Enter to continue...")
            input()

    def stop_proxy_server(self):
        """Stop the proxy server"""
        if not self.server_running:
            console.print("[yellow]Server is not running[/yellow]")
            return

        console.print("Stopping proxy server...")

        try:
            self.proxy_server.stop()
            self.server_running = False
            console.print("[green][OK][/green] Server stopped")

        except Exception as e:
            console.print(f"[red]ERROR:[/red] Failed to stop server: {e}")

        console.print("\nPress Enter to continue...")
        input()

    def login(self):
        """Handle the login flow"""
        console.print("Starting OAuth login flow...")

        try:
            # Use the event loop to run the async authenticate method
            success = self.loop.run_until_complete(self.auth_flow.authenticate())

            if success:
                console.print("[green]Authentication successful![/green]")
            else:
                console.print("[red]Authentication failed[/red]")

        except Exception as e:
            console.print(f"[red]ERROR:[/red] {e}")

        console.print("\nPress Enter to continue...")
        input()

    def refresh_token(self):
        """Attempt to refresh the access token"""
        console.print("Attempting to refresh token...")

        try:
            success = self.loop.run_until_complete(self.oauth.refresh_tokens())

            if success:
                console.print("[green]Token refreshed successfully![/green]")
            else:
                console.print("[red]Token refresh failed - please login again[/red]")

        except Exception as e:
            console.print(f"[red]ERROR:[/red] {e}")

        console.print("\nPress Enter to continue...")
        input()

    def logout(self):
        """Clear stored tokens"""
        if Confirm.ask("Are you sure you want to clear all tokens?"):
            try:
                self.storage.clear_tokens()
                console.print("[green]Tokens cleared successfully[/green]")
            except Exception as e:
                console.print(f"[red]ERROR:[/red] {e}")
        else:
            console.print("Logout cancelled")

        console.print("\nPress Enter to continue...")
        input()

    def run(self):
        """Main CLI loop"""
        while True:
            self.clear_screen()
            self.display_header()
            self.display_menu()

            choice = Prompt.ask("Select option [1-6]", choices=["1", "2", "3", "4", "5", "6"])

            if choice == "1":
                if self.server_running:
                    self.stop_proxy_server()
                else:
                    self.start_proxy_server()
            elif choice == "2":
                self.login()
            elif choice == "3":
                self.refresh_token()
            elif choice == "4":
                self.show_token_status()
            elif choice == "5":
                self.logout()
            elif choice == "6":
                if self.server_running:
                    console.print("Stopping server before exit...")
                    self.stop_proxy_server()
                # Clean up the event loop
                self.loop.close()
                console.print("Goodbye!")
                break

def main():
    """Entry point for the CLI"""
    try:
        cli = AnthropicProxyCLI()
        cli.run()
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/yellow]")
        console.print("Goodbye!")
    except Exception as e:
        console.print(f"\n[red]Fatal error:[/red] {e}")

if __name__ == "__main__":
    main()