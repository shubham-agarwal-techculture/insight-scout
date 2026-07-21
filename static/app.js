const scoutBtn = document.getElementById("scoutBtn");
const phaseLabel = document.getElementById("phaseLabel");
const phaseDetail = document.getElementById("phaseDetail");
const activityLog = document.getElementById("activityLog");
const insightTrack = document.getElementById("insightTrack");
const emptyState = document.getElementById("emptyState");
const insightsEl = document.getElementById("insights");
const errorBox = document.getElementById("errorBox");
const liveView = document.getElementById("liveView");
const historyView = document.getElementById("historyView");
const historyList = document.getElementById("historyList");
const historyListWrap = document.getElementById("historyListWrap");
const historyEmpty = document.getElementById("historyEmpty");
const historyDetail = document.getElementById("historyDetail");
const historyInsights = document.getElementById("historyInsights");
const historyDetailMeta = document.getElementById("historyDetailMeta");
const historyBack = document.getElementById("historyBack");
const historyCount = document.getElementById("historyCount");
const viewTabs = document.querySelectorAll(".nav-item");
const statusChip = document.getElementById("statusChip");
const statusChipLabel = document.getElementById("statusChipLabel");
const pageTitle = document.getElementById("pageTitle");
const pageSubtitle = document.getElementById("pageSubtitle");
const btnSpinner = scoutBtn?.querySelector(".btn-spinner");

let buffer = "";
let activeView = "live";
let historyRuns = [];
const toolRows = new Map();
const generatedImages = new Map(); // insight n -> url
const generatingImages = new Set();

const PHASE_COPY = {
  starting: ["Initializing", "Booting local Cursor agent runtime"],
  researching: ["Researching", "Cross-checking claims across independent sources"],
  writing: ["Composing", "Drafting verified insights"],
  done: ["Complete", "Five dual-sourced insights are ready"],
  error: ["Failed", "Run interrupted — see error details below"],
};

const STATUS_LABELS = {
  idle: "Idle",
  starting: "Initializing",
  researching: "Researching",
  writing: "Composing",
  done: "Complete",
  error: "Failed",
};

function setStatusChip(phase) {
  if (!statusChip || !statusChipLabel) return;
  const chipPhase =
    phase === "starting" || phase === "researching" || phase === "writing"
      ? "running"
      : phase === "done"
        ? "done"
        : phase === "error"
          ? "error"
          : "idle";
  statusChip.className = `status-chip status-${chipPhase}`;
  statusChipLabel.textContent = STATUS_LABELS[phase] || STATUS_LABELS.idle;
}

function setPhase(phase, detail) {
  const [label, fallback] = PHASE_COPY[phase] || [phase, detail || ""];
  phaseLabel.textContent = label;
  phaseDetail.textContent = detail || fallback;
  setStatusChip(phase);
}

function resetUi() {
  buffer = "";
  toolRows.clear();
  generatedImages.clear();
  generatingImages.clear();
  activityLog.innerHTML = "";
  insightsEl.innerHTML = "";
  insightsEl.hidden = true;
  emptyState.hidden = false;
  errorBox.hidden = true;
  errorBox.textContent = "";
  setStatusChip("idle");
  for (const li of insightTrack.querySelectorAll("li")) {
    li.classList.remove("active", "done");
    li.querySelector(".track-title").textContent = "Pending";
    li.querySelector(".track-state").textContent = "Waiting";
  }
}

function pushActivity(text, className = "") {
  const li = document.createElement("li");
  if (className) li.className = className;
  li.textContent = text;
  activityLog.prepend(li);
  while (activityLog.children.length > 40) {
    activityLog.lastElementChild.remove();
  }
}

function showError(message) {
  errorBox.hidden = false;
  errorBox.textContent = message;
  setPhase("error", message);
}

