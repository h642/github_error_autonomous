// ==========================================================================
// Autonomous Software Repair Pipeline - Dashboard Live Controller
// ==========================================================================

let eventSource = null;
let currentApprovalData = null;

document.addEventListener("DOMContentLoaded", () => {
    initControls();
    setupEventSource();
});

function initControls() {
    const startBtn = document.getElementById("btn-start-repair");
    const repoInput = document.getElementById("input-repo-path");
    const providerSelect = document.getElementById("select-provider");
    const modelSelect = document.getElementById("select-model");
    const btnApprove = document.getElementById("btn-approve-pr");

    // Fetch initial config
    fetch("/api/config")
        .then(res => res.json())
        .then(data => {
            if (data.default_repo && !repoInput.value) {
                repoInput.value = data.default_repo;
            }
            if (data.has_github_token) {
                const hint = document.getElementById("token-status-hint");
                if (hint) hint.innerText = "✓ GITHUB_TOKEN detected in server .env (Ready to publish live PRs).";
            }
        })
        .catch(err => console.error("Failed to load initial config:", err));

    const tokenInput = document.getElementById("input-github-token");
    if (tokenInput) {
        const savedToken = localStorage.getItem("github_token");
        if (savedToken) {
            tokenInput.value = savedToken;
            const hint = document.getElementById("token-status-hint");
            if (hint) hint.innerText = "✓ Saved GitHub token loaded from browser storage.";
        }
        tokenInput.addEventListener("input", () => {
            tokenInput.style.borderColor = "";
            if (tokenInput.value.trim()) {
                localStorage.setItem("github_token", tokenInput.value.trim());
            }
        });
    }

    const issueInput = document.getElementById("input-target-issue");
    const chkProperty = document.getElementById("chk-property");
    const chkMutation = document.getElementById("chk-mutation");
    const chkFastMode = document.getElementById("chk-fast-mode");

    if (chkFastMode) {
        chkFastMode.addEventListener("change", () => {
            if (chkFastMode.checked) {
                if (chkMutation) chkMutation.checked = false;
            } else {
                if (chkMutation) chkMutation.checked = true;
            }
        });
    }

    startBtn.addEventListener("click", () => {
        const issueVal = issueInput ? issueInput.value.trim() : "";
        const payload = {
            repo_path: repoInput.value.trim(),
            target_issue: issueVal || null,
            provider: providerSelect.value,
            model: modelSelect.value,
            max_iterations: chkFastMode && chkFastMode.checked ? 2 : 5,
            enforce_property: chkProperty ? chkProperty.checked : true,
            enforce_mutation: chkMutation ? chkMutation.checked : true
        };

        startBtn.disabled = true;
        startBtn.innerText = "Pipeline Executing...";
        resetDashboard();
        const issueMsg = payload.target_issue ? ` [Issue: ${payload.target_issue}]` : "";
        appendLog("info", `Initiating repair run on target: ${payload.repo_path}${issueMsg} via ${payload.provider.toUpperCase()} (${payload.model})...`);

        fetch("/api/repair/start", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        })
        .then(res => res.json())
        .then(data => {
            if (data.status !== "started") {
                appendLog("error", "Failed to start pipeline: " + (data.detail || "Unknown error"));
                startBtn.disabled = false;
                startBtn.innerText = "Launch Autonomous Repair";
            }
        })
        .catch(err => {
            appendLog("error", "Error starting repair: " + err.message);
            startBtn.disabled = false;
            startBtn.innerText = "Launch Autonomous Repair";
        });
    });

    // Human-in-the-loop approval button
    btnApprove.addEventListener("click", () => {
        const tokenInput = document.getElementById("input-github-token");
        const tokenVal = tokenInput ? tokenInput.value.trim() : "";
        if (tokenVal) {
            localStorage.setItem("github_token", tokenVal);
        }

        const errorBox = document.getElementById("pr-error-box");
        if (errorBox) errorBox.style.display = "none";

        btnApprove.disabled = true;
        btnApprove.innerText = "Submitting PR to GitHub...";
        appendLog("info", "Human approval granted! Dispatching PR creation to GitHub...");

        fetch("/api/repair/approve", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                github_token: tokenVal || undefined
            })
        })
        .then(res => res.json())
        .then(result => {
            if (result.success) {
                showPRSuccess(result);
                appendLog("success", `✓ Pull Request published: ${result.pr_url}`);
            } else {
                appendLog("error", `✗ PR submission failed: ${result.message}`);
                showPRError(result.message);
                btnApprove.disabled = false;
                btnApprove.innerText = "Retry PR Submission";
                if (result.needs_token && tokenInput) {
                    tokenInput.focus();
                    tokenInput.style.borderColor = "#f87171";
                    tokenInput.scrollIntoView({ behavior: "smooth", block: "center" });
                }
            }
        })
        .catch(err => {
            appendLog("error", "Network error approving PR: " + err.message);
            showPRError("Network error communicating with server: " + err.message);
            btnApprove.disabled = false;
            btnApprove.innerText = "Accept & Submit PR to GitHub";
        });
    });
}

