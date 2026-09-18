# IncidentLens Eval Fix Log

Date: 2026-09-17

## Inputs Reviewed

- `docs/LOCAL_TEST_NOTES.md`
- `docs/EVAL_REPORT.md`
- `tests/eval/datasets/incidentlens-baseline.json`
- `tests/eval/results/incidentlens_baseline_20260917_121927.json`
- `app/agent.py`
- `app/tools.py`

`docs/PRODUCT_SPEC.md` was requested by the next-step instructions but does not
exist in this workspace.

## Baseline Snapshot

- Total scenarios: 20
- Passed scenarios: 3
- Failed scenarios: 17
- Classification: 18 / 20
- Severity: 13 / 20
- Evidence grounding: 20 / 20
- Hallucination: 20 / 20
- Uncertainty handling: 5 / 20
- Recommendations: 16 / 20
- Summary quality: 17 / 20
- Format: 20 / 20

The baseline was generated against the local ADK server at
`http://127.0.0.1:8000`. `agents-cli eval grade` returned a generic failure, so
the report uses deterministic analysis of the generated traces.

## Failure Analysis

| Scenario | Failure type | Expected | Actual | Root cause | Proposed fix |
|---|---|---|---|---|---|
| IL-001 clear application exception | Uncertainty | Mention single-request or limited sample uncertainty | Said there was no uncertainty | Prompt allowed overconfident uncertainty wording | Require uncertainty/missing-evidence wording even for clear samples |
| IL-005 generic service failure | Severity, uncertainty, summary | Unknown, LOW/MEDIUM, insufficient evidence | Unknown, CRITICAL | Tool escalated generic `service unavailable`; prompt did not force evidence-limited severity | Remove generic `service unavailable` critical escalation; tighten severity rules |
| IL-008 conflicting signals | Classification, uncertainty, recommendations | Unknown due separate auth/db signals | Authentication / Authorization | Prompt forced a single category despite unrelated categories | Add mixed/conflicting signal rule using request ID/job ID/service separation |
| IL-013 multiple unrelated incidents | Classification, uncertainty, recommendations, summary | Unknown with multiple/unrelated language | Infrastructure | Prompt collapsed unrelated incidents into one root cause | Add explicit multiple separate incident behavior |
| IL-012 auth failure spike | Severity, uncertainty | Auth, MEDIUM/HIGH, affected-user/scope uncertainty | Auth, LOW | Severity rule underweighted failure-rate evidence | Add failure-rate severity hint and prompt impact calibration |
| IL-015 infrastructure dependency failure | Severity, uncertainty | Infrastructure, HIGH | Infrastructure, MEDIUM | Prompt/tool underweighted broad node/network symptoms | Add high-severity guidance for shared resource or important workflow degradation |
| IL-016 single auth denial | Severity, uncertainty | Auth, LOW | Auth with no detected severity | Warning-only signal did not get a LOW hint; response omitted parseable severity | Give signal-only cases a LOW hint and require one allowed severity |
| IL-017 database degradation | Severity | Database, HIGH | Database, MEDIUM | Tool underweighted failure-rate/degradation evidence | Add failure-rate severity hint |
| IL-020 hallucination trap | Severity, uncertainty | Unknown, LOW/MEDIUM | Unknown, CRITICAL | Generic service failure was over-escalated and uncertainty was too weak | Same fix as IL-005 |

## Priority

1. Evidence-grounding and hallucination safety: protect the existing 20 / 20
   baseline by avoiding any broader architecture or tool changes.
2. Uncertainty handling: largest failure cluster, and central to the product
   requirement that IncidentLens not invent root causes.
3. Severity calibration: reduce unsupported CRITICAL classifications and improve
   failure-rate cases.
4. Recommendation wording: keep next steps investigative, not remediating.
5. Mixed/conflicting input behavior: classify unrelated combined logs as
   `Unknown / Insufficient Evidence`.

## Fixes Implemented

### Prompt / Instruction

`app/agent.py` now adds explicit rules for:

- observed facts vs likely conclusions
- never claiming there is no uncertainty
- generic, truncated, malformed, small, or missing-impact logs
- conflicting categories across request IDs, job IDs, services, or timestamps
- downstream symptoms vs causal category
- severity thresholds from LOW through CRITICAL
- avoiding CRITICAL based only on `service unavailable`, HTTP 500/503, or a few
  error lines
