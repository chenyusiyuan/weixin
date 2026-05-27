const state = {
  resources: [],
  currentResource: "customers",
  selectedRecord: null,
  llmProfiles: [],
  defaultLlmProfileId: "default",
  evalIntentOptions: [],
  evalFiles: [],
  evalGroups: [],
  evalExpandedGroups: new Set(),
  evalGroupViewsTouched: new Set(),
  evalSelectedIds: new Set(),
  currentEvalFileId: "",
  currentEvalView: "all",
  currentView: "eval",
  currentEvalPanel: "workbench",
  currentEvalDetail: null,
  currentEvalJobId: "",
  currentEvalJob: null,
  evalJobs: [],
  evalJobTimer: null,
  evalJobRefreshKey: "",
  evalJobRefreshInFlight: false,
  evalJobRefreshPending: null,
  evalAnalytics: null,
  pendingEvalGenerateIds: [],
  pendingEvalRetryFailed: false,
  evalAnnotationSaveQueue: new Map(),
  showIntentReviewEditor: false,
};

const SAMPLE_EVAL_TXTS = [
  {
    filename: "2026-06-001.txt",
    llm_profile_id: "glm-5.1",
    raw_text: `客户:你好
客户:你好
客服:您好 请问有什么可以帮您的呢？
<divy<bry</div>
客户:我款想延期周五还
客服:亲亲不用担心 客服已经了解您的情况，为了确保您的信息安全，辛苦您提供一下几项相关信息，帮您处理一下
客服:陈女士亲亲正在非常努力的处理您的问题哈，您稍微等等，查清楚了马上告知您结果哦
客服:相信您自己肯定也是不希望逾期的，并且您能主动联系我们客服进行沟通，也能感受到您是有还款有意愿的，所以冒昧的了解下，您这边是什么原因导致无法
户:公司些事项，所以款周五还
客户:和你们说声，要不你们也着急催收
客服:大家都有遇到困难的时候，作为客服理解您的处境，只是未能及时还款导致逾期会上报征信，且会产生相关逾期费用~亲亲有和家人朋友周转一下吗
客户:说声就不要继续电话信息来
客服:亲亲是担心电话打扰是吗
户:对的
客户:周五还上，所以给你们协商下
客服:那我帮您申请停呼本人及联系人两天
客户:拖欠
客服:您看可以吗
客户:好的，感谢
客服:您客气了亲亲，常把"谢谢"挂嘴边的人，您一定是最善良可爱的人
客服:辛苦宝能给我点一个五星好评哟，万分感谢0(_)0。
客服:亲亲申请好了
客户:好的
客服:嗯嗯辛苦亲亲了`,
  },
  {
    filename: "2026-06-002.txt",
    llm_profile_id: "qwen3.6-flash",
    raw_text: `客户:帮我看一下现在还有没有额度
客服:您好，系统显示您当前暂无可用额度，具体以页面展示和系统综合评估为准。
客户:那我要怎么才能重新有额度
客服:额度由系统根据您的账户状态、还款记录等综合评估。
客服:人工无法干预，建议您保持良好还款记录并关注后续页面展示。
客户:我这个会员费哪里来的
客户:我不认可这个扣费，能退吗
客服:您好，查询到会员是在您借款时开通的，可能是操作时未注意到相关权益说明。
客服:我理解您的诉求，这边可以为您记录反馈，具体退费结果以业务审核为准。
客户:多久能有结果
客服:正常会在3个工作日内反馈处理结果，建议您保持电话畅通。`,
  },
];

const EVAL_RATINGS = [
  { id: "usable", label: "可用", score: 1 },
  { id: "borderline", label: "勉强可用", score: 0.5 },
  { id: "unusable", label: "不可用", score: 0 },
  { id: "skip", label: "跳过", score: null },
];

const EVAL_ISSUE_TAGS = [
  "答非所问",
  "数据错误",
  "工具未查",
  "话术风险",
  "太泛化",
  "遗漏关键信息",
  "语气不合适",
];

const EVAL_IDENTITY_FLOW = {
  mode: "display_only_success",
  label: "核身展示成功流程",
  validation: "disabled",
  mock_customer_id: "C100",
  steps: [
    { title: "触发核身", detail: "按真实链路展示核身引导" },
    { title: "客户输入任意内容", detail: "评测场景不校验姓名、手机号或证件号" },
    { title: "核身成功", detail: "固定绑定 C100 mock 数据继续生成回复" },
  ],
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

function showError(err) {
  alert(err.message || String(err));
}

async function init() {
  bindEvents();
  await loadLlmProfiles();
  await initEvalWorkspace();
  await loadResources();
  await loadResource("customers");
}

function bindEvents() {
  $("evalViewBtn").addEventListener("click", () => switchView("eval"));
  $("analyticsViewBtn").addEventListener("click", () => switchView("analytics"));
  $("adminViewBtn").addEventListener("click", () => switchView("admin"));
  $("loadResourceBtn").addEventListener("click", () => loadResource(state.currentResource));
  $("newRecordBtn").addEventListener("click", newRecord);
  $("saveRecordBtn").addEventListener("click", saveRecord);
  $("deleteRecordBtn").addEventListener("click", deleteRecord);
  $("resetDataBtn").addEventListener("click", resetData);
  $("evalImportBtn").addEventListener("click", () => $("evalTxtInput").click());
  $("evalTxtInput").addEventListener("change", importEvalTxtFiles);
  $("evalViewSelect").addEventListener("change", changeEvalView);
  $("evalGenerateSelectedBtn").addEventListener("click", () => openEvalGenerateDialog(selectedEvalFileIds(), false));
  $("evalDeleteBtn").addEventListener("click", deleteSelectedEvalFiles);
  $("evalRunDialogueBtn").addEventListener("click", () => openEvalGenerateDialog(currentEvalFileIds(), false));
  $("evalExportBtn").addEventListener("click", exportEvalResult);
  $("evalResetRatingsBtn").addEventListener("click", resetCurrentEvalAnnotations);
  $("evalModelSelect").addEventListener("change", changeEvalModel);
  $("evalProgressBtn").addEventListener("click", openEvalProgressDialog);
  $("analyticsModelFilter").addEventListener("change", () => loadEvalAnalytics());
  $("analyticsIntentFilter").addEventListener("change", () => loadEvalAnalytics());
  $("analyticsStatusFilter").addEventListener("change", () => loadEvalAnalytics());
  $("analyticsBadcaseOnly").addEventListener("change", () => loadEvalAnalytics());
  $("analyticsRefreshBtn").addEventListener("click", () => loadEvalAnalytics());
  $("analyticsExportBtn").addEventListener("click", exportEvalResult);
  $("analyticsAllQuickBtn").addEventListener("click", showAllAnalytics);
  $("analyticsBadcaseQuickBtn").addEventListener("click", () => setAnalyticsBadcaseFilter(true));
  $("evalGenerateDialogClose").addEventListener("click", closeEvalGenerateDialog);
  $("evalGenerateDialogCancel").addEventListener("click", closeEvalGenerateDialog);
  $("evalGenerateDialogStart").addEventListener("click", startEvalGenerateFromDialog);
  $("evalProgressDialogClose").addEventListener("click", closeEvalProgressDialog);
  $("evalProgressDialogDone").addEventListener("click", closeEvalProgressDialog);
  $("evalProgressRefreshBtn").addEventListener("click", loadEvalJobs);
}

function switchView(view) {
  const isEval = view === "eval";
  const isAnalytics = view === "analytics";
  const isAdmin = view === "admin";
  state.currentView = view;
  $("evalView").classList.toggle("hidden", !isEval);
  $("analyticsView").classList.toggle("hidden", !isAnalytics);
  $("adminView").classList.toggle("hidden", !isAdmin);
  $("evalSidebarPanel").classList.toggle("hidden", !isEval);
  $("analyticsSidebarPanel").classList.toggle("hidden", !isAnalytics);
  $("adminSidebarPanel").classList.toggle("hidden", !isAdmin);
  $("evalViewBtn").classList.toggle("active", isEval);
  $("analyticsViewBtn").classList.toggle("active", isAnalytics);
  $("adminViewBtn").classList.toggle("active", isAdmin);
  if (isAnalytics) {
    state.currentEvalPanel = "analytics";
    loadEvalAnalytics();
  } else if (isEval) {
    state.currentEvalPanel = "workbench";
  }
}

async function loadLlmProfiles() {
  const data = await request("/llm-profiles");
  state.llmProfiles = data.profiles || [];
  state.defaultLlmProfileId = data.default_profile_id || state.llmProfiles[0]?.id || "default";
  renderEvalModelSelect();
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
  } catch (err) {
    showError(err);
  }
}

function initEvalPrototype() {
  state.evalFiles = SAMPLE_EVAL_TXTS.map((sample) =>
    buildEvalTxtFile(sample.raw_text, sample.filename, sample.llm_profile_id),
  );
  state.currentEvalFileId = state.evalFiles[0]?.txt_id || "";
  renderEvalPrototype();
}

function renderEvalPrototype() {
  renderEvalModelSelect();
  renderEvalFileList();
  renderEvalFile();
  renderEvalStats();
  renderEvalJsonPreviews();
}

function renderEvalModelSelect() {
  const select = $("evalModelSelect");
  if (!select) return;
  const file = currentEvalFile();
  let ids = state.llmProfiles.length
    ? state.llmProfiles.map((profile) => profile.id)
    : ["glm-5.1", "qwen3.6-flash", "deepseek-v4-pro"];
  if (file?.llm_profile_id && !ids.includes(file.llm_profile_id)) {
    ids = [...ids, file.llm_profile_id];
  }
  select.replaceChildren(
    ...ids.map((id) => {
      const opt = document.createElement("option");
      opt.value = id;
      opt.textContent = id;
      return opt;
    }),
  );
  select.value = file?.llm_profile_id || ids[0] || "";
  select.disabled = evalGeneratedCount(file) > 0;
  select.title = select.disabled ? "当前 TXT 已开始生成，模型已固定" : "";
}

function renderEvalFileList() {
  const wrap = $("evalFileList");
  if (!wrap) return;
  wrap.replaceChildren();
  state.evalFiles.forEach((file) => {
    const stats = evalStatsForFile(file);
    const item = document.createElement("button");
    item.type = "button";
    item.className = `eval-file-item ${file.txt_id === state.currentEvalFileId ? "active" : ""}`;
    item.innerHTML = `
      <span>
        <strong>${escapeHtml(file.name)}</strong>
        <em>${escapeHtml(file.llm_profile_id)} · ${stats.rated}/${stats.generated || stats.total} 已评 · 丢弃 ${file.dropped_lines.length} 行</em>
      </span>
      <b>${escapeHtml(formatRate(stats.weightedRate))}</b>
    `;
    item.addEventListener("click", () => {
      state.currentEvalFileId = file.txt_id;
      renderEvalPrototype();
    });
    wrap.appendChild(item);
  });
}

