import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from skill_loader import FakeResp, load  # noqa: E402

pod = load("podcast-generation")


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for k in [
        "VOLCENGINE_TTS_API_KEY",
        "VOLCENGINE_TTS_APPID",
        "VOLCENGINE_TTS_ACCESS_TOKEN",
        "VOLCENGINE_TTS_CLUSTER",
        "VOLCENGINE_TTS_RESOURCE_ID",
        "VOLCENGINE_TTS_BASE_URL",
        "VOLCENGINE_TTS_VOICE_MALE",
        "VOLCENGINE_TTS_VOICE_FEMALE",
        "MINIMAX_API_KEY",
        "PODCAST_GENERATION_PROVIDER",
        "MINIMAX_API_HOST",
        "MINIMAX_TTS_MODEL",
        "MINIMAX_TTS_VOICE_MALE",
        "MINIMAX_TTS_VOICE_FEMALE",
        "MINIMAX_TTS_MAX_RETRIES",
    ]:
        monkeypatch.delenv(k, raising=False)
    # never actually sleep during backoff in tests
    monkeypatch.setattr(pod.time, "sleep", lambda *_: None)


def test_resolve_prefers_volcengine(monkeypatch):
    monkeypatch.setenv("VOLCENGINE_TTS_APPID", "a")
    monkeypatch.setenv("VOLCENGINE_TTS_ACCESS_TOKEN", "t")
    assert pod._resolve_tts_provider() == "volcengine"


def test_resolve_accepts_volcengine_v3_single_key(monkeypatch):
    monkeypatch.setenv("VOLCENGINE_TTS_API_KEY", "single-key")
    assert pod._resolve_tts_provider() == "volcengine"


def test_resolve_falls_back_to_minimax(monkeypatch):
    monkeypatch.setenv("MINIMAX_API_KEY", "m")
    assert pod._resolve_tts_provider() == "minimax"


def test_resolve_override(monkeypatch):
    monkeypatch.setenv("VOLCENGINE_TTS_APPID", "a")
    monkeypatch.setenv("VOLCENGINE_TTS_ACCESS_TOKEN", "t")
    monkeypatch.setenv("PODCAST_GENERATION_PROVIDER", "minimax")
    assert pod._resolve_tts_provider() == "minimax"


def test_resolve_unknown_raises(monkeypatch):
    monkeypatch.setenv("MINIMAX_API_KEY", "m")
    monkeypatch.setenv("PODCAST_GENERATION_PROVIDER", "openai")
    with pytest.raises(ValueError):
        pod._resolve_tts_provider()


def test_minimax_tts_decodes_hex(monkeypatch):
    monkeypatch.setenv("MINIMAX_API_KEY", "m")
    captured = {}

    def fake_post(url, headers=None, json=None, **kw):
        captured["url"] = url
        captured["json"] = json
        return FakeResp(
            {
                "data": {"audio": b"audiobytes".hex(), "status": 2},
                "base_resp": {"status_code": 0},
            }
        )

    monkeypatch.setattr(pod.requests, "post", fake_post)
    out = pod.text_to_speech_minimax("hello", "male-qn-qingse")
    assert out == b"audiobytes"
    assert captured["url"].endswith("/v1/t2a_v2")
    assert captured["json"]["voice_setting"]["voice_id"] == "male-qn-qingse"
    assert captured["json"]["output_format"] == "hex"


def test_process_line_minimax_voice_mapping(monkeypatch):
    monkeypatch.setenv("MINIMAX_API_KEY", "m")
    seen = {}

    def fake_tts(text, voice_id):
        seen["voice_id"] = voice_id
        return b"x"

    monkeypatch.setattr(pod, "text_to_speech_minimax", fake_tts)
    line = pod.ScriptLine(speaker="female", paragraph="hi")
    idx, audio = pod._process_line((0, line, 1, "minimax"))
    assert audio == b"x"
    assert seen["voice_id"] == "female-tianmei"


