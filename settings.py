import os
from pathlib import Path

# Port configuration
PORT = int(os.getenv("PORT", 8081))
LOG_LEVEL = os.getenv("LOG_LEVEL", "info")

# Anthropic API configuration (from plan.md section 2)
ANTHROPIC_VERSION = os.getenv("ANTHROPIC_VERSION", "2023-06-01")
# Updated beta headers to match OpenCode implementation for OAuth support
ANTHROPIC_BETA = os.getenv("ANTHROPIC_BETA", "oauth-2025-04-20,claude-code-20250219,interleaved-thinking-2025-05-14,fine-grained-tool-streaming-2025-05-14")
API_BASE = os.getenv("API_BASE", "https://api.anthropic.com")

# OAuth configuration (from plan.md sections 2 and 3)
# For Claude Pro/Max, authorization goes through claude.ai
AUTH_BASE_AUTHORIZE = os.getenv("AUTH_BASE_AUTHORIZE", "https://claude.ai")
# Token exchange always goes through console.anthropic.com
AUTH_BASE_TOKEN = os.getenv("AUTH_BASE_TOKEN", "https://console.anthropic.com")
CLIENT_ID = os.getenv("CLIENT_ID", "9d1c250a-e61b-44d9-88ed-5944d1962f5e")
REDIRECT_URI = "https://console.anthropic.com/oauth/code/callback"
SCOPES = "org:create_api_key user:profile user:inference"

# Token storage (from plan.md section 3.6)
TOKEN_FILE = os.getenv("TOKEN_FILE", str(Path.home() / ".anthropic-oauth-proxy" / "tokens.json"))

# Model defaults (from plan.md section 7)
DEFAULT_MODEL = "claude-3-7-sonnet-latest"  # Good balance of performance and cost for coding

# Timeout settings
REQUEST_TIMEOUT = 120.0