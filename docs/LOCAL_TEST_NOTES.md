# IncidentLens Local Test Notes

Date: 2026-09-17

## Local Server

Workspace:

```text
D:\CodexTmp\incidentlens-workspace
```

The local ADK playground was started from PowerShell with D-drive temp/cache
paths. The API key was set in the local shell and was not written to this file.

```powershell
cd D:\CodexTmp\incidentlens-workspace

$env:Path = 'D:\CodexTmp\google-agents-cli\uv-bin;' + $env:Path
$env:TEMP = 'D:\CodexTmp'
$env:TMP = 'D:\CodexTmp'
$env:UV_CACHE_DIR = 'D:\CodexTmp\uv-cache'
$env:NPM_CONFIG_CACHE = 'D:\CodexTmp\npm-cache'
$env:SQLITE_TMPDIR = 'D:\CodexTmp\adk-sqlite-tmp'
$env:ADK_DISABLE_LOCAL_STORAGE = 'true'
$env:OPENAI_API_KEY = '<set in local PowerShell session>'

agents-cli playground --host 127.0.0.1 --port 8000 --no-reload_agents
```

Observed running process:

```text
adk.exe web . --host 127.0.0.1 --port 8000
```

## URL / Interface

Playground URL:

```text
http://127.0.0.1:8000/dev-ui/?app=app
```

Reachability checks:

```text
GET /dev-ui/?app=app               -> 200
GET /list-apps                     -> 200, ["app"]
GET /apps/app/app-info             -> 200
TCP 127.0.0.1:8000                 -> LISTEN
```

ADK reports the root agent as `incidentlens` and exposes the `analyze_logs`
tool. Runtime traces showed the model provider as OpenAI:

```text
gen_ai.system = openai
gen_ai.request.model = openai/gpt-4o-mini
modelVersion = gpt-4o-mini-2024-07-18
```

## Credit / API Check

After OpenAI credits were added, a live `/run` call succeeded. The agent called
`analyze_logs` and returned a structured incident report.

## Test Scenarios

These were manual local checks against the running ADK `/run` endpoint. No
`agents-cli eval` command, eval dataset, deployment config, or production
integration was created.

### Scenario 1 - Database Incident

Input:

```text
Analyze these production logs for incident triage:
2026-09-17T12:00:01Z INFO checkout-api request_id=req-1001 POST /checkout started user_id=8842
2026-09-17T12:00:02Z ERROR checkout-api request_id=req-1001 database connection timeout after 30000ms host=postgres-primary db=orders
2026-09-17T12:00:02Z ERROR checkout-api request_id=req-1001 failed to persist order: database connection pool exhausted active=50 idle=0 max=50
2026-09-17T12:00:03Z WARN checkout-api request_id=req-1002 retrying database query attempt=1 error="connection timeout"
2026-09-17T12:00:04Z ERROR checkout-api request_id=req-1002 database connection timeout after 30000ms host=postgres-primary db=orders
2026-09-17T12:00:05Z ERROR checkout-api request_id=req-1003 failed POST /checkout status=500 reason="db unavailable"
2026-09-17T12:00:06Z ERROR checkout-worker order_writer repeated database failures count=37 window=60s
```

Actual output:

```text
## Incident Classification
Database, based on multiple observed errors indicating issues with database connectivity and pool exhaustion.

## Severity
MEDIUM, as there are repeated errors related to database timeouts and connection pool exhaustion which are affecting operations but not indicating a complete outage.

## Summary
The logs indicate that there are significant issues with database connectivity during checkout API operations. Multiple requests are failing due to timeouts and a connection pool that has reached its maximum capacity. This has resulted in at least one failed order request and a significant number of repeated database failure alerts.

## Evidence From Logs
- Line 2: `2026-09-17T12:00:02Z ERROR checkout-api request_id=req-1001 database connection timeout after 30000ms host=postgres-primary db=orders`
- Line 3: `2026-09-17T12:00:02Z ERROR checkout-api request_id=req-1001 failed to persist order: database connection pool exhausted active=50 idle=0 max=50`
- Line 4: `2026-09-17T12:00:03Z WARN checkout-api request_id=req-1002 retrying database query attempt=1 error="connection timeout"`
- Line 5: `2026-09-17T12:00:04Z ERROR checkout-api request_id=req-1002 database connection timeout after 30000ms host=postgres-primary db=orders`
- Line 6: `2026-09-17T12:00:05Z ERROR checkout-api request_id=req-1003 failed POST /checkout status=500 reason="db unavailable"`
- Line 7: `2026-09-17T12:00:06Z ERROR checkout-worker order_writer repeated database failures count=37 window=60s`

## Confidence
HIGH, because there are multiple logs indicating database connection issues and the logs provide consistent evidence of the problem.

## Recommended Next Investigation Steps
1. Check the configuration of the database connection pool to ascertain if the limits can be increased.
2. Investigate the database server (postgres-primary) performance and error logs for signs of resource constraints or failures.
3. Review application logs for any patterns or specific queries that might contribute to the connection pool exhaustion.

## Uncertainty / Missing Evidence
No specific details regarding the load on the database or the number of concurrent users were provided, which could further clarify the root cause of the connection pool exhaustion.
```

