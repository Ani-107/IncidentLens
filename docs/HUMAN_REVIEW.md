# IncidentLens Human Review

Date: 2026-09-17

Note: `docs/PRODUCT_SPEC.md` was requested for review input, but that file does
not exist in this workspace. This review package is based on the original user
requirements, `docs/LOCAL_TEST_NOTES.md`, `docs/EVAL_REPORT.md`,
`docs/EVAL_FIX_LOG.md`, the current implementation, and the current evaluation
dataset.

## 1. PRODUCT OVERVIEW

IncidentLens is an MVP incident-triage agent built with Google's Agent
Development Kit. It helps an engineer or incident responder inspect server and
application logs during a production incident.

The user gives IncidentLens raw log text. Useful logs include timestamps,
service names, request IDs, job IDs, HTTP statuses, exception messages, stack
traces, database errors, authentication failures, container failures, and
resource exhaustion messages.

IncidentLens returns a structured incident report with:

- incident classification
- severity
- summary
- evidence from the supplied logs
- confidence
- recommended next investigation steps
- uncertainty and missing evidence

The intended problem is first-pass triage: quickly separate observed log facts
from likely conclusions, avoid invented evidence, and make clear when the logs
do not support a confident root-cause category.

## 2. USER WORKFLOW

1. User provides logs.
2. IncidentLens calls the `analyze_logs` helper to extract error levels,
   category hints, timestamps, line-numbered signal excerpts, severity hints,
   and missing-evidence notes.
3. IncidentLens classifies the incident as exactly one of:
   - `Application`
   - `Infrastructure`
   - `Database`
   - `Authentication / Authorization`
   - `Unknown / Insufficient Evidence`
4. IncidentLens assigns severity as exactly one of:
   - `LOW`
   - `MEDIUM`
   - `HIGH`
   - `CRITICAL`
5. IncidentLens cites log evidence by line number and excerpt.
6. IncidentLens recommends next investigation steps.
7. IncidentLens states what remains unknown, ambiguous, or missing.

The current prompt explicitly instructs the agent to separate observed facts
from likely conclusions and uncertainty. It also instructs the agent not to
claim there is no uncertainty, because even clear log samples may be missing
traffic, deploy, host, metric, or trace context.

## 3. DEMONSTRATION CASES

The examples below are representative observed outputs from local manual testing
and the baseline evaluation traces. The current code has since received prompt
and tool fixes, but a successful post-fix end-to-end evaluation artifact has not
yet been generated.

### Example 1 - Clear Database Incident

Source: baseline eval case `IL-003-clear-database-deadlock`. This case passed.

Input logs:

```text
Analyze these production logs for incident triage:
2026-09-17T14:10:00Z INFO billing-worker batch_id=batch-44 starting invoice close
2026-09-17T14:10:03Z ERROR billing-worker database transaction failed db=postgres database=billing error="deadlock detected"
2026-09-17T14:10:04Z ERROR postgres pid=7312 relation=invoices deadlock detected while updating row
2026-09-17T14:10:05Z WARN billing-worker retrying SQL transaction attempt=1
2026-09-17T14:10:07Z ERROR billing-worker transaction rollback after lock wait timeout
```

Agent output observed:

- Classification: `Database`
- Severity: `MEDIUM`
- Summary: billing invoice close hit database deadlock and transaction rollback
  errors.
- Evidence identified:
  - line 2: database transaction failed, `deadlock detected`
  - line 3: postgres deadlock while updating row
  - line 5: transaction rollback after lock wait timeout
- Confidence: `HIGH`
- Recommended next steps:
  - investigate deadlock patterns and queries
  - review database logs around the timestamps
  - inspect transaction management and query behavior
- Uncertainty handling: reasonable. It noted that SQL commands, process impact,
  and user impact were missing.

### Example 2 - Noisy Input

Source: baseline eval case `IL-009-noisy-logs`. Classification and severity were
reasonable, but the case failed the deterministic uncertainty metric.

Input logs:

