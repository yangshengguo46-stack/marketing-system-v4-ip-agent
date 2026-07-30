import argparse
import base64
import hashlib
import json
import logging
import mimetypes
import os
import random
import re
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import requests

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MINIMAX_DEFAULT_HOST = "https://api.minimaxi.com"
# MiniMax base_resp codes worth retrying: unknown, timeout, RPM limit, TPM limit.
MINIMAX_RETRYABLE_CODES = {1000, 1001, 1002, 1039}
DEFAULT_TTS_MAX_RETRIES = 4
DEFAULT_MAX_WORKERS = 4
DEFAULT_MINIMAX_MAX_WORKERS = 1
MEDIA_EXECUTION_CONTRACT_VERSION = "personal-ip-media-execution-v1"
VOLCENGINE_TTS_V3_URL = "https://openspeech.bytedance.com/api/v3/tts/unidirectional"
VOLCENGINE_TTS_V3_RESOURCE = "seed-tts-2.0"


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _file_artifact(path: str) -> dict:
    resolved = Path(path).resolve()
    digest = hashlib.sha256()
    with resolved.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return {
        "ref": resolved.as_uri(),
        "sha256": digest.hexdigest(),
        "size_bytes": resolved.stat().st_size,
        "mime_type": mimetypes.guess_type(resolved.name)[0]
        or "application/octet-stream",
    }


