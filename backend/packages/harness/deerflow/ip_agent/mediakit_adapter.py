"""Thin, bounded adapters around the official Volcengine MediaKit CLI.

MediaKit owns media execution.  This module only provides process isolation,
schema checks and deterministic normalization for the IP evidence boundary.
It deliberately contains no account, IP-strategy or creative logic.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

import httpx

from deerflow.community.url_safety import resolve_host_addresses, validate_public_http_url

_LOCAL_ADAPTER_VERSION = "official-mediakit-local-metadata-v1"
_CLOUD_ADAPTER_VERSION = "official-mediakit-cloud-video-v1"
_CLOUD_RESULT_NORMALIZATION_VERSION = "mediakit-cloud-semantic-allowlist-v3"
_CLOUD_ENDPOINT = "https://mediakit.cn-beijing.volces.com"
_MAX_JSON_OUTPUT_BYTES = 2 * 1024 * 1024
_MAX_RESULT_REDIRECTS = 4
_RESULT_DOWNLOAD_TIMEOUT_SECONDS = 45
_MAX_EVIDENCE_PAYLOAD_CHARS = 24_000
_MAX_POLL_ATTEMPTS = 80
_POLL_INTERVAL_SECONDS = 3
_POLL_QUERY_TIMEOUT_SECONDS = 30
_POLL_TOTAL_TIMEOUT_SECONDS = 300
_PASSTHROUGH_ENV = (
    "LANG",
    "LC_ALL",
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
    "REQUESTS_CA_BUNDLE",
    "CURL_CA_BUNDLE",
    "SYSTEMROOT",
    "WINDIR",
    "COMSPEC",
    "PATHEXT",
)
_CLOUD_PASSTHROUGH_ENV = (
    *_PASSTHROUGH_ENV,
    "HTTPS_PROXY",
    "HTTP_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
    "https_proxy",
    "http_proxy",
    "all_proxy",
    "no_proxy",
)
MediaKitCloudCapability = Literal["asr", "ocr", "scene_segmentation", "storyline"]
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_CLOUD_VIDEO_COMMANDS: dict[MediaKitCloudCapability, tuple[str, tuple[str, ...]]] = {
    "asr": (
        "asr-subtitles",
        ("--video-url", "{sealed_source}", "--enable-confidence=true"),
    ),
    "ocr": (
        "video-ocr",
        ("--video-url", "{sealed_source}", "--mode", "Subtitle"),
    ),
    "scene_segmentation": (
        "segment-scenes",
        ("--video-url", "{sealed_source}"),
    ),
    "storyline": (
        "analyze-video-storyline",
        ("--video-urls", "{sealed_source}"),
    ),
}
_CLOUD_COMMON_SEMANTIC_KEYS = frozenset(
    {
        "action",
        "actions",
        "bbox",
        "box",
        "character",
        "characters",
        "clip",
        "clips",
        "confidence",
        "content",
        "cuttime",
        "data",
        "description",
        "duration",
        "durationseconds",
        "end",
        "endseconds",
        "endtime",
        "fade",
        "height",
        "highlight",
        "highlights",
        "index",
        "item",
        "items",
        "label",
        "labels",
        "language",
        "languages",
        "mode",
        "output",
        "outputs",
        "payloadexcerpt",
        "point",
        "points",
        "position",
        "result",
        "results",
        "scene",
        "scenes",
        "score",
        "scores",
        "segment",
        "segments",
        "speaker",
        "speakerid",
        "start",
        "startseconds",
        "starttime",
        "subject",
        "subjects",
        "summary",
        "text",
        "texts",
        "time",
        "timestamp",
        "timestamps",
        "title",
        "transcript",
        "transcripts",
        "transition",
        "truncated",
        "truncationreasoncodes",
        "type",
        "value",
        "width",
        "word",
        "words",
        "x",
        "y",
    }
)
_CLOUD_CAPABILITY_SEMANTIC_KEYS: dict[MediaKitCloudCapability, frozenset[str]] = {
    "asr": frozenset(
        {
            "sentence",
            "sentences",
            "subtitle",
            "subtitles",
            "subtitletext",
            "utterance",
            "utterances",
        }
    ),
    "ocr": frozenset({"subtitle", "subtitles", "region", "regions"}),
    "scene_segmentation": frozenset({"boundary", "boundaries"}),
    "storyline": frozenset(
        {
            "clipdialogue",
            "clipendtime",
            "clipindex",
            "clipscore",
            "clipstarttime",
            "clipsummary",
            "cliptitle",
            "highlightclipsindex",
            "highlightindex",
            "highlightsummary",
            "highlighttitle",
            "sourcevideoinfo",
            "sourcevideoindex",
            "sourcevideosummary",
            "sourcevideotag",
            "sourcevideotitle",
            "stories",
            "story",
            "storyline",
            "storylineclips",
            "storylinehighlights",
        }
    ),
}
_PROVIDER_OPERATIONAL_KEYS = frozenset(
    {
        "apikey",
        "apikeyecho",
        "accesskey",
        "audiourl",
        "authorization",
        "callbackargs",
        "clienttoken",
        "cookie",
        "credential",
        "downloadurl",
        "fileid",
        "filepath",
        "jobid",
        "localpath",
        "outputpath",
        "password",
        "requestid",
        "resulturl",
        "secretkey",
        "sessionid",
        "sourcepath",
        "taskid",
        "token",
        "uploadid",
        "uploadurl",
        "url",
        "urls",
        "videourl",
        "videourls",
    }
)
_URL_IN_TEXT = re.compile(r"https?://[^\s<>'\"]+", re.IGNORECASE)
_POSIX_PATH_IN_TEXT = re.compile(r"(?<![A-Za-z0-9])/(?:[^/\s]+/)+[^/\s,;]*")
_WINDOWS_PATH_IN_TEXT = re.compile(r"(?i)\b[A-Z]:\\(?:[^\\\s]+\\)+[^\\\s,;]*")
_OPERATIONAL_ID_IN_TEXT = re.compile(r"(?i)\b(?:task|request|req|file|upload|job)[_:-][A-Za-z0-9][A-Za-z0-9._:-]{2,}\b")
_PROVIDER_RESULT_HOST_SUFFIXES = ("volces.com",)
_PROVIDER_RESULT_URL_KEYS: dict[MediaKitCloudCapability, tuple[str, ...]] = {
    "asr": ("subtitle_url", "result_url", "download_url", "file_url", "asr_url"),
    "ocr": ("subtitle_url", "result_url", "download_url", "file_url", "ocr_url"),
    "scene_segmentation": ("result_url", "download_url", "file_url"),
    "storyline": ("result_url", "download_url", "file_url"),
}
_PROVIDER_RESULT_CONTENT_TYPES = frozenset(
    {
        "application/json",
        "application/octet-stream",
        "application/x-subrip",
        "text/plain",
        "text/vtt",
    }
)


class MediaKitAdapterError(ValueError):
    """A bounded MediaKit execution or contract failure."""


@dataclass(frozen=True)
class MediaKitMetadataProbe:
    metadata: dict[str, Any]
    receipt: dict[str, str]


@dataclass(frozen=True)
class MediaKitCloudExecution:
    payload: dict[str, Any]
    receipt: dict[str, str]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _parse_json_output(
    result: subprocess.CompletedProcess[str],
    *,
    label: str,
) -> dict[str, Any]:
    if result.returncode != 0:
        raise MediaKitAdapterError(f"MediaKit {label} failed")
    if len(result.stdout.encode("utf-8", errors="replace")) > _MAX_JSON_OUTPUT_BYTES:
        raise MediaKitAdapterError(f"MediaKit {label} exceeded the output limit")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise MediaKitAdapterError(f"MediaKit {label} returned invalid JSON") from exc
    if not isinstance(payload, dict) or payload.get("error"):
        raise MediaKitAdapterError(f"MediaKit {label} returned an invalid result")
    return payload


def _isolated_local_environment(
    *,
    home: Path,
    output: Path,
    ffmpeg_bin_dir: Path,
) -> dict[str, str]:
    inherited_path = os.getenv("PATH", "")
    environment = {key: value for key in _PASSTHROUGH_ENV if (value := os.getenv(key)) is not None}
    environment.update(
        {
            "HOME": str(home),
            "USERPROFILE": str(home),
            "PATH": os.pathsep.join(part for part in (str(ffmpeg_bin_dir), inherited_path) if part),
            "MEDIAKIT_OUTPUT_PATH": str(output),
            "MEDIAKIT_SURFACE": "agent",
            "MEDIAKIT_RUNTIME": "deerflow-ip-agent",
            "MEDIAKIT_DISABLE_UPDATE_CHECK": "1",
        }
    )
    return environment


def _isolated_cloud_environment(
    *,
    home: Path,
    output: Path,
    temporary: Path,
    api_key: str,
) -> dict[str, str]:
    environment = {key: value for key in _CLOUD_PASSTHROUGH_ENV if (value := os.getenv(key)) is not None}
    environment.update(
        {
            "HOME": str(home),
            "USERPROFILE": str(home),
            "TMPDIR": str(temporary),
            "TEMP": str(temporary),
            "TMP": str(temporary),
            "MEDIAKIT_API_KEY": api_key,
            "MEDIAKIT_ENDPOINT": _CLOUD_ENDPOINT,
            "MEDIAKIT_OUTPUT_PATH": str(output),
            "MEDIAKIT_SURFACE": "agent",
            "MEDIAKIT_RUNTIME": "deerflow-ip-agent",
            "MEDIAKIT_DISABLE_UPDATE_CHECK": "1",
        }
    )
    return environment


def _run_json(
    command: list[str],
    *,
    environment: Mapping[str, str],
    timeout: float,
    label: str,
) -> dict[str, Any]:
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=dict(environment),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise MediaKitAdapterError(f"MediaKit {label} could not complete") from exc
    return _parse_json_output(result, label=label)


def _number(value: Any, *, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise MediaKitAdapterError(f"MediaKit metadata omitted {field}") from exc
    if number <= 0:
        raise MediaKitAdapterError(f"MediaKit metadata returned invalid {field}")
    return number


def _optional_positive_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _optional_positive_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _normalize_metadata(payload: Mapping[str, Any], *, source_size: int) -> dict[str, Any]:
    format_meta = payload.get("format_meta")
    video_meta = payload.get("video_stream_meta")
    audio_meta = payload.get("audio_stream_meta")
    if not isinstance(format_meta, Mapping) or not isinstance(video_meta, Mapping):
        raise MediaKitAdapterError("MediaKit metadata result has an unsupported schema")

    duration = _number(
        # Prefer the decodable video-track duration.  Container duration may
        # include a longer audio tail, which would make the last frame sample
        # land after the final video frame.
        video_meta.get("duration") or format_meta.get("duration"),
        field="duration",
    )
    width = _optional_positive_int(video_meta.get("width"))
    height = _optional_positive_int(video_meta.get("height"))
    if width is None or height is None:
        raise MediaKitAdapterError("MediaKit metadata omitted video dimensions")
    try:
        reported_size = int(format_meta.get("size"))
    except (TypeError, ValueError) as exc:
        raise MediaKitAdapterError("MediaKit metadata omitted source size") from exc
    if reported_size != source_size:
        raise MediaKitAdapterError("MediaKit metadata source size does not match the sealed snapshot")

    codec = str(video_meta.get("codec") or "").strip() or None
    container = str(format_meta.get("container") or "").strip() or None
    return {
        "duration_seconds": round(duration, 3),
        "width": width,
        "height": height,
        "frame_rate": (round(frame_rate, 3) if (frame_rate := _optional_positive_float(video_meta.get("fps"))) else None),
        "video_codec": codec,
        "has_audio": isinstance(audio_meta, Mapping) and bool(audio_meta),
        "container": container,
        "size_bytes": source_size,
    }


def cloud_video_capability_spec(capability: MediaKitCloudCapability) -> dict[str, Any]:
    """Return the non-secret, path-free CLI contract used by a cloud stage."""
    try:
        command, arguments = _CLOUD_VIDEO_COMMANDS[capability]
    except KeyError as exc:
        raise MediaKitAdapterError("MediaKit cloud capability is unsupported") from exc
    return {
        "adapter_version": _CLOUD_ADAPTER_VERSION,
        "result_normalization_version": _CLOUD_RESULT_NORMALIZATION_VERSION,
        "executor": "official-mediakit-cli",
        "execution_mode": "cloud",
        "capability": capability,
        "command": command,
        "semantic_args": list(arguments),
        "input_transport": "cli_local_path_auto_upload",
        "provider_endpoint_origin": _CLOUD_ENDPOINT,
        "provider_content_attestation": "unavailable",
        "polling_mode": "caller_deadline_single_query",
        "max_poll_attempts": _MAX_POLL_ATTEMPTS,
        "poll_interval_seconds": _POLL_INTERVAL_SECONDS,
        "poll_total_timeout_seconds": _POLL_TOTAL_TIMEOUT_SECONDS,
    }


def cloud_provider_request_sha256(
    *,
    capability: MediaKitCloudCapability,
    source_sha256: str,
    stage_spec_sha256: str,
) -> str:
    """Hash the exact path-free provider request intent for one cloud stage.

    The official CLI replaces ``{sealed_source}`` with an isolated local path
    and uploads it internally.  Local paths and provider-generated task/file
    identifiers are therefore intentionally absent; the sealed content hash,
    immutable stage contract and deterministic client-token rule carry the
    binding across the approval and execution runs.
    """

    source_digest = str(source_sha256 or "").strip().lower()
    stage_digest = str(stage_spec_sha256 or "").strip().lower()
    if not _SHA256_RE.fullmatch(source_digest):
        raise MediaKitAdapterError("MediaKit source SHA-256 is invalid")
    if not _SHA256_RE.fullmatch(stage_digest):
        raise MediaKitAdapterError("MediaKit stage SHA-256 is invalid")
    capability_spec = cloud_video_capability_spec(capability)
    return _canonical_sha256(
        {
            "contract_version": "volcengine-mediakit-provider-request-v1",
            "adapter_version": _CLOUD_ADAPTER_VERSION,
            "provider": "volcengine-mediakit",
            "capability": capability,
            "source_sha256": source_digest,
            "stage_spec_sha256": stage_digest,
            "command": capability_spec["command"],
            "semantic_args": capability_spec["semantic_args"],
            "input_transport": capability_spec["input_transport"],
            "provider_endpoint_origin": capability_spec["provider_endpoint_origin"],
            "client_token_derivation": "owner_call_stage_sha256_when_admitted",
            "provider_input_attestation": "not_provided",
        }
    )


def _resolve_cloud_session(session_root: Path) -> tuple[Path, Path, Path]:
    session_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    root = session_root.resolve(strict=True)
    if not root.is_dir():
        raise MediaKitAdapterError("MediaKit cloud session is unavailable")
    root.chmod(0o700)
    home = root / "home"
    output = home / ".mediakit" / "output"
    temporary = root / "tmp"
    for directory in (home, output, temporary):
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        directory.chmod(0o700)
    return home, output, temporary


def _decode_result_file(encoded: bytes) -> Any:
    text = encoded.decode("utf-8", errors="replace")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def _validate_provider_result_url(value: str) -> str:
    try:
        parsed = urlsplit(str(value or "").strip())
        port = parsed.port
    except ValueError as exc:
        raise MediaKitAdapterError("MediaKit result URL is invalid") from exc
    hostname = (parsed.hostname or "").strip().rstrip(".").lower()
    if (
        parsed.scheme.lower() != "https"
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or port not in {None, 443}
        or not any(hostname == suffix or hostname.endswith(f".{suffix}") for suffix in _PROVIDER_RESULT_HOST_SUFFIXES)
    ):
        raise MediaKitAdapterError("MediaKit result URL is outside the provider boundary")
    safety_error = validate_public_http_url(
        value,
        action="download a MediaKit result",
        resolver=resolve_host_addresses,
    )
    if safety_error:
        raise MediaKitAdapterError("MediaKit result URL failed the public-network boundary")
    return value


def _download_provider_result(url: str) -> tuple[bytes, str]:
    current = _validate_provider_result_url(url)
    with httpx.Client(
        timeout=httpx.Timeout(_RESULT_DOWNLOAD_TIMEOUT_SECONDS, connect=15.0),
        follow_redirects=False,
        trust_env=False,
    ) as client:
        for _ in range(_MAX_RESULT_REDIRECTS + 1):
            with client.stream("GET", current) as response:
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location")
                    if not location:
                        raise MediaKitAdapterError("MediaKit result redirect omitted its target")
                    current = _validate_provider_result_url(str(response.url.join(location)))
                    continue
                if response.status_code < 200 or response.status_code >= 300:
                    raise MediaKitAdapterError("MediaKit result download failed")
                content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                if content_type and content_type not in _PROVIDER_RESULT_CONTENT_TYPES:
                    raise MediaKitAdapterError("MediaKit result content type is unsupported")
                length = response.headers.get("content-length")
                if length:
                    try:
                        declared_length = int(length)
                    except ValueError as exc:
                        raise MediaKitAdapterError("MediaKit result length is invalid") from exc
                    if declared_length <= 0 or declared_length > _MAX_JSON_OUTPUT_BYTES:
                        raise MediaKitAdapterError("MediaKit result exceeded the output limit")
                chunks: list[bytes] = []
                observed = 0
                for chunk in response.iter_bytes(64 * 1024):
                    observed += len(chunk)
                    if observed > _MAX_JSON_OUTPUT_BYTES:
                        raise MediaKitAdapterError("MediaKit result exceeded the output limit")
                    chunks.append(chunk)
                if observed == 0:
                    raise MediaKitAdapterError("MediaKit result download was empty")
                return b"".join(chunks), content_type or "unknown"
        raise MediaKitAdapterError("MediaKit result exceeded the redirect limit")


def _read_result_file(
    payload: dict[str, Any],
    *,
    output: Path,
    capability: MediaKitCloudCapability,
) -> tuple[dict[str, Any], dict[str, Any]]:
    local_path = payload.pop("local_path", None)
    encoded: bytes | None = None
    transport = "inline_result" if "result_file" in payload else "inline"
    content_type = "application/json"
    if isinstance(local_path, str) and local_path.strip():
        try:
            candidate = Path(local_path).resolve(strict=True)
            candidate.relative_to(output.resolve(strict=True))
        except (OSError, ValueError) as exc:
            raise MediaKitAdapterError("MediaKit result file escaped its isolated output") from exc
        if not candidate.is_file():
            raise MediaKitAdapterError("MediaKit result file is unavailable")
        with candidate.open("rb") as file:
            encoded = file.read(_MAX_JSON_OUTPUT_BYTES + 1)
        transport = "isolated_local_path"
        content_type = "unknown"
    else:
        result_urls = {str(payload.pop(key)).strip() for key in _PROVIDER_RESULT_URL_KEYS[capability] if isinstance(payload.get(key), str) and str(payload.get(key)).strip()}
        if len(result_urls) > 1:
            raise MediaKitAdapterError("MediaKit returned conflicting result URLs")
        if result_urls:
            encoded, content_type = _download_provider_result(result_urls.pop())
            transport = "bounded_provider_https"
    if encoded is None:
        return payload, {"transport": transport}
    if len(encoded) > _MAX_JSON_OUTPUT_BYTES:
        raise MediaKitAdapterError("MediaKit result exceeded the output limit")
    payload["result_file"] = _decode_result_file(encoded)
    return payload, {
        "transport": transport,
        "content_type": content_type,
        "size_bytes": len(encoded),
        "sha256": hashlib.sha256(encoded).hexdigest(),
    }


def _semantic_cloud_payload(terminal: Mapping[str, Any]) -> dict[str, Any]:
    """Remove the provider task envelope and retain only media-result data."""
    if "result_file" in terminal:
        result = terminal.get("result_file")
        if isinstance(result, Mapping):
            payload: dict[str, Any] = dict(result)
        elif isinstance(result, list):
            payload = {"items": result}
        elif isinstance(result, str):
            payload = {"content": result}
        elif result is None:
            payload = {}
        else:
            payload = {"value": result}
    else:
        envelope_keys = {
            "_notice",
            "error",
            "request_id",
            "status",
            "success",
            "task_id",
        }
        payload = {str(key): value for key, value in terminal.items() if str(key) not in envelope_keys}
    if terminal.get("truncated") is True:
        payload["truncated"] = True
        payload["truncation_reason_codes"] = list(terminal.get("truncation_reason_codes") or [])
    return payload


def _normalized_provider_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def sanitize_cloud_payload(
    payload: Mapping[str, Any],
    *,
    capability: MediaKitCloudCapability,
    redactions: tuple[str, ...] = (),
) -> tuple[dict[str, Any], list[str]]:
    """Return the bounded semantic payload that may cross into evidence.

    Provider output is untrusted.  Only media-semantic fields survive, while
    operational identifiers, URLs, paths and known secret values are removed.
    The function is intentionally idempotent so the evidence layer can repeat
    it and verify the adapter receipt against the exact exposed payload.
    """

    allowed_keys = _CLOUD_COMMON_SEMANTIC_KEYS | _CLOUD_CAPABILITY_SEMANTIC_KEYS[capability]
    sensitive_values = tuple(
        sorted(
            {value for raw in redactions if len(value := str(raw or "").strip()) >= 4},
            key=len,
            reverse=True,
        )
    )
    truncation_codes: set[str] = set()
    redaction_codes: set[str] = set()

    def scrub_text(value: str, *, limit: int) -> str:
        result = " ".join(value.split())
        original = result
        for sensitive in sensitive_values:
            result = result.replace(sensitive, "[redacted]")
        result = _URL_IN_TEXT.sub("[external-url]", result)
        result = _WINDOWS_PATH_IN_TEXT.sub("[local-path]", result)
        result = _POSIX_PATH_IN_TEXT.sub("[local-path]", result)
        result = _OPERATIONAL_ID_IN_TEXT.sub("[operational-id]", result)
        if result != original:
            redaction_codes.add("PROVIDER_TEXT_REDACTED")
        if len(result) > limit:
            truncation_codes.add("PROVIDER_TEXT_TRUNCATED")
        return result[:limit]

    def sanitize(value: Any, *, depth: int) -> Any:
        if depth > 6:
            truncation_codes.add("PROVIDER_DEPTH_TRUNCATED")
            return "[truncated]"
        if isinstance(value, Mapping):
            entries = list(value.items())
            if len(entries) > 100:
                truncation_codes.add("PROVIDER_OBJECT_TRUNCATED")
            result: dict[str, Any] = {}
            for raw_key, raw_value in entries[:100]:
                key = scrub_text(str(raw_key), limit=100)
                normalized_key = _normalized_provider_key(key)
                if (
                    normalized_key in _PROVIDER_OPERATIONAL_KEYS
                    or normalized_key.endswith("url")
                    or normalized_key.endswith("path")
                    or any(
                        marker in normalized_key
                        for marker in (
                            "authorization",
                            "cookie",
                            "credential",
                            "password",
                            "secret",
                            "token",
                        )
                    )
                ):
                    redaction_codes.add("PROVIDER_OPERATIONAL_FIELDS_REMOVED")
                    continue
                if normalized_key not in allowed_keys:
                    truncation_codes.add("PROVIDER_FIELDS_NOT_ALLOWLISTED")
                    continue
                result[key] = sanitize(raw_value, depth=depth + 1)
            return result
        if isinstance(value, list):
            if len(value) > 100:
                truncation_codes.add("PROVIDER_LIST_TRUNCATED")
            return [sanitize(item, depth=depth + 1) for item in value[:100]]
        if isinstance(value, str):
            return scrub_text(value, limit=2_000)
        if value is None or isinstance(value, bool | int | float):
            return value
        truncation_codes.add("PROVIDER_VALUE_NORMALIZED")
        return scrub_text(str(value), limit=500)

    sanitized = sanitize(payload, depth=0)
    if not isinstance(sanitized, dict):
        sanitized = {}
        truncation_codes.add("PROVIDER_RESULT_SCHEMA_UNSUPPORTED")
    if truncation_codes:
        existing_codes = sanitized.get("truncation_reason_codes")
        if not isinstance(existing_codes, list):
            existing_codes = []
        sanitized["truncated"] = True
        sanitized["truncation_reason_codes"] = sorted(
            {
                *truncation_codes,
                *(str(code) for code in existing_codes[:100]),
            }
        )

    encoded = json.dumps(
        sanitized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    if len(encoded) > _MAX_EVIDENCE_PAYLOAD_CHARS:
        truncation_codes.add("PROVIDER_PAYLOAD_CHAR_LIMIT")
        sanitized = {
            "truncated": True,
            "truncation_reason_codes": sorted(truncation_codes),
            "payload_excerpt": encoded[: _MAX_EVIDENCE_PAYLOAD_CHARS - 1_000],
        }
    return sanitized, sorted(truncation_codes | redaction_codes)


def run_cloud_video_capability(
    source: Path,
    *,
    expected_source_sha256: str,
    mediakit: Path,
    api_key: str,
    capability: MediaKitCloudCapability,
    client_token: str,
    stage_spec_sha256: str,
    session_root: Path,
) -> MediaKitCloudExecution:
    """Run one cloud analysis on the already sealed local video snapshot.

    The official CLI owns local-file upload and provider task execution.  This
    boundary verifies the local bytes before and after, isolates CLI state per
    evidence request, bounds polling, and retains only hashed operational IDs.
    The provider does not attest the uploaded content hash.
    """
    try:
        source = source.resolve(strict=True)
        mediakit = mediakit.resolve(strict=True)
    except OSError as exc:
        raise MediaKitAdapterError("MediaKit cloud dependency is unavailable") from exc
    if not source.is_file() or not mediakit.is_file():
        raise MediaKitAdapterError("MediaKit cloud dependency is unavailable")
    if len(expected_source_sha256) != 64 or _sha256_file(source) != expected_source_sha256:
        raise MediaKitAdapterError("MediaKit source hash does not match the sealed snapshot")
    if len(stage_spec_sha256) != 64:
        raise MediaKitAdapterError("MediaKit stage specification hash is invalid")
    api_key = str(api_key or "").strip()
    if not api_key:
        raise MediaKitAdapterError("MediaKit API key is not configured")
    client_token = str(client_token or "").strip()
    if not client_token:
        raise MediaKitAdapterError("MediaKit client token is missing")

    capability_spec = cloud_video_capability_spec(capability)
    command_name = str(capability_spec["command"])
    arguments = [str(source) if value == "{sealed_source}" else value for value in capability_spec["semantic_args"]]
    home, output, temporary = _resolve_cloud_session(session_root)
    environment = _isolated_cloud_environment(
        home=home,
        output=output,
        temporary=temporary,
        api_key=api_key,
    )
    submit = _run_json(
        [
            str(mediakit),
            "--cloud",
            "video",
            command_name,
            *arguments,
            "--client-token",
            client_token,
        ],
        environment=environment,
        timeout=180,
        label=f"{capability} submission",
    )
    task_id = str(submit.get("task_id") or "").strip()
    if not task_id:
        raise MediaKitAdapterError(f"MediaKit {capability} did not return task_id")
    deadline = time.monotonic() + _POLL_TOTAL_TIMEOUT_SECONDS
    final: dict[str, Any] = {}
    for attempt in range(_MAX_POLL_ATTEMPTS):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise MediaKitAdapterError(f"MediaKit {capability} polling reached its deadline")
        final = _run_json(
            [
                str(mediakit),
                "--cloud",
                "shared",
                "query-task",
                "--task-id",
                task_id,
            ],
            environment=environment,
            timeout=min(_POLL_QUERY_TIMEOUT_SECONDS, remaining),
            label=f"{capability} polling",
        )
        if str(final.get("task_id") or "").strip() != task_id:
            raise MediaKitAdapterError(f"MediaKit {capability} polling returned a different task_id")
        status = str(final.get("status") or "").strip().lower()
        if status == "completed":
            break
        if status in {"failed", "canceled", "cancelled"}:
            raise MediaKitAdapterError(f"MediaKit {capability} reached a failed terminal status")
        if status not in {"queued", "pending", "running", "processing"}:
            raise MediaKitAdapterError(f"MediaKit {capability} returned an unknown task status")
        if attempt + 1 >= _MAX_POLL_ATTEMPTS:
            raise MediaKitAdapterError(f"MediaKit {capability} polling did not reach completed status")
        sleep_for = min(_POLL_INTERVAL_SECONDS, deadline - time.monotonic())
        if sleep_for <= 0:
            raise MediaKitAdapterError(f"MediaKit {capability} polling reached its deadline")
        time.sleep(sleep_for)
    final, result_transport = _read_result_file(
        dict(final),
        output=output,
        capability=capability,
    )
    request_id = str(final.get("request_id") or "").strip()
    semantic_payload = _semantic_cloud_payload(final)
    if not semantic_payload:
        raise MediaKitAdapterError(f"MediaKit {capability} completed without a semantic result")
    payload, _reason_codes = sanitize_cloud_payload(
        semantic_payload,
        capability=capability,
        redactions=(
            api_key,
            client_token,
            task_id,
            request_id,
            str(source),
            str(mediakit),
            str(session_root.resolve()),
            str(home),
            str(output),
            str(temporary),
        ),
    )

    if _sha256_file(source) != expected_source_sha256:
        raise MediaKitAdapterError("MediaKit source hash changed during cloud execution")
    receipt = {
        "adapter_version": _CLOUD_ADAPTER_VERSION,
        "result_normalization_version": _CLOUD_RESULT_NORMALIZATION_VERSION,
        "executor": "official-mediakit-cli",
        "execution_mode": "cloud",
        "capability": capability,
        "source_sha256": expected_source_sha256,
        "mediakit_sha256": _sha256_file(mediakit),
        "stage_spec_sha256": stage_spec_sha256,
        "submission_sha256": _canonical_sha256(submit),
        "result_sha256": _canonical_sha256(payload),
        "task_id_sha256": hashlib.sha256(task_id.encode("utf-8")).hexdigest(),
        "provider_input_attestation": "not_provided",
        "polling_mode": "caller_deadline_single_query",
        "result_transport": str(result_transport["transport"]),
    }
    if result_transport.get("sha256"):
        receipt["result_file_sha256"] = str(result_transport["sha256"])
        receipt["result_file_size_bytes"] = int(result_transport["size_bytes"])
        receipt["result_file_content_type"] = str(result_transport["content_type"])
    if request_id:
        receipt["request_id_sha256"] = hashlib.sha256(request_id.encode("utf-8")).hexdigest()
    return MediaKitCloudExecution(payload=payload, receipt=receipt)


def probe_video_metadata(
    source: Path,
    *,
    expected_source_sha256: str,
    mediakit: Path,
    ffmpeg_bin_dir: Path,
) -> MediaKitMetadataProbe:
    """Probe one sealed local snapshot through the official CLI local mode."""
    try:
        source = source.resolve(strict=True)
        mediakit = mediakit.resolve(strict=True)
        ffmpeg_bin_dir = ffmpeg_bin_dir.resolve(strict=True)
    except OSError as exc:
        raise MediaKitAdapterError("MediaKit local probe dependency is unavailable") from exc
    if not source.is_file() or not mediakit.is_file() or not ffmpeg_bin_dir.is_dir():
        raise MediaKitAdapterError("MediaKit local probe dependency is unavailable")
    if len(expected_source_sha256) != 64 or _sha256_file(source) != expected_source_sha256:
        raise MediaKitAdapterError("MediaKit source hash does not match the sealed snapshot")

    with tempfile.TemporaryDirectory(prefix="ip-mediakit-local-") as temporary:
        root = Path(temporary)
        home = root / "home"
        output = home / ".mediakit" / "output"
        output.mkdir(parents=True)
        environment = _isolated_local_environment(
            home=home,
            output=output,
            ffmpeg_bin_dir=ffmpeg_bin_dir,
        )
        prefix = [str(mediakit), "--local", "video", "probe-video-metadata"]
        schema = _run_json(
            [*prefix, "--schema"],
            environment=environment,
            timeout=30,
            label="metadata schema",
        )
        input_schema = schema.get("input_schema")
        required = input_schema.get("required") if isinstance(input_schema, Mapping) else None
        if schema.get("name") != "probe_video_metadata" or not isinstance(required, list) or "video_url" not in required:
            raise MediaKitAdapterError("MediaKit metadata schema is incompatible")
        payload = _run_json(
            [*prefix, "--video-url", str(source)],
            environment=environment,
            timeout=90,
            label="metadata probe",
        )

    if _sha256_file(source) != expected_source_sha256:
        raise MediaKitAdapterError("MediaKit source hash changed during local probing")
    metadata = _normalize_metadata(payload, source_size=source.stat().st_size)
    receipt = {
        "adapter_version": _LOCAL_ADAPTER_VERSION,
        "executor": "official-mediakit-cli",
        "execution_mode": "local",
        "source_sha256": expected_source_sha256,
        "mediakit_sha256": _sha256_file(mediakit),
        "schema_sha256": _canonical_sha256(schema),
        "result_sha256": _canonical_sha256(payload),
    }
    return MediaKitMetadataProbe(metadata=metadata, receipt=receipt)


__all__ = [
    "MediaKitCloudExecution",
    "MediaKitAdapterError",
    "MediaKitMetadataProbe",
    "cloud_provider_request_sha256",
    "cloud_video_capability_spec",
    "probe_video_metadata",
    "run_cloud_video_capability",
    "sanitize_cloud_payload",
]
