Here’s a complete, minimal-moving-parts implementation plan for a tiny local proxy that:

• exposes an OpenAI-compatible /v1/chat/completions endpoint on localhost
• obtains and refreshes Anthropic OAuth (Claude Pro/Max) tokens with PKCE (no CLI)
• forwards requests to Anthropic’s /v1/messages using the OAuth access token (Bearer)
• translates responses (and streaming) back into OpenAI Chat Completions format

I’m keeping scope tight so another agent can implement it in a few hours.

---

# 0) Ground rules, constraints, and what’s “special” about this flow

1. You’re using the **consumer OAuth** used by Claude Code (Pro/Max accounts), not console API keys. That means:
   • You must hit Anthropic’s **authorize** and **token** endpoints on console.anthropic.com with **PKCE** and scopes including user\:inference. The Claude Code authorize URL (with client\_id and redirect) is visible in public bug reports. ([GitHub][1])
   • You must call the normal **/v1/messages** API with `Authorization: Bearer <access_token>` and the standard `anthropic-version` header. ([Anthropic][2])
   • In practice, Anthropic currently gates OAuth-based inference behind **beta headers** (noted by multiple devs). Expect to include `anthropic-beta: oauth-2025-04-20` (and, if needed, a “claude-code” beta tag). This can change. ([GitHub][3])

2. Token & scope details to rely on (from OpenCode & Claude Code breadcrumbs):
   • authorize endpoint: `https://console.anthropic.com/oauth/authorize`
   • token endpoint: `https://console.anthropic.com/v1/oauth/token`
   • redirect path used by Claude Code/OpenCode: `/oauth/code/callback` (hosted by Anthropic)
   • scopes: `org:create_api_key user:profile user:inference`
   • a public `client_id` used by Claude Code has been disclosed in issues (PKCE means no client secret). Use with caution; Anthropic can change server-side policy at any time. ([GitHub][1])

3. Streaming is **SSE** on Anthropic with specific event names. You must translate these to OpenAI’s streaming chunks. ([Anthropic][4])

4. Plans & limits: Usage is metered against your Pro/Max plan (resets every five hours; weekly guardrails may also apply). Don’t assume unlimited. Handle 429s gracefully. ([Anthropic Help Center][5])

5. Terms & risk: This approach mirrors what devs have observed in the wild. It’s **subject to Anthropic policy**, and may stop working if headers/scopes/app policy change. If you want a supported route, point Cline/Roo at the official **Claude Code** provider. ([Anthropic][6])

---

# 1) Minimal project layout

• proxy.py – FastAPI (or Flask) app exposing OpenAI-compatible endpoints
• oauth.py – PKCE generator + browser login helper + token exchange + refresh
• translate.py – request/response translation between OpenAI Chat Completions and Anthropic Messages
• storage.py – tiny JSON file helper for tokens (chmod 600)
• settings.py – constants/env handling (ports, beta headers, model mapping)
• README.md – how to run and how to point Cline/Roo to localhost

Dependencies (lean): fastapi (or flask), uvicorn, httpx, itsdangerous or secrets+hashlib (for PKCE), pydantic (optional). Avoid heavyweight OAuth SDKs to keep code minimal.

---

# 2) Configuration knobs

Environment variables (fallback defaults in settings.py):

