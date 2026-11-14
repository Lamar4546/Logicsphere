"""Groq OpenAI-compatible chat client used by reasoning-only agent paths."""
import json
import os
import requests

DEFAULT_API_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_MODEL = "llama-3.3-70b-versatile"


class MiniMaxError(RuntimeError):
    pass


def is_configured() -> bool:
    """Whether a supported OpenAI-compatible provider has a key."""
    return bool(os.environ.get("GROQ_API_KEY") or os.environ.get("AI_API_KEY") or os.environ.get("MINIMAX_API_KEY"))


def provider_name() -> str:
    """Human-safe provider label; credentials are never returned."""
    default = "groq" if os.environ.get("GROQ_API_KEY") or os.environ.get("AI_API_KEY") else "minimax"
    return os.environ.get("AI_PROVIDER", default).strip().lower() or default


def _api_key() -> str | None:
    # Generic and MiniMax variables remain supported for existing deployments.
    return os.environ.get("GROQ_API_KEY") or os.environ.get("AI_API_KEY") or os.environ.get("MINIMAX_API_KEY")


def _api_url() -> str:
    return os.environ.get("GROQ_API_URL") or os.environ.get("AI_API_URL") or os.environ.get("MINIMAX_API_URL") or DEFAULT_API_URL


def _model() -> str:
    return os.environ.get("GROQ_MODEL") or os.environ.get("AI_MODEL") or os.environ.get("MINIMAX_MODEL") or DEFAULT_MODEL


def chat(messages: list[dict], *, json_mode: bool = False, temperature: float = 0.3) -> str:
    """
    Calls Groq chat completions and returns the assistant message content
    as a string. Raises MiniMaxError on failure; callers decide whether to
    fall back to deterministic logic (see risk_agent.py, central_manager.py,
    communication_agent.py), so provider outages either degrade to a
    known-safe rule-based path or surface clearly.
    """
    api_key = _api_key()
    if not api_key:
        raise MiniMaxError("No AI provider API key is set.")

    payload = {
        "model": _model(),
        "messages": messages,
        "temperature": temperature,
        "stream": False,
    }
    if json_mode:
        # Groq supports response_format for JSON-mode chat completions.
        payload["response_format"] = {"type": "json_object"}

    try:
        resp = requests.post(
            _api_url(),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as exc:
        raise MiniMaxError(f"{provider_name()} request failed: {exc}") from exc

    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as exc:
        raise MiniMaxError(f"Unexpected {provider_name()} response shape: {data}") from exc


def chat_json(messages: list[dict], *, temperature: float = 0.2) -> dict:
    """Convenience wrapper for structured output. Raises MiniMaxError if the
    response isn't valid JSON — callers should catch this and fall back."""
    content = chat(messages, json_mode=True, temperature=temperature)
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise MiniMaxError(f"{provider_name()} did not return valid JSON: {content}") from exc
