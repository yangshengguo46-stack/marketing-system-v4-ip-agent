from __future__ import annotations

import importlib.util
import io
import json
import shutil
import sys
import uuid
from pathlib import Path

import pytest
import yaml
from PIL import Image


def _load_module():
    path = Path(__file__).resolve().parents[2] / "scripts" / "ip_agent_m2_method_attribution.py"
    spec = importlib.util.spec_from_file_location("ip_agent_m2_method_attribution", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


e3 = _load_module()


def _write_yaml(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(value, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def _fixture_repo(tmp_path: Path) -> tuple[Path, Path, str, tuple[str, ...]]:
    root = (tmp_path / "repo").resolve()
    product = root / "product/defaults/agents/ip-agent"
    product.mkdir(parents=True)
    _write_yaml(
        product / "config.yaml",
        {
            "name": "ip-agent",
            "description": "clean IP Agent",
            "skills": [],
            "tool_allowlist": list(e3.m2.BASE_TOOL_ALLOWLIST),
            "memory_enabled": False,
        },
    )
    (product / "SOUL.md").write_text("clean soul\n", encoding="utf-8")

    real_root = Path(__file__).resolve().parents[2]
    shutil.copytree(
        real_root / e3._RESEARCH_RELATIVE,
        root / e3._RESEARCH_RELATIVE,
    )
    for skill_name in e3.METHOD_SOURCE_SKILLS:
        skill = root / "skills/public" / skill_name / "SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text(f"---\nname: {skill_name}\n---\n", encoding="utf-8")

    state = root / e3.m2.TEST_STATE_RELATIVE
    state.mkdir(parents=True)
    marker = {
        "schema_version": e3.m2.TEST_MODE_SCHEMA_VERSION,
        "root": str(root),
        "state_dir": str(state),
        "profile": e3.m2.TEST_PROFILE_EVIDENCE,
    }
    (state / e3.m2.TEST_MARKER_NAME).write_text(json.dumps(marker), encoding="utf-8")
    (state / e3.m2.TEST_EXTENSIONS_CONFIG_NAME).write_text(
        json.dumps(
            {
                "middlewares": [],
                "mcpInterceptors": [e3.m2.EVIDENCE_PAID_CALL_INTERCEPTOR],
                "mcpInterceptorsRequired": True,
                "mcpServers": {
                    e3.m2.EVIDENCE_MCP_SERVER_NAME: {
                        "required": True,
                        "tools": {
                            "collect_douyin_benchmark_account": {
                                "required": True
                            },
                            "inspect_reference_videos": {"required": True},
                        },
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    _write_yaml(
        state / "config.yaml",
        {
            "models": [
                {
                    "name": "fixture-model",
                    "display_name": "fixture",
                    "use": "deerflow.models.patched_deepseek:PatchedChatDeepSeek",
                    "model": "fixture-model",
                    "api_key": "$VOLCENGINE_API_KEY",
                    "api_base": "https://example.invalid/api/v3",
                    "supports_thinking": True,
                    "supports_vision": True,
                }
            ]
        },
    )

    thread_id = str(uuid.UUID(int=1))
    works = [
        {
            "work_id": index,
            "ownership_evidence": "api_author_match",
            "title": f"work {index}",
        }
        for index in range(1, 13)
    ]
    account = {
        "contract_version": e3.EXPECTED_ACCOUNT_CONTRACT,
        "operation_status": "ok",
        "source": {"input_ref": e3.EXPECTED_SOURCE_REF},
        "profile": {"display_name": e3.EXPECTED_PROFILE_NAME},
        "works": works,
        "coverage": {"public_work_inventory": "partial"},
    }
    items = []
    image_blocks = []
    image_digests = []
    for index in range(1, 4):
        content_sha = str(index) * 64
        relative = f"outputs/reference-video-evidence/{content_sha[:24]}/contact-sheet.jpg"
        host = state / "users/default/threads" / thread_id / "user-data" / relative
        host.parent.mkdir(parents=True, exist_ok=True)
        image_buffer = io.BytesIO()
        Image.new("RGB", (16, 9), color=(index * 40, 20, 80)).save(
            image_buffer,
            format="JPEG",
        )
        image_bytes = image_buffer.getvalue()
        host.write_bytes(image_bytes)
        image_digests.append(e3._sha256_bytes(image_bytes))
        items.append(
            {
                "status": "ok",
                "source": {
                    "content_sha256": content_sha,
                    "public_metadata": {
                        "id": index,
                        "uploader": e3.EXPECTED_PROFILE_NAME,
                    },
                },
                "contact_sheet_ref": relative,
                "coverage": {
                    "sampled_frames": "completed",
                    "asr": "unavailable_provider_not_configured",
                    "ocr": "unavailable_provider_not_configured",
                },
            }
        )
        image_blocks.append(
            {
                "type": "image",
                "url": "/mnt/user-data/" + relative,
                "mime_type": "image/jpeg",
            }
        )
    videos = {
        "contract_version": e3.EXPECTED_VIDEO_CONTRACT,
        "operation_status": "ok",
        "completed_count": 3,
        "items": items,
    }
    payload = {
        "schema_version": e3.m2.M2_REPLAY_SCHEMA_VERSION,
        "groups": [
            {
                "status": "success",
                "thread_id": thread_id,
                "tool_results": [
                    {
                        "name": "ip_evidence_collect_douyin_benchmark_account",
                        "status": "success",
                        "content": [{"type": "text", "text": account}],
                    },
                    {
                        "name": "ip_evidence_inspect_reference_videos",
                        "status": "success",
                        "content": [
                            {"type": "text", "text": videos},
                            *image_blocks,
                        ],
                    },
                ],
            }
        ],
    }
    source = state / "evaluations/m2/source/results.json"
    source.parent.mkdir(parents=True)
    source.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return root, source, e3._sha256_file(source), tuple(image_digests)


def test_load_frozen_evidence_seals_two_contracts_and_three_images(tmp_path: Path):
    root, source, digest, image_digests = _fixture_repo(tmp_path)

    evidence = e3.load_frozen_evidence(
        root,
        source,
        expected_source_sha256=digest,
        expected_contact_sheet_sha256=image_digests,
    )

    assert evidence.account["profile"]["display_name"] == e3.EXPECTED_PROFILE_NAME
    assert evidence.videos["completed_count"] == 3
    assert len(evidence.images) == 3
    assert len({image.sha256 for image in evidence.images}) == 3
    assert len(evidence.bundle_sha256) == 64


def test_frozen_evidence_rejects_source_digest_drift(tmp_path: Path):
    root, source, _digest, _image_digests = _fixture_repo(tmp_path)

    with pytest.raises(RuntimeError, match="digest mismatch"):
        e3.load_frozen_evidence(
            root,
            source,
            expected_source_sha256="0" * 64,
        )


def test_frozen_evidence_rejects_missing_contact_sheet(tmp_path: Path):
    root, source, digest, image_digests = _fixture_repo(tmp_path)
    state = root / e3.m2.TEST_STATE_RELATIVE
    image = next(state.glob("users/default/threads/**/contact-sheet.jpg"))
    image.unlink()

    with pytest.raises(FileNotFoundError, match="contact sheet is missing"):
        e3.load_frozen_evidence(
            root,
            source,
            expected_source_sha256=digest,
            expected_contact_sheet_sha256=image_digests,
        )


def test_frozen_evidence_rejects_contact_sheet_digest_drift(tmp_path: Path):
    root, source, digest, image_digests = _fixture_repo(tmp_path)
    state = root / e3.m2.TEST_STATE_RELATIVE
    image = next(state.glob("users/default/threads/**/contact-sheet.jpg"))
    image.write_bytes(image.read_bytes() + b"drift")

    with pytest.raises(RuntimeError, match="digest mismatch"):
        e3.load_frozen_evidence(
            root,
            source,
            expected_source_sha256=digest,
            expected_contact_sheet_sha256=image_digests,
        )


@pytest.mark.parametrize(
    "value",
    (
        "Bearer abcdefghijklmnop",
        "aaaabbbb.ccccdddd.eeeeffff",
        "https://example.invalid/?access_token=secret",
    ),
)
def test_frozen_evidence_rejects_credential_values_under_safe_keys(value: str):
    with pytest.raises(RuntimeError, match="credential"):
        e3._assert_no_sensitive_evidence({"visible_title": value})


def test_method_assets_have_one_common_contract_and_six_sources(tmp_path: Path):
    root, _source, _digest, _image_digests = _fixture_repo(tmp_path)

    assets = e3.load_method_assets(root)

    assert set(assets.source_skill_sha256) == set(e3.METHOD_SOURCE_SKILLS)
    assert not set(assets.source_skill_sha256) & set(e3.EXCLUDED_METHOD_SKILLS)
    assert assets.common_contract.strip() in assets.skill_bodies["placebo"]
    assert assets.common_contract.strip() in assets.skill_bodies["method"]
    assert e3.EXPERIMENT_SKILL_NAME in assets.skill_bodies["placebo"]
    assert e3.EXPERIMENT_SKILL_NAME in assets.skill_bodies["method"]
    assert assets.skill_bodies["placebo"] != assets.skill_bodies["method"]


def test_directorial_assets_replace_only_the_treatment(tmp_path: Path):
    root, _source, _digest, _image_digests = _fixture_repo(tmp_path)
    legacy = e3.load_method_assets(root)
    directorial = e3.load_method_assets(
        root,
        root
        / "product/research/ip-agent/m2/directorial-causality/experiment.json",
    )

    assert directorial.experiment_id == "m2-e4-directorial-causality-v1"
    assert directorial.source_skill_sha256 == {}
    assert directorial.skill_bodies["placebo"] == legacy.skill_bodies["placebo"]
    assert directorial.skill_bodies["method"] != legacy.skill_bodies["method"]
    assert "ip-agent-m2-semantic-bridge-v1" in directorial.skill_bodies["method"]
    assert "远距离结构同构" in directorial.skill_bodies["method"]


def test_frozen_request_uses_one_slash_prefixed_user_message_and_no_view_tool(
    tmp_path: Path,
):
    root, source, digest, image_digests = _fixture_repo(tmp_path)
    evidence = e3.load_frozen_evidence(
        root,
        source,
        expected_source_sha256=digest,
        expected_contact_sheet_sha256=image_digests,
    )

    messages, receipt = e3.build_frozen_request(evidence)

    assert len(messages) == 1
    assert messages[0]["role"] == "user"
    assert [block["type"] for block in messages[0]["content"]] == [
        "text",
        "image_url",
        "image_url",
        "image_url",
    ]
    assert messages[0]["content"][0]["text"].startswith(f"/{e3.EXPERIMENT_SKILL_NAME} ")
    assert "view_image" not in json.dumps(messages, ensure_ascii=False)
    assert "base64" not in json.dumps(receipt)
    assert receipt["evidence_bundle_sha256"] == evidence.bundle_sha256

    original_hash = receipt["request_sha256"]
    evidence.images[0].host_path.write_bytes(b"replaced after sealing")
    _messages_again, receipt_again = e3.build_frozen_request(evidence)
    assert receipt_again["request_sha256"] == original_hash


def test_checkpoint_projection_binds_the_actual_slash_user_message(tmp_path: Path):
    root, source, digest, image_digests = _fixture_repo(tmp_path)
    evidence = e3.load_frozen_evidence(
        root,
        source,
        expected_source_sha256=digest,
        expected_contact_sheet_sha256=image_digests,
    )
    messages, receipt = e3.build_frozen_request(evidence)
    run_id = str(uuid.uuid4())
    values = {
        "messages": [
            {
                "type": "human",
                "content": message["content"],
                "additional_kwargs": {"run_id": run_id},
            }
            for message in messages
        ]
    }

    projection = e3._checkpoint_request_projection(values, run_id=run_id)

    assert e3._sha256_bytes(e3._canonical_json_bytes(projection)) == receipt["request_sha256"]


def test_temporary_surface_is_zero_tool_and_fully_removed(tmp_path: Path):
    root, _source, _digest, _image_digests = _fixture_repo(tmp_path)
    body = e3.load_method_assets(root).skill_bodies["placebo"]
    state = root / e3.m2.TEST_STATE_RELATIVE

    with e3.temporary_experiment_surface(root, initial_skill_body=body) as surface:
        config = yaml.safe_load(surface.agent_config_path.read_text(encoding="utf-8"))
        assert config["skills"] == [e3.EXPERIMENT_SKILL_NAME]
        assert config["tool_allowlist"] == []
        assert config["memory_enabled"] is False
        assert surface.skill_path.read_text(encoding="utf-8") == body
        assert surface.marker_path.is_file()

    assert not (state / e3.DIRTY_MARKER_NAME).exists()
    assert not e3._surface_paths(state).agent_dir.exists()
    assert not e3._surface_paths(state).skill_dir.exists()


def test_temporary_surface_recovers_its_own_atomic_temp_file(tmp_path: Path):
    root, _source, _digest, _image_digests = _fixture_repo(tmp_path)
    body = e3.load_method_assets(root).skill_bodies["placebo"]
    state = root / e3.m2.TEST_STATE_RELATIVE

    with e3.temporary_experiment_surface(root, initial_skill_body=body) as surface:
        temporary = surface.skill_path.with_name(".SKILL.md.tmp")
        temporary.write_text(body, encoding="utf-8")
        temporary.chmod(0o600)

    assert not e3._surface_paths(state).skill_dir.exists()


def test_temporary_surface_refuses_to_delete_modified_file(tmp_path: Path):
    root, _source, _digest, _image_digests = _fixture_repo(tmp_path)
    body = e3.load_method_assets(root).skill_bodies["placebo"]
    state = root / e3.m2.TEST_STATE_RELATIVE

    with pytest.raises(RuntimeError, match="refusing to delete modified"):
        with e3.temporary_experiment_surface(root, initial_skill_body=body) as surface:
            surface.skill_path.write_text("externally replaced", encoding="utf-8")

    assert (state / e3.DIRTY_MARKER_NAME).exists()


def test_temporary_surface_cleans_a_partial_setup_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root, _source, _digest, _image_digests = _fixture_repo(tmp_path)
    body = e3.load_method_assets(root).skill_bodies["placebo"]
    state = root / e3.m2.TEST_STATE_RELATIVE
    original = e3.m2._write_private_text

    def fail_on_soul(path: Path, value: str) -> None:
        if path.name == "SOUL.md":
            raise OSError("simulated setup failure")
        original(path, value)

    monkeypatch.setattr(e3.m2, "_write_private_text", fail_on_soul)

    with pytest.raises(OSError, match="simulated setup failure"):
        with e3.temporary_experiment_surface(root, initial_skill_body=body):
            pass

    assert not (state / e3.DIRTY_MARKER_NAME).exists()
    assert not e3._surface_paths(state).agent_dir.exists()
    assert not e3._surface_paths(state).skill_dir.exists()


def test_recover_refuses_while_an_experiment_lock_is_active(tmp_path: Path):
    root, _source, _digest, _image_digests = _fixture_repo(tmp_path)
    body = e3.load_method_assets(root).skill_bodies["placebo"]
    state = root / e3.m2.TEST_STATE_RELATIVE

    with e3.temporary_experiment_surface(root, initial_skill_body=body):
        with e3.m2._exclusive_replay_lock(state):
            with pytest.raises(RuntimeError, match="another M2 replay"):
                e3.recover_experiment(root)


def test_method_model_config_freezes_temperature_and_output_limit(tmp_path: Path):
    root, _source, _digest, _image_digests = _fixture_repo(tmp_path)

    path, digest = e3.prepare_method_model_config(root)
    config = yaml.safe_load(path.read_text(encoding="utf-8"))

    assert e3._sha256_file(path) == digest
    assert len(config["models"]) == 1
    model = config["models"][0]
    assert model["name"] == e3.DEFAULT_MODEL_NAME
    assert model["model"] == e3.PROVIDER_MODEL_NAME
    assert model["temperature"] == 0
    assert model["max_tokens"] == e3.FROZEN_MAX_TOKENS


def test_graph_superstep_limit_does_not_replace_the_one_call_validator():
    assert e3.RECURSION_LIMIT == e3.m2.M2_RECURSION_LIMIT == 100
    result = _valid_arm_result("a" * 64, "b" * 64, "c" * 64)
    result["usage"]["llm_call_count"] = 2

    errors = e3.validate_arm_result(
        result,
        requested_model=e3.DEFAULT_MODEL_NAME,
        expected_skill_hash="a" * 64,
        expected_skill_path=(f"/mnt/skills/custom/{e3.EXPERIMENT_SKILL_NAME}/SKILL.md"),
        request_sha256="b" * 64,
        evidence_bundle_sha256="c" * 64,
        model_config_sha256="e" * 64,
        effective_model_receipt=result["effective_model_receipt_before"],
    )

    assert "run usage does not report exactly one LLM call" in errors


def _valid_arm_result(skill_hash: str, request_hash: str, bundle_hash: str) -> dict:
    model_receipt = {
        "name": e3.DEFAULT_MODEL_NAME,
        "model": e3.PROVIDER_MODEL_NAME,
        "supports_thinking": True,
        "supports_vision": True,
        "temperature": e3.FROZEN_TEMPERATURE,
        "max_tokens": e3.FROZEN_MAX_TOKENS,
        "effective_config_sha256": "d" * 64,
    }
    return {
        "status": "success",
        "errors": [],
        "request_sha256": request_hash,
        "checkpoint_request_sha256": request_hash,
        "evidence_bundle_sha256": bundle_hash,
        "model_config_sha256_before": "e" * 64,
        "model_config_sha256_after": "e" * 64,
        "effective_model_receipt_before": model_receipt,
        "effective_model_receipt_after": model_receipt,
        "runtime_metadata": {
            "agent_name": e3.EXPERIMENT_AGENT_NAME,
            "available_skills": [e3.EXPERIMENT_SKILL_NAME],
            "indexed_skill_names": [e3.EXPERIMENT_SKILL_NAME],
            "tool_allowlist": [],
            "assembled_tool_names": [],
            "memory_enabled": False,
            "thinking_enabled": True,
            "is_plan_mode": False,
            "subagent_enabled": False,
            "model_name": e3.DEFAULT_MODEL_NAME,
        },
        "skill_activations": [
            {
                "name": "SkillActivationMiddleware",
                "action": "activate",
                "changes": {
                    "skill_name": e3.EXPERIMENT_SKILL_NAME,
                    "category": "custom",
                    "path": f"/mnt/skills/custom/{e3.EXPERIMENT_SKILL_NAME}/SKILL.md",
                    "content_hash": skill_hash,
                },
            }
        ],
        "llm_calls": [
            {
                "caller": "lead_agent",
                "finish_reason": "stop",
                "model_name": "doubao-seed-evolving-latest-version",
            }
        ],
        "usage": {"llm_call_count": 1},
        "tool_calls": [],
        "tool_results": [],
        "model_tool_bindings": [],
        "final_answer": "完整方案",
    }


def test_arm_validation_requires_one_activation_one_llm_and_zero_tools():
    result = _valid_arm_result("a" * 64, "b" * 64, "c" * 64)

    errors = e3.validate_arm_result(
        result,
        requested_model=e3.DEFAULT_MODEL_NAME,
        expected_skill_hash="a" * 64,
        expected_skill_path=f"/mnt/skills/custom/{e3.EXPERIMENT_SKILL_NAME}/SKILL.md",
        request_sha256="b" * 64,
        evidence_bundle_sha256="c" * 64,
        model_config_sha256="e" * 64,
        effective_model_receipt=result["effective_model_receipt_before"],
    )

    assert errors == []
    result["tool_calls"] = [{"name": "view_image"}]
    assert "method attribution run used a tool" in e3.validate_arm_result(
        result,
        requested_model=e3.DEFAULT_MODEL_NAME,
        expected_skill_hash="a" * 64,
        expected_skill_path=f"/mnt/skills/custom/{e3.EXPERIMENT_SKILL_NAME}/SKILL.md",
        request_sha256="b" * 64,
        evidence_bundle_sha256="c" * 64,
        model_config_sha256="e" * 64,
        effective_model_receipt=result["effective_model_receipt_before"],
    )


def test_event_summary_reads_provider_metadata_from_ai_message_content():
    events = [
        {
            "event_type": "run.start",
            "metadata": {
                "agent_name": e3.EXPERIMENT_AGENT_NAME,
                "available_skills": [e3.EXPERIMENT_SKILL_NAME],
                "indexed_skill_names": [e3.EXPERIMENT_SKILL_NAME],
                "tool_allowlist": [],
                "assembled_tool_names": [],
                "memory_enabled": False,
                "thinking_enabled": True,
                "is_plan_mode": False,
                "subagent_enabled": False,
                "model_name": e3.DEFAULT_MODEL_NAME,
            },
        },
        {
            "event_type": "llm.ai.response",
            "metadata": {
                "llm_call_index": 1,
                "caller": "lead_agent",
                "usage": {"total_tokens": 10},
            },
            "content": {
                "response_metadata": {
                    "finish_reason": "stop",
                    "model_name": "doubao-seed-evolving-latest-version",
                    "model_provider": "deepseek",
                    "system_fingerprint": None,
                }
            },
        },
    ]

    _runtime, calls, _bindings, _activations = e3._summarize_events(events)

    assert calls[0]["finish_reason"] == "stop"
    assert calls[0]["model_name"] == "doubao-seed-evolving-latest-version"
    assert calls[0]["system_fingerprint"] is None


def test_blind_packet_hides_arm_mapping(tmp_path: Path):
    root, source, digest, image_digests = _fixture_repo(tmp_path)
    evidence = e3.load_frozen_evidence(
        root,
        source,
        expected_source_sha256=digest,
        expected_contact_sheet_sha256=image_digests,
    )
    rubric, _raw, _rubric_sha = e3._load_rubric(
        e3.load_method_assets(root).rubric_path
    )
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    first = output_dir / "placebo-output.txt"
    second = output_dir / "method-output.txt"
    first.write_text("输出甲", encoding="utf-8")
    second.write_text("输出乙", encoding="utf-8")
    payload = {
        "arms": [
            {
                "arm": "placebo",
                "output": {
                    "path": str(first),
                    "sha256": e3._sha256_file(first),
                },
            },
            {
                "arm": "method",
                "output": {
                    "path": str(second),
                    "sha256": e3._sha256_file(second),
                },
            },
        ]
    }

    artifacts = e3._write_blind_packet(
        destination=output_dir,
        payload=payload,
        evidence=evidence,
        rubric=rubric,
    )

    blind = json.loads(Path(artifacts["blind_review_path"]).read_text(encoding="utf-8"))
    assert set(blind["outputs"]) == {"X", "Y"}
    assert "mapping" not in blind
    assert artifacts["status"] == "awaiting_blind_reviews"
    assert "unblinding_path" not in artifacts
    assert not (output_dir / "unblinding.json").exists()


def test_rubric_freezes_95_content_points_plus_5_objective_points(tmp_path: Path):
    root, _source, _digest, _image_digests = _fixture_repo(tmp_path)

    rubric, _raw, digest = e3._load_rubric(
        e3.load_method_assets(root).rubric_path
    )

    assert sum(item["max_score"] for item in rubric["content_dimensions"]) == 95
    assert rubric["objective_tool_efficiency"]["max_score"] == 5
    assert len(digest) == 64


def _blind_review(
    blind: dict,
    *,
    blind_sha256: str,
    reviewer_id: str,
    x_score: int,
    y_score: int,
) -> dict:
    dimensions = blind["rubric"]["content_dimensions"]

    def output(label: str, total_target: int) -> dict:
        remaining = total_target
        scores = {}
        for index, dimension in enumerate(dimensions):
            maximum = dimension["max_score"]
            score = min(maximum, remaining) if index < len(dimensions) - 1 else remaining
            remaining -= score
            scores[dimension["id"]] = {
                "score": score,
                "reason": "依据输出原文逐项评分",
                "quotes": [],
            }
        return {
            "output_sha256": blind["outputs"][label]["sha256"],
            "dimension_scores": scores,
            "direct_failures": [],
            "total_content_score": total_target,
        }

    return {
        "schema_version": e3.REVIEW_SCHEMA_VERSION,
        "blind_review_sha256": blind_sha256,
        "reviewer_id": reviewer_id,
        "attestation": "scored_without_arm_mapping",
        "outputs": {"X": output("X", x_score), "Y": output("Y", y_score)},
    }


def test_review_aggregation_counts_one_rule_once_per_reviewer():
    rubric = {"content_dimensions": [{"id": "evidence_accuracy"}]}

    def output(failures: list[dict]) -> dict:
        return {
            "dimension_scores": {"evidence_accuracy": {"score": 10}},
            "direct_failures": failures,
        }

    duplicate_from_one_reviewer = [
        {"rule_id": "F7", "quote": "例子一", "reason": "同一规则"},
        {"rule_id": "F7", "quote": "例子二", "reason": "同一规则"},
    ]
    reviews = [
        {"outputs": {"X": output(duplicate_from_one_reviewer), "Y": output([])}},
        {"outputs": {"X": output([]), "Y": output([])}},
    ]

    aggregated = e3._aggregate_reviews(reviews, rubric)

    assert aggregated["X"]["direct_failures"] == []
    reviews[1]["outputs"]["X"]["direct_failures"] = [{"rule_id": "F7", "quote": "独立审查", "reason": "第二票"}]
    aggregated = e3._aggregate_reviews(reviews, rubric)
    assert aggregated["X"]["direct_failures"] == ["F7"]


def test_unblinding_is_created_only_after_two_bound_reviews(tmp_path: Path):
    root, source, digest, image_digests = _fixture_repo(tmp_path)
    evidence = e3.load_frozen_evidence(
        root,
        source,
        expected_source_sha256=digest,
        expected_contact_sheet_sha256=image_digests,
    )
    rubric, rubric_raw, rubric_sha256 = e3._load_rubric(
        e3.load_method_assets(root).rubric_path
    )
    state = root / e3.m2.TEST_STATE_RELATIVE
    destination = state / "evaluations/m2-method-attribution/test-run"
    destination.mkdir(parents=True)
    arms = []
    for arm, text in (("placebo", "输出甲"), ("method", "输出乙")):
        path = destination / f"{arm}-output.txt"
        path.write_text(text, encoding="utf-8")
        arms.append(
            {
                "arm": arm,
                "output": {"path": str(path), "sha256": e3._sha256_file(path)},
            }
        )
    artifacts = e3._write_blind_packet(
        destination=destination,
        payload={"arms": arms},
        evidence=evidence,
        rubric=rubric,
    )
    rubric_path = destination / "rubric.json"
    e3.m2._write_private_bytes(rubric_path, rubric_raw)
    e3.m2._write_private_text(rubric_path.with_suffix(".json.sha256"), rubric_sha256 + "\n")
    results_path = destination / "results.json"
    e3._write_with_digest(
        results_path,
        {
            "schema_version": e3.SCHEMA_VERSION,
            "instrument_valid": True,
            "arms": arms,
            "blind_artifacts": artifacts,
            "rubric": {"path": str(rubric_path), "sha256": rubric_sha256},
        },
    )
    blind_path = Path(artifacts["blind_review_path"])
    blind = json.loads(blind_path.read_text(encoding="utf-8"))
    reviews = []
    for index in (1, 2):
        review_path = tmp_path / f"incoming-review-{index}.json"
        review_path.write_text(
            json.dumps(
                _blind_review(
                    blind,
                    blind_sha256=artifacts["blind_review_sha256"],
                    reviewer_id=f"reviewer-{index}",
                    x_score=70,
                    y_score=50,
                ),
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        reviews.append(review_path)

    assert not (destination / "unblinding.json").exists()
    unblinding_path = e3.unblind_experiment(
        root,
        results_path=results_path,
        review_paths=reviews,
    )

    unblinding = json.loads(unblinding_path.read_text(encoding="utf-8"))
    assert set(unblinding["mapping"]) == {"X", "Y"}
    assert set(unblinding["mapping"].values()) == set(e3.ARMS)
    assert set(unblinding["scores"]) == set(e3.ARMS)
    assert (destination / "review-seal.json.sha256").is_file()