• PORT=8081
• LOG\_LEVEL=info
• ANTHROPIC\_VERSION=2023-06-01 (required by Anthropic) ([Anthropic][2])
• ANTHROPIC\_BETA=oauth-2025-04-20\[,claude-code-20250219] (adjust as needed) ([GitHub][7])
• CLIENT\_ID=9d1c250a-e61b-44d9-88ed-5944d1962f5e (value seen in public Claude Code links; override if Anthropic changes it) ([GitHub][1])
• AUTH\_BASE=[https://console.anthropic.com](https://console.anthropic.com)
• API\_BASE=[https://api.anthropic.com](https://api.anthropic.com)
• TOKEN\_FILE=\~/.anthropic-oauth-proxy/tokens.json

---

# 3) OAuth (PKCE) flow (no CLI)

Goal: obtain {access\_token, refresh\_token, expires\_at} and keep them fresh.

3.1 Generate PKCE
• Create a high-entropy code\_verifier (43–128 chars) and SHA-256 → base64-url encode to get code\_challenge (S256). Store both in memory. (Standard PKCE) ([Auth0][8])

3.2 Construct the authorize URL
• GET {AUTH\_BASE}/oauth/authorize with:
client\_id = CLIENT\_ID
response\_type = code
redirect\_uri = /oauth/code/callback
scope = “org\:create\_api\_key user\:profile user\:inference”
code\_challenge, code\_challenge\_method=S256
state = random nonce (you can reuse the code\_verifier or store a separate nonce)
• Open it in the default browser and prompt the user to complete login/consent. Auth URL format is documented in real issue threads; values above match those. ([GitHub][1])

3.3 Handling the callback (practical “paste-the-code” approach)
Because the redirect\_uri is Anthropic-hosted, your app won’t directly receive the browser redirect. In practice, after login Anthropic’s page shows the **code** for pasting into the client (this is reported in Claude Code issues). Present a simple local page ([http://127.0.0.1:8081/auth](http://127.0.0.1:8081/auth)) instructing the user to paste the code blob. Store it temporarily. ([GitHub][9])

3.4 Exchange the code for tokens
• POST {AUTH\_BASE}/v1/oauth/token with JSON:
grant\_type = authorization\_code
code = <pasted code>
client\_id = CLIENT\_ID
redirect\_uri = [https://console.anthropic.com/oauth/code/callback](https://console.anthropic.com/oauth/code/callback)
code\_verifier = \<verifier from 3.1>
• Store access\_token, refresh\_token, expires\_in → compute expires\_at. (This is exactly how OpenCode exchanges; see their code path.) ([GitHub][10])

3.5 Refresh flow
• When expired or on 401 from Anthropic: POST {AUTH\_BASE}/v1/oauth/token with JSON:
grant\_type = refresh\_token
refresh\_token = <stored>
client\_id = CLIENT\_ID
• Replace stored tokens. (OpenCode does this; same endpoint.) ([GitHub][10])

3.6 Token storage
• Save to TOKEN\_FILE with chmod 600:
{ "access\_token": "...", "refresh\_token": "...", "expires\_at": 1737052800 }
• Provide /auth/status endpoint to display “OK/Expired/Missing” (no secrets in response).

3.7 Errors to surface nicely
• “This credential is only authorized for use with Claude Code…” → tell user to ensure beta header is set and scopes include user\:inference; also warn the feature may be gated. ([GitHub][3])

---

# 4) OpenAI-compatible HTTP surface (lowest viable set)

Implement these routes:

4.1 GET /healthz
Returns 200 {“ok”: true}

4.2 GET /auth/login
Starts PKCE, opens authorize URL in browser, returns a minimal HTML page telling user to paste the “code” into /auth/exchange

4.3 POST /auth/exchange
Body: { "code": "<paste from Anthropic page>" }
Action: token exchange (3.4), write TOKEN\_FILE, return 200

4.4 GET /auth/status
Shows whether tokens are present/valid and when they expire (no secrets)

4.5 POST /v1/chat/completions
The OpenAI-compatible entrypoint. Body (subset): model, messages\[], temperature, top\_p, max\_tokens (or max\_completion\_tokens), stream (bool). Returns OpenAI-shaped response (see §6).

4.6 GET /v1/models (optional but useful)
Return a tiny static list containing one or a few Anthropic SKUs (e.g., “claude-3-7-sonnet-latest”), so tools that enumerate models won’t choke. Anthropic model naming varies across channels; safest is a stable alias like “claude-3-7-sonnet-latest”. ([Anthropic][11])

---

# 5) Forwarding to Anthropic

5.1 Required headers when calling Anthropic
• Authorization: Bearer \<access\_token>
• anthropic-version: 2023-06-01 (current canonical header) ([Anthropic][2])
• anthropic-beta: oauth-2025-04-20\[,claude-code-20250219] (observed requirement for OAuth tokens; expect changes) ([GitHub][3])
• Content-Type: application/json
• Optional: a friendly User-Agent

5.2 Endpoint & method
• POST {API\_BASE}/v1/messages

5.3 401 handling
• If Anthropic returns 401, call refresh (3.5) once, then retry the same request.

---

# 6) Request/response translation (OpenAI ↔ Anthropic)

6.1 OpenAI Chat Completions → Anthropic Messages

Input you’ll accept (subset):
• model (string)
• messages: array of {role: system|user|assistant, content: string}
• temperature, top\_p (pass through)
• max\_tokens or max\_completion\_tokens → Anthropic’s max\_tokens

Mapping rules:
• Pull the first “system” message (if present) → Anthropic “system” string. (Anthropic supports a dedicated system param.) ([Anthropic][12])
• Convert messages to Anthropic’s format, preserving role user/assistant and collapsing content to simple text blocks for MVP.
• Temperature/top\_p pass through; ignore unsupported OpenAI params (presence\_penalty, frequency\_penalty).
• Tool/function calling: omit in MVP (keep code minimal). You can add Anthropic tools later if needed.

Example Anthropic request you build internally (conceptually):
• model: same as input (or map aliases)
• system: string (from first system message)
• messages: \[{role:"user", content:\[{type:"text", text:"…"}]}, …]
• max\_tokens: integer
• temperature/top\_p as provided

6.2 Anthropic non-streaming → OpenAI non-streaming

Anthropic returns a “message” object with content blocks and usage. Build this shape:

• id: “chatcmpl-…local” (any unique id ok)
• object: “chat.completion”
• created: unix seconds
• model: echo the input model
• choices: single item with
– index: 0
– message: {role: “assistant”, content: "<concatenated text from Anthropic content blocks>"}
– finish\_reason: map Anthropic stop\_reason to openai finish\_reason (e.g., “stop\_sequence”→“stop”, “end\_turn”→“stop”, “max\_tokens”→“length”)
• usage: { prompt\_tokens: anthropic.usage.input\_tokens, completion\_tokens: anthropic.usage.output\_tokens, total\_tokens: sum }

6.3 Streaming (SSE) translation

Anthropic SSE emits a sequence like:
message\_start → content\_block\_start → content\_block\_delta\* → content\_block\_stop → message\_delta\* → message\_stop. ([Anthropic][4])

Translate to OpenAI stream chunks:
• On first content\_block\_start: emit a chunk with role “assistant” and empty content (OpenAI usually sends a role token once).
• For each content\_block\_delta(text=“…”) emit a standard OpenAI “delta” with that text.
• On message\_stop: emit “\[DONE]”.

Keep it minimal: only handle text deltas; ignore non-text blocks/events for MVP.

---

# 7) Models and defaults

Pick one Anthropic model as default (good for coding), e.g. “claude-3-7-sonnet-latest” (the 3.7 Sonnet family is well-documented and designed for coding). Let callers override via the OpenAI “model” field. ([Anthropic][13])

If the caller provides a model alias you don’t recognize, pass it through as-is to Anthropic (the server will resolve or error). If you need a definitive ID later, Anthropic’s Models API can resolve aliases. ([Anthropic][11])

---

# 8) Minimal ergonomics for Cline / Roo

• In Cline/Roo, choose **OpenAI** provider and set “Base URL” to `http://127.0.0.1:8081/v1`.
• Provide the “API Key” field with any placeholder string (the proxy will ignore it).
• Ensure you’ve run /auth/login → /auth/exchange first so the proxy has tokens.
• If you hit “credential only valid for Claude Code” errors, ensure your proxy is sending the beta header(s). ([GitHub][3])

---

# 9) Error handling & logging (MVP)

• 400 on malformed OpenAI request (missing model/messages)
• 401 if tokens missing/expired and refresh failed; respond with {error: {message: “OAuth expired; visit /auth/login again”}}
• 429: pass through Anthropic’s status & body
• 5xx: pass through status; include upstream request id if present
• Log one line per request (method, path, upstream ms, result code); never log tokens

---

# 10) Security & privacy

• Store tokens at TOKEN\_FILE with permission 600; create parent dir 700
• Bind to 127.0.0.1 only
• No CORS; no UI beyond the simple “paste code” page
• Do not ship the client\_id hard-coded in a public fork; read from env so it’s easy to change if Anthropic rotates policy.
• Add a big note in README: “This uses Anthropic consumer OAuth and may break or be disallowed; use at your own risk.”

---

# 11) Test checklist (before pointing tools at it)

A) OAuth
• Start server, GET /auth/login, complete browser flow, paste code to /auth/exchange → 200
• GET /auth/status → shows valid tokens (expiry in the future)

B) Non-streamed
• curl POST [http://127.0.0.1:8081/v1/chat/completions](http://127.0.0.1:8081/v1/chat/completions) with a minimal body: model + two messages (system+user) → 200; verify assistant text returns; verify `usage` is populated

C) Streamed
• Same request with `"stream": true` and curl’s `--no-buffer` → see incremental chunks and a terminal “\[DONE]”

D) Expiry
• Force an invalid access\_token and retry → proxy performs refresh and succeeds

E) Hard failure
• Remove refresh\_token and call → 401 with helpful message

---

# 12) “Gotchas” and how to future-proof

• **Beta headers** are the biggest moving target. Keep `ANTHROPIC_BETA` configurable; if you see “OAuth auth unsupported” or “Claude Code only” messages, try including the latest oauth/claude-code beta tags. (Community reports list values like `oauth-2025-04-20` and `claude-code-20250219`.) ([GitHub][7])
• Scopes: ensure `user:inference` is requested; OpenCode sets this alongside profile and org key scopes. ([GitHub][10])
• Streaming: implement only text deltas first; Anthropic can also stream tool calls and other event types—skip for MVP. ([Anthropic][4])
• Models: prefer “-latest” aliases to avoid pin drift; confirm available models for consumer OAuth (they can differ by channel or time). ([Anthropic][11])

---

# 13) References you’ll need while implementing

• Claude Code setup & auth (OAuth as default), and IAM doc. ([Anthropic][6])
• Anthropic API version header (anthropic-version: 2023-06-01). ([Anthropic][2])
• Anthropic streaming event sequence (message\_start, content\_block\_delta, …). ([Anthropic][4])
• OpenCode’s OAuth params (client\_id, redirect\_uri, scopes) and token exchange pattern. ([GitHub][10])
• Public issue exposing authorize URL with client\_id & redirect. ([GitHub][1])
• Observed need for `anthropic-beta: oauth-2025-04-20` (sometimes plus a claude-code tag). ([GitHub][3])
• Model background for Claude 3.7 Sonnet (for sensible defaults). ([Anthropic][13])

---

# 14) Optional phase-2 extras (only if you need them)

• Tools / function-calling translation (OpenAI “tools” → Anthropic “tools”)
• File upload passthrough (multipart → Anthropic’s /messages with input images)
• Session persistence & multi-tenant token stores
• A tiny `/v1/models` passthrough to Anthropic’s Models API instead of a static list (read-only alias resolution). ([Anthropic][11])

---

If you want, I can follow this plan and output the smallest possible FastAPI+httpx implementation next time—kept to a few hundred lines, with the paste-the-code handshake and streaming translation baked in.

[1]: https://github.com/anthropics/claude-code/issues/218?utm_source=chatgpt.com "OAuth Success on web page but Error in Terminal: OAuth error ... - GitHub"
[2]: https://docs.anthropic.com/en/api/versioning?utm_source=chatgpt.com "Versions - Anthropic"
[3]: https://github.com/sst/opencode/issues/417 "Question: How does opencode work with Claude Code OAuth tokens when AI SDK fails? · Issue #417 · sst/opencode · GitHub"
[4]: https://docs.anthropic.com/en/docs/build-with-claude/streaming?utm_source=chatgpt.com "Streaming Messages - Anthropic"
[5]: https://support.anthropic.com/en/articles/11014257-about-claude-s-max-plan-usage?utm_source=chatgpt.com "About Claude's Max Plan Usage | Anthropic Help Center"
[6]: https://docs.anthropic.com/en/docs/claude-code/setup?utm_source=chatgpt.com "Set up Claude Code - Anthropic"
[7]: https://github.com/snipeship/ccflare/issues/37?utm_source=chatgpt.com "Missing Required Header in Documentation #37 - GitHub"
[8]: https://auth0.com/docs/get-started/authentication-and-authorization-flow/authorization-code-flow-with-pkce?utm_source=chatgpt.com "Authorization Code Flow with Proof Key for Code Exchange (PKCE)"
[9]: https://github.com/anthropics/claude-code/issues/1484?utm_source=chatgpt.com "[BUG] Claude Code OAuth Authentication Fails - \"OAuth account ..."
[10]: https://github.com/sst/opencode/blob/dev/packages/opencode/src/auth/anthropic.ts?utm_source=chatgpt.com "opencode/packages/opencode/src/auth/anthropic.ts at dev · sst ... - GitHub"
[11]: https://docs.anthropic.com/en/api/models?utm_source=chatgpt.com "Get a Model - Anthropic"
[12]: https://docs.anthropic.com/en/api/messages-examples?utm_source=chatgpt.com "Messages examples - Anthropic"
[13]: https://www.anthropic.com/news/claude-3-7-sonnet?utm_source=chatgpt.com "Claude 3.7 Sonnet and Claude Code - anthropic.com"
