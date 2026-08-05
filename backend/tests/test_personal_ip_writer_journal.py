from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult
from langchain_core.utils.function_calling import convert_to_openai_tool

from deerflow.config.app_config import AppConfig
from deerflow.config.database_config import DatabaseConfig
from deerflow.persistence.engine import close_engine, get_session_factory, init_engine_from_config
from deerflow.persistence.personal_ip_content import PersonalIPContentRepository
from deerflow.personal_ip.content_contracts import (
    SemanticCausalRoute,
    WriterBrainRequest,
    semantic_causal_route_digest,
)
from deerflow.personal_ip.runtime import PersonalIPRuntimeServices, configure_personal_ip_runtime
from deerflow.personal_ip.writer_brain import WriterBrainService
from deerflow.runtime.events.store.memory import MemoryRunEventStore
from deerflow.runtime.journal import RunJournal
from deerflow.tools.builtins import personal_ip_content_tools
from deerflow.tools.builtins.personal_ip_content_tools import _ip_content_write, ip_content_write_tool
from deerflow.utils import oneshot_llm

_RAW_SECRET = "raw-provider-secret-must-not-leak"
_DIRECT_BOUNDARY_OK = '{"supported":true,"unsupported_spans":[],"reason_codes":[],"semantic_route_supported":true,"semantic_route_digest":null}'
_SEMANTIC_ROUTE = {
    "association_path": ["轻松表达", "关系里的回避", "认真表达"],
    "human_theme": "认真表达",
    "causal_pattern": "旧策略让误解加深，换招后必须承担失去认可的代价",
    "episode_tension": "继续讨人喜欢与冒险说真话不能兼得",
    "mission_bridge": "让观众记住认真表达的关系议题",
    "attribution_guard": "不把真实经历塞进虚构人物",
}
_SEMANTIC_DIGEST = semantic_causal_route_digest(
    SemanticCausalRoute.model_validate(_SEMANTIC_ROUTE),
)
_SEMANTIC_BOUNDARY_OK = json.dumps(
    {
        "supported": True,
        "unsupported_spans": [],
        "reason_codes": [],
        "semantic_route_supported": True,
        "semantic_route_digest": _SEMANTIC_DIGEST,
    },
    ensure_ascii=False,
    separators=(",", ":"),
)


class _PrivateRunJournal(BaseCallbackHandler):
    """A callback identity that must stay on the runtime-only path."""


class _RecordingModelRunner:
    def __init__(self, outputs: list[str]) -> None:
        self._outputs = list(outputs)
        self.calls: list[dict] = []

    async def __call__(self, **kwargs) -> str:
        self.calls.append(kwargs)
        return self._outputs.pop(0)


def _program(*, semantic: bool) -> dict:
    program = {
        "title": "认真表达主线" if semantic else "真实进展主线",
        "mission": {
            "goal_priority": ["recognition"] if semantic else ["trust"],
            "time_horizon": "long_term" if semantic else "near_term",
            "deadline_or_window": "未来一年" if semantic else "本月",
            "desired_action": "记住认真表达议题" if semantic else "理解真实进展",
            "success_signal": "观众能复述议题" if semantic else "出现基于事实的询问",
            "non_goals": ["不编造事实"],
            "rationale": "先固定本轮结果，再选择内容路线。",
        },
        "audience": {
            "situation": "关系中回避认真表达的人" if semantic else "尚不了解真实进展的人",
            "state": "hypothesized",
            "uncertainties": ["尚无发布后观察"],
        },
        "attribution": {
            "primary_carrier": {"kind": "person", "identity": "真实本人"},
            "supporting_carriers": [],
            "desired_association": "能说清两难" if semantic else "只说可核对事实",
            "attribution_guard": "真实本人不是虚构故事主人公",
            "rationale": "归因给人的判断，不归因给虚构事件。",
        },
        "differentiation": {
            "statement": "从具体两难切入" if semantic else "用真实进展而非效果承诺",
            "contrast": "泛化情绪口号" if semantic else "空泛结果宣传",
            "basis": [{"claim": "本轮目标由用户给出", "state": "user_asserted"}],
            "reason_to_choose": "具体且可复述",
            "reason_to_believe": "只使用明确提供的材料",
            "sacrifice": "不补造履历或效果",
            "test_signal": "观众能准确复述本轮承诺",
            "uncertainties": ["差异仍待真实发布验证"],
        },
    }
    if semantic:
        program["editorial_spine"] = {
            "source_concepts": ["轻松表达"],
            "human_theme": "认真表达",
            "recurring_question": "一个人何时愿意放弃讨喜而说真话",
            "boundary": "不虚构真实本人经历",
        }
    return program


