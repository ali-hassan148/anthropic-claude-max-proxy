# Anthropic Claude Max Proxy

Pure Anthropic proxy for Claude Pro/Max subscriptions using OAuth.

## SUPPORT MY WORK
<a href="https://buymeacoffee.com/Pimzino" target="_blank"><img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me A Coffee" style="height: 60px !important;width: 217px !important;" ></a>

## DISCLAIMER

**FOR EDUCATIONAL PURPOSES ONLY**

This tool:
- Is NOT affiliated with or endorsed by Anthropic
- Uses undocumented OAuth flows from Claude Code
- May violate Anthropic's Terms of Service
- Could stop working at any time without notice
- Comes with NO WARRANTY or support

**USE AT YOUR OWN RISK. The authors assume no liability for any consequences.**

For official access, use Claude Code or Anthropic's API with console API keys.

## Prerequisites

- Active Claude Pro or Claude Max subscription
- Python 3.8+
- pip

## Quick Start

1. **Virtual Environment Setup (Recommended)**
```bash
python -m venv venv
```

2. **Install:**
```bash
venv/Scripts/Activate.ps1
pip install -r requirements.txt
```

3. **Configure (optional):**
```bash
cp config.example.json config.json
```

4. **Run:**
```bash
python cli.py
```

5. **Authenticate:**
- Select option 2 (Login)
- Browser opens automatically
- Complete login at claude.ai
- Copy the authorization code
- Paste in terminal

6. **Start proxy:**
- Select option 1 (Start Proxy Server)
- Server runs at `http://127.0.0.1:8081`

## Client Configuration

Configure your Anthropic API client:

- **Base URL:** `http://127.0.0.1:8081`
- **API Key:** Any non-empty string (e.g., "dummy")
- **Model:** `claude-sonnet-4-20250514` (or any available Claude model)
- **Endpoint:** `/v1/messages`

## Available Models

- `claude-sonnet-4-20250514` - Claude 4 Sonnet (latest) **[RECOMMENDED]**
- `claude-3-5-sonnet-20241022` - Claude 3.5 Sonnet (latest)
- `claude-3-5-haiku-20241022` - Claude 3.5 Haiku (latest)
- `claude-3-opus-20240229` - Claude 3 Opus
- See proxy startup output for complete model list

## Configuration Priority

1. Environment variables (highest)
2. config.json file
3. Built-in defaults (lowest)

## License

MIT License - see [LICENSE](LICENSE) file

This software is provided for educational purposes only. Users assume all risks.
