const samples = {
  database: {
    label: "Database incident",
    text: `Analyze these production logs for incident triage:
2026-09-17T12:00:01Z INFO checkout-api request_id=req-1001 POST /checkout started user_id=8842
2026-09-17T12:00:02Z ERROR checkout-api request_id=req-1001 database connection timeout after 30000ms host=postgres-primary db=orders
2026-09-17T12:00:02Z ERROR checkout-api request_id=req-1001 failed to persist order: database connection pool exhausted active=50 idle=0 max=50
2026-09-17T12:00:03Z WARN checkout-api request_id=req-1002 retrying database query attempt=1 error="connection timeout"
2026-09-17T12:00:04Z ERROR checkout-api request_id=req-1002 database connection timeout after 30000ms host=postgres-primary db=orders
2026-09-17T12:00:05Z ERROR checkout-api request_id=req-1003 failed POST /checkout status=500 reason="db unavailable"
2026-09-17T12:00:06Z ERROR checkout-worker order_writer repeated database failures count=37 window=60s`,
  },
  application: {
    label: "Application exception",
    text: `Analyze these production logs for incident triage:
2026-09-17T12:10:00Z INFO orders-api request_id=req-2001 GET /orders/553 started
2026-09-17T12:10:01Z ERROR orders-api request_id=req-2001 HTTP 500 Internal Server Error
2026-09-17T12:10:01Z ERROR orders-api request_id=req-2001 Unhandled TypeError: Cannot read properties of undefined (reading 'total')
2026-09-17T12:10:01Z ERROR orders-api request_id=req-2001 stacktrace: TypeError at calculateInvoiceTotal (/srv/app/invoice.js:88:14)
2026-09-17T12:10:01Z ERROR orders-api request_id=req-2001 stacktrace: at handleGetOrder (/srv/app/routes/orders.js:142:9)
2026-09-17T12:10:02Z INFO orders-api request_id=req-2001 response status=500 duration_ms=842`,
  },
  infrastructure: {
    label: "Infrastructure failure",
    text: `Analyze these production logs for incident triage:
2026-09-17T12:20:03Z WARN payments-api pod=payments-api-7c9 memory usage 94 percent limit=1024Mi
2026-09-17T12:20:05Z ERROR kernel pod=payments-api-7c9 container=app OOMKilled memory cgroup out of memory
2026-09-17T12:20:06Z ERROR kubelet pod=payments-api-7c9 container app exited code=137 reason=OOMKilled
2026-09-17T12:20:08Z ERROR payments-api health check failed after container restart status=503
2026-09-17T12:20:11Z WARN load-balancer upstream payments-api no healthy endpoints available`,
  },
  auth: {
    label: "Auth failure",
    text: `Analyze these production logs for incident triage:
2026-09-17T12:30:00Z INFO gateway request_id=req-4001 GET /api/profile started
2026-09-17T12:30:01Z WARN gateway request_id=req-4001 HTTP 401 Unauthorized path=/api/profile
2026-09-17T12:30:01Z ERROR auth-service request_id=req-4001 token validation failed reason="signature verification failed" kid=prod-key-17
2026-09-17T12:30:01Z WARN auth-service request_id=req-4002 OAuth token expired audience=incidentlens-api
2026-09-17T12:30:02Z WARN gateway request_id=req-4003 HTTP 403 Forbidden path=/admin/users role=viewer`,
  },
  insufficient: {
    label: "Insufficient evidence",
    text: `Analyze these production logs for incident triage:
2026-09-17T12:40:00Z INFO worker job_id=job-991 started
2026-09-17T12:40:02Z ERROR worker job_id=job-991 operation failed
2026-09-17T12:40:03Z INFO worker job_id=job-991 exiting with status=1`,
  },
};

const els = {
  analyzeButton: document.querySelector("#analyzeButton"),
  categoryHint: document.querySelector("#categoryHint"),
  clearButton: document.querySelector("#clearButton"),
  copyButton: document.querySelector("#copyButton"),
  elapsedTime: document.querySelector("#elapsedTime"),
  lineCount: document.querySelector("#lineCount"),
  logInput: document.querySelector("#logInput"),
  modelStatus: document.querySelector("#modelStatus"),
  reportOutput: document.querySelector("#reportOutput"),
  runMeta: document.querySelector("#runMeta"),
  sampleSelect: document.querySelector("#sampleSelect"),
  serverStatus: document.querySelector("#serverStatus"),
  severityHint: document.querySelector("#severityHint"),
  signalCount: document.querySelector("#signalCount"),
  stopButton: document.querySelector("#stopButton"),
  toolOutput: document.querySelector("#toolOutput"),
};

