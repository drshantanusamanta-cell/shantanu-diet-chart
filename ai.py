"""Gemini API wrapper.

The API key is read from Streamlit secrets (or a local .env), so it stays on the
server and is never exposed to the patient's browser.
"""

import base64
import json
import os
import time

import requests

# Current stable Flash model with no announced shutdown date.
# History worth remembering: the original app used gemini-2.5-flash-preview-09-2025,
# and plain gemini-2.5-flash is itself scheduled for shutdown on 16 Oct 2026.
# Check https://ai.google.dev/gemini-api/docs/deprecations once a year.
MODEL = "gemini-3.5-flash"
ENDPOINT = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"

TIMEOUT_SECONDS = 120
MAX_RETRIES = 2


class ConfigError(RuntimeError):
    """API key missing or malformed."""


class GeminiError(RuntimeError):
    """The API call failed or returned something unusable."""


def get_api_key() -> str:
    """Read the key from Streamlit secrets first, then the environment."""
    key = ""
    try:
        import streamlit as st

        key = st.secrets.get("GEMINI_API_KEY", "")
    except Exception:
        pass

    if not key:
        key = os.getenv("GEMINI_API_KEY", "")

    if not key:
        raise ConfigError(
            "GEMINI_API_KEY is not set. On Streamlit Cloud add it under "
            "**Manage app → Settings → Secrets**. Locally, put it in a `.env` file."
        )
    return key.strip()


def _extract_text(payload: dict) -> str:
    candidates = payload.get("candidates") or []
    if not candidates:
        feedback = payload.get("promptFeedback", {})
        if feedback.get("blockReason"):
            raise GeminiError(
                f"The request was blocked by a safety filter ({feedback['blockReason']}). "
                "Try removing the uploaded images and generating again."
            )
        raise GeminiError("The AI returned no response. Please try again.")

    parts = candidates[0].get("content", {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts)

    if not text.strip():
        reason = candidates[0].get("finishReason", "")
        if reason == "MAX_TOKENS":
            raise GeminiError(
                "The response was cut short. Try again, or remove some lab reports."
            )
        raise GeminiError("The AI returned an empty response. Please try again.")
    return text


def _parse_json(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```")[1]
        if cleaned.lstrip().lower().startswith("json"):
            cleaned = cleaned.lstrip()[4:]
    try:
        return json.loads(cleaned.strip())
    except json.JSONDecodeError as exc:
        raise GeminiError(
            "The AI response could not be read as valid data. Please try again."
        ) from exc


def call_gemini(user_prompt: str, system_prompt: str, files: list | None = None) -> dict:
    """Send a prompt (plus optional images/PDFs) and return the parsed JSON reply.

    `files` is a list of dicts: {"mime_type": str, "data": bytes}
    """
    api_key = get_api_key()

    parts: list[dict] = [{"text": user_prompt}]
    for f in files or []:
        parts.append(
            {
                "inline_data": {
                    "mime_type": f["mime_type"],
                    "data": base64.b64encode(f["data"]).decode("ascii"),
                }
            }
        )

    body = {
        "contents": [{"parts": parts}],
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.7,
            # Generous, because Gemini 3.x counts internal "thinking" tokens
            # against this budget. Too low and a full chart gets truncated.
            "maxOutputTokens": 32768,
        },
    }

    last_error = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            response = requests.post(
                ENDPOINT,
                headers={
                    "Content-Type": "application/json",
                    "x-goog-api-key": api_key,
                },
                json=body,
                timeout=TIMEOUT_SECONDS,
            )
        except requests.Timeout:
            last_error = GeminiError(
                "The AI took too long to respond. Please try again."
            )
        except requests.RequestException as exc:
            last_error = GeminiError(f"Could not reach the AI service: {exc}")
        else:
            if response.status_code == 200:
                return _parse_json(_extract_text(response.json()))

            # Surface Google's own message where we can — it's usually clearer.
            detail = ""
            try:
                detail = response.json().get("error", {}).get("message", "")
            except Exception:
                detail = response.text[:200]

            if response.status_code in (429, 500, 502, 503):
                last_error = GeminiError(
                    f"The AI service is busy or rate-limited ({response.status_code}). "
                    f"{detail}"
                )
            else:
                # 400/403 are configuration problems; retrying won't help.
                raise GeminiError(f"AI service error ({response.status_code}): {detail}")

        if attempt < MAX_RETRIES:
            time.sleep(2 * (attempt + 1))

    raise last_error or GeminiError("The request failed. Please try again.")
