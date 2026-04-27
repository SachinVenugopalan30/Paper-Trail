// Paper Trail — frontend logic
// Vanilla ES module. Streams chat tokens via SSE, fires retrieval in parallel,
// renders markdown safely via marked + DOMPurify.

const els = {
  providerSelect: document.getElementById("provider-select"),
  modelHost: document.getElementById("model-field-host"),
  status: document.getElementById("status"),
  statusLabel: document.getElementById("status-label"),
  chat: document.getElementById("chat-stream"),
  onboarding: document.getElementById("onboarding"),
  sourcesList: document.getElementById("sources-list"),
  sourcesCount: document.getElementById("sources-count"),
  form: document.getElementById("composer-form"),
  input: document.getElementById("query-input"),
  sendBtn: document.getElementById("send-btn"),
};

const state = {
  providers: {},
  activeProvider: null,
  activeModel: null,
  history: [],
  streaming: false,
};

// ---------- helpers ----------

function setStatus(stateName, label) {
  els.status.dataset.state = stateName;
  els.status.title = label;
  els.statusLabel.textContent = label;
}

function clearChildren(node) {
  while (node.firstChild) node.removeChild(node.firstChild);
}

function el(tag, opts = {}, children = []) {
  const node = document.createElement(tag);
  if (opts.class) node.className = opts.class;
  if (opts.text != null) node.textContent = opts.text;
  if (opts.attrs) {
    for (const [k, v] of Object.entries(opts.attrs)) node.setAttribute(k, v);
  }
  if (opts.style) {
    for (const [k, v] of Object.entries(opts.style)) node.style.setProperty(k, v);
  }
  for (const child of children) {
    if (child) node.appendChild(child);
  }
  return node;
}

function renderMarkdown(target, mdText) {
  // marked + DOMPurify is the safe HTML render path.
  const html = window.marked.parse(mdText, { breaks: true, gfm: true });
  const clean = window.DOMPurify.sanitize(html);
  const wrap = document.createElement("div");
  wrap.innerHTML = clean;
  target.replaceChildren(...wrap.childNodes);
}

function dismissOnboarding() {
  if (els.onboarding && els.onboarding.parentNode) {
    els.onboarding.classList.add("fade-out");
    setTimeout(() => els.onboarding?.remove(), 200);
  }
}

function scrollChatToBottom() {
  els.chat.scrollTo({ top: els.chat.scrollHeight, behavior: "smooth" });
}

// ---------- provider/model controls ----------

async function loadProviders() {
  setStatus("loading", "Loading providers");
  try {
    const r = await fetch("/api/providers");
    if (!r.ok) throw new Error(`providers: ${r.status}`);
    const data = await r.json();
    state.providers = data.providers || {};
    state.activeProvider = data.active?.provider || null;
    state.activeModel = data.active?.model || "";

    populateProviderSelect();
    rebuildModelField();
    setStatus("idle", "Idle");
  } catch (e) {
    console.error(e);
    setStatus("error", "Provider load failed");
  }
}

function populateProviderSelect() {
  clearChildren(els.providerSelect);
  for (const name of Object.keys(state.providers)) {
    const opt = el("option", { text: name, attrs: { value: name } });
    if (name === state.activeProvider) opt.selected = true;
    els.providerSelect.appendChild(opt);
  }
}

function rebuildModelField() {
  const provider = state.activeProvider;
  const spec = state.providers[provider];
  els.modelHost.replaceChildren();

  if (!spec) return;

  if (spec.type === "select") {
    const sel = el("select", { attrs: { id: "model-select" } });
    for (const m of spec.options || []) {
      const opt = el("option", { text: m, attrs: { value: m } });
      if (m === state.activeModel) opt.selected = true;
      sel.appendChild(opt);
    }
    sel.addEventListener("change", () => {
      state.activeModel = sel.value;
      pushConfig();
    });
    els.modelHost.appendChild(sel);
  } else if (spec.type === "select-or-text") {
    const sel = el("select", { attrs: { id: "model-select" } });
    let matched = false;
    for (const m of spec.options || []) {
      const opt = el("option", { text: m, attrs: { value: m } });
      if (m === state.activeModel) {
        opt.selected = true;
        matched = true;
      }
      sel.appendChild(opt);
    }
    const customOpt = el("option", { text: "Custom…", attrs: { value: "__custom__" } });
    sel.appendChild(customOpt);
    if (!matched && state.activeModel) {
      customOpt.selected = true;
    }

    const txt = el("input", {
      attrs: { type: "text", id: "model-text", placeholder: "model name" },
    });
    txt.value = matched ? "" : state.activeModel || "";
    txt.style.display = matched ? "none" : "";

    sel.addEventListener("change", () => {
      if (sel.value === "__custom__") {
        txt.style.display = "";
        txt.focus();
      } else {
        txt.style.display = "none";
        state.activeModel = sel.value;
        pushConfig();
      }
    });
    txt.addEventListener("change", () => {
      const v = txt.value.trim();
      if (!v) return;
      state.activeModel = v;
      pushConfig();
    });

    els.modelHost.appendChild(sel);
    els.modelHost.appendChild(txt);
  } else {
    // type === "text"
    const txt = el("input", {
      attrs: {
        type: "text",
        id: "model-text",
        placeholder: spec.placeholder || "model name",
      },
    });
    txt.value = state.activeModel || "";
    txt.addEventListener("change", () => {
      const v = txt.value.trim();
      if (!v) return;
      state.activeModel = v;
      pushConfig();
    });
    els.modelHost.appendChild(txt);
  }
}

