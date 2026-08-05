import json
import os
import shutil
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.mediakit_source import (  # noqa: E402
    EXPECTED_MEDIAKIT_CAPABILITIES,
    MEDIAKIT_COMMIT,
    binary_path,
    media_environment,
    parse_capability_catalog,
    validate_source,
)


def test_vendored_mediakit_source_is_complete_and_has_no_prebuilt_binary() -> None:
    root = Path(__file__).resolve().parents[1]

    source = validate_source(root)

    assert MEDIAKIT_COMMIT == "279e5bb97e97c6875ae2c6891c2c3fa9a43f39c0"
    assert (source / "go.mod").is_file()
    assert not (source / "mediakit").exists()
    manifest = json.loads(
        (source / "VENDORED_VERSION.json").read_text(encoding="utf-8")
    )
    assert manifest["upstream_tree"] == "e9b40b73ef691e7bbf5a38c9af4e06d699d62beb"
    assert manifest["retained_source_file_count"] == 119
    assert manifest["capability_count"] == 40
    assert manifest["license_review_status"] == "upstream-conflict-open"


def test_vendored_mediakit_source_rejects_any_untracked_tree_change(
    tmp_path: Path,
) -> None:
    root = Path(__file__).resolve().parents[1]
    copied = tmp_path / "third_party" / "volcengine" / "mediakit-cli"
    copied.parent.mkdir(parents=True)
    shutil.copytree(root / "third_party" / "volcengine" / "mediakit-cli", copied)
    (copied / "unexpected.txt").write_text("drift", encoding="utf-8")

    with pytest.raises(RuntimeError, match="file count mismatch"):
        validate_source(tmp_path)


def test_expected_runtime_catalog_matches_the_pinned_cli_help() -> None:
    root = Path(__file__).resolve().parents[1]
    binary = binary_path(root)
    if not binary.is_file():
        pytest.skip("project-local MediaKit CLI is not built")
    import subprocess

    result = subprocess.run(
        [str(binary), "--help-full"],
        capture_output=True,
        text=True,
        check=True,
        env=media_environment(root),
    )

    assert parse_capability_catalog(result.stdout) == EXPECTED_MEDIAKIT_CAPABILITIES
    assert sum(len(tools) for tools in EXPECTED_MEDIAKIT_CAPABILITIES.values()) == 40


