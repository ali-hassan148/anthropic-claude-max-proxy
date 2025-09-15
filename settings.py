import os
from pathlib import Path
from config_loader import get_config_loader

# Get the config loader instance
config = get_config_loader()

# Server configuration
PORT = config.get("PORT", "server.port", 8081)
LOG_LEVEL = config.get("LOG_LEVEL", "server.log_level", "info")

# Model configuration
DEFAULT_MODEL = config.get("DEFAULT_MODEL", "models.default", "claude-sonnet-4-0")

# Anthropic API configuration
ANTHROPIC_VERSION = config.get("ANTHROPIC_VERSION", "api.anthropic_version", "2023-06-01")
ANTHROPIC_BETA = config.get("ANTHROPIC_BETA", "api.anthropic_beta",
                            "oauth-2025-04-20,claude-code-20250219,interleaved-thinking-2025-05-14,fine-grained-tool-streaming-2025-05-14")
API_BASE = config.get("API_BASE", "api.api_base", "https://api.anthropic.com")
REQUEST_TIMEOUT = config.get("REQUEST_TIMEOUT", "api.request_timeout", 120.0)

# OAuth configuration
AUTH_BASE_AUTHORIZE = config.get("AUTH_BASE_AUTHORIZE", "oauth.auth_base_authorize", "https://claude.ai")
AUTH_BASE_TOKEN = config.get("AUTH_BASE_TOKEN", "oauth.auth_base_token", "https://console.anthropic.com")
CLIENT_ID = config.get("CLIENT_ID", "oauth.client_id", "9d1c250a-e61b-44d9-88ed-5944d1962f5e")
REDIRECT_URI = config.get("REDIRECT_URI", "oauth.redirect_uri", "https://console.anthropic.com/oauth/code/callback")
SCOPES = config.get("SCOPES", "oauth.scopes", "org:create_api_key user:profile user:inference")

# Token storage
TOKEN_FILE = config.get("TOKEN_FILE", "storage.token_file", str(Path.home() / ".anthropic-claude-max-proxy" / "tokens.json"))