def _direct_request() -> WriterBrainRequest:
    return WriterBrainRequest.model_validate(
        {
            "work_title": "一次真实进展",
            "entry_route": "zero_start",
            "objective": {"desired_change": "让观众理解已经发生的一步"},
            "editorial_program": _program(semantic=False),
            "direction": {
                "contract_version": "personal-ip-direction-v2",
                "premise": "从已经发生的进展开始",
                "audience_situation": "尚不了解进展的人",
                "core_tension": "说明进展但不夸大结果",
                "content_promise": "只呈现已发生的事实",
                "creative_route": "事实口述",
                "rationale": "现有事实足以成立。",
                "truth_mode": "factual",
                "route_kind": "demonstration",
                "claim_basis": [
                    {
                        "claim": "今天完成了第一次公开演示",
                        "state": "user_asserted",
                        "usage": "attributed_fact",
                    }
                ],
            },
        }
    )


def _semantic_request() -> WriterBrainRequest:
    return WriterBrainRequest.model_validate(
        {
            "work_title": "第一次认真说话",
            "entry_route": "zero_start",
            "objective": {"desired_change": "让观众愿意认真表达一次"},
            "editorial_program": _program(semantic=True),
            "direction": {
                "contract_version": "personal-ip-direction-v2",
                "premise": "玩笑成为真话的障碍",
                "audience_situation": "习惯用轻松逃避认真表达的人",
                "core_tension": "被喜欢与被理解不能继续靠同一旧策略获得",
                "content_promise": "看见一次说真话如何改变关系",
                "creative_route": "纯虚构关系故事",
                "rationale": "方向理由留在总编辑决策层。",
                "truth_mode": "fictional",
                "route_kind": "semantic_story",
                "semantic_route": _SEMANTIC_ROUTE,
            },
            "story_engine_seed": {
                "recurring_conflict": "一个人总用玩笑维持关系，真正求助时仍被当成玩笑",
                "desire_a": "继续讨人喜欢",
                "desire_b": "冒险说出真话",
                "relationship_at_stake": "一段靠轻松表象维系的友情",
                "causal_pattern": _SEMANTIC_ROUTE["causal_pattern"],
                "tone": "克制",
            },
        }
    )


@pytest.mark.asyncio
async def test_run_oneshot_llm_forwards_private_callbacks_to_the_model(monkeypatch) -> None:
    internal_message = AIMessage(
        content="内部脚本",
        usage_metadata={"input_tokens": 2, "output_tokens": 3, "total_tokens": 5},
    )
    model = SimpleNamespace(ainvoke=AsyncMock(return_value=internal_message))
    monkeypatch.setattr(oneshot_llm, "create_chat_model", lambda **_kwargs: model)
    event_store = MemoryRunEventStore()
    journal = RunJournal("run-1", "thread-1", event_store, flush_threshold=100)
    lead_message = AIMessage(content="给用户的最终回答")
    journal.on_llm_end(
        LLMResult(generations=[[ChatGeneration(message=lead_message)]]),
        run_id=uuid4(),
        tags=["lead_agent"],
    )

    result = await oneshot_llm.run_oneshot_llm(
        system_instruction="只处理安全输入",
        user_content="安全内容",
        run_name="ip-agent-script-writer-v2",
        app_config=AppConfig.model_construct(),
        thread_id="thread-1",
        callbacks=[journal],
    )

    assert result == "内部脚本"
    invoke = model.ainvoke.await_args
    assert invoke.kwargs["config"]["callbacks"] == [journal]
    assert invoke.kwargs["config"]["tags"] == ["middleware:ip-agent-script-writer-v2"]
    assert _RAW_SECRET not in repr(invoke.args[0])
    assert _RAW_SECRET not in repr(invoke.kwargs["config"])

    journal.on_llm_end(
        LLMResult(generations=[[ChatGeneration(message=internal_message)]]),
        run_id=uuid4(),
        tags=invoke.kwargs["config"]["tags"],
    )
    await journal.flush()

    completion = journal.get_completion_data()
    assert completion["last_ai_message"] == "给用户的最终回答"
    assert completion["middleware_tokens"] == 5
    events = await event_store.list_events("thread-1", "run-1")
    internal_event = next(event for event in events if event["event_type"] == "llm.ai.response" and event["content"]["content"] == "内部脚本")
    assert internal_event["metadata"]["caller"] == "middleware:ip-agent-script-writer-v2"


