"""Deterministic baseline checks for IncidentLens eval traces."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ALLOWED_CLASSIFICATIONS = [
    "Application",
    "Infrastructure",
    "Database",
    "Authentication / Authorization",
    "Unknown / Insufficient Evidence",
]
ALLOWED_SEVERITIES = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
UNCERTAINTY_WORDS = [
    "uncertain",
    "uncertainty",
    "insufficient",
    "not enough",
    "missing",
    "unknown",
    "cannot determine",
    "limited",
    "ambiguous",
    "unclear",
]
DEFAULT_FORBIDDEN_RECOMMENDATIONS = [
    "restart the service",
    "restart the pod",
    "increase memory limits",
    "scale up",
    "roll back",
    "rollback",
    "disable",
    "delete",
    "drop table",
    "kill process",
]
PASS_SCORE = 5.0
FAIL_SCORE = 1.0


def content_text(value: Any) -> str:
    """Extract text from ADK/Agent Platform Content-like values."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(content_text(item) for item in value)
    if not isinstance(value, dict):
        return str(value)

    if "response" in value:
        return content_text(value["response"])
    if "content" in value:
        return content_text(value["content"])
    if "text" in value:
        return str(value["text"])
    if "parts" in value:
        return "\n".join(content_text(part) for part in value.get("parts") or [])
    if "functionResponse" in value:
        return json.dumps(value["functionResponse"], sort_keys=True)
    if "function_response" in value:
        return json.dumps(value["function_response"], sort_keys=True)
    return json.dumps(value, sort_keys=True)


def response_text(instance: dict[str, Any]) -> str:
    text = content_text(instance.get("response"))
    if text:
        return text

    responses = instance.get("responses") or []
    if responses:
        return content_text(responses[-1])

    final_text = ""
    for turn in (instance.get("agent_data") or {}).get("turns") or []:
        for event in turn.get("events") or []:
            if event.get("author") != "user":
                event_text = content_text(event.get("content"))
                if event_text:
                    final_text = event_text
    return final_text


def prompt_text(instance: dict[str, Any]) -> str:
    return content_text(instance.get("prompt"))


def expected_data(instance: dict[str, Any]) -> dict[str, Any]:
    expected = instance.get("expected")
    if isinstance(expected, dict):
        return expected

    reference_text = content_text(instance.get("reference"))
    if reference_text:
        try:
            parsed = json.loads(reference_text)
        except json.JSONDecodeError:
            parsed = {}
        if isinstance(parsed, dict):
            return parsed
    return {}


def section(text: str, heading: str) -> str:
    pattern = re.compile(
        rf"(?is)^#+\s*{re.escape(heading)}\s*$([\s\S]*?)(?=^#+\s|\Z)",
        re.MULTILINE,
    )
    match = pattern.search(text)
    return match.group(1).strip() if match else ""


def contains_all(text: str, terms: list[str]) -> tuple[bool, list[str]]:
    lower = text.lower()
    missing = [term for term in terms if term.lower() not in lower]
    return not missing, missing


def contains_any(text: str, terms: list[str]) -> tuple[bool, list[str]]:
    lower = text.lower()
    present = [term for term in terms if term.lower() in lower]
    return bool(present), present


def detected_classification(text: str) -> str | None:
    classification_section = section(text, "Incident Classification")
    haystack = classification_section or text[:500]
    for classification in ALLOWED_CLASSIFICATIONS:
        if classification.lower() in haystack.lower():
            return classification
    return None


def detected_severity(text: str) -> str | None:
    severity_section = section(text, "Severity")
    haystack = severity_section or text[:800]
    for severity in ALLOWED_SEVERITIES:
        if re.search(rf"\b{severity}\b", haystack, re.IGNORECASE):
            return severity
    return None


def has_required_sections(text: str) -> bool:
    headings = [
        "Incident Classification",
        "Severity",
        "Summary",
        "Evidence From Logs",
        "Confidence",
        "Recommended Next Investigation Steps",
        "Uncertainty / Missing Evidence",
    ]
    return all(section(text, heading) for heading in headings)


def metric_result(score: float, explanation: str) -> dict[str, Any]:
    return {"score": round(float(score), 4), "explanation": explanation}


def binary_score(ok: bool) -> float:
    return PASS_SCORE if ok else FAIL_SCORE