def test_product_policy_promotes_default_agent_evidence_mediakit_capabilities() -> None:
    root = Path(__file__).resolve().parents[1]
    policy = yaml.safe_load(
        (root / "product" / "volcengine" / "capabilities.yaml").read_text(
            encoding="utf-8"
        )
    )["capabilities"]["media_editing_and_understanding"]

    catalog = {
        domain: tuple(tools)
        for domain, tools in policy["capability_catalog"]["domains"].items()
    }
    assert catalog == EXPECTED_MEDIAKIT_CAPABILITIES

    mode_tools = [
        tool
        for tools in policy["capability_catalog"]["modes"].values()
        for tool in tools
    ]
    expected_tools = {
        tool for tools in EXPECTED_MEDIAKIT_CAPABILITIES.values() for tool in tools
    }
    assert len(mode_tools) == len(set(mode_tools)) == 40
    assert set(mode_tools) == expected_tools
    assert policy["agent_direct_access"] is False
    assert policy["upstream_skill_runtime_status"] == "quarantined-reference-only"
    promoted = [
        "probe-video-metadata",
        "asr-subtitles",
        "video-ocr",
        "segment-scenes",
        "analyze-video-storyline",
    ]
    assert policy["production_admission"]["promoted_capabilities"] == promoted
    assert policy["production_admission"]["key_alone_enables_cloud"] is True
    assert (
        policy["production_admission"]["per_capability_paid_admission_required"]
        is False
    )
    for capability in promoted:
        override = policy["capability_lifecycle"]["current_overrides"][capability]
        assert override["state"] == "product_promoted"
        assert override["exposure"] == "default-ip-agent-evidence-mcp"
    assert (
        policy["capability_catalog"]["marketing_100_plus_is_runtime_contract"] is False
    )
    assert (
        policy["known_upstream_gaps"]["output_contract"][
            "cli_schema_is_sufficient_for_cloud_semantics"
        ]
        is False
    )

    product_catalog = policy["official_product_catalog"]
    assert product_catalog["total"] == 63
    assert product_catalog["counting_basis"] == (
        "grouped-items-in-the-official-multimedia-toolset-overview-not-the-sidebar-document-count"
    )
    assert {
        group: len(items) for group, items in product_catalog["groups"].items()
    } == {
        "video": 25,
        "image": 13,
        "editing": 20,
        "audio": 4,
        "large_model": 1,
    }
    assert sum(len(items) for items in product_catalog["groups"].values()) == 63
    assert product_catalog["separately_documented_not-yet-in-primary-directory"] == [
        "semantic-segmentation",
        "video-face-swap",
    ]

    video_chat = policy["separate_provider_surfaces"]["video_understanding_chat"]
    assert video_chat["counted_in_pinned_cli_commands"] is False
    assert video_chat["lifecycle_state"] == "real_sample_verified"
    assert video_chat["exposure"] == "none"
    assert (
        video_chat["implementation_status"] == "isolated-adapter-real-sample-verified"
    )
    assert video_chat["authentication"] == {
        "requires": ["volcengine-ark-api-key", "mediakit-api-key"],
        "credential_sources": {
            "volcengine-ark-api-key": "VOLCENGINE_API_KEY",
            "mediakit-api-key": "MEDIAKIT_API_KEY",
        },
        "wire_format": "composite-bearer-with-slash",
        "product_control": (
            "compose-server-side-and-never-persist-or-expose-the-composite-value"
        ),
    }
    assert video_chat["model_selection"] == {
        "mode": "caller-supplied-explicit-ark-model-id",
        "q157_canary_model_id": "doubao-seed-2-0-pro-260215",
        "provider_auto_routing": False,
    }
    assert video_chat["preprocessing"]["fps"] == {
        "default": 1,
        "minimum": 0.01,
        "maximum": 5,
    }
    assert video_chat["audio_understanding_supported"] is False
    assert video_chat["input"] == {
        "modalities": ["text", "video-url"],
        "maximum_video_url_size_gb": 5,
        "base64_and_files_api": {
            "supported_by_this_mediakit_endpoint": False,
            "separate_contract": "volcengine-ark-direct-video-understanding",
            "maximum_size_gb_not_inherited": True,
        },
    }
    assert video_chat["pricing"] == {
        "mediakit_video-understanding-processing-currently-free": True,
        "ark_input-and-output-tokens-billed-separately": True,
        "ark-price-document": "https://docs.volcengine.com/docs/82379/1544106?lang=zh",
        "price-status": "public-tariff-estimate-not-provider-quote-or-invoice",
        "fixed-model-id": "doubao-seed-2-0-pro-260215",
        "model-family": "doubao-seed-2.0-pro",
        "billing-mode": "online-standard",
        "service-tier": "default",
        "prompt-tier-selects-whole-request-rate": True,
        "uncached-prompt-cny-per-million-by-upper-inclusive-token-bound": {
            32768: 3.2,
            131072: 4.8,
            262144: 9.6,
        },
        "completion-cny-per-million-by-upper-inclusive-prompt-token-bound": {
            32768: 16,
            131072: 24,
            262144: 48,
        },
        "reasoning-accounting": "included-once-in-provider-completion-tokens",
        "cache-assumption": (
            "all-prompt-tokens-uncached-until-explicit-cache-is-proven"
        ),
    }
    assert video_chat["real_sample_validation"]["first-clear-time-error-seconds"] == 0.2
    assert video_chat["real_sample_validation"]["fixed-profile-repeatability"] == (
        "passed-six-of-six-core-fields-on-two-official-fixture-runs"
    )
    assert (
        video_chat["real_sample_validation"]["evidence_mcp_integration"]
        == "not-yet-complete"
    )
    assert video_chat["real_sample_validation"]["stable-canonical-douyin-work-url"] == (
        "failed-provider-operator-error-500-with-real-credential"
    )
    assert video_chat["real_sample_validation"]["mediakit-uploaded-file-id"] == (
        "upload-succeeded-chat-failed-provider-500"
    )
    assert video_chat["real_sample_validation"]["stable-provider-input"] == (
        "passed-remux-temporary-https-on-one-exact-douyin-work"
    )
    assert video_chat["real_sample_validation"]["selected-ingress"] == (
        "mediakit-remux-temporary-https-public-reference-canary"
    )
    assert video_chat["real_sample_validation"]["ingress-state"] == (
        "protocol-canary-passed-not-yet-evidence-mcp-integrated"
    )
    assert video_chat["real_sample_validation"]["managed-remux-https"] == {
        "adapter": "volcengine-mediakit-remux-https-ingress-v1",
        "input": "sealed-local-source-to-mediakit-uri",
        "output": "provider-temporary-https",
        "output-ttl-seconds-observed": 86399,
        "source-to-candidate-binding": "audio-and-video-packet-payload-equivalent",
        "source-duration-seconds": 70.867,
        "candidate-duration-seconds": 70.867,
        "chat-outcome": "success",
        "chat-total-tokens": 41313,
        "pricing-document": "https://docs.volcengine.com/docs/6448/2486473?lang=zh",
        "published-remux-cny-per-output-minute": 0.007,
        "q157-public-tariff-estimate-cny": 0.008268,
        "actual-provider-cny-returned": False,
        "runtime-url-persisted": False,
        "immediate-delete-or-revoke-receipt": "unavailable",
        "public-reference-scope": "protocol-canary-passed",
        "private-or-confidential-scope": "not-approved",
        "product-promoted": False,
    }
    assert video_chat["real_sample_validation"]["native-upload-authentication"] == (
        "mediakit-api-key-only-confirmed"
    )
    assert video_chat["real_sample_validation"]["cross-service-tos-authorization"] == (
        "operator-confirmed-enabled"
    )
    assert video_chat["real_sample_validation"]["rejected-diagnosis"] == (
        "missing-tos-authorization-or-tos-credentials-for-native-upload"
    )
    assert video_chat["output"]["timestamped-evidence-guaranteed"] is False
    assert video_chat["semantic_boundary"] == [
        "output-is-provider-model-inference-not-source-fact",
        "omitted-or-misread-events-remain-possible",
        "no-account-or-work-identity-authority",
        "no-virality-causality-or-ip-direction-authority",
        "reconcile-material-claims-with-sealed-frames-asr-ocr-and-human-ground-truth",
    ]

    smart_strategy = policy["separate_provider_surfaces"][
        "video_understanding_smart_strategy"
    ]
    assert smart_strategy["counted_in_pinned_cli_commands"] is False
    assert smart_strategy["lifecycle_state"] == "paid-canary-external-blocked"
    assert smart_strategy["exposure"] == "none"
    assert smart_strategy["input"]["protocols"] == [
        "http",
        "https",
        "mediakit",
        "vod",
        "tos",
    ]
    assert smart_strategy["asynchronous_execution"][
        "recoverable-encrypted-task-handle"
    ] == ("standalone-canary-wired-not-product-promoted")
    assert smart_strategy["q157_paid_canary"]["provider-safe-error-code"] == (
        "AbilityProcessingError"
    )
    assert smart_strategy["q157_paid_canary"]["provider-safe-error-type"] == (
        "InternalServerError"
    )
    assert smart_strategy["routing"]["manual_fps"]["minimum"] == 0.2
    assert smart_strategy["routing"]["maximum_frames"] == 1000
    assert smart_strategy["pricing"]["mediakit_cny_per_input_minute"] == 0.01

    semantic_segmentation = policy["separate_provider_surfaces"][
        "semantic_segmentation"
    ]
    assert semantic_segmentation["lifecycle_state"] == "contract_verified"
    assert semantic_segmentation["output"]["timestamps_only"] is True
    assert (
        semantic_segmentation["output"]["segment_transcript_or_semantic_label_returned"]
        is False
    )
    assert semantic_segmentation["pricing"]["cny_per_input_minute"] == 0.03

    vibe = policy["separate_provider_surfaces"]["vibe_editing"]
    assert vibe["lifecycle_state"] == "real_sample_verified"
    assert vibe["output"]["editable_timeline_returned"] is False
    assert vibe["output"]["edl_returned"] is False
    assert vibe["preview_editor"]["web_sdk_status"] == "future"

    drama_script = policy["separate_provider_surfaces"]["drama_script_restoration"]
    assert drama_script["output"]["creative-script-generation"] is False
    assert "advertising" in drama_script["unsupported_inputs"]
    assert drama_script["pricing"]["cny_per_input_minute"] == 3

    replacement = policy["replacement_boundary"]
    assert replacement["video-use"]["relationship"] == "provider-beneath-method"
    assert (
        replacement["hyperframes"]["relationship"]
        == "complementary-programmatic-renderer"
    )
    assert replacement["vibe-editing"]["forbidden_role"] == [
        "sole-editable-project-authority",
        "sole-deterministic-final-renderer",
        "evidence-or-causal-creative-authority",
    ]
    assert policy["known_upstream_gaps"]["local_trim_precision"][
        "requested_window_real_ab_seconds"
    ] == {
        "start": 1,
        "end": 3,
        "expected_duration": 2,
        "observed_duration": 2.166016,
    }
    assert policy["known_upstream_gaps"]["async_recovery"] == {
        "paid-call-recovery-repository-implemented": True,
        "adapter-submit-query-wired": False,
        "provider-task-reference-is-durably-persisted-by-current-product-path": False,
        "risk": "timeout-or-process-loss-can-still-leave-a-billable-task-unrecoverable-before-adapter-wiring",
        "product_control": "no-new-product-path-paid-promotion-until-submit-query-uses-the-recovery-repository",
    }


