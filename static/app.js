const scoutBtn = document.getElementById("scoutBtn");
const phaseLabel = document.getElementById("phaseLabel");
const phaseDetail = document.getElementById("phaseDetail");
const activityLog = document.getElementById("activityLog");
const insightTrack = document.getElementById("insightTrack");
const emptyState = document.getElementById("emptyState");
const insightsEl = document.getElementById("insights");
const errorBox = document.getElementById("errorBox");

let buffer = "";
const toolRows = new Map();
const generatedImages = new Map(); // insight n -> url
const generatingImages = new Set();

const PHASE_COPY = {
  starting: ["Booting agent", "Opening local Cursor runtime"],
  researching: ["Cross-checking sources", "Redundant verification in progress"],
  writing: ["Composing insights", "Turning verified finds into astonishments"],
  done: ["Scout complete", "Five dual-sourced insights are ready"],
  error: ["Scout interrupted", "Something failed — check the message below"],
};

function setPhase(phase, detail) {
  const [label, fallback] = PHASE_COPY[phase] || [phase, detail || ""];
  phaseLabel.textContent = label;
  phaseDetail.textContent = detail || fallback;
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
  for (const li of insightTrack.querySelectorAll("li")) {
    li.classList.remove("active", "done");
    li.querySelector("em").textContent = "Waiting";
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

function linkify(text) {
  const escaped = text
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
  return escaped.replace(
    /(https?:\/\/[^\s)]+)/g,
    '<a href="$1" target="_blank" rel="noopener noreferrer">$1</a>'
  );
}

function parseInsights(markdown) {
  const parts = markdown.split(/^###\s+Insight\s+(\d+)\s*:\s*/im);
  const items = [];
  for (let i = 1; i < parts.length; i += 2) {
    const n = Number(parts[i]);
    const body = parts[i + 1] || "";
    const titleMatch = body.match(/^([^\n]+)/);
    const title = (titleMatch ? titleMatch[1] : `Insight ${n}`).trim();
    const twist = extractField(body, "The twist");
    const legit = extractField(body, "Why it's legit");
    const miss = extractField(body, "Why you'd miss it");
    const image = extractImageUrl(body);
    items.push({ n, title, twist, legit, miss, image, raw: body.trim() });
  }
  return items;
}

function extractField(body, label) {
  const re = new RegExp(
    `\\*\\*${label}:\\*\\*\\s*([\\s\\S]*?)(?=\\n\\s*-\\s*\\*\\*|\\n###|$)`,
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

function renderInsights(markdown, { complete }) {
  const items = parseInsights(markdown);
  if (!items.length) return;

  emptyState.hidden = true;
  insightsEl.hidden = false;
  insightsEl.innerHTML = "";

  const highest = Math.max(...items.map((i) => i.n));

  for (const item of items) {
    const card = document.createElement("article");
    card.className = "insight-card";
    card.dataset.insightN = String(item.n);
    const isWriting = !complete && item.n === highest;
    if (isWriting) card.classList.add("writing", "cursor-blink");

    const resolvedImage = item.image || generatedImages.get(item.n) || "";
    const needsAi =
      complete &&
      !resolvedImage &&
      Boolean(item.title) &&
      Boolean(item.twist || item.legit);

    card.innerHTML = `
      <p class="num">Insight ${String(item.n).padStart(2, "0")}</p>
      <h2>${escapeHtml(item.title)}</h2>
      ${imageHtml(resolvedImage, item.title, {
        generating: needsAi || generatingImages.has(item.n),
        insightN: item.n,
        allowFallback: Boolean(item.image) && !generatedImages.has(item.n),
      })}
      ${sectionHtml("The twist", item.twist)}
      ${sectionHtml("Why it's legit", item.legit)}
      ${sectionHtml("Why you'd miss it", item.miss)}
    `;
    insightsEl.appendChild(card);

    const track = insightTrack.querySelector(`li[data-n="${item.n}"]`);
    if (track) {
      track.classList.toggle("active", isWriting);
      track.classList.toggle("done", complete || item.n < highest || Boolean(item.miss));
      track.querySelector("em").textContent = item.title.slice(0, 42);
    }

    if (needsAi) {
      requestAiImage(item);
    }
  }

  if (!complete && items.length) {
    setPhase("writing", `Drafting insight ${highest} of 5`);
  }
}

function sectionHtml(label, text) {
  if (!text) return "";
  return `
    <div class="section">
      <strong>${label}</strong>
      <p>${linkify(text)}</p>
    </div>
  `;
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
    [...card.querySelectorAll(".section")]
      .find((s) => s.querySelector("strong")?.textContent === "The twist")
      ?.querySelector("p")?.textContent?.trim() || "";
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
        twist: item.twist || "",
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
      pushActivity(`finished · ${event.status}`);
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
  scoutBtn.querySelector(".cta-label").textContent = ok
    ? "Scout again"
    : "Try again";
}

async function startScout() {
  resetUi();
  scoutBtn.disabled = true;
  scoutBtn.classList.add("running");
  scoutBtn.querySelector(".cta-label").textContent = "Scouting…";
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
  startScout();
});

fetch("/api/health")
  .then((r) => r.json())
  .then((data) => {
    if (!data.api_key_configured) {
      showError("CURSOR_API_KEY is missing. Set it in .env, then restart the server.");
      scoutBtn.disabled = true;
    }
  })
  .catch(() => {});
