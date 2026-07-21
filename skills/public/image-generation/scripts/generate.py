import base64
import json
import os

import requests

MINIMAX_DEFAULT_HOST = "https://api.minimaxi.com"
VOLCENGINE_ARK_DEFAULT_HOST = "https://ark.cn-beijing.volces.com/api/v3"
VOLCENGINE_IMAGE_DEFAULT_MODEL = "doubao-seedream-5-0-260128"
# MiniMax image-01 caps the prompt at 1500 characters and rejects longer requests
# with a generic "invalid params" error, so validate before calling the API.
MINIMAX_PROMPT_MAX_CHARS = 1500


def validate_image(image_path: str) -> bool:
    """Validate if an image file can be opened and is not corrupted."""
    from PIL import Image  # lazy import: keeps module importable without Pillow

    try:
        with Image.open(image_path) as image:
            image.verify()
        with Image.open(image_path) as image:
            image.load()
        return True
    except Exception as exc:
        print(f"Warning: Image '{image_path}' is invalid or corrupted: {exc}")
        return False


def _resolve_provider(override_env: str, existing_provider: str, has_existing_creds: bool) -> str:
    """Pick the generation provider.

    1. Explicit <SKILL>_PROVIDER override wins.
    2. Otherwise prefer Volcengine when its unified Ark API key is present.
    3. Otherwise preserve the upstream provider fallback order.
    """
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
        f"No credentials found. Set VOLCENGINE_API_KEY for Volcengine Seedream, "
        f"GEMINI_API_KEY for {existing_provider}, "
        f"or MINIMAX_API_KEY for minimax (optionally force with {override_env})."
    )


def _volcengine_ark_host() -> str:
    return os.getenv("VOLCENGINE_ARK_BASE_URL", VOLCENGINE_ARK_DEFAULT_HOST).rstrip("/")


def _minimax_host() -> str:
    return os.getenv("MINIMAX_API_HOST", MINIMAX_DEFAULT_HOST).rstrip("/")


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


def _download_image(url: str, output_file: str) -> None:
    response = requests.get(url, timeout=300)
    response.raise_for_status()
    _ensure_output_dir(output_file)
    with open(output_file, "wb") as f:
        f.write(response.content)


VOLCENGINE_IMAGE_SIZES = {
    "1:1": "2048x2048",
    "16:9": "2560x1440",
    "9:16": "1440x2560",
    "4:3": "2304x1728",
    "3:4": "1728x2304",
    "3:2": "2496x1664",
    "2:3": "1664x2496",
    "21:9": "3024x1296",
    "9:21": "1296x3024",
}


def _generate_image_volcengine(
    prompt: str, reference_images: list[str], output_file: str, aspect_ratio: str
) -> str:
    """Generate or edit an image through Volcengine Ark Seedream.

    Ark uses one synchronous endpoint for text-to-image, reference generation,
    and image editing.  Keep the output count deterministic here; storyboard
    batches should call this function once per named asset so every receipt maps
    to exactly one file.
    """
    api_key = os.getenv("VOLCENGINE_API_KEY")
    if not api_key:
        return "VOLCENGINE_API_KEY is not set"

    body = {
        "model": os.getenv("VOLCENGINE_IMAGE_MODEL", VOLCENGINE_IMAGE_DEFAULT_MODEL),
        "prompt": _minimax_prompt(prompt),
        "size": os.getenv(
            "VOLCENGINE_IMAGE_SIZE",
            VOLCENGINE_IMAGE_SIZES.get(aspect_ratio, "2K"),
        ),
        "sequential_image_generation": "disabled",
        "stream": False,
        "response_format": "url",
        "watermark": os.getenv("VOLCENGINE_IMAGE_WATERMARK", "false").lower()
        in {"1", "true", "yes", "on"},
    }
    if reference_images:
        body["image"] = [_to_data_url(path) for path in reference_images]

    response = requests.post(
        f"{_volcengine_ark_host()}/images/generations",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=body,
        timeout=300,
    )
    response.raise_for_status()
    payload = response.json()
    images = payload.get("data") or []
    if not images:
        raise Exception(f"Volcengine Seedream returned no image data: {payload}")

    first = images[0]
    if first.get("url"):
        _download_image(first["url"], output_file)
    elif first.get("b64_json"):
        _ensure_output_dir(output_file)
        with open(output_file, "wb") as f:
            f.write(base64.b64decode(first["b64_json"]))
    else:
        raise Exception(f"Volcengine Seedream returned no downloadable image: {first}")
    return f"Successfully generated image to {output_file} via Volcengine Seedream"


def _ensure_output_dir(output_file: str) -> None:
    """Create the output file's parent directory so nested paths don't fail."""
    output_dir = os.path.dirname(output_file)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)


def _minimax_prompt(raw: str) -> str:
    """Extract the single text prompt MiniMax image-01 expects.

    The shared prompt file is structured JSON (a consolidated ``prompt`` plus
    Gemini-oriented fields like ``style`` / ``composition`` / ``negative_prompt``),
    but MiniMax consumes one string and expands it via ``prompt_optimizer``. The
    provider adapts the input itself — the caller never needs to know MiniMax is
    active. Use the JSON ``prompt`` field; fall back to the raw text for plain-text
    prompt files or JSON without a ``prompt`` field.
    """
    text = raw.strip()
    try:
        data = json.loads(text)
    except (ValueError, json.JSONDecodeError):
        return text
    if isinstance(data, dict):
        core = data.get("prompt")
        if isinstance(core, str) and core.strip():
            return core.strip()
    return text


