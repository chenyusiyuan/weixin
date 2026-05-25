const state = {
  sessions: [],
  currentSessionId: "",
  resources: [],
  currentResource: "customers",
  selectedRecord: null,
  isSending: false,
  currentSession: null,
  llmProfiles: [],
  defaultLlmProfileId: "default",
};

const $ = (id) => document.getElementById(id);

function api(path) {
  return `/api/demo${path}`;
}

async function request(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (options.body && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }
  const resp = await fetch(api(path), { ...options, headers });
  const text = await resp.text();
  const data = text ? JSON.parse(text) : {};
  if (!resp.ok) {
    throw new Error(data.detail || resp.statusText);
  }
  return data;
}

function pretty(data) {
  return JSON.stringify(data ?? {}, null, 2);
}

function formatMeta(meta = {}) {
  const parts = [];
  if (meta.route) parts.push(meta.route);
  if (meta.matched_skill_name || meta.matched_skill_id) {
    parts.push(meta.matched_skill_name || meta.matched_skill_id);
  }
  if (meta.tools_called?.length) parts.push(`tools: ${meta.tools_called.join(", ")}`);
  return parts.join(" | ");
}

function showError(err) {
  alert(err.message || String(err));
}

async function init() {
  bindEvents();
  await loadLlmProfiles();
  await Promise.all([loadHealth(false), loadResources()]);
  await loadSessions();
  if (!state.sessions.length) {
    await createSession();
  } else {
    await selectSession(state.sessions[0].session_id);
  }
  await loadResource("customers");
}

function bindEvents() {
  $("chatViewBtn").addEventListener("click", () => switchView("chat"));
  $("adminViewBtn").addEventListener("click", () => switchView("admin"));
  $("newSessionBtn").addEventListener("click", createSession);
  $("chatForm").addEventListener("submit", sendChat);
  $("chatInput").addEventListener("keydown", handleChatInputKeydown);
  $("llmProfileSelect").addEventListener("change", updateLlmProfile);
  $("probeHealthBtn").addEventListener("click", () => renderCustomerPanel(state.currentSession));
  $("loadResourceBtn").addEventListener("click", () => loadResource(state.currentResource));
  $("newRecordBtn").addEventListener("click", newRecord);
  $("saveRecordBtn").addEventListener("click", saveRecord);
  $("deleteRecordBtn").addEventListener("click", deleteRecord);
  $("resetDataBtn").addEventListener("click", resetData);
  document.querySelectorAll("[data-customer]").forEach((btn) => {
    btn.addEventListener("click", () => injectCustomer(btn.dataset.customer));
  });
}

function handleChatInputKeydown(event) {
  if (event.key !== "Enter" || event.isComposing) return;
  event.preventDefault();
  if (!state.isSending) {
    $("chatForm").requestSubmit();
  }
}

function switchView(view) {
  const isChat = view === "chat";
  $("chatView").classList.toggle("hidden", !isChat);
  $("adminView").classList.toggle("hidden", isChat);
  $("chatViewBtn").classList.toggle("active", isChat);
  $("adminViewBtn").classList.toggle("active", !isChat);
}

async function loadHealth(probe) {
  try {
    const profileId = selectedLlmProfileId();
    const data = await request(
      `/health?probe=${probe ? "true" : "false"}&llm_profile_id=${encodeURIComponent(profileId)}`,
    );
    renderHealth(data);
  } catch (err) {
    $("healthStrip").textContent = `健康状态读取失败：${err.message}`;
  }
}

function renderHealth(data) {
  const items = [
    ["database", "数据库"],
    ["runtime", "运行时"],
    ["llm", "LLM"],
    ["embedding", "Embedding"],
  ];
  $("healthStrip").replaceChildren(
    ...items.map(([key, label]) => {
      const value = data[key] || {};
      const el = document.createElement("div");
      const lastCall = value.last_call || {};
      const runtimeClient = value.runtime_client || {};
      const displayStatus = lastCall.status === "error"
        ? "error"
        : lastCall.status === "ok"
          ? "ok"
        : value.status || runtimeClient.status || "unknown";
      el.className = `health-pill ${displayStatus}`;
      const detail = lastCall.status === "error"
        ? (lastCall.error || lastCall.status_code || "last call failed")
        : value.error
        || runtimeClient.detail
        || value.profile_id
        || value.model
        || value.domain_classifier
        || value.db_path
        || "";
      el.innerHTML = `<strong>${escapeHtml(label)}: ${escapeHtml(displayStatus)}</strong><span>${escapeHtml(String(detail))}</span>`;
      return el;
    }),
  );
}