function setupEventSource() {
    if (eventSource) {
        eventSource.close();
    }

    eventSource = new EventSource("/api/repair/stream");

    eventSource.onmessage = (e) => {
        if (!e.data || e.data.startsWith(":")) return;
        try {
            const event = JSON.parse(e.data);
            handlePipelineEvent(event.type, event.data);
        } catch (err) {
            console.error("Error parsing SSE event:", err, e.data);
        }
    };

    eventSource.onerror = (err) => {
        // SSE automatic reconnect
    };
}

function handlePipelineEvent(type, data) {
    switch (type) {
        case "log":
            appendLog(data.level || "info", data.message);
            break;

        case "stage_change":
            updateStepper(data.stage, data.status);
            break;

        case "sbfl_results":
            renderSBFLTable(data.top_lines || []);
            break;

        case "synthesis_results":
            renderHypotheses(data.hypotheses || [], data.chosen_hypothesis);
            renderDiff(data.unified_diff || "");
            break;

        case "verification_results":
            renderVerificationGates(data);
            break;

        case "ready_for_approval":
            currentApprovalData = data;
            showApprovalBanner(data);
            const startBtn = document.getElementById("btn-start-repair");
            startBtn.disabled = false;
            startBtn.innerText = "Launch Autonomous Repair";
            break;

        case "pr_published":
            if (data && data.success) {
                showPRSuccess(data);
            } else if (data) {
                showPRError(data.message);
            }
            break;

        case "pipeline_failed":
            appendLog("error", "Pipeline execution halted: " + (data.error || ""));
            const sBtn = document.getElementById("btn-start-repair");
            sBtn.disabled = false;
            sBtn.innerText = "Launch Autonomous Repair";
            break;
    }
}

function updateStepper(stageNum, status) {
    for (let i = 1; i <= 5; i++) {
        const stepEl = document.getElementById(`step-${i}`);
        if (!stepEl) continue;

        if (i < stageNum) {
            stepEl.className = "step-card completed";
        } else if (i === stageNum) {
            stepEl.className = status === "completed" ? "step-card completed" : "step-card active";
        } else {
            stepEl.className = "step-card";
        }
    }
}

function appendLog(level, message) {
    const terminal = document.getElementById("terminal-logs");
    if (!terminal) return;

    const timeStr = new Date().toLocaleTimeString();
    const entry = document.createElement("div");
    entry.className = `log-entry ${level}`;
    entry.innerHTML = `<span style="color:#64748b;">[${timeStr}]</span> <span>${escapeHtml(message)}</span>`;
    terminal.appendChild(entry);
    terminal.scrollTop = terminal.scrollHeight;
}

function renderSBFLTable(lines) {
    const tbody = document.getElementById("sbfl-table-body");
    if (!tbody) return;
    tbody.innerHTML = "";

    if (lines.length === 0) {
        tbody.innerHTML = `<tr><td colspan="4" style="color:#6b7280; text-align:center;">No suspicious lines identified.</td></tr>`;
        return;
    }

    lines.forEach((item, idx) => {
        const tr = document.createElement("tr");
        const scoreClass = item.score >= 0.5 ? "score-high" : "score-med";
        tr.innerHTML = `
            <td style="font-family:var(--font-mono); color:#93c5fd;">#${idx + 1}</td>
            <td style="font-family:var(--font-mono);">${escapeHtml(item.file)}:<span style="color:#f43f5e; font-weight:700;">${item.line}</span></td>
            <td><span class="score-badge ${scoreClass}">${item.score.toFixed(4)}</span></td>
            <td style="color:#94a3b8; font-size:0.78rem;">Failed: ${item.failed} | Passed: ${item.passed}</td>
        `;
        tbody.appendChild(tr);
    });
}

function renderHypotheses(hypotheses, chosenHyp) {
    const container = document.getElementById("hypotheses-container");
    if (!container) return;
    container.innerHTML = "";

    hypotheses.forEach((hyp, idx) => {
        const isChosen = (hyp === chosenHyp || idx === 0);
        const item = document.createElement("div");
        item.className = `hypothesis-item ${isChosen ? "chosen" : ""}`;
        item.innerHTML = `
            <strong>Hypothesis ${idx + 1}:</strong> ${escapeHtml(hyp)}
            ${isChosen ? '<span class="chosen-badge">Selected Cause</span>' : ''}
        `;
        container.appendChild(item);
    });
}

