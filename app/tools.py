# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Lightweight log analysis helpers for the IncidentLens agent."""

from __future__ import annotations

import re
from collections import Counter

ERROR_LEVEL_RE = re.compile(
    r"\b(emerg|alert|crit|critical|fatal|error|err|exception|traceback|panic|"
    r"warn|warning)\b",
    re.IGNORECASE,
)
TIMESTAMP_RE = re.compile(
    r"(\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?Z?|"
    r"\d{2}/[A-Za-z]{3}/\d{4}:\d{2}:\d{2}:\d{2}\s[+-]\d{4})"
)

CATEGORY_KEYWORDS = {
    "Application": [
        "exception",
        "traceback",
        "stacktrace",
        "nullpointer",
        "typeerror",
        "valueerror",
        "indexerror",
        "runtimeerror",
        "panic",
        "unhandled",
        "route handler",
        "validation",
        "500 internal",
    ],
    "Infrastructure": [
        "timeout",
        "timed out",
        "connection refused",
        "connection reset",
        "econnreset",
        "econnrefused",
        "enotfound",
        "dns",
        "network",
        "upstream",
        "load balancer",
        "503",
        "504",
        "oomkilled",
        "pod",
        "container",
        "node",
        "disk",
        "memory",
        "cpu",
    ],
    "Database": [
        "database",
        "db",
        "sql",
        "postgres",
        "postgresql",
        "mysql",
        "oracle",
        "mongodb",
        "redis",
        "connection pool",
        "deadlock",
        "lock wait",
        "query",
        "transaction",
        "constraint",
        "migration",
    ],
    "Authentication / Authorization": [
        "auth",
        "authentication",
        "authorization",
        "unauthorized",
        "forbidden",
        "permission",
        "access denied",
        "jwt",
        "token",
        "oauth",
        "oidc",
        "saml",
        "401",
        "403",
        "iam",
        "credential",
    ],
}


def _excerpt(line: str) -> str:
    normalized = " ".join(line.strip().split())
    if len(normalized) <= 500:
        return normalized
    return f"{normalized[:497]}..."


def _matching_categories(line: str) -> list[str]:
    lower_line = line.lower()
    matches = []
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(keyword in lower_line for keyword in keywords):
            matches.append(category)
    return matches


def analyze_logs(logs: str) -> dict:
    """Extracts observed error signals from production logs.

    Args:
        logs: Raw server or application log text supplied by the user.

    Returns:
        A JSON-serializable dictionary of observed log signals, category hints,
        severity hints, and missing-evidence notes.
    """
    lines = logs.splitlines()
    non_empty_lines = [
        (index, line) for index, line in enumerate(lines, start=1) if line.strip()
    ]

    signals = []
    category_counts: Counter[str] = Counter()
    level_counts: Counter[str] = Counter()
    timestamps = []

    for line_number, line in non_empty_lines:
        timestamp_match = TIMESTAMP_RE.search(line)
        if timestamp_match:
            timestamps.append(timestamp_match.group(0))

        level_match = ERROR_LEVEL_RE.search(line)
        categories = _matching_categories(line)

        if not level_match and not categories:
            continue

        level = level_match.group(0).upper() if level_match else "SIGNAL"
        level_counts[level] += 1
        for category in categories:
            category_counts[category] += 1

        signals.append(
            {
                "line_number": line_number,
                "level": level,
                "category_hints": categories,
                "excerpt": _excerpt(line),
            }
        )

    hard_error_count = sum(
        level_counts[level]
        for level in level_counts
        if level not in {"WARN", "WARNING", "SIGNAL"}
    )
    warning_count = level_counts["WARN"] + level_counts["WARNING"]

    if hard_error_count >= 10:
        severity_hint = "HIGH"
    elif hard_error_count >= 3:
        severity_hint = "MEDIUM"
    elif hard_error_count >= 1 or warning_count >= 3:
        severity_hint = "LOW"
    elif signals:
        severity_hint = "LOW"
    else:
        severity_hint = "Unknown / Insufficient Evidence"

    lower_logs = logs.lower()
    critical_phrases = [
        "critical",
        "fatal",
        "panic",
        "outage",
        "all requests failing",
        "100% failure",
        "failure_rate=100%",
        "no healthy endpoints",
        "customer impact",
        "customer-wide",
        "database unavailable",
        "oomkilled",
    ]
    if any(phrase in lower_logs for phrase in critical_phrases):
        severity_hint = "CRITICAL" if hard_error_count >= 1 else "HIGH"
    elif re.search(r"\bfailure[_ -]?rate\b", lower_logs) and hard_error_count >= 1:
        severity_hint = "HIGH"

    top_category = (
        category_counts.most_common(1)[0][0]
        if category_counts
        else "Unknown / Insufficient Evidence"
    )

    missing_evidence = []
    if not signals:
        missing_evidence.append(
            "No explicit error, warning, exception, or category keyword signals were found."
        )
    if not timestamps:
        missing_evidence.append("No recognizable timestamps were found.")
    if not category_counts:
        missing_evidence.append("No category-specific keywords were found.")
    if len(non_empty_lines) < 5:
        missing_evidence.append("The supplied log sample is very small.")

    return {
        "status": "success",
        "total_lines": len(lines),
        "non_empty_lines": len(non_empty_lines),
        "signal_count": len(signals),
        "level_counts": dict(level_counts),
        "category_counts": dict(category_counts),
        "suggested_category": top_category,
        "suggested_severity": severity_hint,
        "time_range": {
            "first_seen": timestamps[0] if timestamps else None,
            "last_seen": timestamps[-1] if timestamps else None,
        },
        "signals": signals[:25],
        "truncated_signals": max(len(signals) - 25, 0),
        "missing_evidence": missing_evidence,
    }
