# Anthropic OAuth Proxy for Claude Pro/Max

A minimal local proxy that exposes an OpenAI-compatible API while using Anthropic's OAuth flow for Claude Pro/Max accounts.

⚠️ **IMPORTANT WARNING**: This proxy uses Anthropic's consumer OAuth flow (as used by Claude Code) and may break or be disallowed at any time. It is subject to Anthropic policy changes. Use at your own risk. For officially supported access, use the Claude Code provider directly.

**Note**: This proxy specifically uses the Claude Pro/Max OAuth flow through `claude.ai` (not the console API key flow). You need an active Claude Pro or Claude Max subscription for this to work.

## Features

- ✅ OpenAI-compatible `/v1/chat/completions` endpoint
- ✅ OAuth PKCE flow with browser-based authentication (no CLI required)
- ✅ Automatic token refresh on expiry
- ✅ Full streaming support with SSE translation
- ✅ Compatible with Cline, Roo, and other OpenAI-compatible tools
- ✅ Secure token storage with proper file permissions
- ✅ Localhost-only binding for security

## Installation

1. **Clone or download this repository**

2. **Install dependencies**:
```bash
pip install -r requirements.txt
```

## Configuration

The proxy can be configured using environment variables. Create a `.env` file or export these variables:

```bash
# Server configuration
PORT=8081                    # Port to run the proxy on (default: 8081)
LOG_LEVEL=info              # Logging level (default: info)

# Anthropic API configuration
ANTHROPIC_VERSION=2023-06-01                           # API version header
ANTHROPIC_BETA=oauth-2025-04-20,claude-code-20250219  # Beta headers for OAuth
API_BASE=https://api.anthropic.com                     # Anthropic API base URL

# OAuth configuration
AUTH_BASE=https://console.anthropic.com                                    # OAuth authorization base URL
CLIENT_ID=9d1c250a-e61b-44d9-88ed-5944d1962f5e                           # Claude Code client ID
TOKEN_FILE=~/.anthropic-oauth-proxy/tokens.json                          # Token storage location

# Model defaults
DEFAULT_MODEL=claude-3-7-sonnet-latest  # Default model if not specified
```

## Usage

### 1. Start the proxy server

```bash
python proxy.py
```

The server will start on `http://127.0.0.1:8081`

### 2. Authenticate with Anthropic

1. Visit `http://127.0.0.1:8081/auth/login` in your browser
2. You'll be redirected to Anthropic's login page
3. Complete the authentication process
4. After authorization, copy the code shown on the Anthropic page
5. Paste the code into the form on the proxy page
6. Click "Submit Code"

You should see a success message if authentication worked.

### 3. Check authentication status

Visit `http://127.0.0.1:8081/auth/status` to verify your tokens are valid.

### 4. Configure your OpenAI-compatible client

#### For Cline/Roo:
1. Choose **OpenAI** as the provider
2. Set Base URL to: `http://127.0.0.1:8081/v1`
3. Set API Key to any placeholder string (e.g., `dummy`)
4. Select model: `claude-3-7-sonnet-latest` or another available model

#### For other tools:
Configure them to use:
- Base URL: `http://127.0.0.1:8081/v1`
- API Key: any non-empty string
- Model: See available models below

## Available Models

The proxy supports all current Claude models:

### Claude 4 (Latest Generation)
- `claude-opus-4-1-20250805` - Latest Opus 4.1 (best for complex tasks)
- `claude-opus-4-1` - Alias for latest Opus 4.1
- `claude-sonnet-4-20250514` - Claude Sonnet 4 (excellent coding performance)
- `claude-sonnet-4-0` - Alias for Claude Sonnet 4

### Claude 3.7
- `claude-3-7-sonnet-20250219` - Claude 3.7 Sonnet (hybrid reasoning)
- `claude-3-7-sonnet-latest` - Alias for latest 3.7 Sonnet (default model)

### Claude 3.5
- `claude-3-5-sonnet-latest` - Latest Sonnet 3.5
- `claude-3-5-sonnet-20241022` - Specific Sonnet 3.5 version
- `claude-3-5-haiku-20241022` - Fast and efficient Haiku 3.5
- `claude-3-5-haiku-latest` - Latest Haiku 3.5

### Claude 3
- `claude-3-opus-latest` - Claude 3 Opus
- `claude-3-opus-20240229` - Specific Opus 3 version
- `claude-3-sonnet-20240229` - Claude 3 Sonnet
- `claude-3-haiku-20240307` - Claude 3 Haiku

## Available Endpoints

- `GET /healthz` - Health check
- `GET /auth/login` - Start OAuth login flow
- `POST /auth/exchange` - Exchange authorization code for tokens
- `GET /auth/status` - Check token status (no secrets exposed)
- `POST /v1/chat/completions` - OpenAI-compatible chat endpoint
- `GET /v1/models` - List available models

## Testing

### Test non-streaming request:
```bash
curl -X POST http://127.0.0.1:8081/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-3-7-sonnet-latest",
    "messages": [
      {"role": "system", "content": "You are a helpful assistant."},
      {"role": "user", "content": "Hello, how are you?"}
    ],
    "max_tokens": 100
  }'
```

### Test streaming request:
```bash
curl -X POST http://127.0.0.1:8081/v1/chat/completions \
  -H "Content-Type: application/json" \
  --no-buffer \
  -d '{
    "model": "claude-3-7-sonnet-latest",
    "messages": [
      {"role": "user", "content": "Count to 5 slowly"}
    ],
    "stream": true
  }'
```

## Troubleshooting

### "Credential is only authorized for use with Claude Code" error
- Ensure the `ANTHROPIC_BETA` environment variable includes the correct beta headers
- Current required headers: `oauth-2025-04-20,claude-code-20250219`
- These may change; check GitHub issues for updates

### 401 Unauthorized errors
- Your token may have expired
- Visit `/auth/login` to re-authenticate
- The proxy will attempt automatic refresh, but if the refresh token is invalid, you'll need to login again

### 429 Rate limit errors
- You've hit your Claude Pro/Max usage limits
- Usage resets every 5 hours on Pro/Max plans
- Check your usage at claude.ai

### Connection refused
- Ensure the proxy is running
- Check that you're using the correct port (default: 8081)
- Verify the proxy is bound to 127.0.0.1

## Security Notes

- Tokens are stored in `~/.anthropic-oauth-proxy/tokens.json` with 600 permissions (owner read/write only)
- The proxy binds only to localhost (127.0.0.1) for security
- Never expose this proxy to the internet
- The client_id is read from environment variables to avoid hardcoding

## Limitations

- This is an MVP implementation with minimal features
- No support for function calling/tools (can be added later)
- No support for image uploads (can be added later)
- Single-user only (no multi-tenant support)
- Uses consumer OAuth flow which may change without notice

## Legal Notice

This tool uses Anthropic's consumer OAuth flow as observed in Claude Code. It is not officially supported by Anthropic and may stop working if their policies change. For production use or officially supported access, use the Claude Code provider or Anthropic's official API with console API keys.

## Contributing

This is a minimal implementation designed to be easily understood and modified. Feel free to extend it with additional features as needed.

## License

Use at your own risk. This tool is provided as-is for educational and development purposes.