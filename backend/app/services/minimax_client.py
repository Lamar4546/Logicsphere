"""
MiniMax client — OpenAI-compatible Chat Completions API.
https://api.minimax.io/v1/chat/completions

Used everywhere an agent needs reasoning/explanation/drafting, per the
project's architecture principle: MiniMax handles reasoning, planning and
explanations; it never executes anything transactional itself (that stays
in deterministic backend code, gated by human approval — see
workflow_service.py). Risk classification now reasons through MiniMax too,
but the *decision to act* on that classification still requires a human
approval step downstream — this client only ever produces text/JSON that
other code interprets, it has no path to write or execute anything itself.
"""
import json
import os
import requests

DEFAULT_API_URL = "https://api.minimax.io/v1/chat/completions"
# MiniMax's current OpenAI-compatible text endpoint supports this model.
# Deployments can still override it with MINIMAX_MODEL.
DEFAULT_MODEL = "MiniMax-M2.7"


class MiniMaxError(RuntimeError):
    pass


def is_configured() -> bool:
    """Whether the service can make a live MiniMax request."""
    return bool(os.environ.get("MINIMAX_API_KEY"))


def chat(messages: list[dict], *, json_mode: bool = False, temperature: float = 0.3) -> str:
    """
    Calls MiniMax chat completions and returns the assistant message content
    as a string. Raises MiniMaxError on any failure — callers are
    responsible for deciding whether to fall back to deterministic logic
    (see risk_agent.py, central_manager.py, communication_agent.py), so a
    MiniMax outage never silently corrupts a recommendation, it either
    degrades to a known-safe rule-based path or surfaces clearly.
    """
    api_key = os.environ.get("MINIMAX_API_KEY")
    if not api_key:
        raise MiniMaxError("MINIMAX_API_KEY is not set.")

    payload = {
        "model": os.environ.get("MINIMAX_MODEL", DEFAULT_MODEL),
        "messages": messages,
        "temperature": temperature,
        "stream": False,
    }
    if json_mode:
        # MiniMax's OpenAI-compatible endpoint accepts response_format for
        # structured output; if the deployed model/version ignores it, the
        # caller's JSON parsing still has a repair/fallback path.
        payload["response_format"] = {"type": "json_object"}

    try:
        resp = requests.post(
            os.environ.get("MINIMAX_API_URL", DEFAULT_API_URL),
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
        raise MiniMaxError(f"MiniMax request failed: {exc}") from exc

    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as exc:
        raise MiniMaxError(f"Unexpected MiniMax response shape: {data}") from exc


def chat_json(messages: list[dict], *, temperature: float = 0.2) -> dict:
    """Convenience wrapper for structured output. Raises MiniMaxError if the
    response isn't valid JSON — callers should catch this and fall back."""
    content = chat(messages, json_mode=True, temperature=temperature)
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise MiniMaxError(f"MiniMax did not return valid JSON: {content}") from exc