function parseInsights(markdown) {
  const parts = markdown.split(/^###\s+Insight\s+(\d+)\s*:\s*/im);
  const items = [];
  for (let i = 1; i < parts.length; i += 2) {
    const n = Number(parts[i]);
    const body = parts[i + 1] || "";
    const titleMatch = body.match(/^([^\n]+)/);
    const title = (titleMatch ? titleMatch[1] : `Insight ${n}`).trim();
    const takeaway =
      extractField(body, "In short") || extractField(body, "The twist");
    const how =
      extractField(body, "How it works") ||
      extractField(body, "The twist");
    const proof =
      extractField(body, "Proof") || extractField(body, "Why it's legit");
    const miss =
      extractField(body, "Easy to miss because") ||
      extractField(body, "Why you'd miss it");
    const image = extractImageUrl(body);
    items.push({
      n,
      title,
      takeaway,
      how,
      proof,
      miss,
      twist: takeaway,
      image,
      raw: body.trim(),
    });
  }
  return items;
}

function extractField(body, label) {
  const escaped = label.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const re = new RegExp(
    `\\*\\*${escaped}:\\*\\*\\s*([\\s\\S]*?)(?=\\n\\s*-\\s*\\*\\*|\\n###|$)`,
    "i"
  );
  const m = body.match(re);
  return m ? m[1].trim() : "";
}

function extractImageUrl(body) {
  const field = extractField(body, "Image");
  const fromField = firstHttpUrl(field);
  if (fromField) return fromField;

  const md = body.match(/!\[[^\]]*]\(\s*(https?:\/\/[^)\s]+)\s*\)/i);
  if (md) return sanitizeImageUrl(md[1]);

  return "";
}