let abortController = null;
let activeReport = "";
let activeToolOutput = null;
let timerId = null;
let startedAt = 0;

function userId() {
  const key = "incidentlens.userId";
  let value = window.localStorage.getItem(key);
  if (!value) {
    value = `reviewer-${crypto.randomUUID()}`;
    window.localStorage.setItem(key, value);
  }
  return value;
}

function setStatus(element, text, mode = "muted") {
  element.textContent = text;
  element.className = `status-pill ${mode}`.trim();
}

function resetSignals() {
  els.categoryHint.textContent = "-";
  els.severityHint.textContent = "-";
  els.signalCount.textContent = "-";
  els.lineCount.textContent = "-";
  els.toolOutput.textContent = "No tool output yet.";
}

function setBusy(isBusy) {
  els.analyzeButton.disabled = isBusy;
  els.stopButton.disabled = !isBusy;
  els.sampleSelect.disabled = isBusy;
  els.modelStatus.textContent = isBusy ? "Analyzing" : "Idle";
  els.modelStatus.className = isBusy ? "status-pill warn" : "status-pill muted";
}

function startTimer() {
  startedAt = performance.now();
  els.elapsedTime.textContent = "0.0s";
  window.clearInterval(timerId);
  timerId = window.setInterval(() => {
    const elapsed = (performance.now() - startedAt) / 1000;
    els.elapsedTime.textContent = `${elapsed.toFixed(1)}s`;
  }, 100);
}

function stopTimer() {
  window.clearInterval(timerId);
  timerId = null;
}

function escapeHtml(value) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function inlineFormat(value) {
  return escapeHtml(value).replace(/`([^`]+)`/g, "<code>$1</code>");
}

function renderReport(text) {
  if (!text.trim()) {
    els.reportOutput.className = "report empty";
    els.reportOutput.textContent = "Waiting for report...";
    return;
  }

  const lines = text.split(/\r?\n/);
  const html = [];
  let listType = null;

  const closeList = () => {
    if (listType) {
      html.push(`</${listType}>`);
      listType = null;
    }
  };

  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) {
      closeList();
      continue;
    }

    const heading = /^##\s+(.+)$/.exec(trimmed);
    if (heading) {
      closeList();
      html.push(`<h3>${inlineFormat(heading[1])}</h3>`);
      continue;
    }

    const bullet = /^[-*]\s+(.+)$/.exec(trimmed);
    if (bullet) {
      if (listType !== "ul") {
        closeList();
        listType = "ul";
        html.push("<ul>");
      }
      html.push(`<li>${inlineFormat(bullet[1])}</li>`);
      continue;
    }

    const numbered = /^\d+[.)]\s+(.+)$/.exec(trimmed);
    if (numbered) {
      if (listType !== "ol") {
        closeList();
        listType = "ol";
        html.push("<ol>");
      }
      html.push(`<li>${inlineFormat(numbered[1])}</li>`);
      continue;
    }

    closeList();
    html.push(`<p>${inlineFormat(trimmed)}</p>`);
  }

  closeList();
  els.reportOutput.className = "report";
  els.reportOutput.innerHTML = html.join("");
}

function updateToolOutput(response) {
  activeToolOutput = response;
  els.categoryHint.textContent = response.suggested_category || "-";
  els.severityHint.textContent = response.suggested_severity || "-";
  els.signalCount.textContent = String(response.signal_count ?? "-");
  els.lineCount.textContent = String(response.non_empty_lines ?? "-");
  els.toolOutput.textContent = JSON.stringify(response, null, 2);
}

function handleEvent(event) {
  if (event.error || event.errorCode) {
    const message = event.error || event.errorMessage || "Agent request failed.";
    throw new Error(message);
  }

  for (const part of event.content?.parts || []) {
    if (part.functionCall?.name === "analyze_logs") {
      setStatus(els.modelStatus, "Extracting signals", "warn");
    }

    const toolResponse = part.functionResponse?.response;
    if (part.functionResponse?.name === "analyze_logs" && toolResponse) {
      updateToolOutput(toolResponse);
      setStatus(els.modelStatus, "Writing report", "warn");
    }

    if (part.text) {
      activeReport += part.text;
      renderReport(activeReport);
    }
  }
}

function parseSseBlock(block) {
  const lines = block.split(/\r?\n/);
  const data = lines
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.slice(5).trimStart())
    .join("\n");
  if (!data || data === "[DONE]") {
    return null;
  }
  return JSON.parse(data);
}

async function createSession() {
  const response = await fetch(`/apps/app/users/${encodeURIComponent(userId())}/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ state: {} }),
  });
  if (!response.ok) {
    throw new Error(`Session create failed: ${response.status}`);
  }
  return response.json();
}

