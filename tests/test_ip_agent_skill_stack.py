import hashlib
import json
import sqlite3
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]

CORE_SKILLS = {
    "design-ip-differentiation",
    "ip-strategy-director",
    "ip-content-calibration",
    "video-pattern-learning",
    "video-method-distillation",
}

MEDIA_SKILLS = {
    "reference-media-analysis",
    "precise-video-description",
    "cinematic-shot-direction",
    "visual-style-direction",
    "character-design-continuity",
    "production-design-direction",
    "lighting-direction",
    "performance-direction",
    "asset-continuity-management",
    "dialogue-editing-adr",
    "sound-design-foley",
    "music-supervision-scoring",
    "captions-media-accessibility",
    "color-grading-finishing",
    "brand-launch-film-production",
    "product-ad-production",
    "ugc-ad-production",
    "talking-head-podcast-recut",
}

CINEMATIC_IP_SKILLS = {
    "audit-ip-continuity",
    "build-cinematic-ip-system",
    "calibrate-cinematic-ip",
    "coach-ip-screen-performance",
    "design-character-relations",
    "design-cinematography",
    "design-ip-series-bible",
    "design-light-color-texture",
    "design-production-world",
    "design-screen-sound",
    "develop-theme-premise",
    "direct-ip-visual-language",
    "direct-scene-blocking",
    "distill-screen-methods",
    "edit-screen-rhythm",
    "engineer-desire-behavior",
    "engineer-plot-information",
    "ingest-ip-evidence",
    "previsualize-screen-direction",
    "query-cinematic-library",
    "route-ip-genre-engine",
    "run-cinematic-curriculum",
    "shape-ip-emotion",
    "write-action-adventure",
    "write-comedy-satire",
    "write-crime-power-western",
    "write-documentary-reality",
    "write-horror",
    "write-ip-episode",
    "write-musical-performance",
    "write-mystery-thriller",
    "write-romance-family-growth",
    "write-scenes-dialogue",
    "write-scifi-fantasy-animation",
    "write-war-history-epic",
}


def _agent_config() -> dict:
    path = ROOT / "product" / "defaults" / "agents" / "ip-agent" / "config.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_private_operating_intelligence_is_enabled() -> None:
    configured = set(_agent_config()["skills"])
    assert CORE_SKILLS <= configured
    assert MEDIA_SKILLS <= configured
    assert CINEMATIC_IP_SKILLS <= configured

    for name in CORE_SKILLS | MEDIA_SKILLS | CINEMATIC_IP_SKILLS:
        skill = ROOT / "skills" / "public" / name / "SKILL.md"
        assert skill.is_file(), name
        assert "TODO" not in skill.read_text(encoding="utf-8")


def test_first_use_orientation_precedes_generic_research() -> None:
    soul = (
        ROOT / "product" / "defaults" / "agents" / "ip-agent" / "SOUL.md"
    ).read_text(encoding="utf-8")
    operator = (
        ROOT / "skills" / "public" / "personal-ip-operator" / "SKILL.md"
    ).read_text(encoding="utf-8")
    strategy = (
        ROOT / "skills" / "public" / "ip-strategy-director" / "SKILL.md"
    ).read_text(encoding="utf-8")
    research = (
        ROOT / "skills" / "public" / "deep-research" / "SKILL.md"
    ).read_text(encoding="utf-8")

    normalized_soul = " ".join(soul.lower().split())
    assert "material questions without a model or tool call" in normalized_soul
    assert "target group and core problem" in normalized_soul
    assert "preserve the same strict boundary" in normalized_soul
    assert "do not load a skill file, browse/search" in normalized_soul
    assert "ask exactly one conversational question" in normalized_soul
    assert "do not apply this delay to a concrete supplied script, asset or link" in " ".join(
        operator.lower().split()
    )
    assert "do not load another skill" in " ".join(strategy.lower().split())
    assert "product-specific onboarding gates take precedence" in " ".join(
        research.lower().split()
    )


def test_upstream_media_skills_keep_hidden_evaluations() -> None:
    for name in MEDIA_SKILLS:
        assert (ROOT / "skills" / "public" / name / "EVAL.md").is_file(), name


def test_skill_lab_is_isolated_from_customer_agent() -> None:
    configured = set(_agent_config()["skills"])
    assert (
        not {"skillhone", "skillhone-evaluation", "skillhone-optimization"} & configured
    )

    lab = ROOT / "product" / "skill-lab"
    policy = yaml.safe_load((lab / "policy.yaml").read_text(encoding="utf-8"))
    assert policy["mode"] == "evaluation_only"
    assert policy["boundaries"]["expose_lab_to_customer_agent"] is False
    assert policy["boundaries"]["allow_live_skill_self_modification"] is False
    assert policy["promotion"]["require_held_out_regression"] is True

    for name in ("skillhone", "skillhone-evaluation", "skillhone-optimization"):
        assert (lab / "vendor" / name / "SKILL.md").is_file(), name