```text
Analyze these production logs for incident triage:
2026-09-17T14:40:00Z INFO cron heartbeat ok
2026-09-17T14:40:01Z DEBUG feature_flag checkout_v2 enabled=false
2026-09-17T14:40:02Z INFO marketing-banner cache refresh complete
2026-09-17T14:40:03Z ERROR cart-api request_id=req-noise database connection timeout after 30000ms db=carts host=postgres-cart
2026-09-17T14:40:04Z INFO metrics scrape duration_ms=18
2026-09-17T14:40:05Z DEBUG request sampler dropped trace_id=abc123
2026-09-17T14:40:06Z WARN cart-api request_id=req-noise retrying database query attempt=1
```

Agent output observed:

- Classification: `Database`
- Severity: `LOW`
- Summary: cart API had a database connection timeout and then retried the same
  request.
- Evidence identified:
  - line 4: database connection timeout to `postgres-cart`
  - line 7: retrying database query attempt 1
- Confidence: `MEDIUM`
- Recommended next steps:
  - inspect database health and logs
  - review application and database connection configuration
  - monitor frequency to decide whether this is isolated or recurring
- Uncertainty handling: partially correct. It mentioned missing database state,
  application state, user impact, and recurrence, but the deterministic eval
  expected more explicit noisy-sample language.

### Example 3 - Mixed-Signal Incident With A Likely Cause

Source: baseline eval case `IL-006-mixed-application-database`. Classification
and severity were reasonable, but the case failed the deterministic uncertainty
metric.

Input logs:

```text
Analyze these production logs for incident triage:
2026-09-17T14:25:00Z INFO checkout-api request_id=req-mix-db POST /checkout started
2026-09-17T14:25:01Z ERROR checkout-api request_id=req-mix-db database connection pool exhausted active=80 idle=0 max=80 db=orders
2026-09-17T14:25:02Z ERROR checkout-api request_id=req-mix-db SQL query timeout after 30000ms query=insert_order
2026-09-17T14:25:03Z ERROR checkout-api request_id=req-mix-db HTTP 500 Internal Server Error route=/checkout
2026-09-17T14:25:04Z ERROR checkout-api request_id=req-mix-db failed to render error response: NullPointerException
```

Agent output observed:

- Classification: `Database`
- Severity: `MEDIUM`
- Summary: database connection pool exhaustion and SQL timeout appear to drive
  downstream application HTTP 500 and error-rendering failures.
- Evidence identified:
  - line 2: database connection pool exhausted
  - line 3: SQL query timeout
  - line 4: HTTP 500
  - line 5: `NullPointerException`
- Confidence: `HIGH`
- Recommended next steps:
  - inspect database connection pool metrics
  - investigate the `insert_order` query
  - review error handling around the downstream `NullPointerException`
- Uncertainty handling: partially correct. It mentioned missing traffic/query
  context, but did not clearly label application errors as likely downstream
  symptoms. The current prompt was updated to make that distinction explicit.

### Example 4 - Insufficient Evidence

Source: baseline eval case `IL-005-unknown-generic-service-failure`. This was an
important failure.

Input logs:

```text
Analyze these production logs for incident triage:
2026-09-17T14:20:00Z INFO worker job_id=job-5001 started
2026-09-17T14:20:02Z ERROR worker job_id=job-5001 operation failed
2026-09-17T14:20:03Z ERROR service unavailable
2026-09-17T14:20:04Z INFO worker retry scheduled job_id=job-5001 delay_ms=5000
```

Agent output observed:

- Classification: `Unknown / Insufficient Evidence`
- Severity: `CRITICAL`
- Summary: job failed and a service was unavailable, but there was not enough
  detail to determine cause or impact.
- Evidence identified:
  - line 2: `operation failed`
  - line 3: `service unavailable`
- Confidence: `MEDIUM`
- Recommended next steps:
  - review preceding logs
  - check metrics around the failure time
  - inspect dependencies for related availability issues
- Uncertainty handling: mixed. The classification correctly avoided inventing a
  category, but the severity was over-escalated from a short generic sample.
  The current tool no longer treats generic `service unavailable` as enough to
  force `CRITICAL`.

### Example 5 - Difficult Edge Case With Malformed Logs

Source: baseline eval case `IL-019-malformed-unusual-logs`. This case passed.

