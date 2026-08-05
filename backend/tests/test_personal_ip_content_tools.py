from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from langchain_core.utils.function_calling import convert_to_openai_tool

from deerflow.config.app_config import AppConfig
from deerflow.config.database_config import DatabaseConfig
from deerflow.persistence.engine import close_engine, get_session_factory, init_engine_from_config
from deerflow.persistence.personal_ip_content import PersonalIPContentRepository
from deerflow.persistence.personal_ip_subjects import PersonalIPSubjectRepository
from deerflow.personal_ip.content_contracts import BreakdownDraft, ClaimBasis, WriterBrainRequest
from deerflow.personal_ip.runtime import PersonalIPRuntimeServices, configure_personal_ip_runtime
from deerflow.personal_ip.writer_brain import WriterBrainService as RealWriterBrainService
from deerflow.tools.builtins import personal_ip_content_tools as content_tools_module
from deerflow.tools.builtins.personal_ip_content_tools import (
    _ip_content_start_production,
    _ip_content_write,
    ip_content_save_breakdown_tool,
    ip_content_write_tool,
)


def _mcn_writer_tool_payload() -> dict:
    """A caller-owned v2 decision with no server-bound fields."""

    return {
        "work_title": "TikTok MCN 官方账号起号首条",
        "entry_route": "zero_start",
        "objective": {
            "desired_change": "让目标创作者认识机构并愿意了解加入条件",
            "audience_situation": "正在评估是否加入机构的 TikTok 创作者",
            "business_context": "先建立品牌认知，其次吸引合适创作者申请加入",
            "constraints": ["不承诺必然涨粉或收入", "没有提供的机构权益保持未知"],
        },
        "editorial_program": {
            "title": "机构品牌与创作者招募主线",
            "mission": {
                "goal_priority": ["recognition", "conversion", "trust"],
                "time_horizon": "near_term",
                "deadline_or_window": "首个三十天",
                "desired_action": "记住机构并了解加入条件",
                "success_signal": "出现符合条件的创作者咨询或申请",
                "non_goals": ["不以泛流量代替合格申请"],
                "rationale": "官方账号先建立清晰机构认知，再承接招募。",
            },
            "audience": {
                "situation": "正在评估机构合作价值与边界的 TikTok 创作者",
                "state": "hypothesized",
                "uncertainties": ["目标国家、创作者类型和当前阶段尚未确认"],
            },
            "attribution": {
                "primary_carrier": {
                    "kind": "organization",
                    "identity": "该 TikTok MCN 机构",
                },
                "supporting_carriers": [],
                "desired_association": "合作边界清楚、运营判断可核验",
                "attribution_guard": "老板出镜也不把机构官方账号静默改成老板个人 IP",
                "rationale": "用户明确要做机构官方账号。",
            },
            "differentiation": {
                "statement": "以公开合作边界和真实运营判断作为待验证差异方向",
                "contrast": "只喊资源多和欢迎加入的泛化机构宣传",
                "basis": [
                    {
                        "claim": "机构真实权益、案例和目标市场尚待用户补充",
                        "state": "hypothesized",
                    }
                ],
                "reason_to_choose": "能帮助创作者判断是否适配",
                "reason_to_believe": "后续只使用用户提供或可核验的制度与案例",
                "sacrifice": "不做保证结果的招募承诺",
                "test_signal": "目标创作者提出具体合作边界问题或提交合格申请",
                "uncertainties": ["差异化尚未由发布结果验证"],
            },
        },
        "direction": {
            "premise": "先把机构是谁、适合谁和不承诺什么讲清楚",
            "audience_situation": "担心机构只会画饼、正在筛选合作方的创作者",
            "core_tension": "机构需要招募，但不能用空泛承诺换取低质量申请",
            "content_promise": "说明官方账号的两个目标及后续将公开的合作信息",
            "creative_route": "机构代表事实口述加清晰行动入口",
            "rationale": "现有事实不足以做案例证明，先走解释路线。",
            "truth_mode": "factual",
            "route_kind": "explanation",
            "claim_basis": [
                {
                    "claim": "用户是一家 TikTok MCN 机构的老板",
                    "state": "user_asserted",
                    "usage": "attributed_fact",
                },
                {
                    "claim": "官方账号第一诉求是建立品牌",
                    "state": "user_asserted",
                    "usage": "attributed_fact",
                },
                {
                    "claim": "官方账号第二诉求是吸引创作者加入机构",
                    "state": "user_asserted",
                    "usage": "attributed_fact",
                },
                {
                    "claim": "机构具体权益、案例、目标市场和招募条件尚未提供",
                    "state": "unknown",
                    "usage": "excluded",
                },
            ],
        },
        "production_translation": {
            "form": "spoken",
            "constraints": ["官方账号竖屏口播"],
            "delivery_notes": ["具体权益和招募条件未知时不得补造"],
        },
    }