Classification: Database.
Severity: MEDIUM.
Evidence cited: lines 2 through 7 from the supplied logs.
Confidence: HIGH.
Reasonable? Yes. It identified the database signal and did not invent extra log evidence.
Obvious hallucinations: none obvious.
Unexpected behavior: It used "significant issues" and "failed order request" from the log context; acceptable but mildly interpretive.

### Scenario 2 - Application Incident

Input:

```text
Analyze these production logs for incident triage:
2026-09-17T12:10:00Z INFO orders-api request_id=req-2001 GET /orders/553 started
2026-09-17T12:10:01Z ERROR orders-api request_id=req-2001 HTTP 500 Internal Server Error
2026-09-17T12:10:01Z ERROR orders-api request_id=req-2001 Unhandled TypeError: Cannot read properties of undefined (reading 'total')
2026-09-17T12:10:01Z ERROR orders-api request_id=req-2001 stacktrace: TypeError at calculateInvoiceTotal (/srv/app/invoice.js:88:14)
2026-09-17T12:10:01Z ERROR orders-api request_id=req-2001 stacktrace: at handleGetOrder (/srv/app/routes/orders.js:142:9)
2026-09-17T12:10:02Z INFO orders-api request_id=req-2001 response status=500 duration_ms=842
```

Actual output:

```text
## Incident Classification
Application - This classification is supported by multiple observed error signals related to application functionality.

## Severity
MEDIUM - The HTTP 500 Internal Server Error indicates a significant issue, but it appears to be limited to a single request and does not suggest widespread system failure.

## Summary
The logs detail an incident involving the `orders-api` where an internal server error (HTTP 500) occurred during a request to retrieve an order. The error specifically resulted from a `TypeError` indicating that a property was being accessed on an undefined variable, which likely points to a programming issue within the application's invoice calculation logic.

## Evidence From Logs
- Line 2: `2026-09-17T12:10:01Z ERROR orders-api request_id=req-2001 HTTP 500 Internal Server Error`
- Line 3: `2026-09-17T12:10:01Z ERROR orders-api request_id=req-2001 Unhandled TypeError: Cannot read properties of undefined (reading 'total')`
- Line 4: `2026-09-17T12:10:01Z ERROR orders-api request_id=req-2001 stacktrace: TypeError at calculateInvoiceTotal (/srv/app/invoice.js:88:14)`
- Line 5: `2026-09-17T12:10:01Z ERROR orders-api request_id=req-2001 stacktrace: at handleGetOrder (/srv/app/routes/orders.js:142:9)`

## Confidence
HIGH - The evidence is clear and directly indicates an application error related to internal logic, specifically in handling order calculations.

## Recommended Next Investigation Steps
1. Review the code in the `calculateInvoiceTotal` function at line 88 of `invoice.js` to identify why it is receiving an undefined value.
2. Check the input data for the order request to ensure all expected parameters are being passed correctly.
3. Conduct tests to replicate the error and explore any edge cases that could lead to undefined properties in the order data.

## Uncertainty / Missing Evidence
There are no significant uncertainties or missing evidence within the provided logs; however, further context on the expected input data for the order retrieval could enhance the analysis.
```

Classification: Application.
Severity: MEDIUM.
Evidence cited: lines 2 through 5 from the supplied logs.
Confidence: HIGH.
Reasonable? Yes. It correctly treated the TypeError and stack trace as application evidence.
Obvious hallucinations: none obvious.
Unexpected behavior: It stated there are "no significant uncertainties" even though only one request is shown. This is a grounding weakness to investigate.

### Scenario 3 - Infrastructure Incident

Input:

