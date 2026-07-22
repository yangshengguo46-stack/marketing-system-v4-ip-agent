import base64
import hashlib
import json
import mimetypes
import os
import time
from datetime import UTC, datetime
from pathlib import Path

import requests

MINIMAX_DEFAULT_HOST = "https://api.minimaxi.com"
VOLCENGINE_ARK_DEFAULT_HOST = "https://ark.cn-beijing.volces.com/api/v3"
VOLCENGINE_VIDEO_DEFAULT_MODEL = "doubao-seedance-2-0-260128"
MEDIA_EXECUTION_CONTRACT_VERSION = "personal-ip-media-execution-v1"


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


def _resolve_provider(
    override_env: str, existing_provider: str, has_existing_creds: bool
) -> str:
    """Pick provider: explicit override > Volcengine > upstream fallbacks."""
    override = os.getenv(override_env)
    if override:
        return override.strip().lower()
    if os.getenv("VOLCENGINE_API_KEY"):
        return "volcengine"
    if has_existing_creds:
        return existing_provider
    if os.getenv("MINIMAX_API_KEY"):
        return "minimax"
    raise ValueError(
        f"No credentials found. Set VOLCENGINE_API_KEY for Volcengine Seedance, "
        f"GEMINI_API_KEY for {existing_provider}, "
        f"or MINIMAX_API_KEY for minimax (optionally force with {override_env})."
    )


def _volcengine_ark_host() -> str:
    return os.getenv("VOLCENGINE_ARK_BASE_URL", VOLCENGINE_ARK_DEFAULT_HOST).rstrip("/")


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _minimax_host() -> str:
    return os.getenv("MINIMAX_API_HOST", MINIMAX_DEFAULT_HOST).rstrip("/")


def _ensure_output_dir(output_file: str) -> None:
    """Create the output file's parent directory so nested paths don't fail."""
    output_dir = os.path.dirname(output_file)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)


def _check_base_resp(payload: dict) -> None:
    base = payload.get("base_resp") or {}
    if base.get("status_code", 0) != 0:
        raise Exception(
            f"MiniMax error {base.get('status_code')}: {base.get('status_msg')}"
        )


def _guess_mime(image_path: str) -> str:
    ext = os.path.splitext(image_path)[1].lower()
    return {
        ".png": "image/png",
        ".webp": "image/webp",
        ".gif": "image/gif",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
    }.get(ext, "image/jpeg")


def _to_data_url(image_path: str) -> str:
    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    return f"data:{_guess_mime(image_path)};base64,{b64}"