function renderEvalFile() {
  const file = currentEvalFile();
  if (!file) {
    $("evalDialogueTitle").textContent = "TXT 多轮评测";
    $("evalDialogueSub").textContent = "导入 TXT 后会在这里展示逐行抽取结果";
    $("evalSummaryStrip").replaceChildren();
    $("evalTurns").replaceChildren();
    return;
  }

  $("evalDialogueTitle").textContent = file.name;
  $("evalDialogueSub").textContent =
    `${file.txt_id} · 固定模型 ${file.llm_profile_id} · 核身只展示成功流程 · C100 mock 数据 · 抽取 ${file.messages.length} 条，丢弃 ${file.dropped_lines.length} 行`;

  const stats = evalStatsForFile(file);
  $("evalSummaryStrip").replaceChildren(
    evalSummaryPill("生成", `${stats.generated}/${stats.total}`),
    evalSummaryPill("已评", `${stats.rated}/${stats.generated || stats.total}`),
    evalSummaryPill("加权可用率", formatRate(stats.weightedRate)),
    evalSummaryPill("严格可用率", formatRate(stats.strictRate)),
    evalSummaryPill("失败", String(stats.failed)),
  );

  const wrap = $("evalTurns");
  wrap.replaceChildren();
  file.turns.forEach((turn, index) => {
    const card = document.createElement("article");
    card.className = `eval-turn ${turn.status || "pending"}`;
    card.innerHTML = `
      <div class="eval-turn-head">
        <span>用户 Query ${index + 1}</span>
        <button type="button" data-action="run-turn">${turn.model_answer || turn.error ? "重新生成" : "生成模型回复"}</button>
      </div>
      <div class="eval-user">${escapeHtml(turn.user_query)}</div>
      <div class="eval-answer-grid">
        <div>
          <label>模型回复</label>
          <div class="eval-answer model">${escapeHtml(turn.error || turn.model_answer || "尚未生成")}</div>
        </div>
        <div>
          <label>真实坐席</label>
          <div class="eval-answer real">${escapeHtml(turn.real_agent_answer || "该用户 query 后没有紧邻客服回复")}</div>
        </div>
      </div>
      <div class="eval-rating-row"></div>
      <div class="eval-issue-row"></div>
      <textarea class="eval-note-input" placeholder="备注，可为空">${escapeHtml(turn.note || "")}</textarea>
      <div class="eval-trace">${escapeHtml(evalTraceText(turn))}</div>
    `;
    card.querySelector("[data-action='run-turn']").addEventListener("click", () => runEvalTurnPrototype(turn.turn_id));
    const ratingRow = card.querySelector(".eval-rating-row");
    EVAL_RATINGS.forEach((rating) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = turn.rating === rating.id ? "active" : "";
      btn.textContent = rating.label;
      btn.addEventListener("click", () => {
        turn.rating = turn.rating === rating.id ? "" : rating.id;
        renderEvalPrototype();
      });
      ratingRow.appendChild(btn);
    });
    const issueRow = card.querySelector(".eval-issue-row");
    EVAL_ISSUE_TAGS.forEach((tag) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = turn.issue_tags.includes(tag) ? "active" : "";
      btn.textContent = tag;
      btn.addEventListener("click", () => {
        turn.issue_tags = toggleValue(turn.issue_tags, tag);
        renderEvalPrototype();
      });
      issueRow.appendChild(btn);
    });
    card.querySelector(".eval-note-input").addEventListener("input", (event) => {
      turn.note = event.target.value;
      renderEvalJsonPreviews();
    });
    wrap.appendChild(card);
  });
}

function renderEvalStats() {
  const file = currentEvalFile();
  const globalStats = evalStatsForAllFiles();
  const fileStats = evalStatsForFile(file);
  $("evalStats").replaceChildren(
    evalStatBlock("全局统计", globalStats),
    evalStatBlock("当前 TXT", fileStats),
  );
}

function renderEvalJsonPreviews() {
  const file = currentEvalFile();
  $("evalImportPreview").textContent = pretty(file ? {
    txt_id: file.txt_id,
    filename: file.filename,
    mock_customer_id: file.mock_customer_id,
    llm_profile_id: file.llm_profile_id,
    identity_flow: file.identity_flow,
    parse_summary: file.parse_summary,
    messages: file.messages,
    dropped_lines: file.dropped_lines,
  } : {});
  $("evalResultPreview").textContent = pretty(buildEvalExportPayload(file));
}

function buildEvalExportPayload(currentFile = null) {
  return {
    summary: evalStatsForAllFiles(),
    current_txt_id: currentFile?.txt_id || "",
    files: state.evalFiles.map((file) => ({
      txt_id: file.txt_id,
      filename: file.filename,
      mock_customer_id: file.mock_customer_id,
      llm_profile_id: file.llm_profile_id,
      identity_flow: file.identity_flow,
      parse_summary: file.parse_summary,
      summary: evalStatsForFile(file),
      messages: file.messages,
      dropped_lines: file.dropped_lines,
      turns: file.turns.map((turn) => ({
        turn_id: turn.turn_id,
        user_message_index: turn.user_message_index,
        reference_message_index: turn.reference_message_index,
        user_query: turn.user_query,
        real_agent_answer: turn.real_agent_answer,
        model_answer: turn.model_answer,
        rating: turn.rating,
        issue_tags: turn.issue_tags,
        note: turn.note,
        trace_id: turn.trace_id,
        error: turn.error || null,
      })),
    })),
  };
}

function runEvalDialoguePrototype() {
  currentEvalFile()?.turns.forEach((turn) => fillEvalTurnPrototype(turn));
  renderEvalPrototype();
}

function runEvalTurnPrototype(turnId) {
  const turn = currentEvalFile()?.turns.find((item) => item.turn_id === turnId);
  if (turn) {
    fillEvalTurnPrototype(turn);
    renderEvalPrototype();
  }
}

function fillEvalTurnPrototype(turn) {
  turn.model_answer = turn.model_answer || `原型生成：展示核身成功流程后，基于 C100 mock 数据回答「${turn.user_query}」。正式实现时这里会调用现有链路并保存 trace。`;
  turn.status = "generated";
  turn.error = "";
  turn.rating = "";
  turn.issue_tags = [];
  turn.note = "";
  turn.route = "route_b";
  turn.matched_skill = "待链路返回";
  turn.tools_called = ["identity:display_only_success", "mock:C100"];
  turn.trace_id = `tr-prototype-${turn.turn_id}`;
}

function resetEvalRatingsPrototype() {
  currentEvalFile()?.turns.forEach((turn) => {
    turn.rating = "";
    turn.issue_tags = [];
    turn.note = "";
  });
  renderEvalPrototype();
}

function updateEvalModelPrototype() {
  const file = currentEvalFile();
  if (!file || evalGeneratedCount(file) > 0) {
    renderEvalPrototype();
    return;
  }
  file.llm_profile_id = $("evalModelSelect").value;
  renderEvalPrototype();
}

async function importEvalTxtFiles(event) {
  const input = event.target;
  const files = Array.from(input.files || []);
  if (!files.length) return;
  try {
    const profileId = selectedEvalProfileId();
    const imported = [];
    for (const file of files) {
      imported.push(buildEvalTxtFile(await file.text(), file.name, profileId));
    }
    state.evalFiles.push(...imported);
    state.currentEvalFileId = imported[0]?.txt_id || state.currentEvalFileId;
    renderEvalPrototype();
  } catch (err) {
    showError(err);
  } finally {
    input.value = "";
  }
}

