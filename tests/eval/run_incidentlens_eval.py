"""Run the IncidentLens baseline evaluation suite and write a report."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
EVAL_DIR = ROOT / "tests" / "eval"
DATASET = EVAL_DIR / "datasets" / "incidentlens-baseline.json"
CONFIG = EVAL_DIR / "incidentlens_eval_config.yaml"
RESULTS_DIR = EVAL_DIR / "results"
ARTIFACTS_DIR = ROOT / "artifacts" / "incidentlens_eval"
REPORT = ROOT / "docs" / "EVAL_REPORT.md"

_spec = importlib.util.spec_from_file_location(
    "incidentlens_eval_lib", EVAL_DIR / "incidentlens_eval_lib.py"
)
eval_lib = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(eval_lib)

METRICS = [
    "classification",
    "severity",
    "evidence_grounding",
    "hallucination",
    "uncertainty",
    "recommendations",
    "summary_quality",
    "format",
    "overall",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--app-name", default="app")
    parser.add_argument("--dataset", type=Path, default=DATASET)
    parser.add_argument("--config", type=Path, default=CONFIG)
    parser.add_argument("--timestamp", default=datetime.now().strftime("%Y%m%d_%H%M%S"))
    parser.add_argument(
        "--traces-dir",
        type=Path,
        help="Reuse an existing traces directory and skip eval generate.",
    )
    return parser.parse_args()


def eval_env() -> dict[str, str]:
    env = os.environ.copy()
    uv_bin = Path(r"D:\CodexTmp\google-agents-cli\uv-bin")
    if uv_bin.exists():
        env["Path"] = f"{uv_bin};{env.get('Path', '')}"
    env.setdefault("TEMP", r"D:\CodexTmp")
    env.setdefault("TMP", r"D:\CodexTmp")
    env.setdefault("UV_CACHE_DIR", r"D:\CodexTmp\uv-cache")
    env.setdefault("NPM_CONFIG_CACHE", r"D:\CodexTmp\npm-cache")
    env.setdefault("SQLITE_TMPDIR", r"D:\CodexTmp\adk-sqlite-tmp")
    env.setdefault("ADK_DISABLE_LOCAL_STORAGE", "true")
    return env


def run_command(command: list[str], env: dict[str, str]) -> subprocess.CompletedProcess:
    print("$ " + " ".join(command), flush=True)
    return subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )


def run_generate(
    args: argparse.Namespace, traces_dir: Path, env: dict[str, str]
) -> dict[str, Any]:
    traces_dir.mkdir(parents=True, exist_ok=True)
    command = [
        "agents-cli",
        "eval",
        "generate",
        "--dataset",
        str(args.dataset),
        "--url",
        args.url,
        "--app-name",
        args.app_name,
        "--output",
        str(traces_dir),
    ]
    result = run_command(command, env)
    if result.returncode != 0 and "--output" in result.stdout:
        fallback = [*command[:-2], "-o", str(traces_dir)]
        result = run_command(fallback, env)
    if result.returncode != 0:
        raise RuntimeError(f"eval generate failed:\n{result.stdout}")
    return {
        "command": command,
        "stdout": result.stdout,
        "returncode": result.returncode,
    }


def run_grade(
    args: argparse.Namespace, traces_dir: Path, grade_dir: Path, env: dict[str, str]
) -> dict[str, Any]:
    grade_dir.mkdir(parents=True, exist_ok=True)
    command = [
        "agents-cli",
        "eval",
        "grade",
        "--traces",
        str(traces_dir),
        "--config",
        str(args.config),
        "--output",
        str(grade_dir),
    ]
    result = run_command(command, env)
    used_command = command
    if result.returncode != 0:
        fallback = command[:-2]
        fallback_result = run_command(fallback, env)
        if fallback_result.returncode == 0:
            result = fallback_result
            used_command = fallback
    if result.returncode != 0:
        return {
            "command": used_command,
            "stdout": result.stdout,
            "returncode": result.returncode,
            "latest_grade_result": None,
            "error": "agents-cli eval grade failed; deterministic trace analysis still completed.",
        }
    grade_files = sorted(grade_dir.glob("results_*.json"))
    if not grade_files:
        default_grade_dir = ROOT / "artifacts" / "grade_results"
        grade_files = sorted(default_grade_dir.glob("results_*.json"))
    return {
        "command": used_command,
        "stdout": result.stdout,
        "returncode": result.returncode,
        "latest_grade_result": str(grade_files[-1]) if grade_files else None,
    }


def load_dataset(path: Path) -> dict[str, dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    return {case["eval_case_id"]: case for case in data["eval_cases"]}


def score_case(case: dict[str, Any]) -> dict[str, Any]:
    metrics = {metric: eval_lib.evaluate_metric(case, metric) for metric in METRICS}
    failed_metrics = [
        metric for metric in METRICS if metrics[metric]["score"] < eval_lib.PASS_SCORE
    ]
    return {
        "metrics": metrics,
        "passed": not failed_metrics,
        "failed_metrics": failed_metrics,
        "response_text": eval_lib.response_text(case),
        "detected_classification": eval_lib.detected_classification(
            eval_lib.response_text(case)
        ),
        "detected_severity": eval_lib.detected_severity(eval_lib.response_text(case)),
    }


def failure_patterns(failed_metrics: list[str]) -> list[str]:
    patterns = []
    mapping = {
        "classification": "classification problem",
        "severity": "severity problem",
        "evidence_grounding": "evidence extraction / grounding problem",
        "hallucination": "hallucination problem",
        "uncertainty": "uncertainty problem",
        "recommendations": "prompt/instruction problem",
        "summary_quality": "summary quality problem",
        "format": "output formatting problem",
    }
    for metric in failed_metrics:
        if metric in mapping:
            patterns.append(mapping[metric])
    if not patterns and failed_metrics:
        patterns.append("evaluation problem")
    return sorted(set(patterns))


def analyze(
    dataset_cases: dict[str, dict[str, Any]], traces_dir: Path
) -> dict[str, Any]:
    trace_cases = eval_lib.iter_trace_cases(traces_dir)
    merged_cases = []
    seen = set()
    for trace_case in trace_cases:
        case_id = trace_case.get("eval_case_id")
        if not case_id or case_id not in dataset_cases:
            continue
        merged = eval_lib.merge_expected(trace_case, dataset_cases[case_id])
        scored = score_case(merged)
        expected = eval_lib.expected_data(merged)
        merged_cases.append(
            {
                "eval_case_id": case_id,
                "description": merged.get("description", ""),
                "category_group": merged.get("category_group", ""),
                "expected_classification": expected.get("classification"),
                "acceptable_severities": expected.get("acceptable_severities", []),
                **scored,
                "failure_patterns": failure_patterns(scored["failed_metrics"]),
                "trace_file": merged.get("_trace_file"),
            }
        )
        seen.add(case_id)

    for case_id, dataset_case in dataset_cases.items():
        if case_id in seen:
            continue
        merged = eval_lib.merge_expected({}, dataset_case)
        scored = score_case(merged)
        merged_cases.append(
            {
                "eval_case_id": case_id,
                "description": dataset_case.get("description", ""),
                "category_group": dataset_case.get("category_group", ""),
                "expected_classification": dataset_case.get("expected", {}).get(
                    "classification"
                ),
                "acceptable_severities": dataset_case.get("expected", {}).get(
                    "acceptable_severities", []
                ),
                **scored,
                "failure_patterns": ["application/code problem"],
                "trace_file": None,
            }
        )

    total = len(dataset_cases)
    passed = sum(1 for case in merged_cases if case["passed"])
    metric_pass_counts = {
        metric: sum(
            1
            for case in merged_cases
            if case["metrics"][metric]["score"] >= eval_lib.PASS_SCORE
        )
        for metric in METRICS
    }
    by_classification = defaultdict(lambda: {"total": 0, "passed": 0})
    by_severity = defaultdict(lambda: {"total": 0, "passed": 0})
    pattern_counts = Counter()

    for case in merged_cases:
        by_classification[case["expected_classification"]]["total"] += 1
        by_classification[case["expected_classification"]]["passed"] += int(
            case["passed"]
        )
        acceptable_severities = case.get("acceptable_severities") or []
        if isinstance(acceptable_severities, str):
            severity_key = acceptable_severities
        else:
            severity_key = "/".join(str(item) for item in acceptable_severities)
        by_severity[severity_key]["total"] += 1
        by_severity[severity_key]["passed"] += int(case["passed"])
        pattern_counts.update(case["failure_patterns"])

    return {
        "total_scenarios": total,
        "passed_scenarios": passed,
        "failed_scenarios": total - passed,
        "metric_pass_counts": metric_pass_counts,
        "results_by_incident_classification": dict(by_classification),
        "results_by_severity": dict(by_severity),
        "failure_pattern_counts": dict(pattern_counts),
        "cases": sorted(merged_cases, key=lambda item: str(item["eval_case_id"])),
    }


def representative_cases(
    cases: list[dict[str, Any]], passed: bool, limit: int = 3
) -> list[dict[str, Any]]:
    selected = [case for case in cases if case["passed"] is passed]
    if not passed:
        selected = sorted(
            selected,
            key=lambda item: (len(item["failed_metrics"]), item["eval_case_id"]),
            reverse=True,
        )
    return selected[:limit]


def write_machine_results(
    path: Path,
    args: argparse.Namespace,
    traces_dir: Path,
    grade_dir: Path,
    generate_result: dict[str, Any],
    grade_result: dict[str, Any],
    analysis: dict[str, Any],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "dataset": str(args.dataset),
        "config": str(args.config),
        "url": args.url,
        "app_name": args.app_name,
        "traces_dir": str(traces_dir),
        "grade_dir": str(grade_dir),
        "agents_cli_generate": generate_result,
        "agents_cli_grade": grade_result,
        "analysis": analysis,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def markdown_table(rows: list[tuple[str, int, int]]) -> str:
    lines = ["| Group | Passed | Total |", "|---|---:|---:|"]
    lines.extend(f"| {name} | {passed} | {total} |" for name, passed, total in rows)
    return "\n".join(lines)


def write_report(
    path: Path,
    args: argparse.Namespace,
    result_path: Path,
    analysis: dict[str, Any],
    grade_result: dict[str, Any],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cases = analysis["cases"]
    evidence_failures = [
        case
        for case in cases
        if case["metrics"]["evidence_grounding"]["score"] < eval_lib.PASS_SCORE
    ]
    hallucination_failures = [
        case
        for case in cases
        if case["metrics"]["hallucination"]["score"] < eval_lib.PASS_SCORE
    ]
    uncertainty_failures = [
        case
        for case in cases
        if case["metrics"]["uncertainty"]["score"] < eval_lib.PASS_SCORE
    ]
    recommendation_failures = [
        case
        for case in cases
        if case["metrics"]["recommendations"]["score"] < eval_lib.PASS_SCORE
    ]

    class_rows = [
        (str(name), values["passed"], values["total"])
        for name, values in sorted(
            analysis["results_by_incident_classification"].items()
        )
    ]
    severity_rows = [
        (str(name), values["passed"], values["total"])
        for name, values in sorted(analysis["results_by_severity"].items())
    ]
    metric_rows = [
        (
            metric,
            analysis["metric_pass_counts"][metric],
            analysis["total_scenarios"],
        )
        for metric in METRICS
    ]

    lines = [
        "# IncidentLens Evaluation Report",
        "",
        f"Date: {datetime.now().date().isoformat()}",
        "",
        "## Evaluation Command",
        "",
        "```powershell",
        f"uv run python tests/eval/run_incidentlens_eval.py --url {args.url} --app-name {args.app_name}",
        "```",
        "",
        "This baseline used `agents-cli eval generate` against the running local ADK server. `agents-cli eval grade` loaded the local deterministic custom metrics and the 20 generated traces, but returned a generic `Evaluation failed` error without writing a grade-result artifact. The baseline below is computed from the same generated ADK traces using the same deterministic metric library.",
        "",
        "## Baseline Results",
        "",
        f"- Total scenarios: {analysis['total_scenarios']}",
        f"- Passed scenarios: {analysis['passed_scenarios']}",
        f"- Failed scenarios: {analysis['failed_scenarios']}",
        f"- Machine-readable baseline: `{result_path}`",
        f"- Latest agents-cli grade result: `{grade_result.get('latest_grade_result')}`",
        f"- agents-cli grade return code: `{grade_result.get('returncode')}`",
        f"- agents-cli grade note: `{grade_result.get('error', 'none')}`",
        "",
        "## Metric Results",
        "",
        markdown_table(metric_rows),
        "",
        "## Results By Incident Classification",
        "",
        markdown_table(class_rows),
        "",
        "## Results By Severity",
        "",
        markdown_table(severity_rows),
        "",
        "## Failure Counts",
        "",
        f"- Evidence-grounding failures: {len(evidence_failures)}",
        f"- Hallucination failures: {len(hallucination_failures)}",
        f"- Uncertainty-handling failures: {len(uncertainty_failures)}",
        f"- Recommendation failures: {len(recommendation_failures)}",
        "",
        "## Failure Patterns",
        "",
    ]
    if analysis["failure_pattern_counts"]:
        for name, count in sorted(analysis["failure_pattern_counts"].items()):
            lines.append(f"- {name}: {count}")
    else:
        lines.append("- No failures detected by the deterministic baseline checks.")

    lines.extend(["", "## Representative Successful Cases", ""])
    for case in representative_cases(cases, True):
        lines.extend(
            [
                f"### {case['eval_case_id']}",
                "",
                f"- Description: {case['description']}",
                f"- Detected classification: {case['detected_classification']}",
                f"- Detected severity: {case['detected_severity']}",
                "",
            ]
        )

    lines.extend(["## Representative Failed Cases", ""])
    for case in representative_cases(cases, False):
        lines.extend(
            [
                f"### {case['eval_case_id']}",
                "",
                f"- Description: {case['description']}",
                f"- Failed metrics: {', '.join(case['failed_metrics'])}",
                f"- Failure patterns: {', '.join(case['failure_patterns'])}",
            ]
        )
        for metric in case["failed_metrics"]:
            lines.append(f"- {metric}: {case['metrics'][metric]['explanation']}")
        lines.append("")

    lines.extend(
        [
            "## Agent Problems",
            "",
            "- Overconfident impact or uncertainty wording when only a small log sample is available should be treated as an agent prompt problem.",
            "- Remediation-like recommendations should be treated as an agent prompt problem because IncidentLens should recommend investigation only.",
            "- Unsupported root-cause language or invented services/causes should be treated as an agent grounding problem.",
            "",
            "## Evaluation-Design Problems",
            "",
            "- The current baseline uses deterministic text checks, so it can miss nuanced response-quality failures and can flag wording differences as failures.",
            "- Some acceptable severity ranges are intentionally narrow to expose weaknesses; these thresholds may need review after the baseline is discussed.",
            "- The deterministic recommendation checks use keyword heuristics and should later be complemented by a judge rubric if we want more semantic grading.",
            "",
            "## What Should Be Fixed First",
            "",
            "Do not change the agent until this baseline is accepted. When fixing begins, start with prompt changes that force severity and impact claims to be explicitly tied to observed log evidence, then tighten investigation-only recommendation wording, then revisit mixed-signal classification behavior.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    if (
        not shutil.which("agents-cli")
        and not Path(r"D:\CodexTmp\google-agents-cli\uv-bin\agents-cli.exe").exists()
    ):
        print("agents-cli was not found on PATH.", file=sys.stderr)
        return 2

    timestamp = args.timestamp
    traces_dir = args.traces_dir or ARTIFACTS_DIR / "traces" / f"baseline_{timestamp}"
    grade_dir = ARTIFACTS_DIR / "grade_results" / f"baseline_{timestamp}"
    result_path = RESULTS_DIR / f"incidentlens_baseline_{timestamp}.json"

    env = eval_env()
    if args.traces_dir:
        generate_result = {
            "command": None,
            "stdout": f"Reused existing traces from {traces_dir}",
            "returncode": 0,
        }
    else:
        generate_result = run_generate(args, traces_dir, env)
    grade_result = run_grade(args, traces_dir, grade_dir, env)
    dataset_cases = load_dataset(args.dataset)
    analysis = analyze(dataset_cases, traces_dir)
    write_machine_results(
        result_path,
        args,
        traces_dir,
        grade_dir,
        generate_result,
        grade_result,
        analysis,
    )
    write_report(REPORT, args, result_path, analysis, grade_result)

    print("\nIncidentLens baseline evaluation complete.")
    print(f"Total scenarios: {analysis['total_scenarios']}")
    print(f"Passed scenarios: {analysis['passed_scenarios']}")
    print(f"Failed scenarios: {analysis['failed_scenarios']}")
    print(f"Report: {REPORT}")
    print(f"Machine-readable results: {result_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
