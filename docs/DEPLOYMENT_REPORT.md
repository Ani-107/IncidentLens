# IncidentLens Deployment Report

Date: 2026-09-17

## 1. Deployment Target

Deployment was not attempted.

Current `agents-cli-manifest.yaml` still records:

```yaml
deployment_target: 'none'
session_type: 'in_memory'
cicd_runner: 'skip'
region: 'us-east1'
```

Cloud Run remains the recommended target for this MVP because it is the simplest
deployment path for a single ADK/FastAPI agent with Secret Manager support.

Note: a previous scaffold preview path created a `deployment/` directory, but
the manifest was not updated and `agents-cli deploy --list` still reports that
no deployment target is configured.

## 2. Google Cloud Project

Not verified.

`gcloud` is not installed or not available on `PATH` in this environment, so the
current Google Cloud project could not be checked.

## 3. Region

The manifest records `us-east1`.

No deployed region exists yet.

## 4. Deployment Command Used

No deployment command was run.

Latest Cloud Run deploy preview attempts:

```powershell
agents-cli deploy --deployment-target cloud_run --dry-run --service-name incidentlens --region us-east1 --no-confirm-project
agents-cli deploy --list --deployment-target cloud_run
```

Both failed before deployment because no Google Cloud project could be
determined:

```text
Error: Could not determine GCP project. Set one with:
  * pass --project <PROJECT_ID>
  * export GOOGLE_CLOUD_PROJECT=<PROJECT_ID>
  * gcloud config set project <PROJECT_ID>
```

The following command was not executed because prerequisites were missing:

```powershell
agents-cli deploy --deployment-target cloud_run --project <PROJECT_ID> --region us-east1 --secrets OPENAI_API_KEY=incidentlens-openai-api-key --service-name incidentlens --no-confirm-project
```

## 5. Deployment Status

Status: `BLOCKED - NOT DEPLOYED`

Blocking prerequisites:

- `gcloud` is missing or unavailable on `PATH`.
- Google Cloud account could not be verified.
- Google Cloud project could not be verified.
- Application Default Credentials could not be verified.
- Required APIs could not be verified.
- Secret Manager secret for `OPENAI_API_KEY` could not be verified.
- Manifest deployment target is still `none`.
- Current evaluation suite does not pass overall.

## 6. Endpoint

No deployed endpoint exists.

Local development endpoint remains:

```text
http://127.0.0.1:8000/dev-ui/?app=app
```

## 7. Smoke Tests Performed

No deployed smoke tests were performed because deployment did not occur.

Local agent smoke test was previously performed after the API key was fixed:

- Local server reachable.
- App `app` loaded.
- Patched IncidentLens prompt loaded.
- Model call succeeded with `gpt-4o-mini`.
- Agent called `analyze_logs`.
- Response started with `## Incident Classification`.

## 8. Smoke Test Results

Deployed smoke tests: not applicable because no deployment exists.

Local smoke result: passed.

## 9. Environment Variables Used

Local development uses:

- `OPENAI_API_KEY`: set in the running local server process, value not exposed.
- `INCIDENTLENS_MODEL`: optional; defaults to `openai/gpt-4o-mini`.
- `ADK_DISABLE_LOCAL_STORAGE=true`
- `TEMP`, `TMP`, `UV_CACHE_DIR`, `NPM_CONFIG_CACHE`, and `SQLITE_TMPDIR` set to
  D-drive paths for local Windows development.

Deployment would need:

- `OPENAI_API_KEY` supplied from Secret Manager.
- Optional `INCIDENTLENS_MODEL` only if overriding the default model.

## 10. Secrets Configuration

No cloud secret was verified or created.

Recommended Cloud Run secret:

```text
Secret Manager secret name: incidentlens-openai-api-key
Runtime env var: OPENAI_API_KEY
```

Do not store the API key in source files or documentation.

## 11. Deployment Warnings

- `gcloud` is missing, so no Google Cloud authentication, project, API, billing,
  IAM, or Secret Manager state could be verified.
- `agents-cli deploy --list` failed because the manifest has no deployment
  target configured.
- A previous scaffold preview created deployment Terraform files, but the
  manifest still says local-only. Treat this as incomplete deployment
  scaffolding.
- The full `agents-cli lint` check passes after formatting/type fixes.
- Unit tests pass.
- Scaffolded integration tests were not run because they start their own server
  on port 8000, which is already occupied by the working local playground, and
  this shell does not have the model API key available for a separate server.
- The post-fix evaluation suite improved but still fails overall.

## 12. Pre-Deployment Check Results

### Unit Tests

Command:

```powershell
uv run pytest tests\unit
```

Result:

```text
1 passed
```

### Lint / Type Checks

Command:

```powershell
agents-cli lint
```

Result:

```text
ruff check: passed
ruff format --check: passed
codespell: passed
ty check: passed
```

### Evaluation

Command:

```powershell
uv run python tests\eval\run_incidentlens_eval.py --url http://127.0.0.1:8000 --app-name app
```

Result:

```text
Total scenarios: 20
Passed scenarios: 7
Failed scenarios: 13
```

Metric summary:

| Metric | Passed | Total |
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

The eval runner generated traces successfully. `agents-cli eval grade` still
returned a generic `Evaluation failed` error, so the report uses the local
deterministic fallback analysis.

Latest machine-readable eval result:

```text
tests/eval/results/incidentlens_baseline_20260917_131228.json
```

## 13. Rollback Procedure

No deployed service exists, so there is nothing to roll back.

If a future Cloud Run deployment succeeds, rollback can be done with Cloud Run
revision traffic shifting:

```powershell
gcloud run revisions list --service incidentlens --region us-east1 --project <PROJECT_ID>
gcloud run services update-traffic incidentlens --to-revisions <REVISION_NAME>=100 --region us-east1 --project <PROJECT_ID>
```

Alternatively, fix the project and redeploy with `agents-cli deploy`.

## 14. Known Production Limitations

- IncidentLens is not production-ready.
- Evaluation currently passes only 7 / 20 scenarios overall.
- Mixed and unrelated incident logs remain a known weakness.
- Uncertainty handling remains inconsistent.
- Recommendation wording can still miss expected investigation terms.
- Prompt injection inside log content has not been evaluated.
- No deployed authentication/access-control design has been configured.
- No Cloud Run Secret Manager secret has been verified.
- No production observability, alerting, load testing, or rollback validation has
  been performed.

## 15. Manual Steps Needed Before Deployment

1. Install Google Cloud CLI or add it to `PATH`.
2. Authenticate:

```powershell
gcloud auth login --update-adc
gcloud auth application-default login
```

3. Configure a project:

```powershell
gcloud config set project <PROJECT_ID>
```

4. Enable required APIs:

```powershell
gcloud services enable run.googleapis.com cloudbuild.googleapis.com secretmanager.googleapis.com artifactregistry.googleapis.com iam.googleapis.com --project <PROJECT_ID>
```

5. Create or update the OpenAI API key secret in Secret Manager without exposing
   the value in logs or source files.

6. Add Cloud Run deployment scaffolding after reviewing the generated changes:

```powershell
agents-cli scaffold enhance . --name incidentlens --base-template adk --agent-directory app --deployment-target cloud_run --session-type in_memory --cicd-runner skip
```

7. Rerun tests, lint, and evaluation.

8. Only deploy after the remaining eval failures are either fixed or explicitly
   accepted for a non-production demo deployment.