def test_mediakit_real_canary_receipt_preserves_limits_and_hashes() -> None:
    root = Path(__file__).resolve().parents[1]
    receipt_path = (
        root
        / "product"
        / "research"
        / "ip-agent"
        / "mediakit"
        / "2026-08-03-capability-canaries.yaml"
    )
    receipt_text = receipt_path.read_text(encoding="utf-8")
    for private_identifier_digest in (
        "provider_request_id_sha256:",
        "file_id_sha256:",
        "provider_request_sha256:",
        "client_token_sha256:",
        "provider_file_id_sha256:",
        "provider_task_id_sha256:",
        "runtime_url_sha256:",
    ):
        assert private_identifier_digest not in receipt_text
    receipt = yaml.safe_load(receipt_text)

    assert receipt["contract"] == "ip-agent-mediakit-capability-canary-v1"
    assert receipt["video_understanding_chat"]["mechanical_verdict"] == {
        "categorical_observations": "pass_on_this_fixture",
        "first-clear-time_error_seconds": 0.2,
        "exact-edit-boundary": "fail",
        "conclusion": "useful semantic observation; not an exact timeline authority",
    }
    adapter = receipt["video_understanding_chat"]["product_adapter_validation"]
    assert adapter["unit_gate"]["result"] == "13-passed"
    assert (
        adapter["official_fixture_repeatability"]["important_field_consistency"]
        == "6-of-6"
    )
    assert (
        adapter["real_douyin_account_sample"]["verified_account_display_name"]
        == "云沐荟足道官方号"
    )
    assert (
        adapter["real_douyin_account_sample"]["successful_operator_retry"]["usage"][
            "total_tokens"
        ]
        == 40693
    )
    assert adapter["real_douyin_account_sample"]["stable_canonical_work_url_probe"] == {
        "provider_input": "https://www.douyin.com/video/7658501922794432731",
        "credential_source": "test-mode-0600-secret-file",
        "outcome": "provider-operator-error",
        "http_status": 500,
        "safe_error_code": "PROVIDER_OPERATORERROR",
        "billing_outcome": "unknown",
        "automatic_retry": False,
        "conclusion": "canonical-douyin-work-page-did-not-produce-an-accepted-chat-video-input",
    }
    assert adapter["real_douyin_account_sample"]["mediakit_uploaded_file_id_probe"] == {
        "canary_correlation_id": "b4f5db0a-3ad9-4faa-989c-78ee5d62fdac",
        "sealed_source_sha256_verified": True,
        "upload_target_issued": True,
        "sealed_bytes_uploaded": True,
        "provider_input_scheme": "mediakit",
        "provider_file_id_observed": True,
        "provider_identifier_digest_persisted_in_public_research_ledger": False,
        "chat_outcome": "provider-error",
        "http_status": 500,
        "billing_outcome": "unknown",
        "automatic_retry": False,
        "request_sha256": "156be5c1728653e2db26f9f4680bcf610e2574885886f21e3051c1d5278b1f1f",
        "provider_delete_receipt_available": False,
        "conclusion": "uploaded-file-id-path-not-yet-usable-for-video-understanding-chat",
    }
    remux = adapter["real_douyin_account_sample"]["managed_remux_https_ingress_probe"]
    assert remux["unit_gate"] == {
        "command": "uv run pytest -q tests/test_ip_agent_mediakit_remux_ingress.py",
        "result": "24-passed",
        "joint_mediakit_regression": "64-passed",
    }
    assert (
        remux["source_sha256"]
        == "8e098c16f3634f27bbd8ca6bd30e41ed5c9816d6ff4654922d115198a4ec10fc"
    )
    assert remux["runtime_url_persisted"] is False
    assert remux["remux_result"] == {
        "container_format": "MP4",
        "candidate_sha256": "7c744b4e637b203c487d7cfaf02941126fe573008311e9915996e0358bcad66a",
        "candidate_size_bytes": 13437038,
        "duration_seconds": 70.867,
        "duration_delta_seconds": 0,
        "whole_file_byte_identical": False,
        "elementary_stream_payload_equivalent": True,
        "stream_index_order_changed": True,
        "conclusion": "audio-and-video-packet-payloads-preserved-container-bytes-differ",
    }
    assert remux["temporary_https"]["observed_ttl_seconds"] == 86399
    assert remux["chat_result"]["outcome"] == "success"
    assert remux["chat_result"]["usage"]["total_tokens"] == 41313
    assert remux["lifecycle"] == {
        "mediakit_input_retention": "provider-auto-cleanup-after-30-days",
        "temporary_https_expiry_verified": True,
        "immediate_delete_or_revoke_receipt": "unavailable",
        "public_reference_video_use": "protocol-canary-passed-with-declared-retention",
        "private_or_confidential_upload_use": "not-approved",
    }
    assert remux["product_promoted"] is False
    assert adapter["real_douyin_account_sample"]["next_ingress_gate"] == {
        "state": "protocol-canary-passed-integration-required",
        "confirmed": [
            "mediakit-cross-service-tos-authorization-enabled",
            "native-upload-uses-mediakit-api-key-only",
            "native-upload-returned-file-id",
            "remux-produced-chat-readable-temporary-https",
            "remux-preserved-audio-and-video-packet-payloads",
            "video-understanding-chat-succeeded-on-remux-https",
        ],
        "rejected_diagnosis": [
            "tos-not-authorized",
            "mediakit-native-upload-requires-dedicated-bucket",
            "mediakit-native-upload-requires-tos-ak-sk",
        ],
        "current_blocker": "remux-path-not-yet-wired-to-paid-recovery-evidence-mcp-or-isolated-agent",
        "next_canary": [
            "wire-remux-submit-query-through-paid-call-recovery",
            "expose-derived-source-binding-through-evidence-mcp-without-runtime-url",
            "run-two-additional-content-diverse-reference-videos",
            "run-one-isolated-agent-replay",
        ],
        "optional_fallback": {
            "provider": "volcengine-tos",
            "mode": "dedicated-private-bucket-with-short-lived-read-only-https",
            "activate_only_if": "private-or-confidential-input-requires-immediate-delete-control",
        },
    }
    assert adapter["real_douyin_account_sample"]["first_attempt"] == {
        "read_timeout_seconds": 90,
        "outcome": "provider-transport-unknown",
        "automatic_retry": False,
        "billing_outcome": "unknown",
    }
    assert receipt["vibe_exact_trim"]["output"]["duration_seconds"] == 2
    assert (
        receipt["vibe_exact_trim"]["mechanical_verdict"][
            "editable_timeline_or_edl_returned"
        ]
        is False
    )
    assert (
        receipt["local_trim_precision_ab"]["mediakit"]["output_duration_seconds"]
        == 2.166016
    )
    assert (
        receipt["local_trim_precision_ab"]["exact_reference"]["output_duration_seconds"]
        == 2
    )


def test_binary_path_is_project_local_and_platform_specific(tmp_path: Path) -> None:
    assert binary_path(tmp_path, platform_name="darwin") == (
        tmp_path / ".deer-flow" / "bin" / "mediakit-cli"
    )
    assert binary_path(tmp_path, platform_name="win32") == (
        tmp_path / ".deer-flow" / "bin" / "mediakit-cli.exe"
    )


def test_media_environment_prefers_project_local_binaries(tmp_path: Path) -> None:
    path = media_environment(tmp_path)["PATH"].split(os.pathsep)

    assert path[:2] == [
        str(tmp_path / ".deer-flow" / "toolchains" / "ffmpeg" / "bin"),
        str(tmp_path / ".deer-flow" / "bin"),
    ]
