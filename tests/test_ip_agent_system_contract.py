from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "IP_AGENT.md"
LEDGER = ROOT / "docs" / "IP_AGENT_PRODUCT_LEDGER.md"
AUDIT_CLOSEOUT = ROOT / "docs" / "IP_AGENT_AUDIT_REMEDIATION_LEDGER.md"
CAPABILITY_INVENTORY = ROOT / "docs" / "IP_AGENT_SKILL_CAPABILITY_BOUNDARY_LEDGER.md"
LEDGER_HISTORY = ROOT / "product" / "research" / "ip-agent" / "IP_AGENT_PRODUCT_LEDGER_HISTORY_2026-08-04.md"
VIDEO_MIGRATION_HISTORY = ROOT / "docs" / "handoffs" / "VIDEO_PIPELINE_MIGRATION_HISTORY.md"
VOLCENGINE_CAPABILITIES = ROOT / "product" / "volcengine" / "capabilities.yaml"
MEDIAKIT_CANARIES = ROOT / "product" / "research" / "ip-agent" / "mediakit" / "2026-08-03-capability-canaries.yaml"

RESEARCH_DOCUMENTS = {
    "IP_AGENT_NARRATIVE_INTERVIEW_RESEARCH.md",
    "IP_AGENT_INFLUENCE_ASSET_FIRST_PRINCIPLES_RESEARCH.md",
    "IP_AGENT_DIFFERENTIATED_IP_MOAT_RESEARCH.md",
}


def _section(text: str, start: str, end: str) -> str:
    _before, separator, remainder = text.partition(start)
    assert separator, f"missing section: {start}"
    body, separator, _after = remainder.partition(end)
    assert separator, f"missing section boundary: {end}"
    return body


def _markdown_table_rows(section: str, header: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in section.splitlines():
        if not line.startswith("|") or line.startswith("| ---"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if cells and cells[0] != header:
            rows.append(cells)
    return rows


def test_contract_defines_the_shipped_three_board_runtime() -> None:
    text = CONTRACT.read_text(encoding="utf-8")

    assert "skills: []" in text
    assert "memory_enabled: false" in text
    assert "Owner -> Subject -> Objective -> ContentWork" in text
    assert "BreakdownVersion -> DirectionVersion -> ScriptVersion" in text
    assert "ip_content_start_production" in text
    assert "exact typed Evidence MCP ToolMessage" in text
    assert "Production starts from an exact immutable ScriptVersion" in text
    assert "all 97 quarantined public Skills" not in text


def test_product_ledger_is_the_only_current_status_source_and_has_three_boards() -> None:
    text = LEDGER.read_text(encoding="utf-8")
    section = _section(text, "## 三大核心板块", "### 拆解的准确口径")
    rows = _markdown_table_rows(section, "核心板块")

    assert "本文件是唯一当前产品状态记录" in text
    assert len(text.splitlines()) <= 180
    assert all(len(row) == 5 for row in rows)
    assert [row[0] for row in rows] == ["拆解", "编剧脑", "制作"]
    assert [row[2] for row in rows] == [
        "现役",
        "现役",
        "有界接通",
    ]

    competing_claims = [path.relative_to(ROOT).as_posix() for path in (ROOT / "docs").rglob("*.md") if path != LEDGER and "唯一当前产品状态记录" in path.read_text(encoding="utf-8")]
    assert competing_claims == []


def test_product_ledger_has_exactly_one_active_delivery_slice() -> None:
    text = LEDGER.read_text(encoding="utf-8")
    section = _section(text, "## 当前唯一交付主线", "## 后续顺序")
    rows = _markdown_table_rows(section, "编号")

    assert len(rows) == 1
    assert rows[0][0] == "V1 内容纵切"
    assert rows[0][2] == "最终版"
    assert "零起盘 / 精确链接或上传" in rows[0][1]
    assert "完整 ScriptVersion → 绑定 Production" in rows[0][1]
    assert "V1 不把供应商成片、自动发布、账号历史诊断" in text


def test_product_ledger_separates_active_exact_media_analysis_from_isolated_suites() -> None:
    text = LEDGER.read_text(encoding="utf-8")

    assert "精确视频拆解：现役" in text
    assert "固定 `full + 12` 分析" in text
    assert "MediaKit Smart Strategy、Video Understanding Chat、Remux 和 Vibe" in text
    assert "当前保持隔离" in text


def test_product_contract_authority_pointers_exist() -> None:
    expected = {
        LEDGER,
        AUDIT_CLOSEOUT,
        CAPABILITY_INVENTORY,
        LEDGER_HISTORY,
        VIDEO_MIGRATION_HISTORY,
        ROOT / "product" / "defaults" / "agents" / "ip-agent" / "SOUL.md",
    }

    missing = sorted(str(path.relative_to(ROOT)) for path in expected if not path.is_file())
    assert not missing, f"missing IP Agent authority files: {missing}"


def test_supporting_ledgers_cannot_claim_current_product_status() -> None:
    audit = AUDIT_CLOSEOUT.read_text(encoding="utf-8")
    inventory = CAPABILITY_INVENTORY.read_text(encoding="utf-8")

    assert "Status: frozen historical closeout" in audit
    assert "not a current product-status source" in audit
    assert "only active delivery sequence live in `docs/IP_AGENT_PRODUCT_LEDGER.md`" in audit

    assert "能力库存（非产品状态台账）" in inventory
    assert "不能发布" in inventory
    assert "客户可达状态只看 `IP_AGENT_PRODUCT_LEDGER.md`" in inventory


def test_old_ledgers_and_research_are_quarantined_as_history() -> None:
    current = LEDGER.read_text(encoding="utf-8")
    history = LEDGER_HISTORY.read_text(encoding="utf-8")
    video_history = VIDEO_MIGRATION_HISTORY.read_text(encoding="utf-8")

    for marker in ("M2-E2c", "MF-I5d-MK7", "每轮回写模板"):
        assert marker not in current
        assert marker in history

    assert not (ROOT / "docs" / "VIDEO_PIPELINE_MIGRATION_LEDGER.md").exists()
    assert "Historical handoff frozen" in video_history
    assert "not current customer-reachability" in video_history
    assert "Current product state is owned only by `docs/IP_AGENT_PRODUCT_LEDGER.md`" in (video_history)

    for filename in RESEARCH_DOCUMENTS:
        assert not (ROOT / "docs" / filename).exists()
        research_path = ROOT / "product" / "research" / "ip-agent" / filename
        assert research_path.is_file()
        assert "`research_quarantined`" in research_path.read_text(encoding="utf-8")


def test_failed_smart_strategy_canary_remains_external_blocked_and_historical() -> None:
    capabilities = VOLCENGINE_CAPABILITIES.read_text(encoding="utf-8")
    canaries = MEDIAKIT_CANARIES.read_text(encoding="utf-8")
    ledger = LEDGER.read_text(encoding="utf-8")
    history = LEDGER_HISTORY.read_text(encoding="utf-8")

    assert "lifecycle_state: paid-canary-external-blocked" in capabilities
    assert "capability-or-quality-conclusion: unavailable" in capabilities
    assert "verdict: external-blocked-no-capability-or-quality-conclusion" in canaries
    assert "product_promoted: false" in canaries
    assert "Smart Strategy" in ledger
    assert "当前保持隔离" in ledger
    assert "`billing_outcome=unknown / external-blocked`" not in ledger
    assert "`billing_outcome=unknown / external-blocked`" in history
    assert "没有发起第二次 POST" in history