async function analyzeLogs() {
  const logs = els.logInput.value.trim();
  if (!logs) {
    els.logInput.focus();
    setStatus(els.modelStatus, "Logs required", "warn");
    return;
  }

  abortController = new AbortController();
  activeReport = "";
  activeToolOutput = null;
  resetSignals();
  renderReport("");
  setBusy(true);
  startTimer();
  els.runMeta.textContent = "Creating session...";

  try {
    const session = await createSession();
    els.runMeta.textContent = `Session ${session.id}`;

    const response = await fetch("/run_sse", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        app_name: "app",
        user_id: userId(),
        session_id: session.id,
        new_message: {
          role: "user",
          parts: [{ text: logs }],
        },
        streaming: true,
      }),
      signal: abortController.signal,
    });

    if (!response.ok || !response.body) {
      throw new Error(`Run failed: ${response.status}`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        break;
      }
      buffer += decoder.decode(value, { stream: true });
      const blocks = buffer.split(/\r?\n\r?\n/);
      buffer = blocks.pop() || "";
      for (const block of blocks) {
        const event = parseSseBlock(block);
        if (event) {
          handleEvent(event);
        }
      }
    }

    if (buffer.trim()) {
      const event = parseSseBlock(buffer);
      if (event) {
        handleEvent(event);
      }
    }

    setStatus(els.modelStatus, "Complete", "");
    els.copyButton.disabled = !activeReport.trim();
  } catch (error) {
    if (error.name === "AbortError") {
      setStatus(els.modelStatus, "Stopped", "warn");
      els.runMeta.textContent = "Run stopped.";
    } else {
      setStatus(els.modelStatus, "Error", "error");
      els.reportOutput.className = "report";
      els.reportOutput.innerHTML = `<h3>Request Failed</h3><p>${inlineFormat(
        error.message,
      )}</p>`;
    }
  } finally {
    setBusy(false);
    stopTimer();
    abortController = null;
  }
}

async function checkServer() {
  try {
    const response = await fetch("/list-apps");
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    const apps = await response.json();
    setStatus(
      els.serverStatus,
      apps.includes("app") ? "Server ready" : "App not found",
      apps.includes("app") ? "" : "warn",
    );
  } catch (error) {
    setStatus(els.serverStatus, "Server offline", "error");
  }
}

function loadSamples() {
  for (const [key, sample] of Object.entries(samples)) {
    const option = document.createElement("option");
    option.value = key;
    option.textContent = sample.label;
    els.sampleSelect.appendChild(option);
  }
}

els.sampleSelect.addEventListener("change", () => {
  const sample = samples[els.sampleSelect.value];
  if (sample) {
    els.logInput.value = sample.text;
    els.logInput.focus();
  }
});

els.analyzeButton.addEventListener("click", analyzeLogs);
els.stopButton.addEventListener("click", () => abortController?.abort());
els.clearButton.addEventListener("click", () => {
  els.logInput.value = "";
  activeReport = "";
  resetSignals();
  renderReport("");
  els.runMeta.textContent = "No run yet.";
  els.copyButton.disabled = true;
  els.elapsedTime.textContent = "0.0s";
});
els.copyButton.addEventListener("click", async () => {
  if (!activeReport.trim()) {
    return;
  }
  await navigator.clipboard.writeText(activeReport);
  const previous = els.copyButton.textContent;
  els.copyButton.textContent = "Copied";
  window.setTimeout(() => {
    els.copyButton.textContent = previous;
  }, 1000);
});

loadSamples();
checkServer();