```text
Analyze these production logs for incident triage:
2026-09-17T12:20:03Z WARN payments-api pod=payments-api-7c9 memory usage 94 percent limit=1024Mi
2026-09-17T12:20:05Z ERROR kernel pod=payments-api-7c9 container=app OOMKilled memory cgroup out of memory
2026-09-17T12:20:06Z ERROR kubelet pod=payments-api-7c9 container app exited code=137 reason=OOMKilled
2026-09-17T12:20:08Z ERROR payments-api health check failed after container restart status=503
2026-09-17T12:20:11Z WARN load-balancer upstream payments-api no healthy endpoints available
```

Actual output:

```text
## Incident Classification
Infrastructure, based on observed logs indicating memory issues leading to service failures.

## Severity
CRITICAL, as multiple components (pod, health check, load balancer) are affected, leading to service unavailability.

## Summary
The logs indicate significant memory usage in the `payments-api` pod, which triggered an out-of-memory (OOM) situation, resulting in the pod being killed and subsequently failing health checks. This has led to the load balancer reporting no healthy endpoints available, impacting service availability.

## Evidence From Logs
- **Line 1:** "2026-09-17T12:20:03Z WARN payments-api pod=payments-api-7c9 memory usage 94 percent limit=1024Mi"
- **Line 2:** "2026-09-17T12:20:05Z ERROR kernel pod=payments-api-7c9 container=app OOMKilled memory cgroup out of memory"
- **Line 3:** "2026-09-17T12:20:06Z ERROR kubelet pod=payments-api-7c9 container app exited code=137 reason=OOMKilled"
- **Line 4:** "2026-09-17T12:20:08Z ERROR payments-api health check failed after container restart status=503"
- **Line 5:** "2026-09-17T12:20:11Z WARN load-balancer upstream payments-api no healthy endpoints available"

## Confidence
HIGH, as there is clear evidence of a resource exhaustion scenario leading to critical service impacts observed in the logs.

## Recommended Next Investigation Steps
1. Check the resource allocation settings for the `payments-api` pod and consider increasing memory limits.
2. Investigate logs for memory usage patterns leading up to the incident to understand what triggered the high memory consumption.
3. Review the application's memory management to identify potential memory leaks or inefficient memory use.

## Uncertainty / Missing Evidence
There is no information about the overall traffic or load on the `payments-api` prior to the incident, which could provide context on whether this OOM situation was expected or an anomaly. Additionally, there are no logs indicating actions taken after the OOM event or if any efforts were made to auto-restart the service post-incident.
```

Classification: Infrastructure.
Severity: CRITICAL.
Evidence cited: lines 1 through 5 from the supplied logs.
Confidence: HIGH.
Reasonable? Mostly yes. OOMKilled plus no healthy endpoints makes CRITICAL plausible.
Obvious hallucinations: none obvious, though "multiple components" is an interpretation of log sources rather than direct impact scope.
Unexpected behavior: It recommended increasing memory limits, which is close to remediation rather than investigation. This may need prompt tightening.

### Scenario 4 - Authentication Incident

Input:

```text
Analyze these production logs for incident triage:
2026-09-17T12:30:00Z INFO gateway request_id=req-4001 GET /api/profile started
2026-09-17T12:30:01Z WARN gateway request_id=req-4001 HTTP 401 Unauthorized path=/api/profile
2026-09-17T12:30:01Z ERROR auth-service request_id=req-4001 token validation failed reason="signature verification failed" kid=prod-key-17
2026-09-17T12:30:01Z WARN auth-service request_id=req-4002 OAuth token expired audience=incidentlens-api
2026-09-17T12:30:02Z WARN gateway request_id=req-4003 HTTP 403 Forbidden path=/admin/users role=viewer
```

Actual output:

