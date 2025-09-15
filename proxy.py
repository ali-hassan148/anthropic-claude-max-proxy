import json
import logging
import time
from typing import Optional, Dict, Any
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from pydantic import BaseModel
import httpx
import uvicorn

from settings import (
    PORT, LOG_LEVEL, API_BASE, ANTHROPIC_VERSION, ANTHROPIC_BETA,
    DEFAULT_MODEL, REQUEST_TIMEOUT
)
from oauth import OAuthManager
from storage import TokenStorage
from translate import RequestTranslator, ResponseTranslator, StreamTranslator

# Setup logging
logging.basicConfig(level=getattr(logging, LOG_LEVEL.upper()))
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(title="Anthropic OAuth Proxy", version="1.0.0")

# Initialize managers
oauth_manager = OAuthManager()
token_storage = TokenStorage()

# Request models
class CodeExchangeRequest(BaseModel):
    code: str

class ChatCompletionRequest(BaseModel):
    model: Optional[str] = DEFAULT_MODEL
    messages: list
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    max_tokens: Optional[int] = None
    max_completion_tokens: Optional[int] = None
    stream: Optional[bool] = False
    stream_options: Optional[Dict[str, Any]] = None


# Helper functions
async def make_anthropic_request(request_data: Dict[str, Any], access_token: str, retry_on_401: bool = True):
    """Make a request to Anthropic API with automatic token refresh (plan.md section 5)"""
    headers = {
        "Authorization": f"Bearer {access_token}",
        "anthropic-version": ANTHROPIC_VERSION,
        "anthropic-beta": ANTHROPIC_BETA,
        "Content-Type": "application/json",
        "User-Agent": "anthropic-oauth-proxy/1.0"
    }

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        response = await client.post(
            f"{API_BASE}/v1/messages",
            headers=headers,
            json=request_data
        )

        # Handle 401 with automatic refresh (plan.md section 5.3)
        if response.status_code == 401 and retry_on_401:
            logger.info("Got 401, attempting token refresh")
            if await oauth_manager.refresh_tokens():
                new_token = token_storage.get_access_token()
                if new_token:
                    return await make_anthropic_request(request_data, new_token, retry_on_401=False)

        return response


async def stream_anthropic_response(request_data: Dict[str, Any], access_token: str, model: str, include_usage: bool = False):
    """Stream response from Anthropic API"""
    headers = {
        "Authorization": f"Bearer {access_token}",
        "anthropic-version": ANTHROPIC_VERSION,
        "anthropic-beta": ANTHROPIC_BETA,
        "Content-Type": "application/json",
        "User-Agent": "anthropic-oauth-proxy/1.0"
    }

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        async with client.stream(
            "POST",
            f"{API_BASE}/v1/messages",
            headers=headers,
            json=request_data
        ) as response:
            if response.status_code != 200:
                error_text = await response.aread()
                try:
                    error_data = json.loads(error_text.decode())
                    error_msg = error_data.get("error", {}).get("message", "Unknown error")
                    if "OAuth token lacks required scopes" in error_msg:
                        error_msg += " - Please re-authenticate at /auth/login to refresh your OAuth token with proper scopes"
                    raise HTTPException(status_code=response.status_code, detail={"error": {"message": error_msg}})
                except json.JSONDecodeError:
                    raise HTTPException(status_code=response.status_code, detail=error_text.decode())

            async def generate():
                async for line in response.aiter_lines():
                    yield line + "\n"

            # Translate the stream
            async for chunk in StreamTranslator.translate_stream(generate(), model, include_usage):
                yield chunk


# Routes (plan.md section 4)

@app.get("/healthz")
async def health_check():
    """Health check endpoint (plan.md section 4.1)"""
    return {"ok": True}