function firstHttpUrl(text) {
  if (!text) return "";
  const cleaned = text.replace(/^none\b.*/i, "").trim();
  const m = cleaned.match(/https?:\/\/[^\s)<>"']+/i);
  return m ? sanitizeImageUrl(m[0]) : "";
}

function sanitizeImageUrl(url) {
  try {
    const parsed = new URL(url.replace(/[.,;:]+$/, ""));
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") return "";
    return parsed.href;
  } catch {
    return "";
  }
}

function renderInsights(markdown, { complete, container = insightsEl, trackEl = insightTrack } = {}) {
  const items = parseInsights(markdown);
  if (!items.length) return;

  if (container === insightsEl) {
    emptyState.hidden = true;
    insightsEl.hidden = false;
  }
  container.innerHTML = "";

  const highest = Math.max(...items.map((i) => i.n));

  for (const item of items) {
    container.appendChild(buildInsightCard(item, { complete, highest, isLive: container === insightsEl }));
  }

  if (trackEl && container === insightsEl) {
    for (const item of items) {
      const track = trackEl.querySelector(`li[data-n="${item.n}"]`);
      if (!track) continue;
      const isWriting = !complete && item.n === highest;
      track.classList.toggle("active", isWriting);
      track.classList.toggle("done", complete || item.n < highest || Boolean(item.miss));
      track.querySelector(".track-title").textContent = item.title.slice(0, 48);
      track.querySelector(".track-state").textContent = isWriting
        ? "In progress"
        : complete || item.n < highest
          ? "Verified"
          : "Drafting";
    }
  }

  if (!complete && items.length && container === insightsEl) {
    setPhase("writing", `Drafting insight ${highest} of 5`);
  }
}

function buildInsightCard(item, { complete = true, highest = item.n, isLive = false } = {}) {
  const card = document.createElement("article");
  card.className = "insight-card";
  card.dataset.insightN = String(item.n);
  card.style.setProperty("--card-i", String((item.n - 1) % 5));
  const isWriting = isLive && !complete && item.n === highest;
  if (isWriting) card.classList.add("writing", "cursor-blink");

  const resolvedImage = item.image || (isLive ? generatedImages.get(item.n) : "") || "";
  const needsAi =
    isLive &&
    complete &&
    !resolvedImage &&
    Boolean(item.title) &&
    Boolean(item.takeaway || item.how || item.proof);

  const howIsSameAsTakeaway =
    item.how && item.takeaway && item.how.trim() === item.takeaway.trim();

  const imageBlock = imageHtml(resolvedImage, item.title, {
    generating: needsAi || (isLive && generatingImages.has(item.n)),
    insightN: item.n,
    allowFallback: Boolean(item.image) && !(isLive && generatedImages.has(item.n)),
  });
  const hasImage = Boolean(imageBlock);
  const num = String(item.n).padStart(2, "0");

  card.innerHTML = `
    <span class="insight-watermark" aria-hidden="true">${num}</span>
    <header class="insight-card-header">
      <span class="insight-badge">Insight ${num}</span>
      <h2>${escapeHtml(item.title)}</h2>
    </header>
    <div class="insight-card-body">
      ${hasImage ? `<div class="insight-hero">${imageBlock}</div>` : ""}
      <div class="insight-prose">
        ${takeawayHtml(item.takeaway)}
        <div class="insight-details">
          ${howIsSameAsTakeaway ? "" : bodySectionHtml("How it works", item.how)}
          ${bodySectionHtml("Why you'd miss it", item.miss, { compact: true })}
        </div>
        ${proofHtml(item.proof)}
      </div>
    </div>
  `;

  if (needsAi) {
    requestAiImage(item);
  }

  return card;
}

function takeawayHtml(text) {
  if (!text) return "";
  const clean = stripLeadingBullets(text);
  return `
    <blockquote class="takeaway">
      <p>${inlineMarkdown(clean)}</p>
    </blockquote>
  `;
}

function bodySectionHtml(label, text, { compact = false } = {}) {
  if (!text) return "";
  const bullets = parseBulletLines(text);
  const body =
    bullets.length >= 2
      ? `<ul class="insight-bullets">${bullets
          .map((line) => `<li>${inlineMarkdown(line)}</li>`)
          .join("")}</ul>`
      : `<p>${inlineMarkdown(stripLeadingBullets(text))}</p>`;
  return `
    <div class="section${compact ? " is-compact" : ""}">
      <strong>${label}</strong>
      ${body}
    </div>
  `;
}

function proofHtml(text) {
  if (!text) return "";
  const links = parseSourceLinks(text);
  if (links.length) {
    return `
      <div class="section sources">
        <strong>Sources</strong>
        <ul class="source-list">
          ${links
            .map(
              (s) =>
                `<li><a href="${escapeHtml(s.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(s.title)}</a></li>`
            )
            .join("")}
        </ul>
      </div>
    `;
  }
  return bodySectionHtml("Sources", text);
}

function parseBulletLines(text) {
  const lines = text
    .split(/\n+/)
    .map((line) => line.trim())
    .filter(Boolean);
  const bullets = lines
    .map((line) => line.replace(/^[-*•]\s+/, "").trim())
    .filter(Boolean);
  const lookedLikeList = lines.filter((line) => /^[-*•]\s+/.test(line)).length;
  return lookedLikeList >= 2 ? bullets : [];
}

function stripLeadingBullets(text) {
  return text
    .split(/\n+/)
    .map((line) => line.replace(/^[-*•]\s+/, "").trim())
    .filter(Boolean)
    .join(" ");
}

function parseSourceLinks(text) {
  const links = [];
  const mdRe = /\[([^\]]+)\]\(\s*(https?:\/\/[^)\s]+)\s*\)/gi;
  let m;
  while ((m = mdRe.exec(text)) !== null) {
    links.push({ title: m[1].trim(), url: sanitizeImageUrl(m[2]) || m[2] });
  }
  if (links.length) return links.filter((s) => s.url);

  const bare = text.match(/https?:\/\/[^\s)<>"']+/gi) || [];
  return bare.map((url, i) => ({
    title: `Source ${i + 1}`,
    url: sanitizeImageUrl(url) || url,
  }));
}

function inlineMarkdown(text) {
  const placeholders = [];
  let escaped = escapeHtml(text);

  escaped = escaped.replace(
    /\[([^\]]+)\]\(\s*(https?:\/\/[^)\s]+)\s*\)/gi,
    (_, title, url) => {
      const i = placeholders.length;
      placeholders.push(
        `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${title}</a>`
      );
      return `\u0000L${i}\u0000`;
    }
  );

  escaped = escaped
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[^*])\*([^*\n]+)\*(?!\*)/g, "$1<em>$2</em>")
    .replace(/(https?:\/\/[^\s)<]+)/g, (url) => {
      const i = placeholders.length;
      placeholders.push(
        `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(url)}</a>`
      );
      return `\u0000L${i}\u0000`;
    });

  return escaped.replace(/\u0000L(\d+)\u0000/g, (_, i) => placeholders[Number(i)]);
}

function imageHtml(url, title, { generating = false, insightN = 0, allowFallback = false } = {}) {
  if (!url && generating) {
    return `
      <figure class="insight-image is-generating" data-insight-n="${insightN}">
        <div class="image-placeholder">Generating visual…</div>
      </figure>
    `;
  }
  if (!url) return "";
  const onerror = allowFallback
    ? `onAiImageFallback(this, ${Number(insightN)})`
    : `this.closest('figure').hidden = true`;
  return `
    <figure class="insight-image" data-insight-n="${insightN}">
      <img
        src="${escapeHtml(url)}"
        alt="${escapeHtml(title)} visual"
        loading="lazy"
        referrerpolicy="no-referrer"
        onerror="${onerror}"
      />
    </figure>
  `;
}

function onAiImageFallback(img, insightN) {
  const card = img.closest(".insight-card");
  if (!card) {
    img.closest("figure").hidden = true;
    return;
  }
  const title = card.querySelector("h2")?.textContent?.trim() || "";
  const twist =
    card.querySelector(".takeaway p")?.textContent?.trim() ||
    [...card.querySelectorAll(".section")]
      .find((s) => s.querySelector("strong")?.textContent === "How it works")
      ?.querySelector("p, li")
      ?.textContent?.trim() ||
    "";
  const figure = img.closest("figure");
  figure.classList.add("is-generating");
  figure.innerHTML = `<div class="image-placeholder">Generating visual…</div>`;
  requestAiImage({ n: insightN, title, twist, image: "" });
}

async function requestAiImage(item) {
  const n = item.n;
  if (!n || generatedImages.has(n) || generatingImages.has(n)) return;
  if (!item.title) return;

  generatingImages.add(n);
  pushActivity(`generating image · insight ${String(n).padStart(2, "0")}`);

  try {
    const response = await fetch("/api/insights/image", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title: item.title,
        twist: item.twist || item.takeaway || item.how || "",
        insight_n: n,
      }),
    });
    if (!response.ok) {
      let detail = `Image generation failed (${response.status})`;
      try {
        const body = await response.json();
        if (body.detail) detail = typeof body.detail === "string" ? body.detail : detail;
      } catch {
        /* ignore */
      }
      throw new Error(detail);
    }
    const data = await response.json();
    if (!data.url) throw new Error("No image URL returned");
    generatedImages.set(n, data.url);
    applyGeneratedImage(n, data.url, data.provider || "ai");
  } catch (err) {
    pushActivity(`image failed · insight ${String(n).padStart(2, "0")}: ${err.message}`);
    const figure = insightsEl.querySelector(
      `.insight-image[data-insight-n="${n}"]`
    );
    if (figure) figure.hidden = true;
  } finally {
    generatingImages.delete(n);
  }
}

function applyGeneratedImage(n, url, provider) {
  const figure = insightsEl.querySelector(`.insight-image[data-insight-n="${n}"]`);
  if (!figure) return;
  const title =
    figure.closest(".insight-card")?.querySelector("h2")?.textContent?.trim() ||
    `Insight ${n}`;
  figure.classList.remove("is-generating");
  figure.hidden = false;
  figure.innerHTML = `
    <img
      src="${escapeHtml(url)}"
      alt="${escapeHtml(title)} visual"
      loading="lazy"
      onerror="this.closest('figure').hidden = true"
    />
    <figcaption class="image-caption">AI visual · ${escapeHtml(provider)}</figcaption>
  `;
  pushActivity(`image ready · insight ${String(n).padStart(2, "0")} · ${provider}`);
}

window.onAiImageFallback = onAiImageFallback;

function escapeHtml(value) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function handleEvent(event) {
  switch (event.type) {
    case "phase":
      setPhase(event.phase, event.detail);
      pushActivity(event.detail || event.phase);
      break;
    case "started":
      pushActivity(`agent ${event.agent_id} · run ${event.run_id}`);
      break;
    case "tool": {
      const key = event.call_id || event.name;
      const label = `${event.name} · ${event.status}`;
      if (event.status === "running") {
        pushActivity(label, "tool-running");
        toolRows.set(key, true);
        setPhase("researching", `Using ${event.name}`);
      } else {
        pushActivity(label, "tool-done");
        toolRows.delete(key);
      }
      break;
    }
    case "thinking":
      pushActivity(`thinking: ${event.text}`);
      break;
    case "status":
      if (event.message) pushActivity(event.message);
      break;
    case "text":
      buffer += event.text;
      renderInsights(buffer, { complete: false });
      break;
    case "done":
      renderInsights(buffer, { complete: true });
      setPhase("done");
      if (event.prior_insights_skipped) {
        pushActivity(
          `saved to history · avoided ${event.prior_insights_skipped} past insights`
        );
      } else {
        pushActivity("saved to history");
      }
      pushActivity(`finished · ${event.status}`);
      loadHistory();
      finishRun(true);
      break;
    case "error":
      showError(event.message || "Unknown error");
      finishRun(false);
      break;
    default:
      break;
  }
}

function finishRun(ok) {
  scoutBtn.disabled = false;
  scoutBtn.classList.remove("running");
  if (btnSpinner) btnSpinner.hidden = true;
  scoutBtn.querySelector(".cta-label").textContent = ok
    ? "Scout again"
    : "Try again";
  if (ok) phaseLabel.textContent = "Edition complete";
  if (ok) setStatusChip("done");
}

async function startScout() {
  resetUi();
  scoutBtn.disabled = true;
  scoutBtn.classList.add("running");
  if (btnSpinner) btnSpinner.hidden = false;
  scoutBtn.querySelector(".cta-label").textContent = "Scouting…";
  phaseLabel.textContent = "Research in progress";
  setPhase("starting");

  let response;
  try {
    response = await fetch("/api/scout/stream");
  } catch {
    showError("Could not reach the scout server.");
    finishRun(false);
    return;
  }

  if (!response.ok) {
    let detail = `Stream failed (${response.status})`;
    try {
      const body = await response.json();
      if (body.detail) detail = body.detail;
    } catch {
      /* ignore */
    }
    showError(detail);
    finishRun(false);
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let pending = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    pending += decoder.decode(value, { stream: true });
    const chunks = pending.split("\n\n");
    pending = chunks.pop() || "";
    for (const chunk of chunks) {
      const lines = chunk.split("\n");
      let eventName = "message";
      const dataLines = [];
      for (const line of lines) {
        if (line.startsWith("event:")) eventName = line.slice(6).trim();
        else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
      }
      if (eventName === "end") {
        if (scoutBtn.disabled) finishRun(Boolean(buffer));
        return;
      }
      if (!dataLines.length) continue;
      try {
        handleEvent(JSON.parse(dataLines.join("\n")));
      } catch (err) {
        showError(`Bad event payload: ${err}`);
        finishRun(false);
        return;
      }
    }
  }

  if (scoutBtn.disabled) finishRun(Boolean(buffer));
}

scoutBtn.addEventListener("click", () => {
  if (scoutBtn.disabled) return;
  if (activeView !== "live") {
    switchView("live");
  }
  startScout();
});

function switchView(view) {
  activeView = view;
  for (const tab of viewTabs) {
    tab.classList.toggle("active", tab.dataset.view === view);
  }
  liveView.hidden = view !== "live";
  historyView.hidden = view !== "history";

  if (view === "live") {
    pageTitle.textContent = "Insight Scout";
    pageSubtitle.textContent =
      "Five verified insights from cross-checked research — streamed as they're written";
  } else {
    pageTitle.textContent = "Archive";
    pageSubtitle.textContent =
      "Past editions saved on this machine — open any run to read its insights again";
    loadHistory();
  }
}

for (const tab of viewTabs) {
  tab.addEventListener("click", () => {
    if (tab.dataset.view === activeView) return;
    switchView(tab.dataset.view);
  });
}

historyBack.addEventListener("click", () => {
  historyDetail.hidden = true;
  historyListWrap.hidden = historyRuns.length === 0;
  historyEmpty.hidden = historyRuns.length > 0;
});

function formatRunDate(iso) {
  if (!iso) return "Unknown date";
  try {
    return new Intl.DateTimeFormat(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(new Date(iso));
  } catch {
    return iso;
  }
}

function updateHistoryBadge() {
  if (!historyCount) return;
  if (historyRuns.length > 0) {
    historyCount.hidden = false;
    historyCount.textContent = String(historyRuns.length);
  } else {
    historyCount.hidden = true;
  }
}

function renderHistoryList() {
  historyList.innerHTML = "";
  historyEmpty.hidden = historyRuns.length > 0;
  historyListWrap.hidden = historyRuns.length === 0;
  historyDetail.hidden = true;

  for (const run of historyRuns) {
    const li = document.createElement("li");
    const topics = (run.titles || [])
      .slice(0, 3)
      .map((t) => `<li>${escapeHtml(t)}</li>`)
      .join("");
    const count = run.insight_count || 0;

    li.innerHTML = `
      <div class="archive-entry">
        <p class="archive-date">${escapeHtml(formatRunDate(run.created_at))}</p>
        <p class="archive-meta">${count} insight${count === 1 ? "" : "s"}</p>
        ${topics ? `<ul class="archive-topics">${topics}</ul>` : ""}
      </div>
      <button type="button" class="btn-text">Read edition</button>
    `;

    li.querySelector(".btn-text").addEventListener("click", () => openHistoryRun(run.id));
    historyList.appendChild(li);
  }
}

async function openHistoryRun(runId) {
  try {
    const response = await fetch(`/api/history/${encodeURIComponent(runId)}`);
    if (!response.ok) throw new Error(`Failed to load run (${response.status})`);
    const run = await response.json();
    historyListWrap.hidden = true;
    historyEmpty.hidden = true;
    historyDetail.hidden = false;
    historyDetailMeta.textContent = `${formatRunDate(run.created_at)} · ${(run.insights || []).length} insights`;
    historyInsights.innerHTML = "";
    for (const item of run.insights || []) {
      historyInsights.appendChild(buildInsightCard(item, { complete: true, isLive: false }));
    }
  } catch (err) {
    showError(err.message || "Could not load history run.");
  }
}

async function loadHistory() {
  try {
    const response = await fetch("/api/history");
    if (!response.ok) return;
    historyRuns = await response.json();
    updateHistoryBadge();
    if (activeView === "history") {
      renderHistoryList();
    }
  } catch {
    /* ignore */
  }
}

fetch("/api/health")
  .then((r) => r.json())
  .then((data) => {
    if (!data.api_key_configured) {
      showError("CURSOR_API_KEY is missing. Set it in .env, then restart the server.");
      scoutBtn.disabled = true;
    }
  })
  .catch(() => {});

loadHistory();
setStatusChip("idle");