async function loadLlmProfiles() {
  const data = await request("/llm-profiles");
  state.llmProfiles = data.profiles || [];
  state.defaultLlmProfileId = data.default_profile_id || state.llmProfiles[0]?.id || "default";
  renderLlmProfiles();
}

function renderLlmProfiles() {
  const select = $("llmProfileSelect");
  const current = state.currentSession?.llm_profile_id || selectedLlmProfileId();
  const locked = isLlmProfileLocked();
  select.replaceChildren(
    ...state.llmProfiles.map((profile) => {
      const opt = document.createElement("option");
      opt.value = profile.id;
      opt.textContent = profile.id;
      return opt;
    }),
  );
  select.value = state.llmProfiles.some((profile) => profile.id === current)
    ? current
    : state.defaultLlmProfileId;
  select.disabled = locked || state.isSending;
  select.title = locked ? "会话开始后模型已固定" : "";
}

function selectedLlmProfileId() {
  if (isLlmProfileLocked() && state.currentSession?.llm_profile_id) {
    return state.currentSession.llm_profile_id;
  }
  return $("llmProfileSelect")?.value
    || state.currentSession?.llm_profile_id
    || state.defaultLlmProfileId;
}

function isLlmProfileLocked() {
  return Number(state.currentSession?.customer_message_count || 0) > 0;
}

async function loadSessions() {
  const data = await request("/sessions");
  state.sessions = data.sessions || [];
  renderSessions();
}

function renderSessions() {
  const list = $("sessionList");
  list.replaceChildren();
  state.sessions.forEach((session) => {
    const item = document.createElement("div");
    item.className = `session-item ${session.session_id === state.currentSessionId ? "active" : ""}`;
    item.addEventListener("click", () => selectSession(session.session_id));
    const text = document.createElement("div");
    const customer = session.customer_id || "未绑定客户";
    const profile = profileLabel(session.llm_profile_id);
    text.innerHTML = `
      <div class="session-title">${escapeHtml(session.title || session.session_id)}</div>
      <div class="session-meta">${escapeHtml(`${customer} · ${profile}`)}</div>
    `;
    const del = document.createElement("button");
    del.className = "session-delete";
    del.type = "button";
    del.textContent = "删";
    del.addEventListener("click", async (event) => {
      event.stopPropagation();
      await deleteSession(session.session_id);
    });
    item.append(text, del);
    list.appendChild(item);
  });
}

async function createSession() {
  try {
    const data = await request("/sessions", {
      method: "POST",
      body: JSON.stringify({ title: "新对话", llm_profile_id: selectedLlmProfileId() }),
    });
    await loadSessions();
    await selectSession(data.session.session_id);
  } catch (err) {
    showError(err);
  }
}

async function deleteSession(sessionId) {
  try {
    await request(`/sessions/${encodeURIComponent(sessionId)}`, { method: "DELETE" });
    await loadSessions();
    if (state.currentSessionId === sessionId) {
      if (state.sessions.length) {
        await selectSession(state.sessions[0].session_id);
      } else {
        await createSession();
      }
    }
  } catch (err) {
    showError(err);
  }
}

async function selectSession(sessionId) {
  state.currentSessionId = sessionId;
  const data = await request(`/sessions/${encodeURIComponent(sessionId)}/messages`);
  state.currentSession = data.session || null;
  renderLlmProfiles();
  await loadHealth(false);
  $("sessionTitle").textContent = data.session?.title || sessionId;
  $("sessionSub").textContent = data.session?.customer_id
    ? `当前绑定客户：${data.session.customer_id}`
    : "保留真实核身流程，也可一键注入客户";
  renderMessages(data.messages || []);
  renderCustomerPanel(data.session);
  renderSessions();
}

async function updateLlmProfile() {
  if (!state.currentSessionId) return;
  if (isLlmProfileLocked()) {
    renderLlmProfiles();
    return;
  }
  try {
    const data = await request(`/sessions/${encodeURIComponent(state.currentSessionId)}/llm-profile`, {
      method: "POST",
      body: JSON.stringify({ llm_profile_id: selectedLlmProfileId() }),
    });
    state.currentSession = data.session || state.currentSession;
    await loadSessions();
    await loadHealth(false);
  } catch (err) {
    renderLlmProfiles();
    showError(err);
  }
}

function renderMessages(messages) {
  const wrap = $("messages");
  wrap.replaceChildren();
  messages.forEach((message) => {
    appendMessage(
      message.role,
      message.text,
      formatMeta(message.metadata) || message.created_at || "",
      "",
      message,
    );
  });
  wrap.scrollTop = wrap.scrollHeight;
}