function exportEvalResultPrototype() {
  const blob = new Blob([pretty(buildEvalExportPayload(currentEvalFile()))], { type: "application/json;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `eval-results-${new Date().toISOString().slice(0, 10)}.json`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function currentEvalFile() {
  return state.evalFiles.find((file) => file.txt_id === state.currentEvalFileId);
}

function selectedEvalProfileId() {
  return $("evalModelSelect")?.value || currentEvalFile()?.llm_profile_id || state.defaultLlmProfileId;
}

function buildEvalTxtFile(rawText, filename, llmProfileId) {
  const txtId = nextEvalTxtId();
  const parsed = parseEvalTxt(rawText);
  return {
    txt_id: txtId,
    filename,
    name: filename || txtId,
    source_type: "txt",
    mock_customer_id: "C100",
    identity_flow: structuredClone(EVAL_IDENTITY_FLOW),
    llm_profile_id: llmProfileId || state.defaultLlmProfileId,
    imported_at: new Date().toISOString(),
    raw_text: rawText,
    ...parsed,
    turns: buildEvalTurns(parsed.messages, txtId),
  };
}

function nextEvalTxtId() {
  const id = `txt_${String(state.evalFileSequence).padStart(3, "0")}`;
  state.evalFileSequence += 1;
  return id;
}

function parseEvalTxt(rawText) {
  const messages = [];
  const droppedLines = [];
  const lines = String(rawText || "").split(/\r?\n/);
  lines.forEach((line, lineIndex) => {
    const lineNo = lineIndex + 1;
    const match = line.match(/^\s*(客户|客服)\s*[:：]\s*(.*)$/);
    if (!match) {
      if (line.trim()) droppedLines.push({ line: lineNo, content: line });
      return;
    }
    const role = match[1] === "客户" ? "user" : "assistant";
    const content = cleanTranscriptContent(match[2]);
    const last = messages[messages.length - 1];
    if (role === "assistant" && last?.role === "assistant") {
      last.content = appendParagraph(last.content, content);
      last.source_line_end = lineNo;
      last.source_lines.push(lineNo);
      return;
    }
    messages.push({
      role,
      content,
      source_line_start: lineNo,
      source_line_end: lineNo,
      source_lines: [lineNo],
    });
  });
  const numberedMessages = messages.map((message, index) => ({
    message_id: `m${String(index + 1).padStart(3, "0")}`,
    index: index + 1,
    ...message,
  }));
  return {
    messages: numberedMessages,
    dropped_lines: droppedLines,
    parse_summary: {
      raw_lines: lines.length,
      kept_messages: numberedMessages.length,
      user_messages: numberedMessages.filter((message) => message.role === "user").length,
      assistant_messages: numberedMessages.filter((message) => message.role === "assistant").length,
      dropped_lines: droppedLines.length,
    },
  };
}

function buildEvalTurns(messages, txtId) {
  const turns = [];
  messages.forEach((message, index) => {
    if (message.role !== "user") return;
    const next = messages[index + 1];
    turns.push({
      turn_id: `${txtId}_u${String(turns.length + 1).padStart(3, "0")}`,
      user_message_index: message.index,
      reference_message_index: next?.role === "assistant" ? next.index : null,
      user_query: message.content,
      real_agent_answer: next?.role === "assistant" ? next.content : "",
      model_answer: "",
      status: "pending",
      rating: "",
      issue_tags: [],
      note: "",
      route: "",
      matched_skill: "",
      tools_called: [],
      trace_id: "",
      error: "",
    });
  });
  return turns;
}

function cleanTranscriptContent(content) {
  return String(content || "")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/^["“”]+|["“”]+$/g, "")
    .trim();
}

function appendParagraph(existing, next) {
  if (!next) return existing || "";
  if (!existing) return next;
  return `${existing}\n\n${next}`;
}

function evalStatsForAllFiles() {
  return evalStatsForTurns(state.evalFiles.flatMap((file) => file.turns));
}

function evalStatsForFile(file) {
  if (!file) return emptyEvalStats();
  return evalStatsForTurns(file.turns);
}

function evalStatsForTurns(turns) {
  const total = turns.length;
  const generated = turns.filter((turn) => turn.model_answer || turn.error).length;
  const failed = turns.filter((turn) => turn.error).length;
  const scored = turns
    .map((turn) => EVAL_RATINGS.find((rating) => rating.id === turn.rating))
    .filter(Boolean);
  const ratedForDenominator = scored.filter((rating) => rating.id !== "skip");
  const usable = scored.filter((rating) => rating.id === "usable").length;
  const borderline = scored.filter((rating) => rating.id === "borderline").length;
  const unusable = scored.filter((rating) => rating.id === "unusable").length;
  const skipped = scored.filter((rating) => rating.id === "skip").length;
  const score = ratedForDenominator.reduce((sum, rating) => sum + Number(rating.score || 0), 0);
  const weightedRate = ratedForDenominator.length ? score / ratedForDenominator.length : null;
  const strictRate = ratedForDenominator.length ? usable / ratedForDenominator.length : null;
  return {
    total,
    generated,
    rated: scored.length,
    usable,
    borderline,
    unusable,
    skipped,
    failed,
    weightedRate,
    strictRate,
  };
}

function emptyEvalStats() {
  return {
    total: 0,
    generated: 0,
    rated: 0,
    usable: 0,
    borderline: 0,
    unusable: 0,
    skipped: 0,
    failed: 0,
    weightedRate: null,
    strictRate: null,
  };
}

function evalGeneratedCount(file) {
  return file ? evalStatsForFile(file).generated : 0;
}

function evalSummaryPill(label, value) {
  const el = document.createElement("div");
  el.className = "eval-summary-pill";
  el.innerHTML = `<span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong>`;
  return el;
}

function evalStatBlock(title, stats) {
  const el = document.createElement("div");
  el.className = "eval-stat-block";
  el.innerHTML = `
    <h4>${escapeHtml(title)}</h4>
    <div><span>总轮次</span><b>${stats.total}</b></div>
    <div><span>已生成</span><b>${stats.generated}</b></div>
    <div><span>已评</span><b>${stats.rated}</b></div>
    <div><span>可用 / 勉强 / 不可用</span><b>${stats.usable} / ${stats.borderline} / ${stats.unusable}</b></div>
    <div><span>加权可用率</span><b>${formatRate(stats.weightedRate)}</b></div>
  `;
  return el;
}

function evalTraceText(turn) {
  if (turn.error) return `错误：${turn.error}`;
  if (!turn.model_answer) return "待生成，正式实现时失败会诚实返回错误并允许重试";
  return `${turn.route || "-"} | ${turn.matched_skill || "-"} | tools: ${(turn.tools_called || []).join(", ") || "-"} | ${turn.trace_id || "-"}`;
}

const EVAL_REJECT_REASONS = ["推荐错误", "路由错误", "知识不足", "工具错误", "语气不合适", "数据错误", "其他"];

async function initEvalWorkspace() {
  renderEvalModelSelect();
  await loadEvalIntentOptions();
  renderEvalViewSelect();
  await loadEvalFiles();
  await loadEvalAnalytics();
}

async function loadEvalIntentOptions() {
  try {
    const data = await request("/eval/intent-options");
    state.evalIntentOptions = data.intents || [];
  } catch (err) {
    state.evalIntentOptions = [];
  }
}

function evalProfileIds() {
  const ids = state.llmProfiles.map((profile) => profile.id);
  return ids.length ? ids : [state.defaultLlmProfileId || "default"];
}

function renderEvalModelSelect() {
  const select = $("evalModelSelect");
  if (!select) return;
  const previous = select.value || state.defaultLlmProfileId;
  const ids = evalProfileIds();
  select.replaceChildren(
    ...ids.map((id) => {
      const option = document.createElement("option");
      option.value = id;
      option.textContent = id;
      return option;
    }),
  );
  select.value = ids.includes(previous) ? previous : ids[0];
  if (state.currentEvalView !== "all" && ids.includes(state.currentEvalView)) {
    select.value = state.currentEvalView;
  }
  renderEvalGenerateProfileSelect();
  renderAnalyticsModelFilter();
}

function renderEvalGenerateProfileSelect() {
  const select = $("evalGenerateProfileSelect");
  if (!select) return;
  const previous = select.value || selectedEvalProfileId();
  const ids = evalProfileIds();
  select.replaceChildren(
    ...ids.map((id) => {
      const option = document.createElement("option");
      option.value = id;
      option.textContent = id;
      return option;
    }),
  );
  select.value = ids.includes(previous) ? previous : ids[0];
}

function renderAnalyticsModelFilter() {
  const select = $("analyticsModelFilter");
  if (!select) return;
  const previous = select.value;
  const options = [
    { value: "", label: "全部模型" },
    ...evalProfileIds().map((id) => ({ value: id, label: id })),
  ];
  select.replaceChildren(
    ...options.map((item) => {
      const option = document.createElement("option");
      option.value = item.value;
      option.textContent = item.label;
      return option;
    }),
  );
  select.value = options.some((item) => item.value === previous) ? previous : "";
}

function renderEvalViewSelect() {
  const select = $("evalViewSelect");
  if (!select) return;
  const ids = evalProfileIds();
  const options = [
    { value: "all", label: "全部对话" },
    ...ids.map((id) => ({ value: id, label: id })),
  ];
  if (!options.some((option) => option.value === state.currentEvalView)) {
    state.currentEvalView = "all";
  }
  select.replaceChildren(
    ...options.map((item) => {
      const option = document.createElement("option");
      option.value = item.value;
      option.textContent = item.label;
      return option;
    }),
  );
  select.value = state.currentEvalView;
}

async function loadEvalFiles({ refreshDetail = true, preserveScroll = false } = {}) {
  const work = async () => {
    const data = await request(`/eval/txt-files?view=${encodeURIComponent(state.currentEvalView)}`);
    state.evalGroups = data.groups || [{ name: "全部对话", items: data.files || [] }];
    state.evalFiles = state.evalGroups.flatMap((group) => group.items || []);
    const hasCurrent = state.evalFiles.some((file) => file.txt_id === state.currentEvalFileId);
    if (!hasCurrent) {
      state.currentEvalFileId = state.evalFiles[0]?.txt_id || "";
      state.evalSelectedIds.clear();
    }
    renderEvalFileList();
    if (refreshDetail) {
      await loadEvalDetail(state.currentEvalFileId);
    }
  };
  try {
    if (preserveScroll) {
      await withEvalConversationScroll(work);
    } else {
      await work();
    }
  } catch (err) {
    showError(err);
  }
}

function evalGroupKey(group) {
  return `${state.currentEvalView}::${group.name || "未分组"}`;
}

function ensureEvalGroupExpansion() {
  if (!state.evalGroups.length) return;
  if (state.evalGroupViewsTouched.has(state.currentEvalView)) return;
  const expandedInView = state.evalGroups.some((group) => state.evalExpandedGroups.has(evalGroupKey(group)));
  if (expandedInView) return;
  const currentGroup = state.evalGroups.find((group) =>
    (group.items || []).some((file) => file.txt_id === state.currentEvalFileId),
  );
  if (currentGroup) {
    state.evalExpandedGroups.add(evalGroupKey(currentGroup));
  }
}

function evalFilenameCounts(files) {
  return files.reduce((acc, file) => {
    const name = file.filename || "未命名.txt";
    acc.set(name, (acc.get(name) || 0) + 1);
    return acc;
  }, new Map());
}

function evalDisplayFilename(file, counts) {
  const name = file.filename || "未命名.txt";
  if ((counts.get(name) || 0) <= 1) return name;
  return `${name} · ${String(file.txt_id || "").slice(-6)}`;
}

function renderEvalFileList() {
  const wrap = $("evalFileList");
  if (!wrap) return;
  wrap.replaceChildren();
  if (!state.evalGroups.length || !state.evalFiles.length) {
    const empty = document.createElement("div");
    empty.className = "eval-empty-list";
    empty.textContent = "还没有导入 TXT";
    wrap.appendChild(empty);
    return;
  }
  ensureEvalGroupExpansion();
  const filenameCounts = evalFilenameCounts(state.evalFiles);
  state.evalGroups.forEach((group) => {
    const items = group.items || [];
    const key = evalGroupKey(group);
    const expanded = state.evalExpandedGroups.has(key);
    const card = document.createElement("div");
    card.className = `eval-group-card ${expanded ? "expanded" : ""}`;
    const header = document.createElement("button");
    header.className = "eval-group-toggle";
    header.type = "button";
    header.setAttribute("aria-expanded", expanded ? "true" : "false");
    header.innerHTML = `
      <span class="eval-group-main">
        <strong>${escapeHtml(group.name || "未分组")}</strong>
        <small>${expanded ? "点击收起" : "点击展开"}</small>
      </span>
      <span class="eval-group-count">${items.length} 条</span>
      <span class="eval-group-arrow">${expanded ? "^" : "v"}</span>
    `;
    header.addEventListener("click", () => {
      state.evalGroupViewsTouched.add(state.currentEvalView);
      if (state.evalExpandedGroups.has(key)) {
        state.evalExpandedGroups.delete(key);
      } else {
        state.evalExpandedGroups.add(key);
      }
      renderEvalFileList();
    });
    card.appendChild(header);
    const list = document.createElement("div");
    list.className = "eval-group-items";
    (group.items || []).forEach((file) => {
      const row = document.createElement("div");
      row.className = `eval-file-row ${file.txt_id === state.currentEvalFileId ? "active" : ""}`;
      const checked = state.evalSelectedIds.has(file.txt_id) ? "checked" : "";
      const run = file.run || (file.runs || [])[0] || null;
      const displayName = evalDisplayFilename(file, filenameCounts);
      const badcase = evalFileBadcaseState(file, run);
      const badges = [];
      if (state.currentEvalView !== "all" && badcase.status === "badcase") {
        badges.push(`
          <span class="eval-file-badcase ${badcase.status}" title="${escapeHtml(badcase.title)}">
            ${escapeHtml(badcase.label)}
          </span>
        `);
      }
      if (state.currentEvalView !== "all" && run?.intent_error) {
        badges.push(`
          <span class="eval-file-badcase intent-error" title="${escapeHtml(intentErrorTitle(run))}">
            意图
          </span>
        `);
      }
      row.innerHTML = `
        <input class="eval-file-check" type="checkbox" ${checked} aria-label="选择 ${escapeHtml(displayName)}" />
        <button class="eval-file-body" type="button">
          <span class="eval-file-title-line">
            <strong title="${escapeHtml(file.filename || "")}">${escapeHtml(displayName)}</strong>
            ${badges.join("")}
          </span>
          <span class="eval-file-meta">${escapeHtml(evalFileMeta(file, run))}</span>
        </button>
      `;
      row.querySelector(".eval-file-check").addEventListener("change", (event) => {
        if (event.target.checked) {
          state.evalSelectedIds.add(file.txt_id);
        } else {
          state.evalSelectedIds.delete(file.txt_id);
        }
      });
      row.querySelector(".eval-file-body").addEventListener("click", async () => {
        state.currentEvalFileId = file.txt_id;
        await loadEvalDetail(file.txt_id);
        renderEvalFileList();
      });
      list.appendChild(row);
    });
    if (expanded) {
      card.appendChild(list);
    }
    wrap.appendChild(card);
  });
}

function evalFileBadcaseState(file, run) {
  if (file.badcase) {
    return {
      status: "badcase",
      label: "BAD",
      title: file.badcase_note ? `TXT 已标记 Badcase：${file.badcase_note}` : "TXT 已标记 Badcase",
    };
  }
  if (!run) {
    return { status: "pending", label: "未生成", title: "当前模型暂未生成评测结果" };
  }
  return { status: "normal", label: "", title: "" };
}

function evalFileMeta(file, run) {
  const turns = file.user_turn_count ?? file.parse_summary?.user_messages ?? 0;
  const badcase = file.badcase ? " · TXT Badcase" : "";
  if (state.currentEvalView === "all") {
    return `${turns} 个用户 query · ${file.model_count || 0} 个模型结果 · 丢弃 ${file.parse_summary?.dropped_lines || 0} 行${badcase}`;
  }
  if (!run) {
    return `${state.currentEvalView} · 未生成 · ${turns} 个用户 query${badcase}`;
  }
  const intent = effectiveIntent(run).l2 || "未分类";
  const intentReview = run.intent_error ? ` · 意图纠正 ${run.main_intent?.l2 || "未分类"}→${intent}` : "";
  const modelIssues = evalRunIssueMeta(run);
  return `${run.llm_profile_id} · ${evalStatusLabel(run.status)} · ${run.generated_turns}/${run.total_turns} · ${intent}${badcase}${intentReview}${modelIssues}`;
}

function effectiveIntent(run) {
  if (run?.intent_error && run.corrected_intent?.l2) return run.corrected_intent;
  return run?.effective_intent || run?.main_intent || {};
}

function intentErrorTitle(run) {
  const original = run?.main_intent?.l2 || "未分类";
  const corrected = effectiveIntent(run).l2 || "未分类";
  return `意图识别错误：${original} → ${corrected}`;
}

function evalRunIssueMeta(run) {
  if (!run) return "";
  const bits = [];
  const rejected = Number(run.rejected_turns || 0);
  const failed = Number(run.failed_turns || 0);
  if (rejected > 0) bits.push(`${rejected} 条不采纳`);
  if (failed > 0) bits.push(`${failed} 条失败`);
  return bits.length ? ` · ${bits.join(" · ")}` : "";
}

async function loadEvalDetail(txtId, { preserveScroll = false } = {}) {
  const work = async () => {
    if (!txtId) {
      state.currentEvalDetail = null;
      renderEvalConversation();
      renderEvalRunSummary();
      return;
    }
    const profileId = selectedEvalProfileId();
    const data = await request(`/eval/txt-files/${encodeURIComponent(txtId)}?llm_profile_id=${encodeURIComponent(profileId)}`);
    state.currentEvalDetail = data;
    $("evalDialogueTitle").textContent = data.file.filename;
    $("evalDialogueSub").textContent =
      `${data.file.user_turn_count} 个用户 query · 当前模型 ${profileId} · 核身展示成功流程`;
    renderEvalConversation();
    renderEvalRunSummary();
  };
  try {
    if (preserveScroll) {
      await withEvalConversationScroll(work);
    } else {
      await work();
    }
  } catch (err) {
    showError(err);
  }
}

function renderEvalConversation() {
  const wrap = $("evalConversation");
  if (!wrap) return;
  wrap.replaceChildren();
  const detail = state.currentEvalDetail;
  if (!detail) {
    const empty = document.createElement("div");
    empty.className = "eval-empty-state";
    empty.textContent = "导入 TXT 后选择左侧文件查看逐句对话。";
    wrap.appendChild(empty);
    $("evalDialogueTitle").textContent = "评测工作台";
    $("evalDialogueSub").textContent = "导入 TXT 后，按模型生成每句客户 query 的话术推荐并人工标注";
    return;
  }
  const resultsByIndex = new Map((detail.turn_results || []).map((turn) => [Number(turn.message_index), turn]));
  (detail.file.messages || []).forEach((message) => {
    const row = document.createElement("article");
    row.className = `eval-message-row ${message.role === "user" ? "user" : "assistant"}`;
    row.innerHTML = `
      <div class="eval-bubble">
        <span>${message.role === "user" ? "客户" : "真实坐席"}</span>
        <p>${escapeHtml(message.content || "")}</p>
      </div>
    `;
    wrap.appendChild(row);
    if (message.role === "user") {
      wrap.appendChild(evalResultPanel(message, resultsByIndex.get(Number(message.index))));
    }
  });
}

function evalResultPanel(message, turn) {
  const panel = document.createElement("section");
  const status = turn?.status || "pending";
  panel.className = `eval-result-panel ${status}`;
  if (!turn) {
    panel.innerHTML = `
      <div class="eval-result-head">
        <strong>模型推荐</strong>
        <span>暂未生成</span>
      </div>
      <p class="eval-muted">当前模型还没有为这句客户 query 生成结果。</p>
    `;
    return panel;
  }
  const annotation = turn.annotation || {};
  const accepted = annotation.accepted;
  const selectedReasons = annotation.reject_reasons || [];
  const reasonButtons = EVAL_REJECT_REASONS.map((reason) => {
    const active = selectedReasons.includes(reason);
    return `<button type="button" data-reject-reason="${escapeHtml(reason)}" class="${active ? "active" : ""}">${escapeHtml(reason)}</button>`;
  }).join("");
  const meta = [
    turn.route,
    turn.matched_skill_name || turn.matched_skill_id,
    turn.mapped_intent?.l2,
    (turn.tools_called || []).length ? `tools: ${turn.tools_called.join(", ")}` : "",
    turn.trace_id ? `trace: ${turn.trace_id}` : "",
    turn.latency_ms ? `${Math.round(turn.latency_ms)}ms` : "",
  ].filter(Boolean).join(" | ");
  panel.innerHTML = `
    <div class="eval-result-head">
      <strong>模型推荐</strong>
      <span>${escapeHtml(evalStatusLabel(status))}</span>
    </div>
    <div class="eval-model-answer ${status === "error" ? "error" : ""}">${escapeHtml(status === "error" ? turn.error : turn.model_answer || "空回复")}</div>
    <div class="eval-result-meta">${escapeHtml(meta || "-")}</div>
    <div class="eval-annotation-row">
      <button type="button" data-accept="true" class="${accepted === true ? "active" : ""}">采纳</button>
      <button type="button" data-accept="false" class="${accepted === false ? "active danger" : "danger"}">不采纳</button>
    </div>
    <div class="eval-reject-picker ${accepted === false ? "" : "hidden"}">
      <span>不采纳原因</span>
      <div class="eval-reject-options">${reasonButtons}</div>
    </div>
    <textarea class="eval-annotation-note" placeholder="备注，可为空">${escapeHtml(annotation.note || "")}</textarea>
  `;
  panel.querySelector("[data-accept='true']").addEventListener("click", () => {
    annotation.accepted = true;
    annotation.reject_reasons = [];
    turn.annotation = annotation;
    panel.querySelector(".eval-reject-picker")?.classList.add("hidden");
    panel.querySelectorAll("[data-reject-reason]").forEach((button) => button.classList.remove("active"));
    saveEvalAnnotation(turn, { accepted: true, reject_reasons: [], badcase: false });
  });
  panel.querySelector("[data-accept='false']").addEventListener("click", () => {
    annotation.accepted = false;
    turn.annotation = annotation;
    panel.querySelector(".eval-reject-picker")?.classList.remove("hidden");
    panel.querySelector("[data-accept='false']")?.classList.add("active", "danger");
    panel.querySelector("[data-accept='true']")?.classList.remove("active");
    saveEvalAnnotation(turn, {
      accepted: false,
      reject_reasons: annotation.reject_reasons || [],
      badcase: false,
    });
  });
  panel.querySelectorAll("[data-reject-reason]").forEach((button) => {
    button.addEventListener("click", () => {
      const reason = button.dataset.rejectReason;
      const next = toggleValue(annotation.reject_reasons || [], reason);
      annotation.accepted = false;
      annotation.reject_reasons = next;
      turn.annotation = annotation;
      button.classList.toggle("active", next.includes(reason));
      panel.querySelector(".eval-reject-picker")?.classList.remove("hidden");
      panel.querySelector("[data-accept='false']")?.classList.add("active", "danger");
      panel.querySelector("[data-accept='true']")?.classList.remove("active");
      saveEvalAnnotation(turn, {
        accepted: false,
        reject_reasons: next,
        note: annotation.note || "",
        badcase: false,
      });
    });
  });
  panel.querySelector(".eval-annotation-note").addEventListener("change", (event) => {
    annotation.note = event.target.value;
    turn.annotation = annotation;
    saveEvalAnnotation(turn, {
      accepted: annotation.accepted,
      reject_reasons: annotation.reject_reasons || [],
      note: annotation.note,
      badcase: false,
    });
  });
  return panel;
}

function saveEvalAnnotation(turn, patch) {
  const key = turn.turn_result_id;
  const previous = state.evalAnnotationSaveQueue.get(key) || Promise.resolve();
  const next = previous.catch(() => {}).then(() => postEvalAnnotation(turn, patch));
  state.evalAnnotationSaveQueue.set(
    key,
    next.finally(() => {
      if (state.evalAnnotationSaveQueue.get(key) === next) {
        state.evalAnnotationSaveQueue.delete(key);
      }
    }),
  );
  return next;
}

async function postEvalAnnotation(turn, patch) {
  try {
    const annotation = turn.annotation || {};
    await request(`/eval/turn-results/${encodeURIComponent(turn.turn_result_id)}/annotation`, {
      method: "POST",
      body: JSON.stringify({
        accepted: patch.accepted === undefined ? annotation.accepted ?? null : patch.accepted,
        reject_reasons: patch.reject_reasons === undefined ? annotation.reject_reasons || [] : patch.reject_reasons,
        note: patch.note === undefined ? annotation.note || "" : patch.note,
        badcase: patch.badcase === undefined ? Boolean(turn.badcase) : Boolean(patch.badcase),
      }),
    });
    await refreshEvalAfterChange();
  } catch (err) {
    showError(err);
  }
}

async function refreshEvalAfterChange() {
  await withEvalConversationScroll(async () => {
    await Promise.all([
      loadEvalDetail(state.currentEvalFileId),
      loadEvalAnalytics(),
    ]);
    await loadEvalFiles({ refreshDetail: false });
  });
}

function renderEvalRunSummary() {
  const summary = $("evalRunSummary");
  const badcaseList = $("evalBadcaseList");
  if (!summary || !badcaseList) return;
  summary.replaceChildren();
  badcaseList.replaceChildren();
  const detail = state.currentEvalDetail;
  if (!detail) {
    summary.innerHTML = `<div class="eval-summary-card">暂无 TXT</div>`;
    return;
  }
  const run = detail.run;
  summary.appendChild(evalSummaryReviewControls(detail.file, run));
  if (!run) {
    const card = document.createElement("div");
    card.className = "eval-summary-card";
    card.innerHTML = `
      <h4>${escapeHtml(detail.file.filename)}</h4>
      <p>当前模型 ${escapeHtml(selectedEvalProfileId())} 暂未生成。</p>
    `;
    summary.appendChild(card);
    return;
  }
  const rated = run.accepted_turns + run.rejected_turns;
  const acceptance = rated ? run.accepted_turns / rated : null;
  const cards = [
    ["状态", evalStatusLabel(run.status)],
    ["主意图", effectiveIntent(run).l2 || run.main_intent?.l2 || run.main_skill_id || "未分类"],
    ["原识别意图", run.main_intent?.l2 || "未分类"],
    ["意图纠正", run.intent_error ? `已标记错误 → ${effectiveIntent(run).l2 || "未分类"}` : "未标记"],
    ["进度", `${run.generated_turns}/${run.total_turns}`],
    ["采纳率", formatRate(acceptance)],
    ["不采纳", String(run.rejected_turns)],
    ["失败", String(run.failed_turns)],
    ["TXT Badcase", detail.file.badcase ? "已标记" : "未标记"],
    ["最近 trace", latestTrace(detail.turn_results) || "-"],
  ];
  cards.forEach(([label, value]) => {
    const card = document.createElement("div");
    card.className = "eval-summary-card";
    card.innerHTML = `<span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong>`;
    summary.appendChild(card);
  });
  const actions = document.createElement("div");
  actions.className = "eval-summary-actions";
  actions.innerHTML = `
    <button type="button" data-action="regen">重新生成当前 TXT</button>
    <button type="button" data-action="retry">只重试失败</button>
  `;
  actions.querySelector("[data-action='regen']").addEventListener("click", generateCurrentEvalFile);
  actions.querySelector("[data-action='retry']").addEventListener("click", () => openEvalGenerateDialog([detail.file.txt_id], true));
  summary.appendChild(actions);

  const problemTurns = (detail.turn_results || []).filter(isEvalTurnProblem);
  const title = document.createElement("h4");
  title.textContent = "不采纳 / 失败明细";
  badcaseList.appendChild(title);
  if (!problemTurns.length) {
    const empty = document.createElement("p");
    empty.className = "eval-muted";
    empty.textContent = "当前模型暂无不采纳或失败记录。";
    badcaseList.appendChild(empty);
    return;
  }
  problemTurns.forEach((turn) => {
    const item = document.createElement("div");
    item.className = "eval-badcase-item";
    const reasons = turn.status === "error"
      ? turn.error
      : (turn.annotation?.reject_reasons || []).join("、") || "未填写不采纳原因";
    item.innerHTML = `
      <strong>${escapeHtml(turn.user_query)}</strong>
      <span>${escapeHtml(reasons)}</span>
    `;
    badcaseList.appendChild(item);
  });
}

function evalSummaryReviewControls(file, run) {
  const wrap = document.createElement("div");
  wrap.className = "eval-summary-top-actions";
  const note = file.badcase_note ? ` title="${escapeHtml(file.badcase_note)}"` : "";
  wrap.innerHTML = `
    <button type="button" class="eval-txt-badcase-btn ${file.badcase ? "active" : ""}"${note}>
      ${file.badcase ? "取消 BAD" : "标记 BAD"}
    </button>
    <button type="button" class="eval-intent-error-btn ${run?.intent_error ? "active" : ""}" ${run ? "" : "disabled"}>
      ${run?.intent_error ? "取消意图错误" : "意图识别错误"}
    </button>
  `;
  wrap.querySelector(".eval-txt-badcase-btn").addEventListener("click", () => toggleCurrentTxtBadcase(file));
  wrap.querySelector(".eval-intent-error-btn").addEventListener("click", () => toggleIntentReviewEditor(run));
  if (run && (state.showIntentReviewEditor || run.intent_error)) {
    wrap.appendChild(evalIntentReviewEditor(run));
  }
  return wrap;
}

function toggleIntentReviewEditor(run) {
  if (!run) return;
  if (run.intent_error && !state.showIntentReviewEditor) {
    updateEvalRunIntentReview(run, { intent_error: false, corrected_intent_l2: "", note: "" });
    return;
  }
  state.showIntentReviewEditor = !state.showIntentReviewEditor;
  renderEvalRunSummary();
}

function evalIntentReviewEditor(run) {
  const editor = document.createElement("div");
  editor.className = "eval-intent-review-editor";
  const selected = run.corrected_intent?.l2 || effectiveIntent(run).l2 || run.main_intent?.l2 || "";
  const options = intentOptionsWithCurrent(selected);
  editor.innerHTML = `
    <label>纠正后分组
      <select data-role="intent">
        ${options.map((item) => `<option value="${escapeHtml(item.l2)}">${escapeHtml(item.label || item.l2)}</option>`).join("")}
      </select>
    </label>
    <label>备注
      <input data-role="note" value="${escapeHtml(run.intent_error_note || "")}" placeholder="例如：主诉是协商还款，不是停催" />
    </label>
    <div class="eval-intent-review-actions">
      <button type="button" data-action="save" class="primary">保存意图纠正</button>
      <button type="button" data-action="cancel">收起</button>
    </div>
  `;
  const select = editor.querySelector("[data-role='intent']");
  select.value = selected || options[0]?.l2 || "";
  editor.querySelector("[data-action='save']").addEventListener("click", () => {
    updateEvalRunIntentReview(run, {
      intent_error: true,
      corrected_intent_l2: select.value,
      note: editor.querySelector("[data-role='note']").value,
    });
  });
  editor.querySelector("[data-action='cancel']").addEventListener("click", () => {
    state.showIntentReviewEditor = false;
    renderEvalRunSummary();
  });
  return editor;
}

function intentOptionsWithCurrent(current) {
  const options = [...state.evalIntentOptions];
  if (current && !options.some((item) => item.l2 === current)) {
    options.unshift({ l1: "当前", l2: current, label: current });
  }
  if (!options.length) {
    options.push({ l1: "人工", l2: "未分类", label: "未分类" });
  }
  return options;
}

async function updateEvalRunIntentReview(run, payload) {
  try {
    const data = await request(`/eval/runs/${encodeURIComponent(run.run_id)}/intent-review`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    state.showIntentReviewEditor = false;
    updateEvalRunLocally(data.run || run);
    await refreshEvalAfterChange();
  } catch (err) {
    showError(err);
  }
}

function updateEvalRunLocally(updatedRun) {
  if (!updatedRun?.run_id) return;
  if (state.currentEvalDetail?.run?.run_id === updatedRun.run_id) {
    state.currentEvalDetail.run = updatedRun;
  }
  if (Array.isArray(state.currentEvalDetail?.runs)) {
    state.currentEvalDetail.runs = state.currentEvalDetail.runs.map((run) =>
      run.run_id === updatedRun.run_id ? updatedRun : run,
    );
  }
  state.evalGroups.forEach((group) => {
    (group.items || []).forEach((file) => {
      if (file.run?.run_id === updatedRun.run_id) file.run = updatedRun;
      if (Array.isArray(file.runs)) {
        file.runs = file.runs.map((run) => run.run_id === updatedRun.run_id ? updatedRun : run);
      }
    });
  });
  renderEvalRunSummary();
  renderEvalFileList();
}

async function toggleCurrentTxtBadcase(file) {
  const next = !file.badcase;
  const note = next ? file.badcase_note || "" : "";
  try {
    const data = await request(`/eval/txt-files/${encodeURIComponent(file.txt_id)}/badcase`, {
      method: "POST",
      body: JSON.stringify({ badcase: next, note }),
    });
    updateEvalFileBadcaseLocally(data.file || { ...file, badcase: next, badcase_note: note });
    await refreshEvalAfterChange();
  } catch (err) {
    showError(err);
  }
}

function updateEvalFileBadcaseLocally(updatedFile) {
  if (!updatedFile?.txt_id) return;
  if (state.currentEvalDetail?.file?.txt_id === updatedFile.txt_id) {
    state.currentEvalDetail.file.badcase = Boolean(updatedFile.badcase);
    state.currentEvalDetail.file.badcase_note = updatedFile.badcase_note || "";
  }
  state.evalGroups.forEach((group) => {
    (group.items || []).forEach((file) => {
      if (file.txt_id === updatedFile.txt_id) {
        file.badcase = Boolean(updatedFile.badcase);
        file.badcase_note = updatedFile.badcase_note || "";
      }
    });
  });
  state.evalFiles.forEach((file) => {
    if (file.txt_id === updatedFile.txt_id) {
      file.badcase = Boolean(updatedFile.badcase);
      file.badcase_note = updatedFile.badcase_note || "";
    }
  });
  renderEvalFileList();
  renderEvalRunSummary();
}

function latestTrace(turns = []) {
  return [...turns].reverse().find((turn) => turn.trace_id)?.trace_id || "";
}

function isEvalTurnProblem(turn) {
  return Boolean(turn.status === "error" || turn.annotation?.accepted === false);
}

async function importEvalTxtFiles(event) {
  const input = event.target;
  const files = Array.from(input.files || []);
  if (!files.length) return;
  try {
    const payload = { files: [] };
    for (const file of files) {
      payload.files.push({ filename: file.name, content: await file.text() });
    }
    const data = await request("/eval/txt-files/import", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    state.currentEvalFileId = data.files?.[0]?.txt_id || state.currentEvalFileId;
    state.currentEvalView = "all";
    renderEvalViewSelect();
    await loadEvalFiles();
  } catch (err) {
    showError(err);
  } finally {
    input.value = "";
  }
}

async function changeEvalView() {
  state.currentEvalView = $("evalViewSelect").value || "all";
  if (state.currentEvalView !== "all") {
    $("evalModelSelect").value = state.currentEvalView;
  }
  await loadEvalFiles();
}

async function changeEvalModel() {
  if (state.currentEvalView !== "all") {
    state.currentEvalView = selectedEvalProfileId();
    renderEvalViewSelect();
    await loadEvalFiles();
    return;
  }
  await loadEvalDetail(state.currentEvalFileId);
}

function selectedEvalProfileId() {
  return $("evalModelSelect")?.value || state.defaultLlmProfileId || evalProfileIds()[0];
}

function selectedEvalFileIds() {
  const ids = [...state.evalSelectedIds].filter((id) => state.evalFiles.some((file) => file.txt_id === id));
  return ids.length ? ids : state.currentEvalFileId ? [state.currentEvalFileId] : [];
}

function currentEvalFileIds() {
  return state.currentEvalFileId ? [state.currentEvalFileId] : [];
}

async function generateSelectedEvalFiles() {
  openEvalGenerateDialog(selectedEvalFileIds(), false);
}

async function retryFailedEvalFiles() {
  openEvalGenerateDialog(selectedEvalFileIds(), true);
}

async function generateCurrentEvalFile() {
  if (!state.currentEvalFileId) return;
  openEvalGenerateDialog([state.currentEvalFileId], false);
}

function openEvalGenerateDialog(txtIds, retryFailedOnly) {
  if (!txtIds.length) {
    showError(new Error("请先选择 TXT"));
    return;
  }
  state.pendingEvalGenerateIds = txtIds;
  state.pendingEvalRetryFailed = retryFailedOnly;
  renderEvalGenerateProfileSelect();
  $("evalGenerateDialogTitle").textContent = `${retryFailedOnly ? "重试失败" : "生成评测"} · ${txtIds.length} 个 TXT`;
  $("evalGenerateRetryOnlyInput").checked = retryFailedOnly;
  const defaultProfile = state.currentEvalView !== "all" ? state.currentEvalView : selectedEvalProfileId();
  if (evalProfileIds().includes(defaultProfile)) {
    $("evalGenerateProfileSelect").value = defaultProfile;
  }
  $("evalGenerateDialog").showModal();
}

function closeEvalGenerateDialog() {
  $("evalGenerateDialog").close();
}

async function startEvalGenerateFromDialog() {
  const ids = state.pendingEvalGenerateIds;
  const retryFailedOnly = $("evalGenerateRetryOnlyInput").checked;
  await generateEvalFiles(ids, retryFailedOnly, {
    llm_profile_id: $("evalGenerateProfileSelect").value,
    concurrency: Number($("evalGenerateConcurrencyInput").value || 3),
    timeout_seconds: Number($("evalGenerateTimeoutInput").value || 60),
  });
  closeEvalGenerateDialog();
}

async function generateEvalFiles(txtIds, retryFailedOnly, options = {}) {
  if (!txtIds.length) {
    showError(new Error("请先选择 TXT"));
    return;
  }
  const profileId = options.llm_profile_id || (state.currentEvalView !== "all" ? state.currentEvalView : selectedEvalProfileId());
  if (!txtIds.includes(state.currentEvalFileId)) {
    state.currentEvalFileId = txtIds[0] || state.currentEvalFileId;
  }
  syncEvalProfile(profileId);
  try {
    const data = await request("/eval/runs/generate", {
      method: "POST",
      body: JSON.stringify({
        txt_file_ids: txtIds,
        llm_profile_id: profileId,
        concurrency: Number(options.concurrency || 3),
        timeout_seconds: Number(options.timeout_seconds || 60),
        retry_failed_only: retryFailedOnly,
      }),
    });
    state.currentEvalJobId = data.job.job_id;
    state.currentEvalJob = data.job;
    state.evalJobRefreshKey = "";
    state.evalJobRefreshPending = null;
    renderEvalJob(data.job);
    startEvalJobPolling(data.job.job_id);
  } catch (err) {
    showError(err);
  }
}

function startEvalJobPolling(jobId) {
  if (state.evalJobTimer) {
    clearInterval(state.evalJobTimer);
  }
  state.evalJobRefreshKey = "";
  state.evalJobRefreshPending = null;
  state.evalJobTimer = setInterval(() => pollEvalJob(jobId), 1200);
  pollEvalJob(jobId);
}

async function pollEvalJob(jobId) {
  try {
    const data = await request(`/eval/jobs/${encodeURIComponent(jobId)}`);
    const job = data.job;
    renderEvalJob(job);
    const isRunning = job.status === "running";
    await refreshEvalForJob(job, { force: !isRunning });
    if (!isRunning) {
      clearInterval(state.evalJobTimer);
      state.evalJobTimer = null;
    }
  } catch (err) {
    clearInterval(state.evalJobTimer);
    state.evalJobTimer = null;
    showError(err);
  }
}

function syncEvalProfile(profileId) {
  if (!profileId) return;
  const select = $("evalModelSelect");
  const known = evalProfileIds().includes(profileId);
  if (select && known) {
    select.value = profileId;
  }
  if (state.currentEvalView !== "all" && state.currentEvalView !== profileId && known) {
    state.currentEvalView = profileId;
    renderEvalViewSelect();
  }
}

function evalJobRefreshKey(job) {
  return [
    job.job_id,
    job.status,
    job.completed_turns,
    job.success_turns,
    job.failed_turns,
    job.updated_at,
  ].join("|");
}

async function refreshEvalForJob(job, { force = false } = {}) {
  if (!job?.job_id) return;
  const key = evalJobRefreshKey(job);
  if (!force && state.evalJobRefreshKey === key) return;
  state.evalJobRefreshKey = key;
  state.evalJobRefreshPending = { job, force };
  if (state.evalJobRefreshInFlight) return;
  state.evalJobRefreshInFlight = true;
  try {
    while (state.evalJobRefreshPending) {
      const next = state.evalJobRefreshPending;
      state.evalJobRefreshPending = null;
      syncEvalProfile(next.job.llm_profile_id);
      await loadEvalFiles({ preserveScroll: true });
      if (next.force || next.job.status !== "running") {
        await loadEvalAnalytics();
      }
    }
  } finally {
    state.evalJobRefreshInFlight = false;
  }
}

function renderEvalJob(job) {
  state.currentEvalJob = job || null;
  const button = $("evalProgressBtn");
  if (!button) return;
  if (!job?.job_id) {
    button.textContent = "生成进度";
    button.classList.remove("eval-progress-button", "active");
    return;
  }
  const total = job.total_turns || 0;
  const active = job.status === "running";
  button.classList.add("eval-progress-button");
  button.classList.toggle("active", active);
  button.textContent = active
    ? `生成进度 ${job.completed_turns || 0}/${total}`
    : "生成进度";
  if (isEvalProgressDialogOpen()) {
    loadEvalJobs({ silent: true });
  }
}

async function cancelEvalJob(jobId = state.currentEvalJobId) {
  if (!jobId) return;
  try {
    const data = await request(`/eval/jobs/${encodeURIComponent(jobId)}/cancel`, { method: "POST" });
    renderEvalJob(data.job);
    if (state.evalJobTimer) {
      clearInterval(state.evalJobTimer);
      state.evalJobTimer = null;
    }
    await Promise.all([loadEvalFiles({ preserveScroll: true }), loadEvalJobs({ silent: true })]);
  } catch (err) {
    showError(err);
  }
}

async function openEvalProgressDialog() {
  $("evalProgressDialog").showModal();
  await loadEvalJobs();
}

function closeEvalProgressDialog() {
  $("evalProgressDialog").close();
}

function isEvalProgressDialogOpen() {
  return Boolean($("evalProgressDialog")?.open);
}

async function loadEvalJobs({ silent = false } = {}) {
  try {
    const data = await request("/eval/jobs?limit=30");
    state.evalJobs = data.jobs || [];
    renderEvalJobs();
  } catch (err) {
    if (!silent) showError(err);
  }
}

function renderEvalJobs() {
  const wrap = $("evalProgressList");
  if (!wrap) return;
  wrap.replaceChildren();
  if (!state.evalJobs.length) {
    const empty = document.createElement("div");
    empty.className = "eval-progress-empty";
    empty.textContent = "暂无生成任务。";
    wrap.appendChild(empty);
    return;
  }
  state.evalJobs.forEach((job, index) => {
    const details = document.createElement("details");
    details.className = "eval-progress-job";
    details.open = index === 0 || job.status === "running";
    const total = Number(job.total_turns || 0);
    const completed = Number(job.completed_turns || 0);
    const progress = total ? Math.min(100, Math.round((completed / total) * 100)) : 0;
    const config = job.config || {};
    details.innerHTML = `
      <summary>
        <span>
          <strong>${escapeHtml(job.llm_profile_id)} · ${escapeHtml(evalStatusLabel(job.status))}</strong>
          <span>${completed}/${total} · 成功 ${Number(job.success_turns || 0)} · 失败 ${Number(job.failed_turns || 0)} · 并发 ${escapeHtml(config.concurrency || "-")} · 超时 ${escapeHtml(config.timeout_seconds || "-")}s</span>
        </span>
        ${job.status === "running" ? `<button type="button" data-cancel-job="${escapeHtml(job.job_id)}">取消</button>` : ""}
      </summary>
      <div class="eval-progress-meter" style="--progress: ${progress}%"><i></i></div>
      <div class="eval-progress-files"></div>
    `;
    const fileWrap = details.querySelector(".eval-progress-files");
    (job.file_progress || []).forEach((item) => {
      const file = document.createElement("div");
      file.className = `eval-progress-file ${item.status || ""}`;
      file.innerHTML = `
        <span>
          <strong title="${escapeHtml(item.filename)}">${escapeHtml(item.filename)}</strong>
          <span>${escapeHtml(item.llm_profile_id || job.llm_profile_id)} · ${escapeHtml(item.main_intent?.l2 || "未分类")}${item.error ? ` · ${escapeHtml(item.error)}` : ""}</span>
        </span>
        <span>
          <b>${escapeHtml(evalStatusLabel(item.status))}</b>
          <em>${Number(item.generated_turns || 0)}/${Number(item.total_turns || 0)} · 失败 ${Number(item.failed_turns || 0)}</em>
        </span>
      `;
      fileWrap.appendChild(file);
    });
    details.querySelector("[data-cancel-job]")?.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      cancelEvalJob(event.currentTarget.dataset.cancelJob);
    });
    wrap.appendChild(details);
  });
}

async function deleteSelectedEvalFiles() {
  const ids = selectedEvalFileIds();
  if (!ids.length) return;
  if (!confirm(`确认物理删除 ${ids.length} 个 TXT 及其所有评测结果？`)) return;
  try {
    await request("/eval/txt-files", {
      method: "DELETE",
      body: JSON.stringify({ txt_file_ids: ids }),
    });
    ids.forEach((id) => state.evalSelectedIds.delete(id));
    if (ids.includes(state.currentEvalFileId)) {
      state.currentEvalFileId = "";
    }
    await Promise.all([loadEvalFiles(), loadEvalAnalytics()]);
  } catch (err) {
    showError(err);
  }
}

async function resetCurrentEvalAnnotations() {
  const detail = state.currentEvalDetail;
  if (!detail?.turn_results?.length) return;
  if (!confirm("确认清空当前 TXT 当前模型的人工标注？")) return;
  try {
    for (const turn of detail.turn_results) {
      await request(`/eval/turn-results/${encodeURIComponent(turn.turn_result_id)}/annotation`, {
        method: "POST",
        body: JSON.stringify({ accepted: null, reject_reasons: [], note: "", badcase: false }),
      });
    }
    await refreshEvalAfterChange();
  } catch (err) {
    showError(err);
  }
}

function exportEvalResult() {
  const payload = state.currentView === "analytics" || state.currentEvalPanel === "analytics"
    ? state.evalAnalytics || {}
    : state.currentEvalDetail || {};
  const blob = new Blob([pretty(payload)], { type: "application/json;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `eval-${state.currentEvalPanel}-${new Date().toISOString().slice(0, 10)}.json`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

async function switchEvalPanel(panel, options = {}) {
  state.currentEvalPanel = panel;
  $("evalWorkspacePanel")?.classList.toggle("hidden", panel !== "workbench");
  $("evalAnalyticsPanel")?.classList.toggle("hidden", panel !== "analytics");
  $("evalWorkbenchTab")?.classList.toggle("active", panel === "workbench");
  $("evalAnalyticsTab")?.classList.toggle("active", panel === "analytics");
  if (panel === "analytics") {
    await loadEvalAnalytics({ badcase: Boolean(options.badcase) });
  }
}

function currentAnalyticsFilters(options = {}) {
  return {
    llmProfileId: $("analyticsModelFilter")?.value || "",
    intentL2: $("analyticsIntentFilter")?.value || "",
    status: $("analyticsStatusFilter")?.value || "",
    badcase: options.badcase === undefined ? Boolean($("analyticsBadcaseOnly")?.checked) : Boolean(options.badcase),
  };
}

function showAllAnalytics() {
  if ($("analyticsModelFilter")) $("analyticsModelFilter").value = "";
  if ($("analyticsIntentFilter")) $("analyticsIntentFilter").value = "";
  if ($("analyticsStatusFilter")) $("analyticsStatusFilter").value = "";
  if ($("analyticsBadcaseOnly")) $("analyticsBadcaseOnly").checked = false;
  loadEvalAnalytics();
}

function setAnalyticsBadcaseFilter(value) {
  if ($("analyticsBadcaseOnly")) $("analyticsBadcaseOnly").checked = Boolean(value);
  loadEvalAnalytics({ badcase: Boolean(value) });
}

async function loadEvalAnalytics(options = {}) {
  try {
    const filters = currentAnalyticsFilters(options);
    const query = new URLSearchParams();
    if (filters.llmProfileId) query.set("llm_profile_id", filters.llmProfileId);
    if (filters.intentL2) query.set("intent_l2", filters.intentL2);
    if (filters.status) query.set("status", filters.status);
    if (filters.badcase) query.set("badcase", "true");
    const data = await request(`/eval/analytics/summary${query.toString() ? `?${query.toString()}` : ""}`);
    data.filters = filters;
    state.evalAnalytics = data;
    renderEvalAnalytics();
  } catch (err) {
    showError(err);
  }
}

function renderEvalAnalytics() {
  const data = state.evalAnalytics;
  if (!data) return;
  const summary = $("evalAnalyticsSummary");
  const tables = $("evalAnalyticsTables");
  const filters = $("evalAnalyticsFilters");
  if (!summary || !tables || !filters) return;
  syncAnalyticsIntentFilter(data);
  const filterItems = analyticsFilterChips(data.filters || {});
  filters.replaceChildren(...filterItems);
  const subtitle = $("analyticsSubtitle");
  if (subtitle) {
    subtitle.textContent = analyticsSubtitleText(data);
  }
  const items = [
    analyticsKpiCard("TXT 覆盖", data.summary.txt_count, `${data.summary.run_count || 0} 个模型评测`, "neutral"),
    analyticsKpiCard("用户 Query", data.summary.turn_count, `${data.summary.generated_count || 0} 条已生成`, "neutral"),
    analyticsKpiCard("生成成功率", ratioText(data.summary.generated_count, data.summary.turn_count), `${data.summary.failed_count || 0} 条失败`, data.summary.failed_count ? "danger" : "good"),
    analyticsKpiCard("路由准确率", formatRate(data.summary.route_accuracy), `${data.summary.intent_error_count || 0} 个意图错误`, data.summary.intent_error_count ? "danger" : "good"),
    analyticsKpiCard("人工采纳率", formatRate(data.summary.acceptance_rate), `${data.summary.rated_count || 0} 条已评`, data.summary.acceptance_rate === null ? "neutral" : "good"),
    analyticsKpiCard("TXT Badcase", data.summary.badcase_count, "仅统计人工标记的 TXT 级样本", data.summary.badcase_count ? "danger" : "good"),
  ];
  summary.replaceChildren(...items);
  tables.replaceChildren(
    evalAnalyticsPriorityPanel(data),
    evalAnalyticsMetricGrid("模型表现", data.by_model || []),
    evalAnalyticsMetricGrid("二级意图表现", data.by_intent || []),
    evalReasonTable(data.reject_reasons || []),
    evalTxtBadcaseList(data.txt_badcases || []),
    evalIntentErrorList(data.intent_errors || []),
    evalTurnList("不采纳 / 失败明细", data.problem_turns || []),
    evalLowAcceptanceList(data.low_acceptance_runs || []),
    evalTurnList("失败明细", data.failures || []),
  );
}

function syncAnalyticsIntentFilter(data) {
  const select = $("analyticsIntentFilter");
  if (!select) return;
  const previous = select.value;
  const names = new Set((state.evalIntentOptions || []).map((item) => item.l2).filter(Boolean));
  (data.by_intent || []).forEach((row) => {
    if (row.name) names.add(row.name);
  });
  if (previous) names.add(previous);
  select.replaceChildren(
    optionNode("", "全部意图"),
    ...[...names].sort((a, b) => a.localeCompare(b, "zh-Hans-CN")).map((name) => optionNode(name, name)),
  );
  select.value = [...names, ""].includes(previous) ? previous : "";
}

function optionNode(value, label) {
  const option = document.createElement("option");
  option.value = value;
  option.textContent = label;
  return option;
}

function analyticsFilterChips(filters) {
  const chips = [];
  const active = [
    filters.llmProfileId ? `模型：${filters.llmProfileId}` : "",
    filters.intentL2 ? `意图：${filters.intentL2}` : "",
    filters.status ? `状态：${evalStatusLabel(filters.status)}` : "",
    filters.badcase ? "只看 TXT Badcase" : "",
  ].filter(Boolean);
  const items = active.length ? active : ["全部结果"];
  items.forEach((item) => {
    const chip = document.createElement("span");
    chip.className = filters.badcase && item.includes("Badcase") ? "danger" : "";
    chip.textContent = item;
    chips.push(chip);
  });
  return chips;
}

function analyticsSubtitleText(data) {
  const summary = data.summary || {};
  const filters = data.filters || {};
  const scope = [
    filters.llmProfileId || "全部模型",
    filters.intentL2 || "全部意图",
    filters.status ? evalStatusLabel(filters.status) : "",
    filters.badcase ? "TXT Badcase" : "",
  ].filter(Boolean).join(" · ");
  return `${scope}｜${summary.txt_count || 0} 个 TXT，${summary.turn_count || 0} 条用户 query，${summary.rated_count || 0} 条已评`;
}

function analyticsKpiCard(label, value, hint, tone = "neutral") {
  const card = document.createElement("div");
  card.className = `analytics-kpi ${tone}`;
  card.innerHTML = `
    <span>${escapeHtml(label)}</span>
    <strong>${escapeHtml(value)}</strong>
    <em>${escapeHtml(hint || "")}</em>
  `;
  return card;
}

function ratioText(part, total) {
  const denominator = Number(total || 0);
  if (!denominator) return "无数据";
  return `${Math.round((Number(part || 0) / denominator) * 100)}%`;
}

function evalAnalyticsPriorityPanel(data) {
  const box = document.createElement("section");
  box.className = "eval-analytics-box analytics-priority prominent";
  const failures = data.failures || [];
  const problemTurns = data.problem_turns || [];
  const txtBadcases = data.txt_badcases || [];
  const intentErrors = data.intent_errors || [];
  const lowRuns = data.low_acceptance_runs || [];
  const riskCount = (data.summary?.badcase_count || 0) + intentErrors.length + problemTurns.length + lowRuns.length;
  box.innerHTML = `
    <div class="analytics-section-head">
      <div>
        <h3>优先关注</h3>
        <p>先看 TXT Badcase、意图错误、不采纳和失败，适合快速定位质量问题。</p>
      </div>
      <strong>${riskCount} 个风险点</strong>
    </div>
  `;
  const grid = document.createElement("div");
  grid.className = "analytics-priority-grid";
  grid.append(
    analyticsPriorityColumn("TXT Badcase", txtBadcases, (file) => [file.filename, file.badcase_note || `${file.user_turn_count || 0} 个用户 query`]),
    analyticsPriorityColumn("意图错误", intentErrors, (run) => [run.filename || run.txt_id, `${run.llm_profile_id} · ${run.main_intent?.l2 || "未分类"} → ${effectiveIntent(run).l2 || "未分类"}`]),
    analyticsPriorityColumn("单轮问题", problemTurns, (turn) => [turn.user_query, `${turn.run?.llm_profile_id || ""} · ${turn.run?.main_intent?.l2 || "未分类"}`]),
    analyticsPriorityColumn("失败明细", failures, (turn) => [turn.user_query, turn.error || `${turn.run?.llm_profile_id || ""} 生成失败`]),
    analyticsPriorityColumn("低采纳率", lowRuns, (run) => [run.filename || run.txt_id, `${run.llm_profile_id} · ${run.accepted_turns || 0}/${(run.accepted_turns || 0) + (run.rejected_turns || 0)} 采纳`]),
  );
  box.appendChild(grid);
  return box;
}

function analyticsPriorityColumn(title, rows, lineFn) {
  const col = document.createElement("div");
  col.className = "analytics-priority-column";
  col.innerHTML = `<h4>${escapeHtml(title)}<span>${rows.length}</span></h4>`;
  if (!rows.length) {
    const empty = document.createElement("p");
    empty.className = "eval-muted";
    empty.textContent = "暂无数据";
    col.appendChild(empty);
    return col;
  }
  rows.slice(0, 4).forEach((row) => {
    const [main, sub] = lineFn(row);
    const item = document.createElement("div");
    item.className = "analytics-priority-item";
    item.innerHTML = `<strong>${escapeHtml(main)}</strong><span>${escapeHtml(sub || "")}</span>`;
    col.appendChild(item);
  });
  return col;
}

function evalAnalyticsMetricGrid(title, rows) {
  const box = document.createElement("section");
  box.className = "eval-analytics-box analytics-metric-box";
  box.innerHTML = `<h3>${escapeHtml(title)}</h3>`;
  const grid = document.createElement("div");
  grid.className = "analytics-metric-grid";
  if (!rows.length) {
    const empty = document.createElement("p");
    empty.className = "eval-muted";
    empty.textContent = "暂无数据";
    grid.appendChild(empty);
  } else {
    rows.forEach((row) => grid.appendChild(analyticsMetricItem(row)));
  }
  box.appendChild(grid);
  return box;
}

function analyticsMetricItem(row) {
  const item = document.createElement("div");
  item.className = "analytics-metric-item";
  const rate = row.acceptance_rate;
  const bar = rate === null || rate === undefined ? 0 : Math.max(0, Math.min(100, Math.round(rate * 100)));
  item.style.setProperty("--bar", `${bar}%`);
  item.innerHTML = `
    <div class="analytics-metric-title">
      <strong>${escapeHtml(row.name)}</strong>
      <span>${formatRate(row.acceptance_rate)}</span>
    </div>
    <div class="analytics-bar"><i></i></div>
    <div class="analytics-metric-meta">
      <span>${row.turn_count || 0} 轮</span>
      <span>${row.rated_count || 0} 已评</span>
      <span>${row.failed_count || 0} 失败</span>
      <span>${row.issue_count || 0} 问题</span>
      <span>${row.badcase_count || 0} TXT BAD</span>
      <span>${row.intent_error_count || 0} 意图错</span>
    </div>
  `;
  return item;
}

function evalAnalyticsTable(title, rows) {
  const box = document.createElement("section");
  box.className = "eval-analytics-box";
  box.innerHTML = `<h3>${escapeHtml(title)}</h3>`;
  const table = document.createElement("table");
  table.innerHTML = `
    <thead><tr><th>名称</th><th>轮次</th><th>已评</th><th>采纳率</th><th>失败</th><th>单轮问题</th><th>TXT Badcase</th></tr></thead>
    <tbody></tbody>
  `;
  const body = table.querySelector("tbody");
  if (!rows.length) {
    body.innerHTML = `<tr><td colspan="7">暂无数据</td></tr>`;
  } else {
    rows.forEach((row) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${escapeHtml(row.name)}</td>
        <td>${row.turn_count}</td>
        <td>${row.rated_count}</td>
        <td>${formatRate(row.acceptance_rate)}</td>
        <td>${row.failed_count}</td>
        <td>${row.issue_count || 0}</td>
        <td>${row.badcase_count}</td>
      `;
      body.appendChild(tr);
    });
  }
  box.appendChild(table);
  return box;
}

function evalReasonTable(rows) {
  const box = document.createElement("section");
  box.className = "eval-analytics-box";
  box.innerHTML = `<h3>不采纳原因</h3>`;
  const list = document.createElement("div");
  list.className = "eval-reason-list";
  if (!rows.length) {
    list.textContent = "暂无不采纳原因";
  } else {
    rows.forEach((row) => {
      const item = document.createElement("div");
      item.innerHTML = `<span>${escapeHtml(row.reason)}</span><strong>${row.count}</strong>`;
      list.appendChild(item);
    });
  }
  box.appendChild(list);
  return box;
}

function evalTurnList(title, rows) {
  const box = document.createElement("section");
  box.className = "eval-analytics-box prominent";
  box.innerHTML = `<h3>${escapeHtml(title)}</h3>`;
  if (!rows.length) {
    const empty = document.createElement("p");
    empty.className = "eval-muted";
    empty.textContent = "暂无数据";
    box.appendChild(empty);
    return box;
  }
  rows.slice(0, 40).forEach((turn) => {
    const item = document.createElement("div");
    item.className = "eval-turn-list-item";
    const run = turn.run || {};
    const reason = turn.status === "error"
      ? turn.error
      : (turn.annotation?.reject_reasons || []).join("、") || "人工标记";
    item.innerHTML = `
      <strong>${escapeHtml(turn.user_query)}</strong>
      <span>${escapeHtml(run.llm_profile_id || "")} · ${escapeHtml(run.main_intent?.l2 || "未分类")} · ${escapeHtml(reason || "")}</span>
    `;
    box.appendChild(item);
  });
  return box;
}

function evalTxtBadcaseList(rows) {
  const box = document.createElement("section");
  box.className = "eval-analytics-box prominent";
  box.innerHTML = `<h3>TXT Badcase</h3>`;
  if (!rows.length) {
    const empty = document.createElement("p");
    empty.className = "eval-muted";
    empty.textContent = "暂无数据";
    box.appendChild(empty);
    return box;
  }
  rows.slice(0, 40).forEach((file) => {
    const item = document.createElement("div");
    item.className = "eval-turn-list-item";
    item.innerHTML = `
      <strong>${escapeHtml(file.filename)}</strong>
      <span>${escapeHtml(file.badcase_note || "未填写原因")} · ${file.user_turn_count || 0} 个用户 query</span>
    `;
    box.appendChild(item);
  });
  return box;
}

function evalIntentErrorList(rows) {
  const box = document.createElement("section");
  box.className = "eval-analytics-box prominent";
  box.innerHTML = `<h3>意图识别错误</h3>`;
  if (!rows.length) {
    const empty = document.createElement("p");
    empty.className = "eval-muted";
    empty.textContent = "暂无数据";
    box.appendChild(empty);
    return box;
  }
  rows.slice(0, 40).forEach((run) => {
    const item = document.createElement("div");
    item.className = "eval-turn-list-item";
    item.innerHTML = `
      <strong>${escapeHtml(run.filename || run.txt_id)}</strong>
      <span>${escapeHtml(run.llm_profile_id)} · ${escapeHtml(run.main_intent?.l2 || "未分类")} → ${escapeHtml(effectiveIntent(run).l2 || "未分类")}${run.intent_error_note ? ` · ${escapeHtml(run.intent_error_note)}` : ""}</span>
    `;
    box.appendChild(item);
  });
  return box;
}

function evalLowAcceptanceList(rows) {
  const box = document.createElement("section");
  box.className = "eval-analytics-box prominent";
  box.innerHTML = `<h3>低采纳率 TXT</h3>`;
  if (!rows.length) {
    const empty = document.createElement("p");
    empty.className = "eval-muted";
    empty.textContent = "暂无数据";
    box.appendChild(empty);
    return box;
  }
  rows.slice(0, 40).forEach((run) => {
    const rated = (run.accepted_turns || 0) + (run.rejected_turns || 0);
    const item = document.createElement("div");
    item.className = "eval-turn-list-item";
    item.innerHTML = `
      <strong>${escapeHtml(run.filename || run.txt_id)}</strong>
      <span>${escapeHtml(run.llm_profile_id)} · ${escapeHtml(run.main_intent?.l2 || "未分类")} · ${run.accepted_turns}/${rated} 采纳</span>
    `;
    box.appendChild(item);
  });
  return box;
}

function evalStatusLabel(status) {
  const labels = {
    pending: "暂未生成",
    running: "生成中",
    success: "成功",
    completed: "已完成",
    partial_failed: "部分失败",
    error: "失败",
    cancelled: "已取消",
  };
  return labels[status] || status || "未知";
}

function formatRate(value) {
  return value === null || value === undefined ? "未评" : `${Math.round(value * 100)}%`;
}

function toggleValue(values, value) {
  return values.includes(value)
    ? values.filter((item) => item !== value)
    : [...values, value];
}

function captureEvalConversationScroll() {
  const el = $("evalConversation");
  if (!el) return null;
  return { top: el.scrollTop, left: el.scrollLeft };
}

function restoreEvalConversationScroll(position) {
  if (!position) return;
  requestAnimationFrame(() => {
    const el = $("evalConversation");
    if (!el) return;
    const maxTop = Math.max(0, el.scrollHeight - el.clientHeight);
    el.scrollTop = Math.min(position.top, maxTop);
    el.scrollLeft = position.left;
  });
}

async function withEvalConversationScroll(work) {
  const position = captureEvalConversationScroll();
  try {
    return await work();
  } finally {
    restoreEvalConversationScroll(position);
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
