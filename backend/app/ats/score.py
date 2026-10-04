"""Anchored, explainable ATS rules scoring (no JD-similarity criterion)."""
from dataclasses import asdict, dataclass
from typing import Any, Mapping

from .parse import EDUCATION_ORDINAL, Evidence, ParsedCV
from .role_templates import DEFAULT_WEIGHTS
from .taxonomy import SKILLS_BY_ID


_SKILL_LOOKUP = {
    _normalize: skill_id
    for skill_id, skill in SKILLS_BY_ID.items()
    for _normalize in {
        skill_id,
        str(skill["canonical"]).strip().lower().replace("-", "_").replace(" ", "_"),
    }
}


@dataclass
class GateResult:
    gate: str
    status: str  # pass, fail, unknown
    required: Any
    actual: Any


@dataclass
class CriterionResult:
    criterion: str
    weight: float
    score_0_4: int
    evidence: list[dict]
    missing: list[str]


@dataclass
class ScoreResult:
    rules_score: int
    breakdown: list[CriterionResult]
    gate_failures: list[str]
    gate_results: list[GateResult]

    def to_dict(self):
        return asdict(self)


def _job_value(job: Any, name: str, default=None):
    if isinstance(job, Mapping):
        return job.get(name, default)
    return getattr(job, name, default)


def _normalize_key(value: Any) -> str:
    return str(value).strip().lower().replace("-", "_").replace(" ", "_")


def _skill_ids(values: Any) -> list[str]:
    result: list[str] = []
    for value in values or []:
        if isinstance(value, Mapping):
            value = value.get("skill_id", value.get("id", value.get("canonical", "")))
        key = _SKILL_LOOKUP.get(_normalize_key(value), _normalize_key(value))
        if key and key not in result:
            result.append(key)
    return result


def _evidence_dict(evidence: Evidence | Mapping) -> dict:
    if isinstance(evidence, Mapping):
        return {"term": evidence.get("term", ""), "line": evidence.get("line", "")}
    return {"term": evidence.term, "line": evidence.line}


def _coverage_score(matched: int, required: int) -> int:
    if required == 0:
        return 4
    ratio = matched / required
    if ratio < 0.25:
        return 0
    if ratio < 0.50:
        return 1
    if ratio < 0.75:
        return 2
    if ratio < 1.0:
        return 3
    return 4


def _experience_score(years: float | None, minimum: float) -> int:
    if not years:
        return 0
    if minimum <= 0:
        return 4
    ratio = years / minimum
    if ratio < 0.50:
        return 0
    if ratio < 0.75:
        return 1
    if ratio < 1.0:
        return 2
    if ratio < 1.50:
        return 3
    return 4


def _weights(job: Any) -> dict[str, float]:
    supplied = _job_value(job, "weights", None)
    values = dict(DEFAULT_WEIGHTS)
    if supplied is not None:
        unknown = set(supplied) - set(DEFAULT_WEIGHTS)
        if unknown:
            raise ValueError(f"Unknown scoring criteria: {', '.join(sorted(unknown))}")
        values.update(supplied)
    try:
        values = {key: float(value) for key, value in values.items()}
    except (TypeError, ValueError) as exc:
        raise ValueError("Weights must be numeric") from exc
    if any(value < 0 for value in values.values()):
        raise ValueError("Weights cannot be negative")
    if sum(values.values()) <= 0:
        raise ValueError("Weights must sum to more than zero")
    return values


def _configured_gates(job: Any) -> dict[str, Any]:
    configured = _job_value(job, "gates", {}) or {}
    if isinstance(configured, Mapping):
        return dict(configured)
    result: dict[str, Any] = {}
    for item in configured:
        if isinstance(item, Mapping) and item.get("type"):
            result[item["type"]] = item.get("value", item.get("required", True))
    return result


