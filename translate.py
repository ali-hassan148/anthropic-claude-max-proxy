import json
import logging
import time
from typing import Dict, Any, List, Optional, AsyncIterator
from settings import DEFAULT_MODEL

logger = logging.getLogger(__name__)

class RequestTranslator:
    """Translate OpenAI Chat Completions to Anthropic Messages (plan.md section 6.1)"""

    @staticmethod
    def openai_to_anthropic(openai_request: Dict[str, Any]) -> Dict[str, Any]:
        """Convert OpenAI request to Anthropic format"""
        # Extract parameters
        model = openai_request.get("model", DEFAULT_MODEL)
        messages = openai_request.get("messages", [])
        temperature = openai_request.get("temperature")
        top_p = openai_request.get("top_p")

        # Handle max_tokens - Anthropic requires this to be an integer
        max_tokens = openai_request.get("max_tokens")
        if max_tokens is None:
            max_tokens = openai_request.get("max_completion_tokens")
        if max_tokens is None:
            max_tokens = 4096  # Default value
        # Ensure it's an integer
        try:
            max_tokens = int(max_tokens)
        except (TypeError, ValueError):
            logger.warning(f"Invalid max_tokens value: {max_tokens}, using default 4096")
            max_tokens = 4096

        stream = openai_request.get("stream", False)
        stream_options = openai_request.get("stream_options", {})

        # Build Anthropic request
        anthropic_request = {
            "model": model,
            "max_tokens": max_tokens,
            "stream": stream
        }

        logger.debug(f"Translated request - model: {model}, max_tokens: {max_tokens}, stream: {stream}, stream_options: {stream_options}")

        # Add optional parameters
        if temperature is not None:
            anthropic_request["temperature"] = temperature
        if top_p is not None:
            anthropic_request["top_p"] = top_p

        # Process messages (plan.md section 6.1 mapping rules)
        system_message = None
        anthropic_messages = []

        for msg in messages:
            role = msg.get("role")
            content = msg.get("content", "")

            if role == "system":
                # First system message becomes the system parameter
                if system_message is None:
                    system_message = content
            elif role in ["user", "assistant"]:
                # Convert to Anthropic message format
                anthropic_msg = {
                    "role": role,
                    "content": [{"type": "text", "text": content}] if isinstance(content, str) else content
                }
                anthropic_messages.append(anthropic_msg)

        # Add system message if present
        if system_message:
            anthropic_request["system"] = system_message

        anthropic_request["messages"] = anthropic_messages

        return anthropic_request


class ResponseTranslator:
    """Translate Anthropic Messages to OpenAI Chat Completions (plan.md section 6.2)"""

    @staticmethod
    def anthropic_to_openai(anthropic_response: Dict[str, Any], model: str) -> Dict[str, Any]:
        """Convert Anthropic response to OpenAI format"""
        # Extract content from Anthropic response
        content_blocks = anthropic_response.get("content", [])
        content_text = ""

        for block in content_blocks:
            if block.get("type") == "text":
                content_text += block.get("text", "")

        # Map stop reason to finish reason
        stop_reason = anthropic_response.get("stop_reason", "stop")
        finish_reason_map = {
            "end_turn": "stop",
            "stop_sequence": "stop",
            "max_tokens": "length"
        }
        finish_reason = finish_reason_map.get(stop_reason, "stop")

        # Build OpenAI response (plan.md section 6.2)
        usage = anthropic_response.get("usage", {})
        openai_response = {
            "id": f"chatcmpl-local-{int(time.time()*1000)}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": content_text
                },
                "finish_reason": finish_reason
            }],
            "usage": {
                "prompt_tokens": usage.get("input_tokens", 0),
                "completion_tokens": usage.get("output_tokens", 0),
                "total_tokens": usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
            }
        }

        return openai_response


class StreamTranslator:
    """Translate Anthropic SSE stream to OpenAI stream (plan.md section 6.3)"""

    @staticmethod
    async def translate_stream(anthropic_stream: AsyncIterator[str], model: str, include_usage: bool = False) -> AsyncIterator[str]:
        """Convert Anthropic SSE events to OpenAI streaming chunks"""
        chunk_id = f"chatcmpl-stream-{int(time.time()*1000)}"
        created = int(time.time())
        first_chunk_sent = False

        # Track usage data from Anthropic events
        input_tokens = 0
        output_tokens = 0

        async for line in anthropic_stream:
            if not line.strip():
                continue

            if line.startswith("data: "):
                data_str = line[6:]
                if data_str == "[DONE]":
                    yield "data: [DONE]\n\n"
                    break

                try:
                    data = json.loads(data_str)
                    event_type = data.get("type")

                    # Handle different Anthropic event types (plan.md section 6.3)
                    if event_type == "message_start":
                        # Capture initial usage data
                        message = data.get("message", {})
                        usage = message.get("usage", {})
                        input_tokens = usage.get("input_tokens", 0)
                        output_tokens = usage.get("output_tokens", 0)
                        logger.debug(f"Stream message_start - input_tokens: {input_tokens}")

                    elif event_type == "message_delta":
                        # Update usage data (cumulative)
                        delta_usage = data.get("usage", {})
                        if delta_usage:
                            output_tokens = delta_usage.get("output_tokens", output_tokens)
                            logger.debug(f"Stream message_delta - output_tokens: {output_tokens}")

                    elif event_type == "content_block_start":
                        # Emit initial chunk with role
                        if not first_chunk_sent:
                            openai_chunk = {
                                "id": chunk_id,
                                "object": "chat.completion.chunk",
                                "created": created,
                                "model": model,
                                "choices": [{
                                    "index": 0,
                                    "delta": {"role": "assistant", "content": ""},
                                    "finish_reason": None
                                }]
                            }
                            yield f"data: {json.dumps(openai_chunk)}\n\n"
                            first_chunk_sent = True

                    elif event_type == "content_block_delta":
                        # Emit text delta
                        delta = data.get("delta", {})
                        if delta.get("type") == "text_delta":
                            text = delta.get("text", "")
                            openai_chunk = {
                                "id": chunk_id,
                                "object": "chat.completion.chunk",
                                "created": created,
                                "model": model,
                                "choices": [{
                                    "index": 0,
                                    "delta": {"content": text},
                                    "finish_reason": None
                                }]
                            }
                            yield f"data: {json.dumps(openai_chunk)}\n\n"

                    elif event_type == "message_stop":
                        # Emit final chunk with finish reason
                        openai_chunk = {
                            "id": chunk_id,
                            "object": "chat.completion.chunk",
                            "created": created,
                            "model": model,
                            "choices": [{
                                "index": 0,
                                "delta": {},
                                "finish_reason": "stop"
                            }]
                        }
                        yield f"data: {json.dumps(openai_chunk)}\n\n"

                        # Emit usage chunk if requested (OpenAI format for stream_options.include_usage)
                        if include_usage and (input_tokens > 0 or output_tokens > 0):
                            usage_chunk = {
                                "id": chunk_id,
                                "object": "chat.completion.chunk",
                                "created": created,
                                "model": model,
                                "choices": [],
                                "usage": {
                                    "prompt_tokens": input_tokens,
                                    "completion_tokens": output_tokens,
                                    "total_tokens": input_tokens + output_tokens
                                }
                            }
                            yield f"data: {json.dumps(usage_chunk)}\n\n"
                            logger.debug(f"Stream usage emitted - prompt: {input_tokens}, completion: {output_tokens}")

                        yield "data: [DONE]\n\n"
                        break

                except json.JSONDecodeError:
                    continue