def _generate_image_minimax(
    prompt: str, reference_images: list[str], output_file: str, aspect_ratio: str
) -> str:
    api_key = os.getenv("MINIMAX_API_KEY")
    if not api_key:
        return "MINIMAX_API_KEY is not set"
    prompt = _minimax_prompt(prompt)
    if len(prompt) > MINIMAX_PROMPT_MAX_CHARS:
        return (
            f"Prompt is {len(prompt)} characters but MiniMax image-01 accepts at most "
            f"{MINIMAX_PROMPT_MAX_CHARS}. Shorten the prompt to stay within the limit; "
            f"reference images plus a tighter description usually recover the detail."
        )
    body = {
        "model": os.getenv("MINIMAX_IMAGE_MODEL", "image-01"),
        "prompt": prompt,
        "aspect_ratio": aspect_ratio,
        "response_format": "base64",
        "n": 1,
        "prompt_optimizer": True,
    }
    if reference_images:
        # Reference images are passed as character subjects as-is; unlike the Gemini
        # path we do not pre-validate them — invalid files surface as a MiniMax API error.
        body["subject_reference"] = [
            {"type": "character", "image_file": _to_data_url(p)} for p in reference_images
        ]
    response = requests.post(
        f"{_minimax_host()}/v1/image_generation",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=body,
        timeout=60,
    )
    response.raise_for_status()
    payload = response.json()
    _check_base_resp(payload)
    images = (payload.get("data") or {}).get("image_base64") or []
    if not images:
        raise Exception("MiniMax returned no image data")
    _ensure_output_dir(output_file)
    with open(output_file, "wb") as f:
        f.write(base64.b64decode(images[0]))
    return f"Successfully generated image to {output_file}"


def _generate_image_gemini(
    prompt: str, reference_images: list[str], output_file: str, aspect_ratio: str
) -> str:
    parts = []
    valid_reference_images = []
    for ref_img in reference_images:
        if validate_image(ref_img):
            valid_reference_images.append(ref_img)
        else:
            print(f"Skipping invalid reference image: {ref_img}")
    if len(valid_reference_images) < len(reference_images):
        skipped = len(reference_images) - len(valid_reference_images)
        print(f"Note: {skipped} reference image(s) were skipped due to validation failure.")

    for reference_image in valid_reference_images:
        with open(reference_image, "rb") as f:
            image_b64 = base64.b64encode(f.read()).decode("utf-8")
        parts.append({"inlineData": {"mimeType": "image/jpeg", "data": image_b64}})

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return "GEMINI_API_KEY is not set"
    response = requests.post(
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-3-pro-image-preview:generateContent",
        headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
        json={
            "generationConfig": {"imageConfig": {"aspectRatio": aspect_ratio}},
            "contents": [{"parts": [*parts, {"text": prompt}]}],
        },
    )
    response.raise_for_status()
    data = response.json()
    response_parts: list[dict] = data["candidates"][0]["content"]["parts"]
    image_parts = [part for part in response_parts if part.get("inlineData", False)]
    if len(image_parts) == 1:
        base64_image = image_parts[0]["inlineData"]["data"]
        _ensure_output_dir(output_file)
        with open(output_file, "wb") as f:
            f.write(base64.b64decode(base64_image))
        return f"Successfully generated image to {output_file}"
    raise Exception("Failed to generate image")


def generate_image(
    prompt_file: str,
    reference_images: list[str],
    output_file: str,
    aspect_ratio: str = "16:9",
) -> str:
    with open(prompt_file, "r", encoding="utf-8") as f:
        prompt = f.read()
    provider = _resolve_provider(
        "IMAGE_GENERATION_PROVIDER", "gemini", bool(os.getenv("GEMINI_API_KEY"))
    )
    if provider in ("volcengine", "volcano", "seedream"):
        return _generate_image_volcengine(
            prompt, reference_images, output_file, aspect_ratio
        )
    if provider == "minimax":
        return _generate_image_minimax(prompt, reference_images, output_file, aspect_ratio)
    if provider in ("gemini", "google"):
        return _generate_image_gemini(prompt, reference_images, output_file, aspect_ratio)
    raise ValueError(
        f"Unknown image provider: {provider!r} "
        "(use 'volcengine', 'gemini', or 'minimax')"
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate images using Volcengine Seedream, Gemini, or MiniMax API"
    )
    parser.add_argument("--prompt-file", required=True, help="Absolute path to JSON prompt file")
    parser.add_argument("--reference-images", nargs="*", default=[],
                        help="Absolute paths to reference images (space-separated)")
    parser.add_argument("--output-file", required=True, help="Output path for generated image")
    parser.add_argument("--aspect-ratio", required=False, default="16:9",
                        help="Aspect ratio of the generated image")
    args = parser.parse_args()

    try:
        print(generate_image(args.prompt_file, args.reference_images,
                             args.output_file, args.aspect_ratio))
    except Exception as e:
        print(f"Error while generating image: {e}")