@app.get("/auth/login", response_class=HTMLResponse)
async def auth_login():
    """Start OAuth login flow (plan.md section 4.2)"""
    auth_url = oauth_manager.start_login_flow()

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Anthropic OAuth Login</title>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                max-width: 600px;
                margin: 50px auto;
                padding: 20px;
                background: #f5f5f5;
            }}
            .container {{
                background: white;
                padding: 30px;
                border-radius: 8px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }}
            h1 {{
                color: #333;
                margin-bottom: 20px;
            }}
            .step {{
                margin: 20px 0;
                padding: 15px;
                background: #f8f9fa;
                border-left: 4px solid #007bff;
                border-radius: 4px;
            }}
            .code-input {{
                width: 100%;
                padding: 10px;
                font-family: monospace;
                font-size: 14px;
                border: 1px solid #ddd;
                border-radius: 4px;
                margin: 10px 0;
            }}
            .submit-btn {{
                background: #007bff;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 4px;
                cursor: pointer;
                font-size: 16px;
            }}
            .submit-btn:hover {{
                background: #0056b3;
            }}
            .warning {{
                background: #fff3cd;
                border: 1px solid #ffc107;
                color: #856404;
                padding: 10px;
                border-radius: 4px;
                margin-top: 20px;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🔐 Anthropic OAuth Login</h1>

            <div class="step">
                <strong>Step 1:</strong> A browser window should have opened. If not,
                <a href="{auth_url}" target="_blank">click here</a> to open the authorization page.
            </div>

            <div class="step">
                <strong>Step 2:</strong> Complete the login process in the browser.
            </div>

            <div class="step">
                <strong>Step 3:</strong> After authorization, you'll see a code on the Anthropic page.
                Copy and paste it below:
            </div>

            <form id="codeForm">
                <input type="text"
                       class="code-input"
                       id="authCode"
                       placeholder="Paste your authorization code here..."
                       required>
                <button type="submit" class="submit-btn">Submit Code</button>
            </form>

            <div id="result"></div>

            <div class="warning">
                <strong>Note:</strong> This proxy uses Anthropic's consumer OAuth flow (Claude Pro/Max).
                It may stop working if Anthropic changes their policy. Use at your own risk.
            </div>
        </div>

        <script>
            document.getElementById('codeForm').addEventListener('submit', async (e) => {{
                e.preventDefault();
                const code = document.getElementById('authCode').value.trim();
                const resultDiv = document.getElementById('result');

                if (!code) {{
                    resultDiv.innerHTML = '<p style="color: red;">Please enter a code</p>';
                    return;
                }}

                resultDiv.innerHTML = '<p>Exchanging code for tokens...</p>';

                try {{
                    const response = await fetch('/auth/exchange', {{
                        method: 'POST',
                        headers: {{'Content-Type': 'application/json'}},
                        body: JSON.stringify({{code: code}})
                    }});

                    const data = await response.json();

                    if (response.ok) {{
                        resultDiv.innerHTML = '<p style="color: green;">✅ Authentication successful! You can now use the proxy.</p>';
                    }} else {{
                        resultDiv.innerHTML = `<p style="color: red;">❌ Error: ${{data.detail || 'Authentication failed'}}</p>`;
                    }}
                }} catch (error) {{
                    resultDiv.innerHTML = `<p style="color: red;">❌ Error: ${{error.message}}</p>`;
                }}
            }});
        </script>
    </body>
    </html>
    """

    return html_content


@app.post("/auth/exchange")
async def auth_exchange(request: CodeExchangeRequest):
    """Exchange authorization code for tokens (plan.md section 4.3)"""
    try:
        result = await oauth_manager.exchange_code(request.code)
        return result
    except Exception as e:
        logger.error(f"Token exchange failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/auth/status")
async def auth_status():
    """Get token status without exposing secrets (plan.md section 4.4)"""
    return token_storage.get_status()


@app.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest):
    """OpenAI-compatible chat completions endpoint (plan.md section 4.5)"""
    start_time = time.time()

    # Get valid access token
    access_token = oauth_manager.get_valid_token()
    if not access_token:
        logger.error("No valid token available")
        raise HTTPException(
            status_code=401,
            detail={"error": {"message": "OAuth expired; visit /auth/login again"}}
        )

    # Translate request to Anthropic format (plan.md section 6.1)
    anthropic_request = RequestTranslator.openai_to_anthropic(request.model_dump())

    # Log request (plan.md section 9)
    logger.info(f"POST /v1/chat/completions model={request.model} stream={request.stream}")

    try:
        if request.stream:
            # Check if usage should be included in streaming
            include_usage = False
            if request.stream_options:
                include_usage = request.stream_options.get("include_usage", False)

            # Handle streaming response
            return StreamingResponse(
                stream_anthropic_response(anthropic_request, access_token, request.model, include_usage),
                media_type="text/event-stream"
            )
        else:
            # Handle non-streaming response
            response = await make_anthropic_request(anthropic_request, access_token)

            elapsed_ms = int((time.time() - start_time) * 1000)
            logger.info(f"Anthropic request completed in {elapsed_ms}ms status={response.status_code}")

            if response.status_code == 429:
                # Pass through rate limit (plan.md section 9)
                raise HTTPException(status_code=429, detail=response.json())
            elif response.status_code >= 500:
                # Pass through server errors
                raise HTTPException(
                    status_code=response.status_code,
                    detail={"error": response.text, "request_id": response.headers.get("x-request-id")}
                )
            elif response.status_code != 200:
                # Handle other errors
                error_data = response.json()
                error_msg = error_data.get("error", {}).get("message", "Unknown error")

                # Check for OAuth-specific errors (plan.md section 3.7)
                if "credential is only authorized for use with Claude Code" in error_msg:
                    error_msg += " - Ensure beta header is set and scopes include user:inference"
                elif "OAuth token lacks required scopes" in error_msg:
                    error_msg += " - Please re-authenticate at /auth/login to refresh your OAuth token with proper scopes"

                raise HTTPException(status_code=response.status_code, detail={"error": {"message": error_msg}})

            # Translate response to OpenAI format (plan.md section 6.2)
            anthropic_response = response.json()
            openai_response = ResponseTranslator.anthropic_to_openai(anthropic_response, request.model)

            return openai_response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Request failed: {e}")
        raise HTTPException(status_code=500, detail={"error": {"message": str(e)}})


@app.get("/v1/models")
async def list_models():
    """Return available models with detailed metadata (plan.md section 4.6)"""

    # Model metadata with CORRECT context windows and capabilities from Anthropic docs
    # All modern Claude models support 200k context
    model_metadata = {
        # Claude 4 Opus models - 200k context, 32k max output
        "claude-opus-4-1-20250805": {
            "context_length": 200000,
            "max_tokens": 32000,
            "capabilities": {"vision": True, "function_calling": True}
        },
        "claude-opus-4-1": {
            "context_length": 200000,
            "max_tokens": 32000,
            "capabilities": {"vision": True, "function_calling": True}
        },
        "claude-opus-4-20250514": {
            "context_length": 200000,
            "max_tokens": 32000,
            "capabilities": {"vision": True, "function_calling": True}
        },
        "claude-opus-4-0": {
            "context_length": 200000,
            "max_tokens": 32000,
            "capabilities": {"vision": True, "function_calling": True}
        },

        # Claude 4 Sonnet models - 200k context (1M in beta), 64k max output
        "claude-sonnet-4-20250514": {
            "context_length": 200000,  # 1M available in beta
            "max_tokens": 64000,
            "capabilities": {"vision": True, "function_calling": True}
        },
        "claude-sonnet-4-0": {
            "context_length": 200000,  # 1M available in beta
            "max_tokens": 64000,
            "capabilities": {"vision": True, "function_calling": True}
        },

        # Claude 3.7 models - 200k context, 64k max output (128k with beta header)
        "claude-3-7-sonnet-20250219": {
            "context_length": 200000,
            "max_tokens": 64000,  # 128k with beta header
            "capabilities": {"vision": True, "function_calling": True}
        },
        "claude-3-7-sonnet-latest": {
            "context_length": 200000,
            "max_tokens": 64000,  # 128k with beta header
            "capabilities": {"vision": True, "function_calling": True}
        },

        # Claude 3.5 Sonnet models - 200k context, 4096 max output (8192 with beta)
        "claude-3-5-sonnet-latest": {
            "context_length": 200000,
            "max_tokens": 8192,  # Requires beta header for 8192, otherwise 4096
            "capabilities": {"vision": True, "function_calling": True}
        },
        "claude-3-5-sonnet-20241022": {
            "context_length": 200000,
            "max_tokens": 8192,  # Requires beta header for 8192, otherwise 4096
            "capabilities": {"vision": True, "function_calling": True}
        },

        # Claude 3.5 Haiku models - 200k context, 8192 max output
        "claude-3-5-haiku-20241022": {
            "context_length": 200000,
            "max_tokens": 8192,
            "capabilities": {"vision": True, "function_calling": True}
        },
        "claude-3-5-haiku-latest": {
            "context_length": 200000,
            "max_tokens": 8192,
            "capabilities": {"vision": True, "function_calling": True}
        },

        # Claude 3 models - 200k context, 4096 max output
        "claude-3-opus-latest": {
            "context_length": 200000,
            "max_tokens": 4096,
            "capabilities": {"vision": True, "function_calling": True}
        },
        "claude-3-opus-20240229": {
            "context_length": 200000,
            "max_tokens": 4096,
            "capabilities": {"vision": True, "function_calling": True}
        },
        "claude-3-sonnet-20240229": {
            "context_length": 200000,
            "max_tokens": 4096,
            "capabilities": {"vision": True, "function_calling": True}
        },
        "claude-3-haiku-20240307": {
            "context_length": 200000,
            "max_tokens": 4096,
            "capabilities": {"vision": True, "function_calling": True}
        }
    }

    # Build the response with enriched model data
    model_list = []
    for model_id, metadata in model_metadata.items():
        model_info = {
            "id": model_id,
            "object": "model",
            "created": int(time.time()),
            "owned_by": "anthropic",
            "context_length": metadata["context_length"],
            "max_tokens": metadata["max_tokens"],
            "max_output_tokens": metadata["max_tokens"],  # Some clients look for this field
            "capabilities": metadata["capabilities"]
        }
        model_list.append(model_info)

    return {
        "object": "list",
        "data": model_list
    }


if __name__ == "__main__":
    logger.info(f"Starting Anthropic OAuth Proxy on http://127.0.0.1:{PORT}")
    logger.info("Visit http://127.0.0.1:{PORT}/auth/login to authenticate")

    uvicorn.run(
        app,
        host="127.0.0.1",  # Bind to localhost only (plan.md section 10)
        port=PORT,
        log_level=LOG_LEVEL
    )