def _list_value(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return [str(item) for item in value]


def _gate_results(parsed: ParsedCV, job: Any) -> list[GateResult]:
    gates = _configured_gates(job)
    results: list[GateResult] = []
    for gate, required in gates.items():
        gate = _normalize_key(gate)
        if required in (False, None, [], ""):
            continue
        if gate == "nationality_in":
            allowed = _list_value(required)
            actual = parsed.nationality
            status = "unknown" if not actual else "pass" if _normalize_key(actual) in {_normalize_key(x) for x in allowed} else "fail"
        elif gate == "city_in":
            allowed = _list_value(required)
            actual = parsed.city
            if not actual and parsed.willing_to_relocate is None:
                status = "unknown"
            elif parsed.willing_to_relocate is True:
                status = "pass"
            else:
                status = "pass" if actual and _normalize_key(actual) in {_normalize_key(x) for x in allowed} else "fail"
        elif gate in {"language_required", "languages_required"}:
            wanted = _list_value(required)
            actual = parsed.languages
            if not actual:
                status = "unknown"
            else:
                found = {_normalize_key(value) for value in actual}
                status = "pass" if all(_normalize_key(value) in found for value in wanted) else "fail"
        elif gate == "min_years":
            threshold = _job_value(job, "min_years", 0) if required is True else required
            actual = parsed.years_experience
            status = "unknown" if actual is None else "pass" if actual >= float(threshold) else "fail"
            required = threshold
        elif gate == "min_education":
            threshold = _job_value(job, "min_education", None) if required is True else required
            actual = parsed.education
            needed = EDUCATION_ORDINAL.get(_normalize_key(threshold))
            if needed is None:
                raise ValueError(f"Unknown education level: {threshold}")
            status = "unknown" if parsed.education_ordinal is None else "pass" if parsed.education_ordinal >= needed else "fail"
            required = threshold
        elif gate in {"licence_required", "license_required"}:
            actual = parsed.driving_licence
            status = "unknown" if actual is None else "pass" if actual else "fail"
        elif gate in {"transferable_iqama", "transferable_iqama_required"}:
            actual = parsed.transferable_iqama
            status = "unknown" if actual is None else "pass" if actual else "fail"
        else:
            raise ValueError(f"Unknown hard gate: {gate}")
        results.append(GateResult(gate, status, required, actual))
    return results


def score(parsed: ParsedCV, job: Any) -> ScoreResult:
    """Score one parsed CV against a job/template using the Phase 1 rules."""
    weights = _weights(job)
    gate_results = _gate_results(parsed, job)
    failures = [result.gate for result in gate_results if result.status == "fail"]
    if failures:
        return ScoreResult(0, [], failures, gate_results)

    matched_skills = {skill.id: skill for skill in parsed.skills}
    required = _skill_ids(_job_value(job, "required_skills", []))
    preferred = _skill_ids(_job_value(job, "preferred_skills", []))

    def skill_result(criterion: str, wanted: list[str]) -> CriterionResult:
        matched = [skill_id for skill_id in wanted if skill_id in matched_skills]
        evidence = []
        for skill_id in matched:
            evidence.extend(_evidence_dict(item) for item in matched_skills[skill_id].evidence)
        missing = [SKILLS_BY_ID.get(skill_id, {}).get("canonical", skill_id) for skill_id in wanted if skill_id not in matched_skills]
        return CriterionResult(criterion, weights[criterion], _coverage_score(len(matched), len(wanted)), evidence, missing)

    breakdown = [skill_result("required_skills", required)]

    minimum_years = float(_job_value(job, "min_years", 0) or 0)
    exp_evidence = [_evidence_dict(item) for item in parsed.experience_evidence]
    exp_missing = [] if parsed.years_experience is not None else ["years of experience"]
    breakdown.append(CriterionResult(
        "experience", weights["experience"],
        _experience_score(parsed.years_experience, minimum_years),
        exp_evidence, exp_missing,
    ))
    breakdown.append(skill_result("preferred_skills", preferred))

    required_education = _job_value(job, "min_education", None)
    if not required_education:
        education_score, education_missing = 4, []
    else:
        needed = EDUCATION_ORDINAL.get(_normalize_key(required_education))
        if needed is None:
            raise ValueError(f"Unknown education level: {required_education}")
        if parsed.education_ordinal is None:
            education_score, education_missing = 0, [str(required_education)]
        else:
            distance = needed - parsed.education_ordinal
            education_score = 4 if distance <= 0 else 2 if distance == 1 else 0
            education_missing = [] if education_score == 4 else [str(required_education)]
    breakdown.append(CriterionResult(
        "education", weights["education"], education_score,
        [_evidence_dict(item) for item in parsed.education_evidence], education_missing,
    ))

    required_languages = _list_value(_job_value(job, "languages", []))
    found_languages = {_normalize_key(language): language for language in parsed.languages}
    matched_languages = [language for language in required_languages if _normalize_key(language) in found_languages]
    language_evidence = []
    for language in matched_languages:
        actual = found_languages[_normalize_key(language)]
        language_evidence.extend(_evidence_dict(item) for item in parsed.language_evidence.get(actual, []))
    breakdown.append(CriterionResult(
        "languages", weights["languages"],
        _coverage_score(len(matched_languages), len(required_languages)),
        language_evidence,
        [language for language in required_languages if _normalize_key(language) not in found_languages],
    ))

    total_weight = sum(weights.values())
    rules_score = round(sum(item.weight * item.score_0_4 for item in breakdown) / (4 * total_weight) * 100)
    return ScoreResult(rules_score, breakdown, [], gate_results)