def _write_receipt(path: str | None, receipt: dict) -> None:
    if not path:
        return
    target = Path(path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.tmp")
    temporary.write_text(
        json.dumps(receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    os.replace(temporary, target)


def _unknown_cost() -> dict:
    return {"status": "unknown", "reason": "provider billing API is not connected"}


class ScriptLine:
    def __init__(
        self,
        speaker: Literal["male", "female"] = "male",
        paragraph: str = "",
        *,
        voice_type: str | None = None,
        speech_rate: int = 0,
        loudness_rate: int = 0,
        context_texts: list[str] | None = None,
    ):
        self.speaker = speaker
        self.paragraph = paragraph
        self.voice_type = voice_type
        self.speech_rate = speech_rate
        self.loudness_rate = loudness_rate
        self.context_texts = context_texts or []


def _line_rate(value, *, field: str) -> int:
    if value is None:
        return 0
    if isinstance(value, bool):
        raise ValueError(f"{field} must be an integer between -50 and 100")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be an integer between -50 and 100") from exc
    if (
        str(value).strip() not in {str(result), f"{result}.0"}
        or result < -50
        or result > 100
    ):
        raise ValueError(f"{field} must be an integer between -50 and 100")
    return result


def _line_voice(value) -> str | None:
    if value is None or not str(value).strip():
        return None
    voice = str(value).strip()
    if not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", voice):
        raise ValueError(
            "voice_type must contain only letters, numbers, dot, underscore, colon or hyphen"
        )
    return voice


def _line_context_texts(value, *, fallback=None) -> list[str]:
    raw = value
    if raw is None and fallback is not None:
        raw = [fallback]
    if raw is None:
        return []
    if not isinstance(raw, list) or len(raw) > 4:
        raise ValueError("context_texts must be an array with at most four items")
    result: list[str] = []
    for item in raw:
        text = " ".join(str(item or "").split())
        if not text or len(text) > 500:
            raise ValueError("each context_texts item must contain 1 to 500 characters")
        result.append(text)
    return result


class Script:
    def __init__(
        self,
        locale: Literal["en", "zh"] = "en",
        lines: list[ScriptLine] | None = None,
    ):
        self.locale = locale
        self.lines = lines or []

    @classmethod
    def from_dict(cls, data: dict) -> "Script":
        script = cls(locale=data.get("locale", "en"))
        for index, line in enumerate(data.get("lines", [])):
            if not isinstance(line, dict):
                raise ValueError(f"lines[{index}] must be an object")
            speaker = str(line.get("speaker", "male")).strip()
            if speaker not in {"male", "female"}:
                raise ValueError(f"lines[{index}].speaker must be male or female")
            paragraph = str(line.get("paragraph", "")).strip()
            if not paragraph:
                raise ValueError(f"lines[{index}].paragraph must not be empty")
            script.lines.append(
                ScriptLine(
                    speaker=speaker,
                    paragraph=paragraph,
                    voice_type=_line_voice(line.get("voice_type", line.get("voice"))),
                    speech_rate=_line_rate(
                        line.get("speech_rate"),
                        field=f"lines[{index}].speech_rate",
                    ),
                    loudness_rate=_line_rate(
                        line.get("loudness_rate"),
                        field=f"lines[{index}].loudness_rate",
                    ),
                    context_texts=_line_context_texts(
                        line.get("context_texts"),
                        fallback=line.get("context_text"),
                    ),
                )
            )
        return script


def _resolve_provider(
    override_env: str, existing_provider: str, has_existing_creds: bool
) -> str:
    override = os.getenv(override_env)
    if override:
        return override.strip().lower()
    if has_existing_creds:
        return existing_provider
    if os.getenv("MINIMAX_API_KEY"):
        return "minimax"
    raise ValueError(
        f"No credentials found. Set VOLCENGINE_TTS_APPID + VOLCENGINE_TTS_ACCESS_TOKEN "
        f"for {existing_provider}, or MINIMAX_API_KEY for minimax "
        f"(optionally force with {override_env})."
    )


def _resolve_tts_provider() -> str:
    has_volc = bool(
        os.getenv("VOLCENGINE_TTS_API_KEY") or os.getenv("VOLCENGINE_TTS_ACCESS_TOKEN")
    )
    provider = _resolve_provider("PODCAST_GENERATION_PROVIDER", "volcengine", has_volc)
    if provider not in ("volcengine", "minimax"):
        raise ValueError(
            f"Unknown podcast provider: {provider!r} (use 'volcengine' or 'minimax')"
        )
    return provider


def _volcengine_v3_api_key() -> str | None:
    return os.getenv("VOLCENGINE_TTS_API_KEY") or (
        os.getenv("VOLCENGINE_TTS_ACCESS_TOKEN")
        if not os.getenv("VOLCENGINE_TTS_APPID")
        else None
    )


def _decode_concatenated_json(raw: bytes) -> list[dict]:
    """Decode the V3 chunked stream, which may omit newlines between objects."""

    text = raw.decode("utf-8")
    decoder = json.JSONDecoder()
    index = 0
    payloads: list[dict] = []
    while index < len(text):
        while index < len(text) and text[index].isspace():
            index += 1
        if index >= len(text):
            break
        payload, index = decoder.raw_decode(text, index)
        if not isinstance(payload, dict):
            raise ValueError("Volcengine TTS V3 returned a non-object stream item")
        payloads.append(payload)
    return payloads


def _response_bytes(response) -> bytes:
    iterator = getattr(response, "iter_content", None)
    if callable(iterator):
        return b"".join(
            chunk if isinstance(chunk, bytes) else str(chunk).encode("utf-8")
            for chunk in iterator(chunk_size=64 * 1024)
            if chunk
        )
    content = getattr(response, "content", b"")
    if isinstance(content, bytes) and content:
        return content
    text = getattr(response, "text", "")
    return str(text).encode("utf-8")


def _default_max_retries() -> int:
    try:
        return int(os.getenv("MINIMAX_TTS_MAX_RETRIES", str(DEFAULT_TTS_MAX_RETRIES)))
    except ValueError:
        return DEFAULT_TTS_MAX_RETRIES


def _default_max_workers(provider: str) -> int:
    """Each provider owns its own concurrency: MiniMax stays low to avoid rate
    limits, Volcengine keeps the historical default. Not user-tunable by design.
    """
    if provider == "minimax":
        return DEFAULT_MINIMAX_MAX_WORKERS
    return DEFAULT_MAX_WORKERS


def _parse_retry_after(response) -> float | None:
    """Return the server-provided Retry-After (seconds), if any."""
    headers = getattr(response, "headers", None) or {}
    value = headers.get("Retry-After")
    try:
        return float(value) if value else None
    except (TypeError, ValueError):
        return None


def _backoff_sleep(attempt: int, retry_after: float | None) -> None:
    """Sleep with exponential backoff + jitter, honoring Retry-After when present.

    Jitter de-synchronizes concurrent workers that all got rate-limited at once,
    avoiding a thundering-herd retry storm.
    """
    base = retry_after if retry_after else min(2**attempt, 30)
    time.sleep(base + random.uniform(0, 1))


def text_to_speech_volcengine(
    text: str,
    voice_type: str,
    max_retries: int | None = None,
    request_metadata: dict | None = None,
    *,
    speech_rate: int = 0,
    loudness_rate: int = 0,
    context_texts: list[str] | None = None,
) -> bytes | None:
    """Convert text to speech using Volcengine TTS (returns base64-decoded mp3 bytes).

    Retries with exponential backoff on transient HTTP errors (429 / 5xx).
    """
    speech_rate = _line_rate(speech_rate, field="speech_rate")
    loudness_rate = _line_rate(loudness_rate, field="loudness_rate")
    contexts = _line_context_texts(context_texts)
    api_key = _volcengine_v3_api_key()
    if api_key:
        resource = os.getenv("VOLCENGINE_TTS_RESOURCE_ID", VOLCENGINE_TTS_V3_RESOURCE)
        request_id = str(uuid.uuid4())
        context_digest = (
            hashlib.sha256(
                json.dumps(
                    contexts,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
            if contexts
            else None
        )
        if request_metadata is not None:
            request_metadata.update(
                {
                    "request_id": request_id,
                    "voice": voice_type,
                    "model": resource,
                    "protocol": "v3-http-unidirectional",
                    "speech_rate": speech_rate,
                    "loudness_rate": loudness_rate,
                    "context_texts_count": len(contexts),
                    "context_texts_sha256": context_digest,
                }
            )
        payload = {
            "user": {"uid": "personal-ip-agent"},
            "req_params": {
                "text": text,
                "speaker": voice_type,
                "audio_params": {
                    "format": "mp3",
                    "sample_rate": 24000,
                    "speech_rate": speech_rate,
                    "loudness_rate": loudness_rate,
                },
            },
        }
        if contexts:
            payload["req_params"]["context_texts"] = contexts
        headers = {
            "X-Api-Key": api_key,
            "X-Api-Resource-Id": resource,
            "X-Api-Request-Id": request_id,
            "Content-Type": "application/json",
        }
        if max_retries is None:
            max_retries = _default_max_retries()
        for attempt in range(max_retries + 1):
            try:
                response = requests.post(
                    os.getenv("VOLCENGINE_TTS_BASE_URL", VOLCENGINE_TTS_V3_URL),
                    json=payload,
                    headers=headers,
                    timeout=60,
                    stream=True,
                )
            except Exception as exc:
                logger.error(f"Volcengine TTS V3 network error: {exc}")
                if attempt < max_retries:
                    _backoff_sleep(attempt, None)
                    continue
                return None
            if response.status_code == 429 or response.status_code >= 500:
                logger.warning(
                    f"Volcengine TTS V3 transient HTTP {response.status_code} "
                    f"(attempt {attempt + 1}/{max_retries + 1})"
                )
                if attempt < max_retries:
                    _backoff_sleep(attempt, _parse_retry_after(response))
                    continue
                return None
            if response.status_code != 200:
                logger.error(f"Volcengine TTS V3 HTTP error: {response.status_code}")
                return None
            try:
                chunks: list[bytes] = []
                terminal = False
                for item in _decode_concatenated_json(_response_bytes(response)):
                    code = item.get("code")
                    if code == 0 and item.get("data"):
                        chunks.append(base64.b64decode(item["data"]))
                    elif code == 20000000:
                        terminal = True
                    elif code not in (0, None):
                        logger.error(
                            "Volcengine TTS V3 provider error %s: %s",
                            code,
                            item.get("message") or item.get("msg") or "unknown error",
                        )
                        return None
                if chunks and terminal:
                    return b"".join(chunks)
                logger.error("Volcengine TTS V3 returned no complete audio stream")
                return None
            except (ValueError, TypeError, base64.binascii.Error) as exc:
                logger.error(f"Volcengine TTS V3 decode error: {exc}")
                return None
        return None

    app_id = os.getenv("VOLCENGINE_TTS_APPID")
    access_token = os.getenv("VOLCENGINE_TTS_ACCESS_TOKEN")
    if not (app_id and access_token):
        logger.error("Volcengine TTS credentials are not configured")
        return None
    if speech_rate != 0 or loudness_rate != 0 or contexts:
        logger.error(
            "Per-line speech_rate, loudness_rate and context_texts require "
            "the Volcengine V3 single-key route"
        )
        return None
    cluster = os.getenv("VOLCENGINE_TTS_CLUSTER", "volcano_tts")
    if max_retries is None:
        max_retries = _default_max_retries()
    url = "https://openspeech.bytedance.com/api/v1/tts"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer;{access_token}",
    }
    request_id = str(uuid.uuid4())
    if request_metadata is not None:
        request_metadata.update(
            {
                "request_id": request_id,
                "voice": voice_type,
                "model": cluster,
            }
        )
    payload = {
        "app": {"appid": app_id, "token": "access_token", "cluster": cluster},
        "user": {"uid": "podcast-generator"},
        "audio": {"voice_type": voice_type, "encoding": "mp3", "speed_ratio": 1.2},
        "request": {
            "reqid": request_id,
            "text": text,
            "text_type": "plain",
            "operation": "query",
        },
    }
    for attempt in range(max_retries + 1):
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=60)
        except Exception as e:
            logger.error(f"TTS error: {e}")
            if attempt < max_retries:
                _backoff_sleep(attempt, None)
                continue
            return None
        if response.status_code == 429 or response.status_code >= 500:
            logger.warning(
                f"Volcengine TTS transient HTTP {response.status_code} "
                f"(attempt {attempt + 1}/{max_retries + 1})"
            )
            if attempt < max_retries:
                _backoff_sleep(attempt, _parse_retry_after(response))
                continue
            return None
        if response.status_code != 200:
            logger.error(f"TTS API error: {response.status_code} - {response.text}")
            return None
        result = response.json()
        if result.get("code") != 3000:
            logger.error(
                f"TTS error: {result.get('message')} (code: {result.get('code')})"
            )
            return None
        audio_data = result.get("data")
        if audio_data:
            return base64.b64decode(audio_data)
        return None
    return None


def text_to_speech_minimax(
    text: str,
    voice_id: str,
    max_retries: int | None = None,
    request_metadata: dict | None = None,
) -> bytes | None:
    """Convert text to speech using MiniMax t2a_v2 (returns hex-decoded mp3 bytes).

    Retries with exponential backoff on HTTP 429/5xx and on retryable base_resp
    codes (rate/TPM limits, timeouts). Permanent errors (auth, balance, bad input)
    are not retried.
    """
    api_key = os.getenv("MINIMAX_API_KEY")
    host = os.getenv("MINIMAX_API_HOST", MINIMAX_DEFAULT_HOST).rstrip("/")
    if max_retries is None:
        max_retries = _default_max_retries()
    model = os.getenv("MINIMAX_TTS_MODEL", "speech-2.6-hd")
    if request_metadata is not None:
        request_metadata.update({"voice": voice_id, "model": model})
    payload = {
        "model": model,
        "text": text,
        "voice_setting": {"voice_id": voice_id, "speed": 1.0, "vol": 1.0, "pitch": 0},
        "audio_setting": {
            "sample_rate": 32000,
            "bitrate": 128000,
            "format": "mp3",
            "channel": 1,
        },
        "output_format": "hex",
    }
    for attempt in range(max_retries + 1):
        try:
            response = requests.post(
                f"{host}/v1/t2a_v2",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=60,
            )
        except Exception as e:
            logger.error(f"MiniMax TTS error: {e}")
            if attempt < max_retries:
                _backoff_sleep(attempt, None)
                continue
            return None
        if response.status_code == 429 or response.status_code >= 500:
            logger.warning(
                f"MiniMax TTS rate-limited HTTP {response.status_code} "
                f"(attempt {attempt + 1}/{max_retries + 1})"
            )
            if attempt < max_retries:
                _backoff_sleep(attempt, _parse_retry_after(response))
                continue
            return None
        if response.status_code != 200:
            logger.error(f"MiniMax TTS error: {response.status_code} - {response.text}")
            return None
        result = response.json()
        if request_metadata is not None:
            provider_request_id = result.get("request_id") or result.get("trace_id")
            if provider_request_id:
                request_metadata["request_id"] = str(provider_request_id)
        base = result.get("base_resp") or {}
        code = base.get("status_code", 0)
        if code in MINIMAX_RETRYABLE_CODES:
            logger.warning(
                f"MiniMax TTS retryable error {code}: {base.get('status_msg')} "
                f"(attempt {attempt + 1}/{max_retries + 1})"
            )
            if attempt < max_retries:
                _backoff_sleep(attempt, None)
                continue
            return None
        if code != 0:
            logger.error(f"MiniMax TTS error {code}: {base.get('status_msg')}")
            return None
        audio_hex = (result.get("data") or {}).get("audio")
        if audio_hex:
            return bytes.fromhex(audio_hex)
        return None
    return None


def _process_line(args: tuple) -> tuple[int, bytes | None]:
    """Process a single script line for TTS. Returns (index, audio_bytes)."""
    i, line, total, provider = args[:4]
    request_metadata = args[4] if len(args) > 4 else None
    if request_metadata is not None:
        request_metadata["line_number"] = i + 1
    logger.info(f"Processing line {i + 1}/{total} ({line.speaker}) via {provider}")
    if provider == "minimax":
        if line.speaker == "male":
            voice = os.getenv("MINIMAX_TTS_VOICE_MALE", "male-qn-qingse")
        else:
            voice = os.getenv("MINIMAX_TTS_VOICE_FEMALE", "female-tianmei")
        if request_metadata is None:
            audio = text_to_speech_minimax(line.paragraph, voice)
        else:
            audio = text_to_speech_minimax(
                line.paragraph,
                voice,
                request_metadata=request_metadata,
            )
    else:
        if line.voice_type:
            voice = line.voice_type
        elif line.speaker == "male":
            voice = os.getenv("VOLCENGINE_TTS_VOICE_MALE", "zh_male_dayi_uranus_bigtts")
        else:
            voice = os.getenv(
                "VOLCENGINE_TTS_VOICE_FEMALE", "zh_female_vv_uranus_bigtts"
            )
        controls = bool(line.speech_rate or line.loudness_rate or line.context_texts)
        if request_metadata is None and not controls:
            audio = text_to_speech_volcengine(line.paragraph, voice)
        else:
            audio = text_to_speech_volcengine(
                line.paragraph,
                voice,
                request_metadata=request_metadata,
                speech_rate=line.speech_rate,
                loudness_rate=line.loudness_rate,
                context_texts=line.context_texts,
            )
    if not audio:
        logger.warning(f"Failed to generate audio for line {i + 1}")
    return (i, audio)


def tts_node(script: Script, execution_metadata: dict | None = None) -> list[bytes]:
    """Convert script lines to audio chunks using TTS with multi-threading.

    Concurrency is owned by the resolved provider (see _default_max_workers);
    there is no caller-facing knob. Fails loudly: if any line cannot be
    synthesized (even after retries), raise rather than silently emitting an
    incomplete podcast.
    """
    total = len(script.lines)
    if total == 0:
        raise ValueError("Script contains no lines to process")

    provider = _resolve_tts_provider()
    if execution_metadata is not None:
        execution_metadata["provider"] = provider
    has_per_line_controls = any(
        line.voice_type or line.speech_rate or line.loudness_rate or line.context_texts
        for line in script.lines
    )
    if has_per_line_controls and (
        provider != "volcengine" or not _volcengine_v3_api_key()
    ):
        raise ValueError(
            "Per-line voice_type, speech_rate, loudness_rate and context_texts "
            "require the Volcengine V3 single-key route"
        )
    max_workers = _default_max_workers(provider)
    if provider == "volcengine" and not (
        os.getenv("VOLCENGINE_TTS_API_KEY") or os.getenv("VOLCENGINE_TTS_ACCESS_TOKEN")
    ):
        raise ValueError(
            "Volcengine TTS selected but VOLCENGINE_TTS_API_KEY is not set"
        )
    if provider == "minimax" and not os.getenv("MINIMAX_API_KEY"):
        raise ValueError("MiniMax TTS selected but MINIMAX_API_KEY is not set")
    logger.info(
        f"Converting script to audio using {max_workers} workers (provider={provider})..."
    )
    line_metadata = (
        [{} for _line in script.lines] if execution_metadata is not None else []
    )
    tasks = [
        (i, line, total, provider, line_metadata[i])
        if execution_metadata is not None
        else (i, line, total, provider)
        for i, line in enumerate(script.lines)
    ]

    results: dict[int, bytes | None] = {}
    failed_indices: list[int] = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_process_line, task): task[0] for task in tasks}
        for future in as_completed(futures):
            idx, audio = future.result()
            results[idx] = audio
            if not audio:
                failed_indices.append(idx)

    if execution_metadata is not None:
        execution_metadata["lines"] = line_metadata
        execution_metadata["model"] = next(
            (str(item["model"]) for item in line_metadata if item.get("model")),
            None,
        )
    if failed_indices:
        raise ValueError(
            f"TTS failed for {len(failed_indices)}/{total} lines after retries: "
            f"line numbers {sorted(i + 1 for i in failed_indices)}. "
            f"This is usually transient API rate limiting — wait a moment and retry."
        )

    audio_chunks = [results[i] for i in range(total)]
    logger.info(f"Generated {len(audio_chunks)}/{total} audio chunks successfully")
    return audio_chunks


def mix_audio(audio_chunks: list[bytes]) -> bytes:
    """Combine audio chunks into a single audio file."""
    if not audio_chunks:
        raise ValueError("No audio chunks to mix - TTS generation may have failed")
    output = b"".join(audio_chunks)
    if len(output) == 0:
        raise ValueError("Mixed audio is empty - TTS generation may have failed")
    logger.info(f"Audio mixing complete: {len(output)} bytes")
    return output


def generate_markdown(script: Script, title: str = "Podcast Script") -> str:
    lines = [f"# {title}", ""]
    for line in script.lines:
        speaker_name = (
            "**Host (Male)**" if line.speaker == "male" else "**Host (Female)**"
        )
        lines.append(f"{speaker_name}: {line.paragraph}")
        lines.append("")
    return "\n".join(lines)


def generate_podcast(
    script_file: str,
    output_file: str,
    transcript_file: str | None = None,
    receipt_file: str | None = None,
) -> str:
    started_at = _utc_now()
    execution_metadata: dict = {}
    with open(script_file, encoding="utf-8") as f:
        script_json = json.load(f)
    if "lines" not in script_json:
        raise ValueError(
            f"Invalid script format: missing 'lines' key. Got keys: {list(script_json.keys())}"
        )
    script = Script.from_dict(script_json)
    logger.info(f"Loaded script with {len(script.lines)} lines")

    input_artifacts = [_file_artifact(script_file)]
    try:
        if transcript_file:
            title = script_json.get("title", "Podcast Script")
            markdown_content = generate_markdown(script, title)
            transcript_dir = os.path.dirname(transcript_file)
            if transcript_dir:
                os.makedirs(transcript_dir, exist_ok=True)
            with open(transcript_file, "w", encoding="utf-8") as f:
                f.write(markdown_content)
            logger.info(f"Generated transcript to {transcript_file}")

        audio_chunks = tts_node(script, execution_metadata if receipt_file else None)
        if not audio_chunks:
            raise Exception("Failed to generate any audio")
        output_audio = mix_audio(audio_chunks)

        output_dir = os.path.dirname(output_file)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
        with open(output_file, "wb") as f:
            f.write(output_audio)
        outputs = [_file_artifact(output_file)]
        if transcript_file:
            outputs.append(_file_artifact(transcript_file))
        provider = execution_metadata.get("provider") or _resolve_tts_provider()
        lines = execution_metadata.get("lines") or []
        request_ids = [item["request_id"] for item in lines if item.get("request_id")]
        voices = sorted({str(item["voice"]) for item in lines if item.get("voice")})
        line_controls = [
            {
                "line_number": item.get("line_number"),
                "voice": item.get("voice"),
                "speech_rate": item.get("speech_rate", 0),
                "loudness_rate": item.get("loudness_rate", 0),
                "context_texts_count": item.get("context_texts_count", 0),
                "context_texts_sha256": item.get("context_texts_sha256"),
            }
            for item in lines
        ]
        _write_receipt(
            receipt_file,
            {
                "contract_version": MEDIA_EXECUTION_CONTRACT_VERSION,
                "capability": "speech_generation",
                "provider": provider,
                "executor": "podcast-generation-skill",
                "model": execution_metadata.get("model"),
                "status": "succeeded",
                "task_id": None,
                "request_id": request_ids[0] if len(request_ids) == 1 else None,
                "started_at": started_at,
                "completed_at": _utc_now(),
                "parameters": {
                    "locale": script.locale,
                    "line_count": len(script.lines),
                    "voices": voices,
                    "request_ids": request_ids,
                    "line_controls": line_controls,
                },
                "inputs": input_artifacts,
                "outputs": outputs,
                "cost": _unknown_cost(),
            },
        )
    except Exception as exc:
        if receipt_file:
            provider = execution_metadata.get("provider") or "volcengine"
            lines = execution_metadata.get("lines") or []
            request_ids = [
                item["request_id"] for item in lines if item.get("request_id")
            ]
            line_controls = [
                {
                    "line_number": item.get("line_number"),
                    "voice": item.get("voice"),
                    "speech_rate": item.get("speech_rate", 0),
                    "loudness_rate": item.get("loudness_rate", 0),
                    "context_texts_count": item.get("context_texts_count", 0),
                    "context_texts_sha256": item.get("context_texts_sha256"),
                }
                for item in lines
            ]
            _write_receipt(
                receipt_file,
                {
                    "contract_version": MEDIA_EXECUTION_CONTRACT_VERSION,
                    "capability": "speech_generation",
                    "provider": provider,
                    "executor": "podcast-generation-skill",
                    "model": execution_metadata.get("model"),
                    "status": "failed",
                    "task_id": None,
                    "request_id": request_ids[0] if len(request_ids) == 1 else None,
                    "started_at": started_at,
                    "completed_at": _utc_now(),
                    "parameters": {
                        "locale": script.locale,
                        "line_count": len(script.lines),
                        "request_ids": request_ids,
                        "line_controls": line_controls,
                    },
                    "inputs": input_artifacts,
                    "outputs": [],
                    "cost": _unknown_cost(),
                    "failure": {
                        "category": "provider_error",
                        "message": (str(exc) or type(exc).__name__)[:1000],
                        "retryable": "rate limit" in str(exc).lower()
                        or "timed out" in str(exc).lower(),
                    },
                },
            )
        raise

    result = f"Successfully generated podcast to {output_file}"
    if transcript_file:
        result += f" and transcript to {transcript_file}"
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate podcast from script JSON file"
    )
    parser.add_argument(
        "--script-file", required=True, help="Absolute path to script JSON file"
    )
    parser.add_argument(
        "--output-file", required=True, help="Output path for generated podcast MP3"
    )
    parser.add_argument(
        "--transcript-file",
        required=False,
        help="Output path for transcript markdown file (optional)",
    )
    parser.add_argument(
        "--receipt-file",
        required=False,
        help="Write a personal-ip-media-execution-v1 JSON receipt",
    )
    args = parser.parse_args()

    try:
        result = generate_podcast(
            args.script_file, args.output_file, args.transcript_file, args.receipt_file
        )
        print(result)
    except Exception as e:
        import traceback

        print(f"Error generating podcast: {e}")
        traceback.print_exc()