def test_generate_podcast_minimax_end_to_end(monkeypatch, tmp_path):
    monkeypatch.setenv("MINIMAX_API_KEY", "m")

    def fake_post(url, headers=None, json=None, **kw):
        return FakeResp(
            {
                "data": {"audio": b"chunk".hex(), "status": 2},
                "base_resp": {"status_code": 0},
            }
        )

    monkeypatch.setattr(pod.requests, "post", fake_post)
    script = tmp_path / "s.json"
    script.write_text(
        '{"title":"T","locale":"en","lines":[{"speaker":"male","paragraph":"a"},'
        '{"speaker":"female","paragraph":"b"}]}',
        encoding="utf-8",
    )
    out = tmp_path / "o.mp3"
    msg = pod.generate_podcast(str(script), str(out), None)
    assert out.read_bytes() == b"chunkchunk"
    assert "Successfully generated podcast" in msg


def test_volcengine_tts_decodes_base64(monkeypatch):
    import base64

    monkeypatch.setenv("VOLCENGINE_TTS_APPID", "a")
    monkeypatch.setenv("VOLCENGINE_TTS_ACCESS_TOKEN", "t")

    def fake_post(url, headers=None, json=None, **kw):
        return FakeResp({"code": 3000, "data": base64.b64encode(b"volcbytes").decode()})

    monkeypatch.setattr(pod.requests, "post", fake_post)
    out = pod.text_to_speech_volcengine("hi", "zh_male_yangguangqingnian_moon_bigtts")
    assert out == b"volcbytes"


def test_volcengine_v3_single_key_decodes_concatenated_stream(monkeypatch):
    import base64
    import json

    monkeypatch.setenv("VOLCENGINE_TTS_API_KEY", "single-key")
    captured = {}
    stream = (
        json.dumps({"code": 0, "data": base64.b64encode(b"hello").decode()})
        + json.dumps({"code": 0, "data": base64.b64encode(b"-world").decode()})
        + json.dumps({"code": 20000000, "message": "OK"})
    ).encode()

    class StreamResp:
        status_code = 200
        headers = {}

        def iter_content(self, chunk_size=None):
            assert chunk_size
            yield stream[:17]
            yield stream[17:]

    def fake_post(url, headers=None, json=None, **kwargs):
        captured.update(
            {"url": url, "headers": headers, "json": json, "kwargs": kwargs}
        )
        return StreamResp()

    monkeypatch.setattr(pod.requests, "post", fake_post)
    metadata = {}
    out = pod.text_to_speech_volcengine(
        "你好", "zh_female_vv_uranus_bigtts", request_metadata=metadata
    )

    assert out == b"hello-world"
    assert captured["url"].endswith("/api/v3/tts/unidirectional")
    assert captured["headers"]["X-Api-Key"] == "single-key"
    assert captured["headers"]["X-Api-Resource-Id"] == "seed-tts-2.0"
    assert captured["json"]["req_params"]["speaker"] == "zh_female_vv_uranus_bigtts"
    assert captured["kwargs"]["stream"] is True
    assert metadata["protocol"] == "v3-http-unidirectional"


def test_volcengine_v3_applies_per_line_performance_controls(monkeypatch):
    import base64
    import hashlib
    import json

    monkeypatch.setenv("VOLCENGINE_TTS_API_KEY", "single-key")
    captured = {}
    stream = (
        json.dumps({"code": 0, "data": base64.b64encode(b"voice").decode()})
        + json.dumps({"code": 20000000, "message": "OK"})
    ).encode()

    class StreamResp:
        status_code = 200
        headers = {}

        def iter_content(self, chunk_size=None):
            yield stream

    def fake_post(url, headers=None, json=None, **kwargs):
        captured.update({"json": json, "headers": headers})
        return StreamResp()

    monkeypatch.setattr(pod.requests, "post", fake_post)
    metadata = {}
    contexts = ["冷静、警觉、利落；句尾短促落下。"]
    out = pod.text_to_speech_volcengine(
        "一道焊缝正在悄悄变宽。",
        "zh_male_m191_uranus_bigtts",
        request_metadata=metadata,
        speech_rate=24,
        loudness_rate=8,
        context_texts=contexts,
    )

    assert out == b"voice"
    req = captured["json"]["req_params"]
    assert req["audio_params"]["speech_rate"] == 24
    assert req["audio_params"]["loudness_rate"] == 8
    assert req["context_texts"] == contexts
    assert metadata["speech_rate"] == 24
    assert metadata["loudness_rate"] == 8
    assert metadata["context_texts_count"] == 1
    assert (
        metadata["context_texts_sha256"]
        == hashlib.sha256(
            json.dumps(contexts, ensure_ascii=False, separators=(",", ":")).encode()
        ).hexdigest()
    )
    assert contexts[0] not in json.dumps(metadata, ensure_ascii=False)


