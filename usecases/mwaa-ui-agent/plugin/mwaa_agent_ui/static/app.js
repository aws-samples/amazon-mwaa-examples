/* Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
 * SPDX-License-Identifier: MIT-0 */
/* MWAA AI Agent chat UI.
 *
 * Security notes:
 * - Model output and tool data are untrusted. They are rendered only through
 *   textContent / createElement, never innerHTML, and links are not rendered.
 * - Every POST sends the X-MWAA-Agent header with a JSON body; the plugin
 *   rejects requests without it (CSRF protection).
 */
(function () {
  "use strict";

  var STORAGE_PREFIX = "mwaa-agent:v2:";
  var MAX_STORED_MESSAGES = 60;

  var els = {
    env: document.getElementById("env"),
    tier: document.getElementById("tier"),
    context: document.getElementById("context"),
    banner: document.getElementById("banner"),
    messages: document.getElementById("messages"),
    suggestions: document.getElementById("suggestions"),
    form: document.getElementById("composer"),
    input: document.getElementById("input"),
    send: document.getElementById("send"),
    newChat: document.getElementById("new-chat"),
  };

  var page = readPageContext();
  if (/(?:^|[?&])embed=1(?:&|$)/.test(window.location.search)) {
    document.body.classList.add("embed");
    // The launcher panel is narrow: give the environment label its own line above the page context.
    var envEl = document.getElementById("env"), ctxEl = document.getElementById("context");
    if (envEl && ctxEl) ctxEl.parentNode.insertBefore(envEl, ctxEl);
  }
  var storageKey = null;
  // Never restore or render a transcript until /api/me binds storage to the authenticated principal.
  var state = { sessionId: newSessionId(), messages: [], pendingApprovals: null };
  var busy = false;
  var pendingApproval = false;
  var me = null;
  // Tool lines by toolUseId. Kept across turns: after an approval the tool finishes in the next request.
  var toolLines = Object.create(null);

  // ---------------------------------------------------------------- context

  function readPageContext() {
    // Airflow substitutes {DAG_ID} etc. without URL-encoding, so decode manually
    // and keep "+" literal (run ids contain "+00:00").
    var out = { dag_id: null, run_id: null, task_id: null, map_index: null };
    var query = window.location.search.replace(/^\?/, "");
    if (!query) return out;
    query.split("&").forEach(function (pair) {
      var idx = pair.indexOf("=");
      if (idx < 0) return;
      var key = pair.slice(0, idx);
      var value;
      try {
        value = decodeURIComponent(pair.slice(idx + 1));
      } catch (e) {
        value = pair.slice(idx + 1);
      }
      if (!value || /^\{[A-Z_]+\}$/.test(value)) return; // unreplaced template
      if (key === "map_index") {
        var n = parseInt(value, 10);
        out.map_index = isNaN(n) ? null : n;
      } else if (key === "dag_id" || key === "run_id" || key === "task_id") {
        out[key] = value;
      }
    });
    return out;
  }

  function describePage() {
    if (!page.dag_id) {
      return document.body.classList.contains("embed")
        ? "No DAG selected. Open a DAG, run, or task, or name one in your question."
        : "Opened from the navigation bar. Name a DAG to get started.";
    }
    var parts = ["DAG " + page.dag_id];
    if (page.run_id) parts.push("run " + page.run_id);
    if (page.task_id) {
      var t = "task " + page.task_id;
      if (page.map_index !== null && page.map_index >= 0) t += "[" + page.map_index + "]";
      parts.push(t);
    }
    return "Context: " + parts.join(" · ");
  }

  // ---------------------------------------------------------------- storage

  function newSessionId() {
    if (window.crypto && window.crypto.randomUUID) return window.crypto.randomUUID() + "-" + window.crypto.randomUUID().slice(0, 8);
    var bytes = new Uint8Array(24);
    window.crypto.getRandomValues(bytes);
    return Array.prototype.map.call(bytes, function (b) { return ("0" + b.toString(16)).slice(-2); }).join("");
  }

  function loadState() {
    if (!storageKey) return { sessionId: newSessionId(), messages: [], pendingApprovals: null };
    try {
      var raw = window.sessionStorage.getItem(storageKey);
      if (raw) {
        var parsed = JSON.parse(raw);
        if (parsed && typeof parsed.sessionId === "string" && Array.isArray(parsed.messages)) return parsed;
      }
    } catch (e) { /* storage unavailable */ }
    return { sessionId: newSessionId(), messages: [] };
  }

  function saveState() {
    if (!storageKey) return;
    try {
      state.messages = state.messages.slice(-MAX_STORED_MESSAGES);
      window.sessionStorage.setItem(storageKey, JSON.stringify(state));
    } catch (e) { /* ignore */ }
  }

  // ---------------------------------------------------------------- markdown (safe subset)

  function appendInline(parent, text) {
    // Supports `code` and **bold**. Everything else is plain text.
    var re = /(`[^`\n]+`|\*\*[^*\n]+\*\*)/g;
    var last = 0;
    var m;
    while ((m = re.exec(text)) !== null) {
      if (m.index > last) parent.appendChild(document.createTextNode(text.slice(last, m.index)));
      var token = m[0];
      var node;
      if (token.charAt(0) === "`") {
        node = document.createElement("code");
        node.textContent = token.slice(1, -1);
      } else {
        node = document.createElement("strong");
        node.textContent = token.slice(2, -2);
      }
      parent.appendChild(node);
      last = m.index + token.length;
    }
    if (last < text.length) parent.appendChild(document.createTextNode(text.slice(last)));
  }

  function renderMarkdown(container, text) {
    container.textContent = "";
    var lines = text.split("\n");
    var i = 0;
    var list = null;
    var para = [];

    function flushPara() {
      if (!para.length) return;
      var p = document.createElement("p");
      appendInline(p, para.join("\n"));
      container.appendChild(p);
      para = [];
    }
    function closeList() { list = null; }

    while (i < lines.length) {
      var line = lines[i];
      var fence = line.match(/^\s*```(\S*)\s*$/);
      if (fence) {
        flushPara(); closeList();
        var code = [];
        i++;
        while (i < lines.length && !/^\s*```\s*$/.test(lines[i])) { code.push(lines[i]); i++; }
        var pre = document.createElement("pre");
        var c = document.createElement("code");
        c.textContent = code.join("\n");
        pre.appendChild(c);
        container.appendChild(pre);
        i++;
        continue;
      }
      var heading = line.match(/^(#{1,4})\s+(.*)$/);
      if (heading) {
        flushPara(); closeList();
        var h = document.createElement("h" + Math.min(heading[1].length + 1, 4));
        appendInline(h, heading[2]);
        container.appendChild(h);
        i++;
        continue;
      }
      var item = line.match(/^\s*([-*]|\d+\.)\s+(.*)$/);
      if (item) {
        flushPara();
        var ordered = /\d/.test(item[1]);
        if (!list || (list.tagName === "OL") !== ordered) {
          list = document.createElement(ordered ? "ol" : "ul");
          container.appendChild(list);
        }
        var li = document.createElement("li");
        appendInline(li, item[2]);
        list.appendChild(li);
        i++;
        continue;
      }
      if (!line.trim()) { flushPara(); closeList(); i++; continue; }
      closeList();
      para.push(line);
      i++;
    }
    flushPara();
  }

  // ---------------------------------------------------------------- rendering

  function scrollToEnd() { els.messages.scrollTop = els.messages.scrollHeight; }

  function addMessage(role, text, persist) {
    var div = document.createElement("div");
    div.className = "msg " + role;
    if (role === "assistant") renderMarkdown(div, text);
    else div.textContent = text;
    els.messages.appendChild(div);
    if (persist) { state.messages.push({ role: role, text: text }); saveState(); }
    scrollToEnd();
    return div;
  }

  // One collapsible line per tool call. The summary says what ran; expanding it shows the call itself
  // (method and path, AWS operation and parameters), already redacted by the agent. Text nodes only.
  function addToolLine(name) {
    var line = document.createElement("details");
    line.className = "tool";
    var summary = document.createElement("summary");
    summary.textContent = "Running " + name + "…";
    var detail = document.createElement("pre");
    detail.textContent = "Waiting for the call details…";
    line.appendChild(summary);
    line.appendChild(detail);
    els.messages.appendChild(line);
    scrollToEnd();
    return { line: line, summary: summary, detail: detail };
  }

  function showBanner(text) {
    els.banner.textContent = text;
    els.banner.hidden = !text;
  }

  function setBusy(value) {
    busy = value;
    var disabled = busy || pendingApproval || !me || !!(me && me.config_error);
    els.send.disabled = disabled;
    els.input.disabled = disabled;
    els.newChat.disabled = busy || pendingApproval || !me;
    Array.prototype.forEach.call(els.suggestions.querySelectorAll("button"), function (b) { b.disabled = disabled; });
  }

  // Before the first answer: starters for the current page. After an answer: the agent's own next steps
  // for this conversation (state.suggestions). Clicking one sends it; any change it leads to still needs
  // an approval.
  // Printable text only: no control, zero-width or text-direction characters that could make a suggestion
  // read differently from what it sends.
  function validSuggestion(t) {
    return typeof t === "string" && t.length >= 3 && t.length <= 150 &&
      !/[\u0000-\u001f\u007f-\u009f\u00ad\u061c\u180e\u200b-\u200f\u2028-\u202e\u2060-\u206f\ufeff<]/.test(t);
  }

  function renderSuggestions() {
    els.suggestions.textContent = "";
    // Only on the page whose DAG they were made for (covers full reloads and in-app navigation).
    var forThisPage = (state.suggestionsDag || null) === (page.dag_id || null);
    var stored = (forThisPage && Array.isArray(state.suggestions) ? state.suggestions : []).filter(validSuggestion);
    var dynamic = stored.length > 0;
    els.suggestions.setAttribute("aria-label", dynamic ? "Suggested next steps" : "Suggested questions");
    var items = [];
    if (dynamic) {
      var label = document.createElement("span");
      label.className = "suggestions-label";
      label.textContent = "Next steps:";
      els.suggestions.appendChild(label);
      items = stored.slice(0, 3);
    } else {
      if (page.task_id) items.push("Why did this task fail?");
      else if (page.run_id) items.push("Why did this DAG run fail?");
      if (page.dag_id) {
        items.push("Summarize the recent runs of this DAG");
        if (me && me.tier === "operate") items.push("Test this DAG end to end");
      } else {
        items.push("Are there any DAG import errors?");
      }
      if (me && me.can_deploy_dags && !page.run_id) items.push("Write a new DAG for me");
    }
    items.forEach(function (text) {
      var b = document.createElement("button");
      b.type = "button";
      b.className = "secondary";
      b.textContent = text;
      if (dynamic) {
        // The agent's suggestions come from model output, which task logs or DAG code may have steered.
        // Clicking only fills the input: the user reads the exact message and sends it themselves.
        b.title = "Puts this text in the message box. Review it, then press Send.";
        b.addEventListener("click", function () {
          if (busy) return;
          els.input.value = text;
          els.input.focus();
        });
      } else {
        b.addEventListener("click", function () { if (!busy) sendMessage(text); });
      }
      els.suggestions.appendChild(b);
    });
    setBusy(busy);
  }

  // Shows one card per pending action. Decisions are sent together once every card is decided,
  // because the agent resumes only when it has an explicit answer for each action.
  function renderApprovals(approvals) {
    approvals = (approvals || []).filter(function (a) { return a && typeof a.id === "string"; });
    if (!approvals.length) return;
    pendingApproval = true;
    state.pendingApprovals = approvals;
    saveState();
    setBusy(busy);
    var decisions = Object.create(null);
    var remaining = approvals.length;
    var firstButton = null;

    approvals.forEach(function (approval, index) {
      var card = document.createElement("section");
      card.className = "approval";
      card.setAttribute("aria-label", "Approval required");

      var h = document.createElement("h2");
      h.textContent = approvals.length > 1
        ? "Approve action " + (index + 1) + " of " + approvals.length + "?"
        : "Approve this action?";
      card.appendChild(h);

      var p = document.createElement("p");
      p.textContent = "The agent wants to " + (approval.summary || "make a change") + ".";
      card.appendChild(p);

      if (approval.tool === "deploy_dag") {
        // Show exactly what will be written: target, size, checksum, then the complete file.
        var meta = document.createElement("pre");
        var deployMeta = {
          target: approval.target,
          replaces_existing: approval.replaces_existing === true,
          bytes: approval.bytes,
          sha256: approval.sha256,
        };
        // Multi-team environments: the team whose DAG folder (bundle team_<team>) receives the file.
        if (typeof approval.team === "string" && approval.team) deployMeta = Object.assign({ team: approval.team }, deployMeta);
        meta.textContent = JSON.stringify(deployMeta, null, 2);
        card.appendChild(meta);
        var file = document.createElement("pre");
        file.className = "file";
        file.setAttribute("aria-label", "Full content of " + (approval.file_name || "the DAG file"));
        file.textContent = typeof approval.content === "string" ? approval.content : "";
        card.appendChild(file);
      } else {
        var details = { method: approval.method, path: approval.path };
        if (approval.query) details.query = approval.query;
        if (approval.body) details.body = approval.body;
        var pre = document.createElement("pre");
        pre.textContent = JSON.stringify(details, null, 2);
        card.appendChild(pre);
      }

      var actions = document.createElement("div");
      actions.className = "actions";
      var yes = document.createElement("button");
      yes.type = "button";
      yes.textContent = "Approve";
      var no = document.createElement("button");
      no.type = "button";
      no.className = "secondary";
      no.textContent = "Decline";
      actions.appendChild(yes);
      actions.appendChild(no);
      card.appendChild(actions);
      els.messages.appendChild(card);
      if (!firstButton) firstButton = yes;

      function decide(approved) {
        yes.disabled = true;
        no.disabled = true;
        var note = document.createElement("p");
        note.className = "muted";
        note.textContent = approved ? "Approved." : "Declined.";
        if (remaining > 1) note.textContent += " Decide the remaining actions to continue.";
        card.appendChild(note);
        decisions[approval.id] = approved;
        remaining -= 1;
        if (remaining > 0) return;
        pendingApproval = false;
        state.pendingApprovals = null;
        saveState();
        runTurn("api/approve", { session_id: state.sessionId, decisions: decisions, page: page });
      }
      yes.addEventListener("click", function () { decide(true); });
      no.addEventListener("click", function () { decide(false); });
    });
    scrollToEnd();
    if (firstButton) firstButton.focus();
  }

  // ---------------------------------------------------------------- network

  function postJson(url, body) {
    return fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-MWAA-Agent": "1", Accept: "application/x-ndjson" },
      body: JSON.stringify(body),
    });
  }

  function errorText(response) {
    return response.text().then(function (t) {
      try {
        var j = JSON.parse(t);
        if (j && j.detail) return typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
      } catch (e) { /* not json */ }
      return "Request failed (" + response.status + ").";
    });
  }

  function runTurn(url, body) {
    setBusy(true);
    var assistantDiv = null;
    var assistantText = "";
    var renderQueued = false;
    var approvalBatch = [];
    var nextSuggestions = null;
    var thinking = addMessage("assistant", "", false);
    thinking.classList.add("thinking");
    thinking.textContent = "Working";

    function flushText() {
      renderQueued = false;
      if (assistantDiv) { renderMarkdown(assistantDiv, assistantText); scrollToEnd(); }
    }

    function finishAssistant() {
      if (assistantDiv && assistantText.trim()) {
        renderMarkdown(assistantDiv, assistantText);
        state.messages.push({ role: "assistant", text: assistantText });
        saveState();
      }
      assistantDiv = null;
      assistantText = "";
    }

    function handle(ev) {
      if (!ev || typeof ev.type !== "string") return;
      if (thinking && ev.type !== "done") { thinking.remove(); thinking = null; }
      switch (ev.type) {
        case "text":
          if (!assistantDiv) {
            assistantDiv = document.createElement("div");
            assistantDiv.className = "msg assistant";
            els.messages.appendChild(assistantDiv);
          }
          assistantText += String(ev.text || "");
          if (!renderQueued) { renderQueued = true; window.requestAnimationFrame(flushText); }
          break;
        case "tool_start":
          finishAssistant();
          toolLines[ev.id] = addToolLine(String(ev.name || "tool"));
          break;
        case "tool_input":
          if (toolLines[ev.id]) toolLines[ev.id].detail.textContent = String(ev.detail || "");
          break;
        case "tool_end":
          var tool = toolLines[ev.id];
          if (tool) {
            var failed = ev.status === "error" || typeof ev.error === "string";
            tool.summary.textContent = tool.summary.textContent
              .replace(/^Running /, failed ? "Stopped " : "Ran ").replace(/…$/, "");
            if (typeof ev.error === "string") tool.detail.textContent += "\n\n→ " + ev.error;
            if (failed) tool.line.classList.add("failed");
            delete toolLines[ev.id];
          }
          break;
        case "suggestions":
          nextSuggestions = (Array.isArray(ev.items) ? ev.items : []).filter(validSuggestion).slice(0, 3);
          break;
        case "approval_required":
          // Each card arrives as its own event; show them together once the turn ends.
          finishAssistant();
          approvalBatch = approvalBatch.concat(Array.isArray(ev.approvals) ? ev.approvals : []);
          break;
        case "error":
          finishAssistant();
          addMessage("error", String(ev.message || "Something went wrong."), false);
          break;
        case "done":
          break;
        default:
          break;
      }
    }

    return postJson(url, body)
      .then(function (response) {
        if (!response.ok) return errorText(response).then(function (t) { handle({ type: "error", message: t }); });
        var reader = response.body.getReader();
        var decoder = new TextDecoder();
        var buffer = "";
        function pump() {
          return reader.read().then(function (chunk) {
            if (chunk.done) {
              if (buffer.trim()) { try { handle(JSON.parse(buffer)); } catch (e) { /* partial */ } }
              return;
            }
            buffer += decoder.decode(chunk.value, { stream: true });
            var lines = buffer.split("\n");
            buffer = lines.pop();
            lines.forEach(function (line) {
              if (!line.trim()) return;
              try { handle(JSON.parse(line)); } catch (e) { /* skip malformed line */ }
            });
            return pump();
          });
        }
        return pump();
      })
      .catch(function () { handle({ type: "error", message: "Lost the connection to the agent." }); })
      .then(function () {
        if (thinking) { thinking.remove(); thinking = null; }
        finishAssistant();
        if (approvalBatch.length) { renderApprovals(approvalBatch); approvalBatch = []; }
        if (nextSuggestions && nextSuggestions.length) {
          state.suggestions = nextSuggestions;
          state.suggestionsDag = page.dag_id;  // they name this page's DAG and runs
          saveState();
          renderSuggestions();
        }
        setBusy(false);
        if (!pendingApproval) els.input.focus();
      });
  }

  function sendMessage(text) {
    text = text.trim();
    if (!text || busy || pendingApproval) return;
    addMessage("user", text, true);
    els.input.value = "";
    runTurn("api/chat", { session_id: state.sessionId, message: text, page: page });
  }

  // ---------------------------------------------------------------- boot

  // The global launcher (Airflow 3.2+) embeds this page once and sends route changes. Accept them
  // only from our parent window on our own origin, and only with the expected shape.
  function validId(value) {
    return typeof value === "string" && value.length > 0 && value.length <= 250 && !/[\r\n]/.test(value);
  }
  window.addEventListener("message", function (event) {
    if (event.origin !== window.location.origin || event.source !== window.parent) return;
    var data = event.data;
    if (!data || data.type !== "mwaa-agent:page" || typeof data.page !== "object" || !data.page) return;
    var next = { dag_id: null, run_id: null, task_id: null, map_index: null };
    if (validId(data.page.dag_id)) next.dag_id = data.page.dag_id;
    if (next.dag_id && validId(data.page.run_id)) next.run_id = data.page.run_id;
    if (next.dag_id && validId(data.page.task_id)) next.task_id = data.page.task_id;
    if (next.task_id && Number.isInteger(data.page.map_index)) next.map_index = data.page.map_index;
    if (JSON.stringify(next) === JSON.stringify(page)) return;
    page = next;
    els.context.textContent = describePage();
    if (me) renderSuggestions();
    setBusy(busy);
  });

  els.form.addEventListener("submit", function (e) { e.preventDefault(); sendMessage(els.input.value); });
  els.input.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); sendMessage(els.input.value); }
  });
  els.newChat.addEventListener("click", function () {
    if (busy || pendingApproval || !me) return;
    state = { sessionId: newSessionId(), messages: [], pendingApprovals: null, suggestions: null };
    saveState();
    pendingApproval = false;
    toolLines = {};
    els.messages.textContent = "";
    renderSuggestions();
    setBusy(false);
  });

  els.context.textContent = describePage();
  setBusy(false);

  fetch("api/me", { credentials: "same-origin" })
    .then(function (r) {
      if (!r.ok) return errorText(r).then(function (t) { throw new Error(t); });
      return r.json();
    })
    .then(function (data) {
      me = data;
      if (!data.storage_owner_id || !/^[a-f0-9]{64}$/.test(data.storage_owner_id)) {
        throw new Error("The server did not return a valid storage owner binding.");
      }
      storageKey = STORAGE_PREFIX + data.storage_owner_id;
      state = loadState();
      els.messages.textContent = "";
      state.messages.forEach(function (m) { addMessage(m.role, m.text, false); });
      if (Array.isArray(state.pendingApprovals) && state.pendingApprovals.length) renderApprovals(state.pendingApprovals);
      // Name the deployment explicitly: the local runner and Amazon MWAA UIs otherwise look identical.
      var where = data.deployment === "local"
        ? "Local runner (Docker)"
        : "Amazon MWAA · " + (data.environment_name || "unknown environment");
      els.env.textContent = where + " · Airflow " + data.airflow_version;
      els.env.classList.toggle("local", data.deployment === "local");
      els.tier.hidden = false;
      els.tier.textContent = data.can_deploy_dags
        ? "Can run and deploy DAGs (with approval)"
        : data.tier === "operate" ? "Can run DAGs (with approval)" : "Read-only";
      if (data.config_error) showBanner("The agent is not configured: " + data.config_error);
      renderSuggestions();
      setBusy(false);
    })
    .catch(function (err) { showBanner(err.message || "Could not load the agent."); });
})();
