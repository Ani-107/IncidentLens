# IncidentLens Evaluation Report

Date: 2026-09-17

## Evaluation Command

```powershell
uv run python tests/eval/run_incidentlens_eval.py --url http://127.0.0.1:8000 --app-name app
```

This baseline used `agents-cli eval generate` against the running local ADK server. `agents-cli eval grade` loaded the local deterministic custom metrics and the 20 generated traces, but returned a generic `Evaluation failed` error without writing a grade-result artifact. The baseline below is computed from the same generated ADK traces using the same deterministic metric library.

## Baseline Results

- Total scenarios: 20
- Passed scenarios: 7
- Failed scenarios: 13
- Machine-readable baseline: `D:\CodexTmp\incidentlens-workspace\tests\eval\results\incidentlens_baseline_20260917_131228.json`
- Latest agents-cli grade result: `None`
- agents-cli grade return code: `1`
- agents-cli grade note: `agents-cli eval grade failed; deterministic trace analysis still completed.`

## Metric Results

| Group | Passed | Total |
|---|---:|---:|
| classification | 17 | 20 |
| severity | 19 | 20 |
| evidence_grounding | 20 | 20 |
| hallucination | 20 | 20 |
| uncertainty | 10 | 20 |
| recommendations | 16 | 20 |
| summary_quality | 16 | 20 |
| format | 20 | 20 |
| overall | 7 | 20 |

## Results By Incident Classification

| Group | Passed | Total |
|---|---:|---:|
| Application | 0 | 3 |
| Authentication / Authorization | 3 | 4 |
| Database | 3 | 5 |
| Infrastructure | 1 | 4 |
| Unknown / Insufficient Evidence | 0 | 4 |

## Results By Severity

| Group | Passed | Total |
|---|---:|---:|
| CRITICAL | 1 | 1 |
| HIGH | 1 | 2 |
| HIGH/CRITICAL | 0 | 3 |
| LOW | 1 | 1 |
| LOW/MEDIUM | 3 | 7 |
| MEDIUM | 0 | 2 |
| MEDIUM/HIGH | 1 | 4 |

## Failure Counts

- Evidence-grounding failures: 0
- Hallucination failures: 0
- Uncertainty-handling failures: 10
- Recommendation failures: 4

## Failure Patterns

- classification problem: 3
- prompt/instruction problem: 4
- severity problem: 1
- summary quality problem: 4
- uncertainty problem: 10

## Representative Successful Cases

### IL-003-clear-database-deadlock

- Description: Clear database incident with deadlocks and transaction failures.
- Detected classification: Database
- Detected severity: MEDIUM

### IL-004-clear-auth-token-validation

- Description: Clear authentication and authorization failures.
- Detected classification: Authentication / Authorization
- Detected severity: LOW

### IL-009-noisy-logs

- Description: Noisy logs with irrelevant debug/info lines and one real database signal.
- Detected classification: Database
- Detected severity: LOW

## Representative Failed Cases

### IL-013-multiple-unrelated-incidents

- Description: Two unrelated incidents in one input should not be forced into one root cause.
- Failed metrics: classification, recommendations, summary_quality, overall
- Failure patterns: classification problem, prompt/instruction problem, summary quality problem
- classification: Detected classification='Infrastructure'; acceptable=['Unknown / Insufficient Evidence'].
- recommendations: missing recommendation terms; expected one of ['separate', 'timeline', 'request_id', 'job_id']
- summary_quality: summary lacks expected terms; expected one of ['multiple', 'unrelated']
- overall: classification: Detected classification='Infrastructure'; acceptable=['Unknown / Insufficient Evidence']. | recommendations: missing recommendation terms; expected one of ['separate', 'timeline', 'request_id', 'job_id'] | summary_quality: summary lacks expected terms; expected one of ['multiple', 'unrelated']

### IL-008-conflicting-signals

- Description: Database and auth signals appear for different requests with no clear single incident.
- Failed metrics: classification, uncertainty, recommendations, overall
- Failure patterns: classification problem, prompt/instruction problem, uncertainty problem
- classification: Detected classification='Authentication / Authorization'; acceptable=['Unknown / Insufficient Evidence'].
- uncertainty: missing case uncertainty terms; expected one of ['conflicting', 'multiple', 'insufficient', 'separate']
- recommendations: missing recommendation terms; expected one of ['request_id', 'correlate', 'separate', 'timeline']
- overall: classification: Detected classification='Authentication / Authorization'; acceptable=['Unknown / Insufficient Evidence']. | uncertainty: missing case uncertainty terms; expected one of ['conflicting', 'multiple', 'insufficient', 'separate'] | recommendations: missing recommendation terms; expected one of ['request_id', 'correlate', 'separate', 'timeline']

### IL-020-deliberate-hallucination-test

- Description: Ambiguous errors designed to catch invented root causes.
- Failed metrics: uncertainty, summary_quality, overall
- Failure patterns: summary quality problem, uncertainty problem
- uncertainty: missing explicit uncertainty language; missing case uncertainty terms; expected one of ['insufficient', 'cannot determine', 'missing', 'unknown']
- summary_quality: summary lacks expected terms; expected one of ['request failed', 'service unavailable']
- overall: uncertainty: missing explicit uncertainty language; missing case uncertainty terms; expected one of ['insufficient', 'cannot determine', 'missing', 'unknown'] | summary_quality: summary lacks expected terms; expected one of ['request failed', 'service unavailable']

## Agent Problems

- Overconfident impact or uncertainty wording when only a small log sample is available should be treated as an agent prompt problem.
- Remediation-like recommendations should be treated as an agent prompt problem because IncidentLens should recommend investigation only.
- Unsupported root-cause language or invented services/causes should be treated as an agent grounding problem.

## Evaluation-Design Problems

- The current baseline uses deterministic text checks, so it can miss nuanced response-quality failures and can flag wording differences as failures.
- Some acceptable severity ranges are intentionally narrow to expose weaknesses; these thresholds may need review after the baseline is discussed.
- The deterministic recommendation checks use keyword heuristics and should later be complemented by a judge rubric if we want more semantic grading.

## What Should Be Fixed First

Do not change the agent until this baseline is accepted. When fixing begins, start with prompt changes that force severity and impact claims to be explicitly tied to observed log evidence, then tighten investigation-only recommendation wording, then revisit mixed-signal classification behavior.