def test_script_lines_validate_and_keep_per_line_volcengine_controls():
    script = pod.Script.from_dict(
        {
            "locale": "zh",
            "lines": [
                {
                    "speaker": "male",
                    "paragraph": "第一句",
                    "voice_type": "zh_male_m191_uranus_bigtts",
                    "speech_rate": 22,
                    "loudness_rate": 10,
                    "context_text": "克制、坚定，不拖尾。",
                }
            ],
        }
    )

    line = script.lines[0]
    assert line.voice_type == "zh_male_m191_uranus_bigtts"
    assert line.speech_rate == 22
    assert line.loudness_rate == 10
    assert line.context_texts == ["克制、坚定，不拖尾。"]

    with pytest.raises(ValueError, match="speech_rate"):
        pod.Script.from_dict(
            {
                "lines": [
                    {
                        "speaker": "male",
                        "paragraph": "越界",
                        "speech_rate": 101,
                    }
                ]
            }
        )


def test_process_line_passes_volcengine_controls_without_raw_receipt_context(
    monkeypatch,
):
    monkeypatch.setenv("VOLCENGINE_TTS_API_KEY", "single-key")
    captured = {}

    def fake_tts(text, voice_type, **kwargs):
        captured.update({"text": text, "voice_type": voice_type, **kwargs})
        metadata = kwargs["request_metadata"]
        metadata.update(
            {
                "request_id": "request-1",
                "voice": voice_type,
                "model": "seed-tts-2.0",
                "speech_rate": kwargs["speech_rate"],
                "loudness_rate": kwargs["loudness_rate"],
                "context_texts_count": len(kwargs["context_texts"]),
                "context_texts_sha256": "a" * 64,
            }
        )
        return b"x"

    monkeypatch.setattr(pod, "text_to_speech_volcengine", fake_tts)
    line = pod.ScriptLine(
        speaker="male",
        paragraph="落锤句",
        voice_type="zh_male_m191_uranus_bigtts",
        speech_rate=20,
        loudness_rate=10,
        context_texts=["克制、坚定、干净落下。"],
    )
    metadata = {}

    _idx, audio = pod._process_line((0, line, 1, "volcengine", metadata))

    assert audio == b"x"
    assert captured["voice_type"] == "zh_male_m191_uranus_bigtts"
    assert captured["speech_rate"] == 20
    assert captured["loudness_rate"] == 10
    assert captured["context_texts"] == ["克制、坚定、干净落下。"]
    assert "克制" not in json.dumps(metadata, ensure_ascii=False)


def test_tts_node_rejects_per_line_controls_outside_volcengine_v3(monkeypatch):
    line = pod.ScriptLine(
        speaker="male",
        paragraph="不应静默丢失控制",
        speech_rate=20,
    )
    script = pod.Script(locale="zh", lines=[line])

    monkeypatch.setenv("MINIMAX_API_KEY", "m")
    with pytest.raises(ValueError, match="Volcengine V3 single-key"):
        pod.tts_node(script)

    monkeypatch.delenv("MINIMAX_API_KEY")
    monkeypatch.setenv("VOLCENGINE_TTS_APPID", "legacy")
    monkeypatch.setenv("VOLCENGINE_TTS_ACCESS_TOKEN", "legacy-token")
    with pytest.raises(ValueError, match="Volcengine V3 single-key"):
        pod.tts_node(script)