function appendMessage(role, text, metaText = "", extraClass = "", message = null) {
  const wrap = $("messages");
  const el = document.createElement("div");
  el.className = `message ${role} ${extraClass}`.trim();
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = text;
  const meta = document.createElement("div");
  meta.className = "message-meta";
  meta.textContent = metaText;
  el.append(bubble, meta);
  wrap.appendChild(el);
  wrap.scrollTop = wrap.scrollHeight;
  return { el, bubble, meta };
}

function setComposerBusy(isBusy) {
  state.isSending = isBusy;
  $("chatInput").disabled = isBusy;
  $("chatForm").querySelector("button[type='submit']").disabled = isBusy;
  renderLlmProfiles();
}

async function sendChat(event) {
  event.preventDefault();
  const input = $("chatInput");
  const userText = input.value.trim();
  if (!userText || !state.currentSessionId || state.isSending) return;
  input.value = "";
  appendMessage("customer", userText, "刚刚");
  const pending = appendMessage("assistant", "", "正在连接链路...", "pending");
  pending.bubble.innerHTML = `<span class="typing-text">思考中</span><span class="typing-dots"><i></i><i></i><i></i></span>`;
  setComposerBusy(true);
  try {
    const data = await streamChat(userText, pending);
    await loadSessions();
    await selectSession(state.currentSessionId);
  } catch (err) {
    pending.el.classList.remove("pending");
    pending.bubble.textContent = `请求失败：${err.message}`;
    pending.meta.textContent = "error";
    showError(err);
  } finally {
    setComposerBusy(false);
    input.focus();
  }
}

async function streamChat(userText, pending) {
  const resp = await fetch(api("/chat/stream"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_id: state.currentSessionId,
      user_text: userText,
      llm_profile_id: selectedLlmProfileId(),
    }),
  });
  if (!resp.ok || !resp.body) {
    throw new Error(`stream request failed: ${resp.status}`);
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finalData = null;
  let startedAnswer = false;

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";
    for (const line of lines) {
      if (!line.trim()) continue;
      const event = JSON.parse(line);
      if (event.type === "status") {
        pending.meta.textContent = `${event.message}${event.heartbeat ? ` · ${event.heartbeat}s` : ""}`;
      } else if (event.type === "answer_delta") {
        if (!startedAnswer) {
          pending.el.classList.remove("pending");
          pending.bubble.textContent = "";
          pending.meta.textContent = "正在输出话术...";
          startedAnswer = true;
        }
        pending.bubble.textContent += event.delta || "";
        $("messages").scrollTop = $("messages").scrollHeight;
      } else if (event.type === "final") {
        finalData = event;
        pending.el.classList.remove("pending");
        if (!startedAnswer) {
          pending.bubble.textContent = event.response?.answer || "";
        }
        pending.meta.textContent = formatMeta(event.debug) || event.assistant_message?.created_at || "";
      } else if (event.type === "error") {
        throw new Error(event.message || "stream failed");
      }
    }
  }

  if (!finalData) {
    throw new Error("stream ended before final response");
  }
  return finalData;
}

async function renderCustomerPanel(session) {
  const customerId = session?.customer_id || "";
  if (!customerId) {
    $("responseSummary").replaceChildren(emptySummaryCell("未核身", "注入客户或完成核身后展示资料"));
    $("responseJson").innerHTML = `<div class="empty-context">当前 session 尚未绑定客户。</div>`;
    return;
  }

  $("responseSummary").replaceChildren(emptySummaryCell("加载中", `正在读取 ${customerId} 相关信息`));
  try {
    const context = await loadCustomerContext(customerId);
    renderCustomerSummary(customerId, context);
    renderCustomerContext(context);
  } catch (err) {
    $("responseSummary").replaceChildren(emptySummaryCell("读取失败", err.message));
    $("responseJson").innerHTML = `<div class="empty-context">客户信息读取失败：${escapeHtml(err.message)}</div>`;
  }
}

async function loadCustomerContext(customerId) {
  const resources = [
    "customers",
    "bills",
    "loans",
    "memberships",
    "quotas",
    "tickets",
    "call_history",
    "sms_history",
    "stop_collection_history",
    "refund_history",
  ];
  const entries = await Promise.all(resources.map(async (resource) => {
    const data = await request(`/data/${resource}?owner_id=${encodeURIComponent(customerId)}`);
    return [resource, data.records || []];
  }));
  const byResource = Object.fromEntries(entries);
  return {
    customerId,
    profile: byResource.customers?.[0]?.payload || {},
    bill: byResource.bills?.[0]?.payload || {},
    loan: byResource.loans?.[0]?.payload || {},
    membership: byResource.memberships?.[0]?.payload || {},
    quota: byResource.quotas?.[0]?.payload || {},
    tickets: (byResource.tickets || []).map((r) => r.payload),
    calls: (byResource.call_history || []).map((r) => r.payload),
    sms: (byResource.sms_history || []).map((r) => r.payload),
    stops: (byResource.stop_collection_history || []).map((r) => r.payload),
    refunds: (byResource.refund_history || []).map((r) => r.payload),
  };
}