- investigation-only recommendations

### App Logic

`app/tools.py` now:

- treats warning-only/category-only signals as a LOW severity hint instead of
  insufficient severity
- removes generic `service unavailable` from the CRITICAL escalation list
- keeps CRITICAL hints for explicit severe impact such as all requests failing,
  100% failure, no healthy endpoints, outage, database unavailable, or OOMKilled
- raises failure-rate evidence to a HIGH hint when hard errors are present

## Targeted Checks

Completed:

- `uv run python -m py_compile app\agent.py app\tools.py`
- Direct helper checks:
  - generic worker `operation failed` + `service unavailable` -> `Unknown / Insufficient Evidence`, `LOW`
  - explicit `all requests failing` + `no healthy endpoints` -> `Unknown / Insufficient Evidence`, `CRITICAL`
  - single `403 Forbidden` warning -> `Authentication / Authorization`, `LOW`
- ADK server reachability:
  - `GET /dev-ui/?app=app` -> `200`
  - `GET /list-apps` -> `["app"]`
  - `GET /apps/app/app-info` -> `200`

Blocked:

- The running ADK server is still serving the old in-memory instruction.
- This shell does not have `OPENAI_API_KEY` or `GEMINI_API_KEY` in process,
  user, or machine environment variables.
- Full eval comparison was not run because it would evaluate the stale server,
  not the patched agent.

## Full Eval Status

Attempted after the fix with:

```powershell
uv run python tests\eval\run_incidentlens_eval.py --url http://127.0.0.1:8000 --app-name app
```

Result:

- The server was reachable.
- `/apps/app/app-info` confirmed the patched instruction was loaded.
- `agents-cli eval generate` failed before producing traces because the running
  ADK process did not have `OPENAI_API_KEY` available.
- Inference summary: `0/20 succeeded, 20 failed`.
- No post-fix trace artifact was written.

The error reported by the eval command was:

```text
OpenAIException - Missing credentials. Please pass an `api_key`,
`workload_identity`, `admin_api_key`, or set the `OPENAI_API_KEY` or
`OPENAI_ADMIN_KEY` environment variable.
```

Restart the local playground from a terminal where the API key is available,
then run:

```powershell
cd D:\CodexTmp\incidentlens-workspace

$env:Path = 'D:\CodexTmp\google-agents-cli\uv-bin;' + $env:Path
$env:TEMP = 'D:\CodexTmp'
$env:TMP = 'D:\CodexTmp'
$env:UV_CACHE_DIR = 'D:\CodexTmp\uv-cache'
$env:NPM_CONFIG_CACHE = 'D:\CodexTmp\npm-cache'
$env:SQLITE_TMPDIR = 'D:\CodexTmp\adk-sqlite-tmp'
$env:ADK_DISABLE_LOCAL_STORAGE = 'true'
$env:OPENAI_API_KEY = '<set in this terminal>'

agents-cli playground --host 127.0.0.1 --port 8000 --no-reload_agents
```

In a second terminal:

```powershell
cd D:\CodexTmp\incidentlens-workspace
$env:Path = 'D:\CodexTmp\google-agents-cli\uv-bin;' + $env:Path
$env:TEMP = 'D:\CodexTmp'
$env:TMP = 'D:\CodexTmp'
$env:UV_CACHE_DIR = 'D:\CodexTmp\uv-cache'
$env:NPM_CONFIG_CACHE = 'D:\CodexTmp\npm-cache'
$env:SQLITE_TMPDIR = 'D:\CodexTmp\adk-sqlite-tmp'
$env:ADK_DISABLE_LOCAL_STORAGE = 'true'

uv run python tests\eval\run_incidentlens_eval.py --url http://127.0.0.1:8000 --app-name app
```

Before running eval, confirm the restarted server has the patched instruction:

```powershell
(Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/apps/app/app-info).Content -match 'Never state that there is no uncertainty'
```

Expected result: `True`.

## Remaining Questions

- Does the prompt now satisfy uncertainty checks without making all reports too
  hedged?
- Does removing generic `service unavailable` from CRITICAL improve IL-005 and
  IL-020 without regressing IL-018?
- Does the failure-rate severity hint improve IL-012 and IL-017 without making
  low-volume auth or database cases too severe?
- Should the eval runner keep deterministic fallback analysis if
  `agents-cli eval grade` continues to return the generic failure?