def test_volcengine_tts_writes_request_complete_verified_receipt(monkeypatch, tmp_path):
    import base64
    import hashlib
    import json

    monkeypatch.setenv("VOLCENGINE_TTS_APPID", "a")
    monkeypatch.setenv("VOLCENGINE_TTS_ACCESS_TOKEN", "t")
    seen_request_ids = []

    def fake_post(url, headers=None, json=None, **kw):
        seen_request_ids.append(json["request"]["reqid"])
        return FakeResp({"code": 3000, "data": base64.b64encode(b"voice").decode()})

    monkeypatch.setattr(pod.requests, "post", fake_post)
    script = tmp_path / "script.json"
    script.write_text(
        '{"locale":"zh","lines":[{"speaker":"male","paragraph":"第一句"},'
        '{"speaker":"female","paragraph":"第二句"}]}',
        encoding="utf-8",
    )
    output = tmp_path / "voice.mp3"
    receipt_file = tmp_path / "voice.receipt.json"

    pod.generate_podcast(str(script), str(output), None, str(receipt_file))
    receipt = json.loads(receipt_file.read_text(encoding="utf-8"))

    assert receipt["contract_version"] == "personal-ip-media-execution-v1"
    assert receipt["capability"] == "speech_generation"
    assert receipt["provider"] == "volcengine"
    assert receipt["model"] == "volcano_tts"
    assert receipt["parameters"]["line_count"] == 2
    assert set(receipt["parameters"]["request_ids"]) == set(seen_request_ids)
    assert receipt["outputs"][0]["sha256"] == hashlib.sha256(b"voicevoice").hexdigest()
    assert receipt["outputs"][0]["size_bytes"] == len(b"voicevoice")
    serialized = receipt_file.read_text(encoding="utf-8")
    assert "VOLCENGINE_TTS_ACCESS_TOKEN" not in serialized
    assert "第一句" not in serialized
    from deerflow.personal_ip.media_execution import normalize_media_execution_receipt

    normalized = normalize_media_execution_receipt(receipt, entity_type="audio")
    assert normalized["event_type"] == "voice_generated"


def test_volcengine_without_creds_raises(monkeypatch):
    monkeypatch.setenv("PODCAST_GENERATION_PROVIDER", "volcengine")
    script = pod.Script(lines=[pod.ScriptLine("male", "a")])
    with pytest.raises(ValueError):
        pod.tts_node(script)


def test_process_line_minimax_male_and_override(monkeypatch):
    monkeypatch.setenv("MINIMAX_API_KEY", "m")
    seen = []

    def fake_tts(text, voice_id):
        seen.append(voice_id)
        return b"x"

    monkeypatch.setattr(pod, "text_to_speech_minimax", fake_tts)
    male = pod.ScriptLine(speaker="male", paragraph="hi")
    pod._process_line((0, male, 1, "minimax"))
    assert seen[-1] == "male-qn-qingse"
    monkeypatch.setenv("MINIMAX_TTS_VOICE_MALE", "custom-male")
    pod._process_line((0, male, 1, "minimax"))
    assert seen[-1] == "custom-male"


def _seq_post(responses):
    """Return a fake requests.post that yields the given responses in order."""
    calls = {"n": 0}

    def fake_post(*a, **k):
        resp = responses[min(calls["n"], len(responses) - 1)]
        calls["n"] += 1
        return resp

    return fake_post, calls


def test_minimax_retries_on_rate_limit_code(monkeypatch):
    monkeypatch.setenv("MINIMAX_API_KEY", "m")
    fake_post, calls = _seq_post(
        [
            FakeResp({"base_resp": {"status_code": 1002, "status_msg": "rate limit"}}),
            FakeResp({"base_resp": {"status_code": 1039, "status_msg": "tpm limit"}}),
            FakeResp({"data": {"audio": b"ok".hex()}, "base_resp": {"status_code": 0}}),
        ]
    )
    monkeypatch.setattr(pod.requests, "post", fake_post)
    out = pod.text_to_speech_minimax("hi", "male-qn-qingse", max_retries=3)
    assert out == b"ok"
    assert calls["n"] == 3  # two retries then success