async function pushConfig() {
  if (!state.activeProvider || !state.activeModel) return;
  setStatus("loading", `Switching to ${state.activeProvider}/${state.activeModel}`);
  try {
    const r = await fetch("/api/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        provider: state.activeProvider,
        model: state.activeModel,
      }),
    });
    if (!r.ok) {
      const txt = await r.text();
      throw new Error(`config ${r.status}: ${txt}`);
    }
    setStatus("idle", "Idle");
  } catch (e) {
    console.error(e);
    setStatus("error", "Config failed");
  }
}

els.providerSelect.addEventListener("change", () => {
  state.activeProvider = els.providerSelect.value;
  const spec = state.providers[state.activeProvider];
  // pick a sensible default model when swapping providers
  if (spec?.type === "select" || spec?.type === "select-or-text") {
    state.activeModel = spec.options?.[0] || "";
  } else {
    state.activeModel = "";
  }
  rebuildModelField();
  if (state.activeModel) pushConfig();
});

// ---------- chat ----------

function buildBubble(role) {
  const bubble = el("div", { class: `bubble bubble-${role}` });
  const meta = el("div", {
    class: "bubble-meta",
    text: role === "user" ? "You" : "Paper Trail",
  });
  const content = el("div", { class: "bubble-content" });
  bubble.appendChild(meta);
  bubble.appendChild(content);
  return { bubble, content };
}

function appendUserMessage(text) {
  dismissOnboarding();
  const { bubble, content } = buildBubble("user");
  content.textContent = text;
  els.chat.appendChild(bubble);
  scrollChatToBottom();
}

function appendAssistantPlaceholder() {
  const { bubble, content } = buildBubble("assistant");
  bubble.classList.add("streaming");
  const caret = el("span", { class: "caret", text: "▍" });
  bubble.appendChild(caret);
  els.chat.appendChild(bubble);
  scrollChatToBottom();
  return { bubble, content, caret };
}

function appendErrorBubble(message) {
  const { bubble, content } = buildBubble("assistant");
  bubble.classList.add("error");
  content.textContent = message;
  els.chat.appendChild(bubble);
  scrollChatToBottom();
}

// ---------- sources ----------

function renderSourcesEmpty() {
  els.sourcesList.replaceChildren(
    el("p", { class: "sources-empty", text: "No sources retrieved." })
  );
  els.sourcesCount.textContent = "0";
}

function renderSourcesLoading() {
  els.sourcesList.replaceChildren(
    el("p", { class: "sources-empty", text: "Retrieving…" })
  );
  els.sourcesCount.textContent = "…";
}

function badgeKindFor(source) {
  const s = (source || "").toLowerCase();
  if (s.includes("bm25")) return "bm25";
  if (s.includes("vec")) return "vector";
  if (s.includes("graph") || s.includes("kg")) return "graph";
  return "";
}

function renderSources(results) {
  if (!results || results.length === 0) {
    renderSourcesEmpty();
    return;
  }
  const frag = document.createDocumentFragment();
  results.forEach((r, i) => {
    const card = el("article", {
      class: "source-card",
      style: { "--i": String(i) },
    });

    const head = el("div", { class: "source-card-head" });
    const kind = badgeKindFor(r.source);
    const badgeClass = kind ? `source-badge ${kind}` : "source-badge";
    head.appendChild(
      el("span", { class: badgeClass, text: kind || (r.source || "—") })
    );
    head.appendChild(
      el("span", { class: "source-score", text: r.score?.toFixed?.(4) ?? String(r.score) })
    );
    const docId = r.document_id || r.chunk_id || "—";
    head.appendChild(
      el("span", { class: "source-doc", text: docId, attrs: { title: docId } })
    );

    const previewText = (r.preview || "").replace(/\s+/g, " ").trim();
    const preview = el("p", {
      class: "source-preview",
      text: previewText,
    });

    card.appendChild(head);
    card.appendChild(preview);
    frag.appendChild(card);
  });
  els.sourcesList.replaceChildren(frag);
  els.sourcesCount.textContent = String(results.length);
}