function renderCustomerSummary(customerId, context) {
  const p = context.profile;
  const b = context.bill;
  const q = context.quota;
  const cells = [
    ["客户", `${customerId} ${p.customer_name || ""}`],
    ["手机号", p.phone || p.phone_masked || "-"],
    ["账户状态", p.account_status || "-"],
    ["风险标签", p.risk_tag || "-"],
    ["逾期", b.overdue_days != null ? `${b.overdue_days} 天 / ${b.overdue_amount || 0} 元` : "-"],
    ["额度", q.available_quota != null ? `可用 ${q.available_quota}` : "-"],
  ];
  $("responseSummary").replaceChildren(
    ...cells.map(([label, value]) => {
      const el = document.createElement("div");
      el.className = "summary-cell";
      el.innerHTML = `<span>${escapeHtml(label)}</span><strong>${escapeHtml(String(value))}</strong>`;
      return el;
    }),
  );
}

function renderCustomerContext(context) {
  const sections = [
    ["客户画像", context.profile],
    ["账单还款", context.bill],
    ["贷款服务", context.loan],
    ["额度", context.quota],
    ["会员", context.membership],
  ];
  const html = [
    ...sections.map(([title, data]) => contextSection(title, data)),
    listSection("工单记录", context.tickets),
    listSection("退款记录", context.refunds),
    listSection("通话记录", context.calls),
    listSection("短信记录", context.sms),
    listSection("停催记录", context.stops),
  ].filter(Boolean).join("");
  $("responseJson").innerHTML = html || `<div class="empty-context">暂无可展示的客户信息。</div>`;
}

function emptySummaryCell(title, text) {
  const el = document.createElement("div");
  el.className = "summary-cell wide-cell";
  el.innerHTML = `<span>${escapeHtml(title)}</span><strong>${escapeHtml(text)}</strong>`;
  return el;
}

function contextSection(title, data) {
  const rows = Object.entries(data || {}).filter(([, value]) => value !== undefined && value !== null && value !== "");
  if (!rows.length) return "";
  return `
    <section class="context-section">
      <h4>${escapeHtml(title)}</h4>
      ${rows.map(([key, value]) => `
        <div class="context-row">
          <span>${escapeHtml(key)}</span>
          <strong>${escapeHtml(formatCustomerValue(value))}</strong>
        </div>
      `).join("")}
    </section>
  `;
}

function listSection(title, records) {
  if (!records?.length) return "";
  return `
    <section class="context-section">
      <h4>${escapeHtml(title)}</h4>
      ${records.map((record, index) => `
        <div class="context-list-item">
          <div class="context-list-title">#${index + 1}</div>
          ${Object.entries(record || {}).filter(([, value]) => value !== undefined && value !== null && value !== "").map(([key, value]) => `
            <div><span>${escapeHtml(key)}</span><strong>${escapeHtml(formatCustomerValue(value))}</strong></div>
          `).join("")}
        </div>
      `).join("")}
    </section>
  `;
}

function formatCustomerValue(value) {
  if (typeof value === "object") {
    return JSON.stringify(value, null, 2);
  }
  return String(value);
}

async function injectCustomer(customerId) {
  if (!state.currentSessionId) return;
  try {
    await request(`/sessions/${encodeURIComponent(state.currentSessionId)}/inject-customer`, {
      method: "POST",
      body: JSON.stringify({ customer_id: customerId }),
    });
    await loadSessions();
    await selectSession(state.currentSessionId);
    renderCustomerPanel(state.currentSession);
  } catch (err) {
    showError(err);
  }
}

async function loadResources() {
  const data = await request("/resources");
  state.resources = data.resources || [];
  const nav = $("resourceNav");
  nav.replaceChildren();
  state.resources.forEach((resource) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = resource.label;
    btn.dataset.resource = resource.name;
    btn.addEventListener("click", () => loadResource(resource.name));
    nav.appendChild(btn);
  });
}