def _poll_video_task(
    host: str, auth: str, task_id: str, max_attempts: int = 120, interval: int = 3
) -> str:
    for _ in range(max_attempts):
        response = requests.get(
            f"{host}/v1/query/video_generation",
            headers={"Authorization": auth},
            params={"task_id": task_id},
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        status = payload.get("status")
        if status == "Success":
            return payload["file_id"]
        if status == "Fail":
            base = payload.get("base_resp") or {}
            raise Exception(
                f"MiniMax video task {task_id} failed: "
                f"{base.get('status_code')} {base.get('status_msg')}"
            )
        # Surface query-level errors (bad task_id, auth) that arrive as a non-zero
        # base_resp without a terminal status, then keep polling.
        _check_base_resp(payload)
        time.sleep(interval)
    raise Exception(
        f"MiniMax video task {task_id} timed out after {max_attempts} polls"
    )


def _retrieve_file_url(host: str, auth: str, file_id: str) -> str:
    response = requests.get(
        f"{host}/v1/files/retrieve",
        headers={"Authorization": auth},
        params={"file_id": file_id},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    _check_base_resp(payload)
    return payload["file"]["download_url"]


def _download(url: str, output_file: str) -> None:
    response = requests.get(url, timeout=300)
    response.raise_for_status()
    _ensure_output_dir(output_file)
    with open(output_file, "wb") as f:
        f.write(response.content)


def _poll_volcengine_task(
    host: str,
    auth: str,
    task_id: str,
    max_attempts: int = 180,
    interval: int = 5,
) -> dict:
    terminal_failures = {"failed", "expired", "cancelled", "canceled"}
    for _ in range(max_attempts):
        response = requests.get(
            f"{host}/contents/generations/tasks/{task_id}",
            headers={"Authorization": auth},
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        status = str(payload.get("status", "")).lower()
        if status in {"succeeded", "success", "completed"}:
            return payload
        if status in terminal_failures:
            error = payload.get("error") or payload.get("message") or "unknown error"
            raise Exception(f"Volcengine Seedance task {task_id} failed: {error}")
        time.sleep(interval)
    raise Exception(
        f"Volcengine Seedance task {task_id} timed out after {max_attempts} polls"
    )


def _volcengine_video_url(payload: dict) -> str:
    content = payload.get("content") or {}
    if isinstance(content, dict) and content.get("video_url"):
        return content["video_url"]
    output = payload.get("output") or {}
    if isinstance(output, dict) and output.get("video_url"):
        return output["video_url"]
    if payload.get("video_url"):
        return payload["video_url"]
    raise Exception(f"Volcengine Seedance returned no video URL: {payload}")


def _generate_video_volcengine(
    prompt: str,
    reference_images: list[str],
    output_file: str,
    aspect_ratio: str,
    *,
    prompt_file: str | None = None,
    receipt_file: str | None = None,
) -> str:
    api_key = os.getenv("VOLCENGINE_API_KEY")
    if not api_key:
        return "VOLCENGINE_API_KEY is not set"

    started_at = _utc_now()
    task_id = None
    request_id = None
    model = os.getenv("VOLCENGINE_VIDEO_MODEL", VOLCENGINE_VIDEO_DEFAULT_MODEL)
    parameters = {
        "ratio": aspect_ratio,
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "prompt_characters": len(prompt),
    }
    inputs = []
    if prompt_file:
        inputs.append(_file_artifact(prompt_file))
    inputs.extend(_file_artifact(path) for path in reference_images)
    try:
        content: list[dict] = [{"type": "text", "text": prompt}]
        if len(reference_images) == 1:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": _to_data_url(reference_images[0])},
                    "role": "first_frame",
                }
            )
        elif reference_images:
            content.extend(
                {
                    "type": "image_url",
                    "image_url": {"url": _to_data_url(path)},
                    "role": "reference_image",
                }
                for path in reference_images
            )

        try:
            duration = int(os.getenv("VOLCENGINE_VIDEO_DURATION", "5"))
        except ValueError as exc:
            raise ValueError("VOLCENGINE_VIDEO_DURATION must be an integer") from exc
        if duration != -1 and not 4 <= duration <= 15:
            raise ValueError("VOLCENGINE_VIDEO_DURATION must be -1 or between 4 and 15")
        parameters.update(
            {
                "duration": duration,
                "resolution": os.getenv("VOLCENGINE_VIDEO_RESOLUTION", "720p"),
                "generate_audio": _env_bool("VOLCENGINE_VIDEO_GENERATE_AUDIO", True),
                "watermark": _env_bool("VOLCENGINE_VIDEO_WATERMARK", False),
                "return_last_frame": _env_bool(
                    "VOLCENGINE_VIDEO_RETURN_LAST_FRAME", False
                ),
            }
        )
        body = {
            "model": model,
            "content": content,
            "resolution": parameters["resolution"],
            "ratio": aspect_ratio,
            "duration": duration,
            "generate_audio": parameters["generate_audio"],
            "watermark": parameters["watermark"],
            "return_last_frame": parameters["return_last_frame"],
        }
        host = _volcengine_ark_host()
        auth = f"Bearer {api_key}"
        response = requests.post(
            f"{host}/contents/generations/tasks",
            headers={"Authorization": auth, "Content-Type": "application/json"},
            json=body,
            timeout=60,
        )
        response.raise_for_status()
        created = response.json()
        task_id = created.get("id") or created.get("task_id")
        request_id = created.get("request_id")
        if not task_id:
            raise Exception("Volcengine Seedance returned no task ID")
        completed = _poll_volcengine_task(host, auth, task_id)
        _download(_volcengine_video_url(completed), output_file)
        _write_receipt(
            receipt_file,
            {
                "contract_version": MEDIA_EXECUTION_CONTRACT_VERSION,
                "capability": "video_generation",
                "provider": "volcengine",
                "executor": "video-generation-skill",
                "model": model,
                "status": "succeeded",
                "task_id": task_id,
                "request_id": request_id,
                "started_at": started_at,
                "completed_at": _utc_now(),
                "parameters": parameters,
                "inputs": inputs,
                "outputs": [_file_artifact(output_file)],
                "cost": _unknown_cost(),
            },
        )
    except ValueError as exc:
        message = str(exc)
        _write_receipt(
            receipt_file,
            {
                "contract_version": MEDIA_EXECUTION_CONTRACT_VERSION,
                "capability": "video_generation",
                "provider": "volcengine",
                "executor": "video-generation-skill",
                "model": model,
                "status": "failed",
                "task_id": task_id,
                "request_id": request_id,
                "started_at": started_at,
                "completed_at": _utc_now(),
                "parameters": parameters,
                "inputs": inputs,
                "outputs": [],
                "cost": _unknown_cost(),
                "failure": {
                    "category": "invalid_request",
                    "message": message[:1000],
                    "retryable": False,
                },
            },
        )
        raise ValueError(message) from exc
    except Exception as exc:
        message = str(exc) or type(exc).__name__
        retryable = (
            isinstance(exc, (requests.Timeout, requests.ConnectionError))
            or "timed out" in message.lower()
        )
        _write_receipt(
            receipt_file,
            {
                "contract_version": MEDIA_EXECUTION_CONTRACT_VERSION,
                "capability": "video_generation",
                "provider": "volcengine",
                "executor": "video-generation-skill",
                "model": model,
                "status": "failed",
                "task_id": task_id,
                "request_id": request_id,
                "started_at": started_at,
                "completed_at": _utc_now(),
                "parameters": parameters,
                "inputs": inputs,
                "outputs": [],
                "cost": _unknown_cost(),
                "failure": {
                    "category": "provider_error",
                    "message": message[:1000],
                    "retryable": retryable,
                },
            },
        )
        raise
    return (
        f"The video has been generated successfully to {output_file} "
        f"via Volcengine Seedance (task {task_id})"
    )


def _generate_video_minimax(
    prompt: str, reference_images: list[str], output_file: str
) -> str:
    api_key = os.getenv("MINIMAX_API_KEY")
    if not api_key:
        return "MINIMAX_API_KEY is not set"
    host = _minimax_host()
    auth = f"Bearer {api_key}"
    body = {
        "model": os.getenv("MINIMAX_VIDEO_MODEL", "MiniMax-Hailuo-2.3"),
        "prompt": prompt,
    }
    if reference_images:
        body["first_frame_image"] = _to_data_url(reference_images[0])
    response = requests.post(
        f"{host}/v1/video_generation",
        headers={"Authorization": auth, "Content-Type": "application/json"},
        json=body,
        timeout=60,
    )
    response.raise_for_status()
    payload = response.json()
    _check_base_resp(payload)
    task_id = payload["task_id"]
    file_id = _poll_video_task(host, auth, task_id)
    download_url = _retrieve_file_url(host, auth, file_id)
    _download(download_url, output_file)
    return f"The video has been generated successfully to {output_file}"


def download(url: str, output_file: str) -> None:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not set")
    response = requests.get(url, headers={"x-goog-api-key": api_key}, timeout=300)
    response.raise_for_status()
    _ensure_output_dir(output_file)
    with open(output_file, "wb") as f:
        f.write(response.content)


def _generate_video_gemini(
    prompt: str, reference_images: list[str], output_file: str
) -> str:
    reference_payload = []
    request_json = {"instances": [{"prompt": prompt}]}
    for reference_image in reference_images:
        with open(reference_image, "rb") as f:
            image_b64 = base64.b64encode(f.read()).decode("utf-8")
        reference_payload.append(
            {
                "image": {"mimeType": "image/jpeg", "bytesBase64Encoded": image_b64},
                "referenceType": "asset",
            }
        )
    if reference_payload:
        request_json["instances"][0]["referenceImages"] = reference_payload
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return "GEMINI_API_KEY is not set"
    response = requests.post(
        "https://generativelanguage.googleapis.com/v1beta/models/veo-3.1-generate-preview:predictLongRunning",
        headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
        json=request_json,
        timeout=60,
    )
    response.raise_for_status()
    data = response.json()
    operation_name = data["name"]
    while True:
        response = requests.get(
            f"https://generativelanguage.googleapis.com/v1beta/{operation_name}",
            headers={"x-goog-api-key": api_key},
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        if data.get("done", False):
            sample = data["response"]["generateVideoResponse"]["generatedSamples"][0]
            download(sample["video"]["uri"], output_file)
            break
        time.sleep(3)
    return f"The video has been generated successfully to {output_file}"


def generate_video(
    prompt_file: str,
    reference_images: list[str],
    output_file: str,
    aspect_ratio: str = "16:9",
    receipt_file: str | None = None,
) -> str:
    with open(prompt_file, "r", encoding="utf-8") as f:
        prompt = f.read()
    provider = _resolve_provider(
        "VIDEO_GENERATION_PROVIDER", "gemini", bool(os.getenv("GEMINI_API_KEY"))
    )
    if provider in ("volcengine", "volcano", "seedance"):
        return _generate_video_volcengine(
            prompt,
            reference_images,
            output_file,
            aspect_ratio,
            prompt_file=prompt_file,
            receipt_file=receipt_file,
        )
    if provider == "minimax":
        # MiniMax video uses resolution/duration, not aspect_ratio; aspect_ratio ignored.
        return _generate_video_minimax(prompt, reference_images, output_file)
    if provider in ("gemini", "google"):
        return _generate_video_gemini(prompt, reference_images, output_file)
    raise ValueError(
        f"Unknown video provider: {provider!r} "
        "(use 'volcengine', 'gemini', or 'minimax')"
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate videos using Volcengine Seedance, Gemini, or MiniMax API"
    )
    parser.add_argument(
        "--prompt-file", required=True, help="Absolute path to JSON prompt file"
    )
    parser.add_argument(
        "--reference-images",
        nargs="*",
        default=[],
        help="Absolute paths to reference images (space-separated)",
    )
    parser.add_argument(
        "--output-file", required=True, help="Output path for generated video"
    )
    parser.add_argument(
        "--aspect-ratio",
        required=False,
        default="16:9",
        help="Aspect ratio of the generated video (Gemini only)",
    )
    parser.add_argument(
        "--receipt-file",
        required=False,
        help="Write a personal-ip-media-execution-v1 JSON receipt",
    )
    args = parser.parse_args()

    try:
        print(
            generate_video(
                args.prompt_file,
                args.reference_images,
                args.output_file,
                args.aspect_ratio,
                args.receipt_file,
            )
        )
    except Exception as e:
        print(f"Error while generating video: {e}")