def test_minimax_retries_on_http_429(monkeypatch):
    monkeypatch.setenv("MINIMAX_API_KEY", "m")
    fake_post, calls = _seq_post(
        [
            FakeResp({}, status_code=429),
            FakeResp({"data": {"audio": b"ok".hex()}, "base_resp": {"status_code": 0}}),
        ]
    )
    monkeypatch.setattr(pod.requests, "post", fake_post)
    out = pod.text_to_speech_minimax("hi", "male-qn-qingse", max_retries=3)
    assert out == b"ok"
    assert calls["n"] == 2


def test_minimax_no_retry_on_auth_error(monkeypatch):
    monkeypatch.setenv("MINIMAX_API_KEY", "m")
    fake_post, calls = _seq_post(
        [
            FakeResp({"base_resp": {"status_code": 1004, "status_msg": "auth failed"}}),
            FakeResp(
                {"data": {"audio": b"never".hex()}, "base_resp": {"status_code": 0}}
            ),
        ]
    )
    monkeypatch.setattr(pod.requests, "post", fake_post)
    out = pod.text_to_speech_minimax("hi", "male-qn-qingse", max_retries=3)
    assert out is None
    assert calls["n"] == 1  # permanent error: no retry


def test_minimax_gives_up_after_max_retries(monkeypatch):
    monkeypatch.setenv("MINIMAX_API_KEY", "m")
    fake_post, calls = _seq_post(
        [
            FakeResp({"base_resp": {"status_code": 1002, "status_msg": "rate limit"}}),
        ]
    )
    monkeypatch.setattr(pod.requests, "post", fake_post)
    out = pod.text_to_speech_minimax("hi", "male-qn-qingse", max_retries=2)
    assert out is None
    assert calls["n"] == 3  # initial attempt + 2 retries


def test_tts_node_raises_on_partial_failure(monkeypatch):
    monkeypatch.setenv("MINIMAX_API_KEY", "m")
    calls = {"n": 0}

    def fake_tts(text, voice_id, **kw):
        calls["n"] += 1
        return b"x" if calls["n"] == 1 else None

    monkeypatch.setattr(pod, "text_to_speech_minimax", fake_tts)
    script = pod.Script(
        lines=[pod.ScriptLine("male", "a"), pod.ScriptLine("female", "b")]
    )
    with pytest.raises(ValueError) as e:
        pod.tts_node(script)
    assert "2" in str(e.value)  # mentions failed line number 2


def test_tts_node_defaults_to_one_worker_for_minimax(monkeypatch):
    monkeypatch.setenv("MINIMAX_API_KEY", "m")
    captured = {}
    real_executor = pod.ThreadPoolExecutor

    class CapturingExecutor(real_executor):
        def __init__(self, *args, **kwargs):
            captured["max_workers"] = kwargs.get(
                "max_workers", args[0] if args else None
            )
            super().__init__(*args, **kwargs)

    def fake_tts(text, voice_id):
        return b"x"

    monkeypatch.setattr(pod, "ThreadPoolExecutor", CapturingExecutor)
    monkeypatch.setattr(pod, "text_to_speech_minimax", fake_tts)
    script = pod.Script(
        lines=[pod.ScriptLine("male", "a"), pod.ScriptLine("female", "b")]
    )

    assert pod.tts_node(script) == [b"x", b"x"]
    assert captured["max_workers"] == 1


def test_tts_node_keeps_four_worker_default_for_volcengine(monkeypatch):
    monkeypatch.setenv("VOLCENGINE_TTS_APPID", "a")
    monkeypatch.setenv("VOLCENGINE_TTS_ACCESS_TOKEN", "t")
    captured = {}
    real_executor = pod.ThreadPoolExecutor

    class CapturingExecutor(real_executor):
        def __init__(self, *args, **kwargs):
            captured["max_workers"] = kwargs.get(
                "max_workers", args[0] if args else None
            )
            super().__init__(*args, **kwargs)

    def fake_tts(text, voice_type):
        return b"x"

    monkeypatch.setattr(pod, "ThreadPoolExecutor", CapturingExecutor)
    monkeypatch.setattr(pod, "text_to_speech_volcengine", fake_tts)
    script = pod.Script(
        lines=[pod.ScriptLine("male", "a"), pod.ScriptLine("female", "b")]
    )

    assert pod.tts_node(script) == [b"x", b"x"]
    assert captured["max_workers"] == 4