@pytest.mark.asyncio
async def test_content_write_passes_only_the_run_journal_not_runtime_secrets(
    monkeypatch,
) -> None:
    captured: dict = {}

    class _CaptureWriterService:
        def __init__(self, _content, *, subjects) -> None:
            assert subjects is not None

        async def generate_and_save(self, **kwargs) -> dict:
            captured.update(kwargs)
            return {"schema_version": "personal-ip-writer-brain-v2", "script_text": "已保存"}

    monkeypatch.setattr(personal_ip_content_tools, "WriterBrainService", _CaptureWriterService)
    configure_personal_ip_runtime(
        PersonalIPRuntimeServices(
            connections=SimpleNamespace(),
            metrics=SimpleNamespace(),
            publish_receipts=SimpleNamespace(),
            content=SimpleNamespace(),
            subjects=SimpleNamespace(),
        )
    )
    journal = _PrivateRunJournal()
    runtime = SimpleNamespace(
        context={
            "user_id": "owner-1",
            "run_id": "run-1",
            "thread_id": "thread-1",
            "app_config": AppConfig.model_construct(),
            "__run_journal": journal,
            "secrets": {"PROVIDER_TOKEN": _RAW_SECRET},
        },
        state={"messages": []},
        tool_call_id="tool-1",
    )

    try:
        result = json.loads(await _ip_content_write(runtime, _direct_request()))

        assert result["operation_status"] == "ok"
        assert captured["callbacks"] == [journal]
        assert _RAW_SECRET not in repr(captured)
        model_schema = json.dumps(
            convert_to_openai_tool(ip_content_write_tool),
            ensure_ascii=False,
            sort_keys=True,
        )
        assert "__run_journal" not in model_schema
        assert "callbacks" not in model_schema
        assert _RAW_SECRET not in model_schema
    finally:
        configure_personal_ip_runtime(None)


@pytest.mark.parametrize(
    ("request_factory", "outputs", "expected_run_names"),
    [
        (
            _direct_request,
            ["我今天完成了第一次公开演示。", _DIRECT_BOUNDARY_OK],
            ["ip-agent-script-writer-v2", "ip-agent-script-boundary-verifier-v2"],
        ),
        (
            _semantic_request,
            [
                "他想用玩笑求助，但朋友仍没听懂；他转而坦白害怕，只能在继续讨喜和说真话之间选择，代价是失去好感，最终朋友第一次认真听完。",
                "【镜头】他收起笑容：这次我不是开玩笑。朋友终于认真听完。",
                _SEMANTIC_BOUNDARY_OK,
            ],
            [
                "ip-agent-story-engine-v2",
                "ip-agent-script-writer-v2",
                "ip-agent-script-boundary-verifier-v2",
            ],
        ),
    ],
    ids=["direct-two-calls", "semantic-three-calls"],
)
@pytest.mark.asyncio
async def test_writer_brain_forwards_callbacks_to_every_internal_model_call(
    tmp_path,
    request_factory,
    outputs: list[str],
    expected_run_names: list[str],
) -> None:
    await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(tmp_path)))
    session_factory = get_session_factory()
    assert session_factory is not None
    runner = _RecordingModelRunner(outputs)
    service = WriterBrainService(
        PersonalIPContentRepository(session_factory),
        subjects=None,
        model_runner=runner,
    )
    journal = _PrivateRunJournal()

    try:
        await service.generate_and_save(
            owner_user_id="owner-1",
            request=request_factory(),
            idempotency_key=f"run-1:{expected_run_names[0]}",
            created_by_run_id="run-1",
            app_config=AppConfig.model_construct(),
            thread_id="thread-1",
            callbacks=[journal],
        )

        assert [call["run_name"] for call in runner.calls] == expected_run_names
        assert all(call["callbacks"] == [journal] for call in runner.calls)
        assert all(_RAW_SECRET not in repr(call) for call in runner.calls)
    finally:
        await close_engine()