Input logs:

```text
Analyze these production logs for incident triage:
[gw] ??? request_id=req-weird user=unknown status=401 path=/api/profile
not-json {level:error, svc:auth-service, msg:token validation failed, reason:bad-audience}
2026/09/17 15:30:02 WARN auth-service OAuth token rejected audience=mobile-staging expected=incidentlens-api
### malformed trailing line ###
status=403 path=/admin/users role=viewer
```

Agent output observed:

- Classification: `Authentication / Authorization`
- Severity: `LOW`
- Summary: malformed and irregular logs still show token validation, OAuth
  audience, 401, and 403 authorization signals.
- Evidence identified:
  - line 1: status `401` on `/api/profile`
  - line 2: token validation failed, `bad-audience`
  - line 3: OAuth token rejected due audience mismatch
  - line 5: status `403` on `/admin/users`
- Confidence: `MEDIUM`
- Recommended next steps:
  - verify authentication service audience settings
  - gather surrounding logs for frequency and impact
  - inspect roles and permissions for `/admin/users`
- Uncertainty handling: good. It noted missing timestamps and limited user
  detail.

## 4. FAILURE EXAMPLES

### Failure 1 - Generic Service Failure Was Over-Severed

Original input:

```text
2026-09-17T14:20:00Z INFO worker job_id=job-5001 started
2026-09-17T14:20:02Z ERROR worker job_id=job-5001 operation failed
2026-09-17T14:20:03Z ERROR service unavailable
2026-09-17T14:20:04Z INFO worker retry scheduled job_id=job-5001 delay_ms=5000
```

Original output:

- Classification: `Unknown / Insufficient Evidence`
- Severity: `CRITICAL`
- Confidence: `MEDIUM`
- Rationale included only two error lines and `service unavailable`.

Why problematic:

- The classification was appropriately cautious, but severity was unsupported.
- The logs did not show all requests failing, customer-wide impact, no healthy
  endpoints, data loss, or a sustained outage.

What changed:

- `app/tools.py` removed generic `service unavailable` from automatic CRITICAL
  escalation.
- `app/agent.py` now says not to classify CRITICAL from `service unavailable`,
  HTTP 500/503, or a small number of error lines alone.

Current behavior:

- Direct helper check now suggests `Unknown / Insufficient Evidence` and `LOW`
  for a generic worker failure plus `service unavailable`.
- End-to-end post-fix agent output has not yet been successfully evaluated
  because the latest eval run failed due missing `OPENAI_API_KEY` in the ADK
  process.

### Failure 2 - Conflicting Signals Were Forced Into One Category

Original input:

```text
2026-09-17T14:35:00Z ERROR api request_id=req-a database connection timeout after 10000ms db=orders
2026-09-17T14:35:01Z WARN gateway request_id=req-b HTTP 401 Unauthorized path=/api/profile
2026-09-17T14:35:02Z ERROR auth-service request_id=req-b token validation failed reason="expired token"
2026-09-17T14:35:03Z ERROR api request_id=req-c SQL query timeout query=get_cart
2026-09-17T14:35:04Z WARN gateway request_id=req-d HTTP 403 Forbidden path=/admin role=viewer
```

Original output:

- Classification: `Authentication / Authorization`
- Severity: `MEDIUM`
- Evidence included both database and auth lines.

Why problematic:

- The logs contain database and auth signals from different request IDs with no
  causal chain.
- The expected behavior was `Unknown / Insufficient Evidence`, with explicit
  language about conflicting or separate incidents.

What changed:

- `app/agent.py` now instructs the agent to classify as
  `Unknown / Insufficient Evidence` when conflicting categories appear across
  different request IDs, job IDs, services, or timestamps with no causal link.

Current behavior:

- Not yet verified by a successful post-fix end-to-end eval run.
- The updated prompt is visible through `/apps/app/app-info`.

### Failure 3 - Multiple Unrelated Incidents Were Collapsed Into One Cause

Original input:

```text
2026-09-17T15:00:00Z ERROR inventory-api request_id=req-inv database deadlock detected table=stock_reservations
2026-09-17T15:00:01Z ERROR inventory-api request_id=req-inv transaction rollback after lock wait timeout
2026-09-17T15:00:20Z ERROR media-worker job_id=img-77 OOMKilled memory cgroup out of memory
2026-09-17T15:00:21Z ERROR kubelet pod=media-worker-2 container app exited code=137 reason=OOMKilled
2026-09-17T15:00:22Z INFO gateway unrelated request completed status=200
```

Original output:

- Classification: `Infrastructure`
- Severity: `CRITICAL`
- Confidence: `HIGH`
- Uncertainty section said there was no uncertainty.

Why problematic:

- The input combines a database deadlock and an unrelated media-worker OOM event.
- A single infrastructure classification overstates certainty and masks the
  possibility of multiple separate incidents.

What changed:

- `app/agent.py` now explicitly tells the agent to say there may be multiple
  separate or unrelated incidents and use `Unknown / Insufficient Evidence` when
  no causal chain links the categories.
- The prompt also says never to state that there is no uncertainty.

Current behavior:

- Not yet verified by a successful post-fix end-to-end eval run.
- This remains a high-priority review case.

## 5. EVALUATION RESULTS

Baseline evaluation:

- Dataset: `tests/eval/datasets/incidentlens-baseline.json`
- Scenarios: 20
- Passed: 3
- Failed: 17
- Command:

```powershell
uv run python tests\eval\run_incidentlens_eval.py --url http://127.0.0.1:8000 --app-name app
```

Baseline metric results:

| Metric | Passed | Total |
|---|---:|---:|
| classification | 18 | 20 |
| severity | 13 | 20 |
| evidence_grounding | 20 | 20 |
| hallucination | 20 | 20 |
| uncertainty | 5 | 20 |
| recommendations | 16 | 20 |
| summary_quality | 17 | 20 |
| format | 20 | 20 |
| overall | 3 | 20 |

Post-fix results:

- No successful post-fix end-to-end evaluation result is available in the
  workspace.
- A post-fix eval attempt reached the patched server, but all 20 inference cases
  failed before agent response because the running ADK process did not have
  `OPENAI_API_KEY` in its environment.
- No post-fix trace artifact or comparison artifact was written.

Major improvements implemented but not yet measured end to end:

- Stronger uncertainty instructions.
- Explicit mixed/conflicting signal handling.
- Severity rules that require observed impact for CRITICAL.
- Investigation-only recommendation guidance.
- Tool severity hint changes for generic `service unavailable`, warning-only
  signals, and failure-rate evidence.

Remaining failures known from baseline:

- uncertainty handling failed 15 / 20 cases
- severity failed 7 / 20 cases
- classification failed 2 / 20 cases
- recommendations failed 4 / 20 cases
- summary quality failed 3 / 20 cases

Regressions:

- No post-fix regression data exists yet. A successful post-fix eval run is
  needed before claiming any regression status.

## 6. CURRENT CAPABILITIES

Based on manual testing, baseline eval traces, and direct helper checks, the
current version can do the following:

- Start as an ADK app named `app` with root agent `incidentlens`.
- Use LiteLLM with the configured model, defaulting to `openai/gpt-4o-mini`.
- Accept pasted logs through the ADK playground or local ADK endpoints.
- Call `analyze_logs` to extract line-numbered signals from raw logs.
- Return the required report sections.
- Cite evidence from supplied logs with line numbers.
- Correctly identify clear database, application, infrastructure, and
  authentication/authorization examples in manual testing.
- Correctly classify several clear eval examples, with 18 / 20 baseline
  classification checks passing.
- Avoid configured hallucination trigger terms in the baseline deterministic
  eval, with 20 / 20 hallucination checks passing.
- Maintain report format in the baseline deterministic eval, with 20 / 20
  format checks passing.
- Produce low-confidence `Unknown / Insufficient Evidence` output for at least
  one simple manual insufficient-evidence example.

## 7. CURRENT LIMITATIONS

The following has not been demonstrated or cannot yet be trusted:

- A successful post-fix end-to-end evaluation run.
- Production readiness.
- Robust severity calibration across ambiguous or small samples.
- Consistent uncertainty language across all categories.
- Reliable behavior on unrelated incidents combined in one input.
- Reliable behavior on conflicting signals from different request IDs.
- Resistance to prompt injection text embedded inside logs.
- Handling of very large logs beyond the simple MVP path.
- Handling of non-text logs, structured traces, metrics, dashboards, or alerts.
- Any deployment, observability, Slack/email integration, automatic remediation,
  or production incident workflow integration.
- Guaranteed deterministic output, because the model call can vary.
- Operation without a valid model API key.

## 8. KNOWN RISKS

- Hallucinated evidence: baseline checks did not find configured hallucination
  trigger terms, but that does not prove the model will never invent evidence.
- Unsupported root-cause conclusions: mixed or ambiguous logs may still tempt
  the model to choose a single explanation.
- Incorrect severity: baseline severity failed 7 / 20 cases, especially generic
  service failures and failure-rate/degradation cases.
- Incomplete logs: small samples can lead to overconfident impact or root-cause
  language.
- Noisy logs: the agent can filter noise, but uncertainty wording around noisy
  samples needs review.
- Ambiguous incidents: unrelated or conflicting signals are a known difficult
  path and need post-fix validation.
- Prompt injection inside log data: no dedicated injection eval exists yet. Logs
  might contain text that attempts to override instructions.
- Model/API failures: local eval failed when the ADK process lacked
  `OPENAI_API_KEY`; API rate limits, quota errors, or missing credentials can
  prevent incident reports.
- Evaluation design: deterministic text metrics can miss nuanced failures and
  can penalize wording differences.

## 9. HUMAN REVIEW QUESTIONS

Reviewer checklist:

- Does this solve the intended user problem of first-pass log triage?
- Are classifications understandable?
- Is the evidence actually supported by the supplied logs?
- Does the agent distinguish facts from inference?
- Does it admit uncertainty appropriately?
- Are severity assessments reasonable for the observed impact?
- Are recommended next steps useful and investigation-oriented?
- Would I trust this output during a real incident as a triage aid?
- What would prevent me from using it during an incident?
- Does the agent avoid inventing timestamps, services, causes, or impact?
- Does it handle incomplete, noisy, malformed, and ambiguous logs cautiously?
- Are the current eval metrics aligned with the product behavior we want?
- What additional test cases are needed before broader use?

## 10. PRODUCT DECISION INPUTS

Demonstrated strengths:

- Clear report structure is consistently produced in baseline eval.
- Evidence-grounding checks passed in baseline eval.
- Classification was strong on the baseline suite, passing 18 / 20 cases.
- Manual tests showed good behavior on clear database, application,
  infrastructure, authentication, and insufficient-evidence examples.
- The implementation is small and easy to inspect.

Known weaknesses:

- Baseline overall pass rate was low: 3 / 20.
- Uncertainty handling was the largest failure cluster.
- Severity calibration was unreliable for several important cases.
- Mixed or unrelated incidents were sometimes forced into a single category.
- Some recommendations drifted toward remediation rather than investigation.
- Post-fix quality has not been measured end to end.

Unresolved questions:

- Did the prompt/tool fixes improve uncertainty without making every report too
  hedged?
- Did severity improve without regressing clear CRITICAL cases?
- Does the agent now classify conflicting and unrelated multi-incident inputs as
  `Unknown / Insufficient Evidence`?
- Should severity be conservative by default when only a small sample is
  available?
- Should the eval include prompt-injection-in-log cases?

Additional evidence needed:

- Successful post-fix eval run against all 20 cases.
- Side-by-side baseline vs candidate comparison.
- Human review of the five demo scenarios and at least the three failure
  scenarios.
- Additional tests for prompt injection, long logs, structured JSON logs, and
  multi-service incidents.
- A better evaluation rubric for semantic quality beyond deterministic keyword
  checks.

Potential next features:

- Larger and more realistic eval dataset.
- Prompt-injection safety cases for malicious log content.
- Optional structured JSON output for downstream tooling.
- Configurable severity policy.
- Better handling of multi-incident inputs.
- Log chunking/summarization for larger inputs.
- Integration with metrics or traces to validate impact claims.