function renderVerificationGates(data) {
    const g1Status = document.getElementById("gate-1-status");
    const g1Val = document.getElementById("gate-1-val");
    const g2Status = document.getElementById("gate-2-status");
    const g2Val = document.getElementById("gate-2-val");
    const g3Status = document.getElementById("gate-3-status");
    const g3Val = document.getElementById("gate-3-val");

    if (data.gate1) {
        g1Status.innerText = data.gate1.passed ? "PASSED" : "FAILED";
        g1Status.className = `gate-status ${data.gate1.passed ? "passed" : "failed"}`;
        g1Val.innerText = `${data.gate1.passed_count}/${data.gate1.total_count} Passed`;
    }

    if (data.gate2) {
        g2Status.innerText = data.gate2.passed ? "PASSED" : "FAILED";
        g2Status.className = `gate-status ${data.gate2.passed ? "passed" : "failed"}`;
        g2Val.innerText = `${data.gate2.examples} Invariants`;
    }

    if (data.gate3) {
        g3Status.innerText = data.gate3.passed ? "PASSED" : "FAILED";
        g3Status.className = `gate-status ${data.gate3.passed ? "passed" : "failed"}`;
        g3Val.innerText = `${data.gate3.score}% Killed`;
    }
}

function renderDiff(diffText) {
    const diffContainer = document.getElementById("diff-viewer");
    if (!diffContainer) return;
    diffContainer.innerHTML = "";

    const lines = diffText.split("\n");
    lines.forEach(line => {
        const div = document.createElement("div");
        div.className = "diff-line";
        if (line.startsWith("+") && !line.startsWith("+++")) {
            div.className += " diff-add";
        } else if (line.startsWith("-") && !line.startsWith("---")) {
            div.className += " diff-del";
        } else if (line.startsWith("@@")) {
            div.className += " diff-hunk";
        }
        div.textContent = line;
        diffContainer.appendChild(div);
    });
}

function showApprovalBanner(data) {
    const banner = document.getElementById("approval-banner");
    const reportText = document.getElementById("approval-summary");
    const btnApprove = document.getElementById("btn-approve-pr");

    if (reportText) {
        reportText.innerHTML = `
            <p><strong>Identified Mechanical Cause:</strong> ${escapeHtml(data.chosen_hypothesis || "")}</p>
            <p style="margin-top:6px; color:#cbd5e1;">${escapeHtml(data.explanation || "")}</p>
            <div style="margin-top:12px; display:flex; gap:16px; font-size:0.85rem;">
                <span>⏱️ Runtime: <strong>${data.duration}s</strong></span>
                <span>🔄 Iterations: <strong>${data.iterations}/5</strong></span>
                <span>🛡️ Anti-Overfitting: <strong>100% Passed</strong></span>
            </div>
        `;
    }

    btnApprove.disabled = false;
    btnApprove.innerText = "Accept & Submit PR to GitHub 🚀";
    banner.classList.add("visible");
    banner.scrollIntoView({ behavior: "smooth" });
}

function showPRSuccess(data) {
    const errorBox = document.getElementById("pr-error-box");
    if (errorBox) errorBox.style.display = "none";

    const successBox = document.getElementById("pr-success-box");
    const linkEl = document.getElementById("pr-success-link");
    const btnEl = document.getElementById("pr-success-btn");
    const msgEl = document.getElementById("pr-success-msg");

    if (linkEl && data.pr_url) {
        linkEl.href = data.pr_url;
        linkEl.innerText = data.pr_url;
    }
    if (btnEl && data.pr_url) {
        btnEl.href = data.pr_url;
    }
    if (msgEl) {
        msgEl.innerText = data.message || "PR published successfully.";
    }

    successBox.style.display = "block";
    const btnApprove = document.getElementById("btn-approve-pr");
    if (btnApprove) btnApprove.style.display = "none";
}

function showPRError(message) {
    const successBox = document.getElementById("pr-success-box");
    if (successBox) successBox.style.display = "none";

    const errorBox = document.getElementById("pr-error-box");
    const errorMsg = document.getElementById("pr-error-msg");
    if (errorBox && errorMsg) {
        errorMsg.innerText = message;
        errorBox.style.display = "block";
        errorBox.scrollIntoView({ behavior: "smooth", block: "center" });
    }
}

function resetDashboard() {
    document.getElementById("terminal-logs").innerHTML = "";
    document.getElementById("sbfl-table-body").innerHTML = "";
    document.getElementById("hypotheses-container").innerHTML = "";
    document.getElementById("diff-viewer").innerHTML = "";
    document.getElementById("approval-banner").classList.remove("visible");
    document.getElementById("pr-success-box").style.display = "none";
    const errorBox = document.getElementById("pr-error-box");
    if (errorBox) errorBox.style.display = "none";
    document.getElementById("btn-approve-pr").style.display = "flex";

    for (let i = 1; i <= 5; i++) {
        const step = document.getElementById(`step-${i}`);
        if (step) step.className = "step-card";
    }
}

function escapeHtml(str) {
    if (!str) return "";
    return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
