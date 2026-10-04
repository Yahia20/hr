from dataclasses import replace

import pytest

from app.ats.parse import Evidence, SkillMatch, parse_cv
from app.ats.role_templates import DEFAULT_WEIGHTS, HARD_GATES_AVAILABLE, ROLE_TEMPLATES
from app.ats.score import score
from app.ats.taxonomy import SKILLS


BASE_TEXT = """Rami Example
rami@example.test
Experience
Customer service specialist with 4 years experience.
Education
Bachelor degree
Languages
Arabic, English, French, German
Skills
Amadeus, PNR, Excel, customer service
"""


def test_phase_zero_seeds_are_complete_and_cross_referenced():
    assert len(ROLE_TEMPLATES) == 6
    ids = {skill["id"] for skill in SKILLS}
    assert len(ids) == len(SKILLS)
    for skill in SKILLS:
        assert skill["canonical"] and skill["category"]
        assert any(any("a" <= char.lower() <= "z" for char in alias) for alias in skill["aliases"])
        assert any(any("\u0600" <= char <= "\u06ff" for char in alias) for alias in skill["aliases"])
    for template in ROLE_TEMPLATES:
        assert template["weights"] == DEFAULT_WEIGHTS
        assert set(template["required_skills"] + template["preferred_skills"]) <= ids
        assert template["min_years"] >= 0 and template["min_education"]
        assert template["languages"]
        assert template["hard_gates_available"] == HARD_GATES_AVAILABLE
        assert "jd_similarity" not in template["weights"]


def _job(**changes):
    job = {
        "required_skills": ["amadeus", "pnr", "excel", "customer_service"],
        "preferred_skills": [],
        "min_years": 4,
        "min_education": "bachelor",
        "languages": ["Arabic", "English"],
        "gates": {},
        "weights": {"required_skills": 40, "experience": 20, "preferred_skills": 10, "education": 10, "languages": 10},
    }
    job.update(changes)
    return job


@pytest.mark.parametrize("count, expected", [(0, 0), (1, 1), (2, 2), (3, 3), (4, 4)])
def test_required_skill_ladder_boundaries(count, expected):
    parsed = parse_cv(BASE_TEXT)
    required = {"amadeus", "pnr", "excel", "customer_service"}
    parsed = replace(parsed, skills=[item for item in parsed.skills if item.id in required][:count])
    result = score(parsed, _job(weights={"required_skills": 1, "experience": 0, "preferred_skills": 0, "education": 0, "languages": 0}))
    assert result.breakdown[0].score_0_4 == expected


@pytest.mark.parametrize("years, expected", [(1.9, 0), (2.0, 1), (3.0, 2), (4.0, 3), (6.0, 4)])
def test_experience_ladder_boundaries(years, expected):
    parsed = replace(parse_cv(BASE_TEXT), years_experience=years)
    result = score(parsed, _job(weights={"required_skills": 0, "experience": 1, "preferred_skills": 0, "education": 0, "languages": 0}))
    assert next(item for item in result.breakdown if item.criterion == "experience").score_0_4 == expected


@pytest.mark.parametrize("education, ordinal, expected", [("high_school", 1, 0), ("diploma", 2, 2), ("bachelor", 3, 4), ("master", 4, 4)])
def test_education_ladder(education, ordinal, expected):
    parsed = replace(parse_cv(BASE_TEXT), education=education, education_ordinal=ordinal)
    result = score(parsed, _job(weights={"required_skills": 0, "experience": 0, "preferred_skills": 0, "education": 1, "languages": 0}))
    assert next(item for item in result.breakdown if item.criterion == "education").score_0_4 == expected


def test_gate_failure_forces_zero_and_unknown_does_not_fail():
    parsed = parse_cv(BASE_TEXT)
    failed = score(replace(parsed, years_experience=1), _job(gates={"min_years": 4}))
    assert failed.rules_score == 0
    assert failed.gate_failures == ["min_years"]

    unknown = score(replace(parsed, nationality=None), _job(gates={"nationality_in": ["Fictional"]}))
    assert not unknown.gate_failures
    assert unknown.rules_score > 0
    assert unknown.gate_results[0].status == "unknown"


def test_weights_validation():
    parsed = parse_cv(BASE_TEXT)
    with pytest.raises(ValueError, match="more than zero"):
        score(parsed, _job(weights={key: 0 for key in _job()["weights"]}))
    with pytest.raises(ValueError, match="negative"):
        score(parsed, _job(weights={"required_skills": -1}))
    with pytest.raises(ValueError, match="Unknown scoring"):
        score(parsed, _job(weights={"jd_similarity": 10}))


def test_breakdown_has_evidence_for_every_matched_term_and_no_similarity():
    result = score(parse_cv(BASE_TEXT), _job())
    assert [item.criterion for item in result.breakdown] == [
        "required_skills", "experience", "preferred_skills", "education", "languages"
    ]
    required = result.breakdown[0]
    assert len({item["term"] for item in required.evidence}) >= 4
    assert all(item["line"] for item in required.evidence)


def test_rescore_after_manual_correction_changes_rules_score():
    parsed = parse_cv("Tara Example\ntara@example.test\nEducation\nDiploma\n")
    before = score(parsed, _job())
    corrected_skill = SkillMatch("amadeus", "Amadeus", "gds_ticketing", [Evidence("manual correction", "HR correction: Amadeus", 0)])
    corrected = replace(parsed, years_experience=6, skills=[corrected_skill])
    after = score(corrected, _job())
    assert after.rules_score > before.rules_score


def test_role_specific_ticketing_evidence_beats_generic_templates():
    parsed = parse_cv("""Casey Example
Professional Experience
Reservation Agent | January 2018 - January 2024
Air ticketing with Amadeus, NDC, refunds and reissue.
Education
Bachelor degree
Languages
Arabic, English
""")
    ranked = sorted(
        ((score(parsed, template).rules_score, template["id"]) for template in ROLE_TEMPLATES),
        reverse=True,
    )
    assert ranked[0][1] == "reservation_ticketing"