```text
## Incident Classification
Authentication / Authorization; this is observed based on multiple log entries indicating authorization failures.

## Severity
LOW; despite the presence of errors and warnings regarding authorization, they don't indicate a systemic failure or significant impact to system operations.

## Summary
The logs reveal multiple authentication issues, including a failed token validation due to a signature verification error, an HTTP 401 Unauthorized response for a profile request, an expired OAuth token, and an HTTP 403 Forbidden response when accessing an admin endpoint. These signals suggest potential user or token management issues, but they do not appear to affect the overall functionality of the system.

## Evidence From Logs
- Line 2: `2026-09-17T12:30:01Z WARN gateway request_id=req-4001 HTTP 401 Unauthorized path=/api/profile`
- Line 3: `2026-09-17T12:30:01Z ERROR auth-service request_id=req-4001 token validation failed reason="signature verification failed" kid=prod-key-17`
- Line 4: `2026-09-17T12:30:01Z WARN auth-service request_id=req-4002 OAuth token expired audience=incidentlens-api`
- Line 5: `2026-09-17T12:30:02Z WARN gateway request_id=req-4003 HTTP 403 Forbidden path=/admin/users role=viewer`

## Confidence
HIGH; the classification and severity are strongly supported by multiple log entries indicating incidents related to authentication and authorization.

## Recommended Next Investigation Steps
1. Investigate the token signature verification process to identify potential causes for the validation failure.
2. Review the token expiration policy and user notification mechanisms to prevent unauthorized access issues.
3. Check the role-based access control configuration for the `/admin/users` endpoint to ensure proper permissions are enforced.

## Uncertainty / Missing Evidence
There is no ambiguity in the provided logs, but further context around user actions and configurations leading to the authentication issues would be helpful for a complete diagnosis.
```

Classification: Authentication / Authorization.
Severity: LOW.
Evidence cited: lines 2 through 5 from the supplied logs.
Confidence: HIGH.
Reasonable? Classification is good. Severity LOW is acceptable for the small sample, but could be too low if auth failure rates were high.
Obvious hallucinations: none obvious.
Unexpected behavior: It says the logs "do not appear to affect overall functionality" without direct evidence of broader system health.

### Scenario 5 - Insufficient Evidence

Input:

```text
Analyze these production logs for incident triage:
2026-09-17T12:40:00Z INFO worker job_id=job-991 started
2026-09-17T12:40:02Z ERROR worker job_id=job-991 operation failed
2026-09-17T12:40:03Z INFO worker job_id=job-991 exiting with status=1
```

Actual output:

```text
## Incident Classification
Unknown / Insufficient Evidence - The logs do not provide enough context to classify the incident.

## Severity
LOW - The only logged error indicates a job failure without further details or critical impact.

## Summary
At 12:40:02 on 2026-09-17, an error was logged indicating that a worker job (job_id=job-991) failed. The job started moments before, and it exited shortly after with a status of 1. However, the logs do not provide specific details about the cause of the failure, making it difficult to assess the incident fully.

## Evidence From Logs
- Line 2: "2026-09-17T12:40:02Z ERROR worker job_id=job-991 operation failed"
- Line 3: "2026-09-17T12:40:03Z INFO worker job_id=job-991 exiting with status=1"

## Confidence
LOW - The logs are too limited to draw firm conclusions about the incident's nature or impact.

## Recommended Next Investigation Steps
1. Review additional logs surrounding job_id=job-991 for more context regarding the failure.
2. Investigate the conditions that led to the job failure and its exit status.
3. Check for any system metrics or events that correlate with the timing of the error for further clues.

## Uncertainty / Missing Evidence
The logs lack information about what specifically caused the operation to fail, and there are no category-specific keywords identified that could lead to a more defined classification. Additionally, corroborating logs or details about the system state are missing.
```

Classification: Unknown / Insufficient Evidence.
Severity: LOW.
Evidence cited: lines 2 and 3 from the supplied logs.
Confidence: LOW.
Reasonable? Yes. It avoided inventing a root cause.
Obvious hallucinations: none obvious.
Unexpected behavior: none significant.

## Obvious Problems

- Some recommendations drift toward remediation instead of investigation, especially "consider increasing memory limits" in the infrastructure scenario.
- The agent sometimes makes broad negative claims from limited evidence, such as "does not suggest widespread system failure" or "do not appear to affect the overall functionality of the system."
- The tool can mark one signal as both Infrastructure and Database for database connection timeouts; the final classification handled this correctly, but mixed hints should be watched.
- Severity choices are plausible, but they depend heavily on the small sample. The agent should be more explicit that severity is estimated from supplied evidence only.

## Questions / Uncertainties

- Should severity be intentionally conservative when only a small log sample is provided?
- Should the prompt require "observed impact" vs "inferred impact" labels in the severity section?
- Should recommended next steps be constrained more strongly to investigation-only language?
- Should the tool stop tagging database timeouts as Infrastructure when a database-specific signal is also present?

## Next Investigation Step

Tune the prompt and/or deterministic tool output to make the agent more explicit about evidence boundaries, especially severity rationale, broad impact claims, and investigation-only recommendations.
