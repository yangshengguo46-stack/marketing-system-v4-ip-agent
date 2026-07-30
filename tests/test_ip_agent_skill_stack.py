from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]

CORE_SKILLS = {
    "ip-strategy-director",
    "ip-content-calibration",
    "video-pattern-learning",
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


def _agent_config() -> dict:
    path = ROOT / "product" / "defaults" / "agents" / "ip-agent" / "config.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_private_operating_intelligence_is_enabled() -> None:
    configured = set(_agent_config()["skills"])
    assert CORE_SKILLS <= configured
    assert MEDIA_SKILLS <= configured

    for name in CORE_SKILLS | MEDIA_SKILLS:
        skill = ROOT / "skills" / "public" / name / "SKILL.md"
        assert skill.is_file(), name
        assert "TODO" not in skill.read_text(encoding="utf-8")


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