def test_cangjie_methodology_is_attributed_without_vendoring_runtime() -> None:
    skill = ROOT / "skills" / "public" / "video-method-distillation"
    assert (skill / "references" / "method-contract.md").is_file()
    attribution = (ROOT / "THIRD_PARTY_SKILLS.md").read_text(encoding="utf-8")
    assert "https://github.com/kangarooking/cangjie-skill" in attribution
    assert "355dd47a97eeb87d249bf7d32aab561405b6de76" in attribution
    assert (ROOT / "licenses" / "cangjie-skill-MIT.txt").is_file()
    assert not (ROOT / "product" / "skill-lab" / "vendor" / "cangjie-skill").exists()


def test_cinematic_ip_matrix_and_assets_are_complete() -> None:
    matrix = yaml.safe_load(
        (ROOT / "product" / "cinematic-ip" / "matrix.yaml").read_text(encoding="utf-8")
    )
    assert matrix["version"] == "4.0.0"
    assert matrix["architecture"]["total_skills"] == 35
    assert {item["name"] for item in matrix["skills"]} == CINEMATIC_IP_SKILLS
    assert {
        name for names in matrix["skill_groups"].values() for name in names
    } == CINEMATIC_IP_SKILLS

    for name in CINEMATIC_IP_SKILLS:
        root = ROOT / "skills" / "public" / name
        assert (root / "SKILL.md").is_file(), name
        assert (root / "agents" / "openai.yaml").is_file(), name

    database = (
        ROOT
        / "skills"
        / "public"
        / "query-cinematic-library"
        / "assets"
        / "cinema_library.sqlite"
    )
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM films").fetchone()[0] == 358
        assert connection.execute("SELECT COUNT(*) FROM creators").fetchone()[0] == 393
        assert (
            connection.execute("SELECT COUNT(*) FROM mechanism_cards").fetchone()[0]
            == 304
        )

    curriculum = json.loads(
        (
            ROOT
            / "skills"
            / "public"
            / "run-cinematic-curriculum"
            / "references"
            / "curriculum.json"
        ).read_text(encoding="utf-8")
    )
    assert len(curriculum["tracks"]) == 8
    assert sum(len(track["modules"]) for track in curriculum["tracks"]) == 96

    source_manifest = json.loads(
        (ROOT / "product" / "cinematic-ip" / "source_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    for source in source_manifest:
        if path := source.get("path"):
            assert (
                hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
                == source["sha256"]
            )


def test_cinematic_ip_stack_uses_native_product_state() -> None:
    ingest = ROOT / "skills" / "public" / "ingest-ip-evidence"
    calibrate = ROOT / "skills" / "public" / "calibrate-cinematic-ip"
    curriculum = ROOT / "skills" / "public" / "run-cinematic-curriculum"

    assert not (ingest / "scripts" / "ip_os.py").exists()
    assert not (calibrate / "scripts" / "ip_os.py").exists()
    assert "personal_ip_record_strategy" in (ingest / "SKILL.md").read_text(
        encoding="utf-8"
    )

    calibrate_text = (calibrate / "SKILL.md").read_text(encoding="utf-8")
    for tool_name in (
        "personal_ip_run_preflight",
        "personal_ip_prepare_browser_publish",
        "personal_ip_seal_retrospective",
        "personal_ip_promote_evidence",
    ):
        assert tool_name in calibrate_text

    curriculum_cli = (curriculum / "scripts" / "curriculum_cli.py").read_text(
        encoding="utf-8"
    )
    assert "completion-ledger" not in curriculum_cli
    assert 'add_parser("record")' not in curriculum_cli

    orchestration = (
        ROOT / "skills" / "public" / "build-cinematic-ip-system" / "SKILL.md"
    ).read_text(encoding="utf-8")
    assert "客户输出不得出现 Skill 名" in orchestration


def test_differentiation_thesis_is_bound_to_strategy_and_cinematic_work() -> None:
    differentiation = ROOT / "skills" / "public" / "design-ip-differentiation"
    text = (differentiation / "SKILL.md").read_text(encoding="utf-8")
    assert "for a person, brand, product, organization or portfolio" in text
    assert "personal_ip_record_differentiation" in text
    assert "personal_ip_record_asset_observation" in text
    assert (differentiation / "references" / "thesis-contract.md").is_file()
    assert (differentiation / "references" / "decision-judgment.md").is_file()

    strategy = (
        ROOT / "skills" / "public" / "ip-strategy-director" / "SKILL.md"
    ).read_text(encoding="utf-8")
    series = (
        ROOT / "skills" / "public" / "design-ip-series-bible" / "SKILL.md"
    ).read_text(encoding="utf-8")
    direction = (
        ROOT / "skills" / "public" / "direct-ip-visual-language" / "SKILL.md"
    ).read_text(encoding="utf-8")
    assert "design-ip-differentiation" in strategy
    assert "差异化版本" in series
    assert "差异化识别系统" in direction
