"""Privacy boundary shared by the UI-TARS tool and local operator."""

from __future__ import annotations

import io
import re
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit, urlunsplit

_SECRET_FIELD = re.compile(
    r"(?:authorization|cookie|credential|password|passwd|profile[_-]?path|refresh[_-]?token|secret|session|token)",
    re.IGNORECASE,
)
_SECRET_VALUE_PATTERNS = (
    re.compile(r"(?i)\b(?:bearer|basic)\s+[A-Za-z0-9._~+/=-]{8,}"),
    re.compile(r"(?i)\b(?:api[_-]?key|password|passwd|secret|token)\s*[:=]\s*\S+"),
    re.compile(r"\b(?:sk|ak)-[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"\b(?=[A-Za-z0-9_-]{32,}\b)(?=[A-Za-z0-9_-]*[A-Z])(?=[A-Za-z0-9_-]*[a-z])(?=[A-Za-z0-9_-]*\d)[A-Za-z0-9_-]+\b"),
    re.compile(r"(?i)(?:^|[/\\])(?:chrome|chromium|edge|firefox)[/\\].*(?:profile|user data)"),
)
_HIGH_IMPACT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("publish_or_send", re.compile(r"(?i)\b(?:publish|post|send|submit|upload)\b|发布|发送|投稿|提交")),
    ("delete", re.compile(r"(?i)\b(?:delete|remove|erase|trash)\b|删除|移除|清空")),
    ("settings_change", re.compile(r"(?i)\b(?:change|modify|disable|enable|install|uninstall)\b.{0,30}\b(?:setting|permission|account|system)\b|修改.{0,12}(?:设置|权限|系统)|安装|卸载")),
    ("payment", re.compile(r"(?i)\b(?:buy|checkout|pay|purchase|subscribe|charge)\b|购买|付款|支付|订阅|充值")),
)


def sanitize_text(value: object, *, max_chars: int = 600) -> str:
    """Return bounded text with common credentials and URL queries removed."""
    text = str(value or "").replace("\x00", " ").strip()
    for pattern in _SECRET_VALUE_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    words: list[str] = []
    for word in text.split():
        if "://" in word:
            try:
                parsed = urlsplit(word)
                if parsed.scheme and parsed.netloc:
                    word = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
            except ValueError:
                word = "[REDACTED_URL]"
        words.append(word)
    text = " ".join(words)
    return text[:max_chars]


def contains_secret_material(value: object) -> bool:
    """Fail closed when an instruction appears to contain credential material."""
    text = str(value or "")
    return any(pattern.search(text) for pattern in _SECRET_VALUE_PATTERNS)


def high_impact_categories(intent: str) -> list[str]:
    """Classify operations that must cross DeerFlow's existing approval boundary."""
    return [category for category, pattern in _HIGH_IMPACT_PATTERNS if pattern.search(intent)]


def sanitize_mapping(value: Any) -> Any:
    """Recursively remove credential-bearing fields before model/log exposure."""
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for raw_key, raw_value in value.items():
            key = str(raw_key)
            if _SECRET_FIELD.search(key):
                continue
            result[key] = sanitize_mapping(raw_value)
        return result
    if isinstance(value, list):
        return [sanitize_mapping(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize_mapping(item) for item in value]
    if isinstance(value, str):
        return sanitize_text(value, max_chars=2_000)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return sanitize_text(value)


def pixelate_png(raw_png: bytes, *, block_size: int) -> tuple[bytes, int, int]:
    """Remove image metadata and make screen text unreadable before model use."""
    from PIL import Image

    with Image.open(io.BytesIO(raw_png)) as source:
        image = source.convert("RGB")
        width, height = image.size
        if width < 1 or height < 1:
            raise ValueError("desktop screenshot has invalid dimensions")
        small = image.resize(
            (max(1, width // block_size), max(1, height // block_size)),
            resample=Image.Resampling.BOX,
        )
        transformed = small.resize((width, height), resample=Image.Resampling.NEAREST)
        output = io.BytesIO()
        transformed.save(output, format="PNG", optimize=True)
        return output.getvalue(), width, height