async function fetchSources(query) {
  try {
    const r = await fetch("/api/retrieve", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query }),
    });
    if (!r.ok) throw new Error(`retrieve ${r.status}`);
    const data = await r.json();
    renderSources(data.results || []);
  } catch (e) {
    console.error(e);
    renderSourcesEmpty();
  }
}

// ---------- SSE chat ----------

async function streamChat(query, onToken, onDone, onError) {
  const r = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, history: state.history }),
  });
  if (!r.ok || !r.body) {
    onError(new Error(`chat ${r.status}`));
    return;
  }
  const reader = r.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });

    // SSE events split by blank line
    let idx;
    while ((idx = buf.indexOf("\n\n")) !== -1) {
      const raw = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      let event = "message";
      let data = "";
      for (const line of raw.split("\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) data += line.slice(5).trim();
      }
      if (!data) continue;
      let payload;
      try {
        payload = JSON.parse(data);
      } catch {
        continue;
      }
      if (event === "token") onToken(payload.text || "");
      else if (event === "done") onDone();
      else if (event === "error") onError(new Error(payload.message || "stream error"));
    }
  }
  onDone();
}

// ---------- submit ----------

async function submitQuery(rawQuery) {
  const query = (rawQuery || "").trim();
  if (!query || state.streaming) return;
  state.streaming = true;
  els.sendBtn.disabled = true;
  setStatus("streaming", "Thinking");

  appendUserMessage(query);
  const ph = appendAssistantPlaceholder();

  renderSourcesLoading();
  fetchSources(query);

  let accumulated = "";
  let scrollPending = false;

  const onToken = (text) => {
    accumulated += text;
    renderMarkdown(ph.content, accumulated);
    if (!scrollPending) {
      scrollPending = true;
      requestAnimationFrame(() => {
        scrollChatToBottom();
        scrollPending = false;
      });
    }
  };

  const finalize = () => {
    if (ph.caret && ph.caret.parentNode) ph.caret.remove();
    ph.bubble.classList.remove("streaming");
    if (accumulated.trim()) {
      state.history.push({ role: "user", content: query });
      state.history.push({ role: "assistant", content: accumulated });
    }
    state.streaming = false;
    els.sendBtn.disabled = false;
    setStatus("idle", "Idle");
  };

  try {
    let done = false;
    await streamChat(
      query,
      onToken,
      () => {
        if (done) return;
        done = true;
        finalize();
      },
      (err) => {
        if (done) return;
        done = true;
        console.error(err);
        if (!accumulated) {
          ph.bubble.remove();
          appendErrorBubble(`Error: ${err.message}`);
        } else {
          ph.bubble.classList.add("error");
        }
        state.streaming = false;
        els.sendBtn.disabled = false;
        setStatus("error", "Stream error");
      }
    );
  } catch (e) {
    console.error(e);
    if (!accumulated) {
      ph.bubble.remove();
      appendErrorBubble(`Error: ${e.message}`);
    }
    state.streaming = false;
    els.sendBtn.disabled = false;
    setStatus("error", "Stream error");
  }
}

// ---------- composer ----------

function autoGrow() {
  els.input.style.height = "auto";
  const max = 200;
  els.input.style.height = Math.min(els.input.scrollHeight, max) + "px";
}

els.input.addEventListener("input", autoGrow);

els.input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    const q = els.input.value;
    els.input.value = "";
    autoGrow();
    submitQuery(q);
  }
});

els.form.addEventListener("submit", (e) => {
  e.preventDefault();
  const q = els.input.value;
  els.input.value = "";
  autoGrow();
  submitQuery(q);
});

// onboarding suggestions click-through
if (els.onboarding) {
  els.onboarding.querySelectorAll("[data-q]").forEach((node) => {
    node.addEventListener("click", () => {
      const q = node.getAttribute("data-q") || node.textContent || "";
      submitQuery(q);
    });
  });
}

// ---------- boot ----------

loadProviders();