def evaluate_metric(instance: dict[str, Any], metric: str) -> dict[str, Any]:
    text = response_text(instance)
    expected = expected_data(instance)

    if not text:
        return metric_result(0, "No final text response found in trace.")

    if metric == "classification":
        actual = detected_classification(text)
        acceptable = expected.get("acceptable_classifications") or [
            expected.get("classification")
        ]
        acceptable = [item for item in acceptable if item]
        ok = actual in acceptable
        return metric_result(
            binary_score(ok),
            f"Detected classification={actual!r}; acceptable={acceptable!r}.",
        )

    if metric == "severity":
        actual = detected_severity(text)
        acceptable = expected.get("acceptable_severities") or []
        ok = actual in acceptable
        return metric_result(
            binary_score(ok),
            f"Detected severity={actual!r}; acceptable={acceptable!r}.",
        )

    if metric == "evidence_grounding":
        evidence = section(text, "Evidence From Logs")
        terms = expected.get("evidence_terms") or []
        terms_ok, missing_terms = contains_all(evidence or text, terms)
        line_ref_ok = bool(re.search(r"\bline\s+\d+\b", evidence, re.IGNORECASE))
        score = binary_score(terms_ok and line_ref_ok)
        details = []
        if missing_terms:
            details.append(f"missing expected evidence terms: {missing_terms}")
        if not line_ref_ok:
            details.append("missing line-number evidence references")
        return metric_result(score, "; ".join(details) or "Expected evidence present.")

    if metric == "hallucination":
        unacceptable = expected.get("unacceptable_terms") or []
        ok, present = contains_any(text, unacceptable)
        if ok:
            return metric_result(
                FAIL_SCORE, f"Found unacceptable unsupported terms: {present}."
            )
        if "root cause is" in text.lower() and expected.get("require_uncertainty"):
            return metric_result(
                FAIL_SCORE,
                "Uses firm root-cause language despite uncertainty requirement.",
            )
        return metric_result(
            PASS_SCORE, "No configured hallucination trigger terms found."
        )

    if metric == "uncertainty":
        uncertainty = section(text, "Uncertainty / Missing Evidence")
        require_uncertainty = bool(expected.get("require_uncertainty"))
        terms = expected.get("uncertainty_terms") or []
        target_text = uncertainty or text
        has_general_uncertainty, _ = contains_any(target_text, UNCERTAINTY_WORDS)
        has_case_uncertainty, present_case_terms = contains_any(target_text, terms)
        overconfident_phrases = [
            "no significant uncertainties",
            "no ambiguity",
            "no missing evidence",
            "there are no significant uncertainties",
        ]
        overconfident, present_overconfident = contains_any(
            target_text, overconfident_phrases
        )
        ok = True
        reasons = []
        if require_uncertainty and not (
            has_general_uncertainty or has_case_uncertainty
        ):
            ok = False
            reasons.append("missing explicit uncertainty language")
        if require_uncertainty and terms and not has_case_uncertainty:
            ok = False
            reasons.append(f"missing case uncertainty terms; expected one of {terms!r}")
        if overconfident:
            ok = False
            reasons.append(
                f"overconfident uncertainty language: {present_overconfident!r}"
            )
        if ok:
            reasons.append(f"uncertainty terms present: {present_case_terms!r}")
        return metric_result(binary_score(ok), "; ".join(reasons))

    if metric == "recommendations":
        recommendations = section(text, "Recommended Next Investigation Steps")
        required = expected.get("recommendation_terms") or []
        _, present_required = contains_any(recommendations or text, required)
        forbidden = DEFAULT_FORBIDDEN_RECOMMENDATIONS + (
            expected.get("forbidden_recommendation_terms") or []
        )
        has_forbidden, present_forbidden = contains_any(recommendations, forbidden)
        ok = bool(present_required) and not has_forbidden
        reasons = []
        if not present_required:
            reasons.append(
                f"missing recommendation terms; expected one of {required!r}"
            )
        if has_forbidden:
            reasons.append(f"contains remediation-like terms: {present_forbidden!r}")
        return metric_result(
            binary_score(ok), "; ".join(reasons) or "Recommendations look relevant."
        )

    if metric == "summary_quality":
        summary = section(text, "Summary")
        terms = expected.get("summary_terms") or []
        _, present_terms = contains_any(summary or text, terms)
        unacceptable = expected.get("unacceptable_terms") or []
        has_bad_terms, present_bad = contains_any(summary, unacceptable)
        ok = bool(summary) and bool(present_terms) and not has_bad_terms
        reasons = []
        if not summary:
            reasons.append("missing Summary section")
        if not present_terms:
            reasons.append(f"summary lacks expected terms; expected one of {terms!r}")
        if has_bad_terms:
            reasons.append(f"summary contains unsupported terms: {present_bad!r}")
        return metric_result(
            binary_score(ok), "; ".join(reasons) or "Summary matches expected signals."
        )

    if metric == "format":
        ok = has_required_sections(text)
        return metric_result(
            binary_score(ok),
            "Required report sections present."
            if ok
            else "Missing required report sections.",
        )

    if metric == "overall":
        component_metrics = [
            "classification",
            "severity",
            "evidence_grounding",
            "hallucination",
            "uncertainty",
            "recommendations",
            "summary_quality",
            "format",
        ]
        component_results = {
            name: evaluate_metric(instance, name) for name in component_metrics
        }
        score = sum(result["score"] for result in component_results.values()) / len(
            component_results
        )
        failed = [
            f"{name}: {result['explanation']}"
            for name, result in component_results.items()
            if result["score"] < PASS_SCORE
        ]
        return metric_result(
            score, " | ".join(failed) if failed else "All component checks passed."
        )

    raise ValueError(f"Unknown IncidentLens metric: {metric}")


def iter_trace_cases(traces_dir: Path) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for path in sorted(traces_dir.rglob("*.json")):
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, list):
            candidates = data
        elif isinstance(data, dict) and isinstance(data.get("eval_cases"), list):
            candidates = data["eval_cases"]
        elif isinstance(data, dict):
            candidates = [data]
        else:
            candidates = []
        for candidate in candidates:
            if isinstance(candidate, dict):
                candidate = dict(candidate)
                candidate["_trace_file"] = str(path)
                cases.append(candidate)
    return cases


def merge_expected(
    trace_case: dict[str, Any], dataset_case: dict[str, Any]
) -> dict[str, Any]:
    merged = dict(trace_case)
    for key in [
        "eval_case_id",
        "description",
        "category_group",
        "expected",
        "reference",
        "prompt",
    ]:
        if key not in merged and key in dataset_case:
            merged[key] = dataset_case[key]
    return merged