async function loadResource(resource) {
  state.currentResource = resource;
  const owner = $("ownerFilter").value.trim();
  const data = await request(`/data/${resource}${owner ? `?owner_id=${encodeURIComponent(owner)}` : ""}`);
  document.querySelectorAll("#resourceNav button").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.resource === resource);
  });
  $("resourceTitle").textContent = data.resource.label;
  $("resourceHint").textContent = `${data.resource.name} | ${data.resource.kind} | id: ${data.resource.id_field}`;
  renderRecordList(data.records || []);
  if (data.records?.length) {
    selectRecord(data.records[0]);
  } else {
    newRecord();
  }
}

function renderRecordList(records) {
  const list = $("recordList");
  list.replaceChildren();
  records.forEach((record) => {
    const payload = record.payload || {};
    const summary = payload.customer_name || payload.summary || payload.type || payload.status || "";
    const item = document.createElement("div");
    item.className = "record-item";
    item.dataset.recordId = record.record_id;
    item.innerHTML = `
      <strong>${escapeHtml(record.record_id)}${record.immutable ? " · 锁定" : ""}</strong>
      <span>${escapeHtml(record.owner_id)} ${escapeHtml(String(summary))}</span>
    `;
    item.addEventListener("click", () => selectRecord(record));
    list.appendChild(item);
  });
}

function profileLabel(profileId) {
  const profile = state.llmProfiles.find((item) => item.id === profileId)
    || state.llmProfiles.find((item) => item.id === state.defaultLlmProfileId);
  return profile?.id || profileId || state.defaultLlmProfileId;
}

function selectRecord(record) {
  state.selectedRecord = record;
  document.querySelectorAll(".record-item").forEach((item) => {
    item.classList.toggle("active", item.dataset.recordId === record.record_id);
  });
  $("editOwner").value = record.owner_id || "";
  $("editRecordId").value = record.record_id || "";
  $("payloadEditor").value = pretty(record.payload || {});
  $("saveRecordBtn").disabled = Boolean(record.immutable);
  $("deleteRecordBtn").disabled = Boolean(record.immutable || !record.record_id);
  $("saveRecordBtn").title = record.immutable ? "初始 mock 记录不可修改" : "";
  $("deleteRecordBtn").title = record.immutable ? "初始 mock 记录不可删除" : "";
  renderQuickFields(record.payload || {});
}

function newRecord() {
  const owner = $("ownerFilter").value.trim() || "C100";
  const payload = state.currentResource === "customers" ? { customer_id: owner } : {};
  selectRecord({
    resource: state.currentResource,
    owner_id: owner,
    record_id: "",
    payload,
    immutable: false,
  });
}

function renderQuickFields(payload) {
  const wrap = $("quickFields");
  wrap.replaceChildren();
  Object.entries(payload)
    .filter(([, value]) => ["string", "number", "boolean"].includes(typeof value))
    .slice(0, 12)
    .forEach(([key, value]) => {
      const label = document.createElement("label");
      label.textContent = key;
      const input = document.createElement("input");
      input.value = String(value);
      input.addEventListener("input", () => updatePayloadField(key, input.value, typeof value));
      label.appendChild(input);
      wrap.appendChild(label);
    });
}

function updatePayloadField(key, value, type) {
  try {
    const payload = JSON.parse($("payloadEditor").value || "{}");
    if (type === "number") {
      payload[key] = Number(value);
    } else if (type === "boolean") {
      payload[key] = value === "true";
    } else {
      payload[key] = value;
    }
    $("payloadEditor").value = pretty(payload);
  } catch {
    // Keep the user's JSON draft untouched until it parses again.
  }
}

async function saveRecord() {
  try {
    const payload = JSON.parse($("payloadEditor").value || "{}");
    const ownerId = $("editOwner").value.trim() || payload.customer_id || "C100";
    const recordId = $("editRecordId").value.trim();
    await request(`/data/${state.currentResource}`, {
      method: "POST",
      body: JSON.stringify({ owner_id: ownerId, record_id: recordId, payload }),
    });
    await loadResource(state.currentResource);
  } catch (err) {
    showError(err);
  }
}

async function deleteRecord() {
  const recordId = $("editRecordId").value.trim();
  if (!recordId) return;
  try {
    await request(`/data/${state.currentResource}/${encodeURIComponent(recordId)}`, {
      method: "DELETE",
    });
    await loadResource(state.currentResource);
  } catch (err) {
    showError(err);
  }
}

async function resetData() {
  if (!confirm("确认重置 mock 数据？会覆盖后台数据编辑。")) return;
  try {
    await request("/reset-data", { method: "POST" });
    await loadResource(state.currentResource);
    await loadHealth(false);
  } catch (err) {
    showError(err);
  }
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

init().catch(showError);