def _model_visible_write_request_schema() -> dict:
    tool_schema = convert_to_openai_tool(ip_content_write_tool)
    return tool_schema["function"]["parameters"]["properties"]["request"]


def _nullable_object(schema: dict) -> dict:
    return next(option for option in schema["anyOf"] if option.get("type") == "object")


class _FakeWriterModel:
    def __init__(self, outputs: list[str]) -> None:
        self._outputs = list(outputs)

    async def __call__(self, **_kwargs) -> str:
        return self._outputs.pop(0)


def test_content_tool_contract_makes_evidence_refs_discoverable() -> None:
    save_description = ip_content_save_breakdown_tool.description
    write_description = ip_content_write_tool.description
    for description in (save_description, write_description):
        assert "metadata.request_id" in description
        assert "evidence://{request_id}/items/{item_index}/{token}" in description
        assert "media-metadata" in description
        assert "provider/asr" in description
        assert "request_id#field" in description
        assert "absence of music or sound effects" in description

    assert "omit" in write_description and "request.breakdown" in write_description
    breakdown_schema = BreakdownDraft.model_json_schema()
    assert "metadata.request_id" in breakdown_schema["properties"]["evidence_request_id"]["description"]
    assert "first item" in breakdown_schema["properties"]["evidence_item_index"]["description"]
    assert "coverage/asr" in breakdown_schema["$defs"]["BreakdownObservation"]["properties"]["evidence_refs"]["description"]
    claim_schema = ClaimBasis.model_json_schema()
    assert "provider/asr" in claim_schema["properties"]["evidence_refs"]["description"]


def test_write_tool_model_schema_hides_server_bound_fields() -> None:
    request_schema = _model_visible_write_request_schema()
    direction_properties = request_schema["properties"]["direction"]["properties"]
    story_seed_schema = _nullable_object(request_schema["properties"]["story_engine_seed"])

    assert "contract_version" not in direction_properties
    assert "editorial_program_digest" not in direction_properties
    assert "semantic_route_digest" not in story_seed_schema["properties"]


def test_write_tool_model_schema_requires_v2_route_kind() -> None:
    request_schema = _model_visible_write_request_schema()
    direction_schema = request_schema["properties"]["direction"]

    assert "route_kind" in direction_schema["required"]


def test_write_tool_model_contract_converts_mcn_payload_to_v2_request() -> None:
    parsed = ip_content_write_tool.tool_call_schema.model_validate({"request": _mcn_writer_tool_payload()})

    assert isinstance(parsed.request, WriterBrainRequest)
    assert parsed.request.direction.contract_version == "personal-ip-direction-v2"
    assert parsed.request.direction.route_kind == "explanation"
    assert parsed.request.direction.editorial_program_digest is None
    assert parsed.request.story_engine_seed is None


@pytest.mark.asyncio
async def test_content_write_success_returns_all_saved_version_numbers(
    tmp_path,
    monkeypatch,
) -> None:
    await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(tmp_path)))
    sf = get_session_factory()
    assert sf is not None
    content = PersonalIPContentRepository(sf)
    subjects = PersonalIPSubjectRepository(sf)
    fake_model = _FakeWriterModel(
        [
            "我们是一家 TikTok MCN 机构。这个官方账号先建立品牌，再邀请创作者了解加入。",
            '{"supported":true,"unsupported_spans":[],"reason_codes":[],"semantic_route_supported":true,"semantic_route_digest":null}',
        ]
    )
    monkeypatch.setattr(
        content_tools_module,
        "WriterBrainService",
        lambda repository, *, subjects: RealWriterBrainService(
            repository,
            subjects=subjects,
            model_runner=fake_model,
        ),
    )
    configure_personal_ip_runtime(
        PersonalIPRuntimeServices(
            connections=SimpleNamespace(),
            metrics=SimpleNamespace(),
            publish_receipts=SimpleNamespace(),
            content=content,
            subjects=subjects,
        )
    )
    payload = _mcn_writer_tool_payload()
    payload["direction"]["contract_version"] = "personal-ip-direction-v2"
    request = WriterBrainRequest.model_validate(payload)
    runtime = SimpleNamespace(
        context={
            "user_id": "owner-1",
            "run_id": "run-mcn-1",
            "thread_id": "thread-mcn-1",
            "app_config": AppConfig.model_construct(),
        },
        tool_call_id="tool-mcn-1",
        state={"messages": []},
    )

    try:
        result = json.loads(await _ip_content_write(runtime, request))

        assert result["operation_status"] == "ok"
        assert result["editorial_program_version_number"] == 1
        assert result["direction_version_number"] == 1
        assert result["script_version_number"] == 1
    finally:
        configure_personal_ip_runtime(None)
        await close_engine()


@pytest.mark.asyncio
async def test_content_production_tool_only_starts_from_linked_script_version() -> None:
    begin = AsyncMock(
        return_value={
            "id": "video-production-1",
            "contract_version": "personal-ip-video-production-v2",
            "content_work_id": "content-work-1",
            "script_version_id": "script-1",
            "status": "draft",
        }
    )
    configure_personal_ip_runtime(
        PersonalIPRuntimeServices(
            connections=SimpleNamespace(),
            metrics=SimpleNamespace(),
            publish_receipts=SimpleNamespace(),
            video_productions=SimpleNamespace(begin=begin),
        )
    )
    runtime = SimpleNamespace(
        context={
            "user_id": "owner-1",
            "run_id": "run-1",
            "thread_id": "thread-1",
        },
        tool_call_id="tool-1",
    )

    result = json.loads(
        await _ip_content_start_production(
            runtime,
            content_work_id="content-work-1",
            script_version_id="script-1",
            title="制作第一版",
            production_mode="faceless_material",
            target_account_ids=[],
            delivery_spec={"aspect_ratio": "9:16"},
            provider_policy={},
            budget={},
        )
    )

    assert result["operation_status"] == "ok"
    kwargs = begin.await_args.kwargs
    assert kwargs["owner_user_id"] == "owner-1"
    assert kwargs["operation_key"] == "run-1:tool-1"
    assert kwargs["thread_id"] == "thread-1"
    assert kwargs["content_work_id"] == "content-work-1"
    assert kwargs["script_version_id"] == "script-1"
    assert kwargs["source_kind"] == "script"
    assert kwargs["source"] == {}
    assert kwargs["subject_id"] is None

    rejected = json.loads(
        await _ip_content_start_production(
            runtime,
            content_work_id="",
            script_version_id="",
            title="不应创建",
            production_mode="faceless_material",
            target_account_ids=[],
            delivery_spec={},
            provider_policy={},
            budget={},
        )
    )
    assert rejected["status"] == "error"
    assert "are required" in rejected["message"]
    assert begin.await_count == 1
