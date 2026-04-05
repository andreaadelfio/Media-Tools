const state = {
  tools: [],
  files: [],
  selectedFiles: new Set(),
  activeTool: null,
  thumbnails: new Map(),
  thumbnailJobs: 0,
  toolsCollapsed: false,
  currentRoot: "",
  videoUi: {
    selecting: false,
    dragging: false,
    startX: 0,
    startY: 0,
    currentX: 0,
    currentY: 0,
    roi: null,
  },
};

const THUMBNAIL_BATCH_SIZE = 12;
const VIDEO_TOOL_IDS = new Set(["video_extract_frames", "video_make_gif"]);

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(payload.detail || response.statusText);
  }
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    return response.json();
  }
  return response.text();
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function isLikelyPath(value) {
  if (typeof value !== "string") return false;
  return /^[A-Za-z]:\\/.test(value) || value.includes("\\") || value.includes("/");
}

function normalizePath(value) {
  return String(value || "").replaceAll("/", "\\").toLowerCase();
}

function isPathWithinRoot(pathValue) {
  if (!state.currentRoot || typeof pathValue !== "string") {
    return false;
  }
  const root = normalizePath(state.currentRoot);
  const target = normalizePath(pathValue);
  return target.startsWith(root);
}

function looksLikeDirectory(pathValue) {
  if (typeof pathValue !== "string") {
    return false;
  }
  return !/\.[A-Za-z0-9]{1,6}$/.test(pathValue.trim());
}

function fileLink(pathValue) {
  const href = `/api/file?path=${encodeURIComponent(pathValue)}`;
  return `<a href="${href}" target="_blank" rel="noreferrer"><code>${escapeHtml(pathValue)}</code></a>`;
}

function renderResultValue(value, keyName = "") {
  if (Array.isArray(value)) {
    if (!value.length) {
      return `<div class="muted">[]</div>`;
    }
    return `<div class="result-grid">${value.map((item) => `<div class="result-row">${renderResultValue(item, keyName)}</div>`).join("")}</div>`;
  }

  if (value && typeof value === "object") {
    return `<div class="result-grid">${Object.entries(value).map(([key, entry]) => `
      <div class="result-row">
        <strong>${escapeHtml(key)}</strong><br>
        ${renderResultValue(entry, key)}
      </div>
    `).join("")}</div>`;
  }

  if (isLikelyPath(value) && isPathWithinRoot(value) && !looksLikeDirectory(value)) {
    return fileLink(value);
  }

  if (isLikelyPath(value)) {
    return `<code>${escapeHtml(value)}</code>`;
  }

  return `<code>${escapeHtml(value)}</code>`;
}

function renderSessionBanner(rootPath) {
  const banner = document.getElementById("session-banner");
  banner.textContent = rootPath ? rootPath : "Nessuna cartella selezionata.";
  banner.classList.toggle("muted", !rootPath);
}

function renderFileFilterBanner() {
  const banner = document.getElementById("file-filter-banner");
  if (!state.activeTool) {
    banner.textContent = "Seleziona un tool per filtrare i file compatibili.";
    banner.classList.add("muted");
    return;
  }
  const allowed = (state.activeTool.allowed_types || []).length
    ? state.activeTool.allowed_types.join(", ")
    : "nessun file richiesto";
  const browserReady = state.activeTool.browser_ready !== false;
  banner.textContent = browserReady
    ? `Tool attivo: ${state.activeTool.name} · tipi ammessi: ${allowed}`
    : `Tool attivo: ${state.activeTool.name} · presente nel progetto originale ma non ancora disponibile dalla UI browser`;
  banner.classList.toggle("muted", false);
}

function iconForFile(type) {
  if (type === "audio") return "AUD";
  if (type === "video") return "VID";
  if (type === "image") return "IMG";
  return "FILE";
}

function filteredFiles() {
  if (!state.activeTool || !(state.activeTool.allowed_types || []).length) {
    return state.activeTool?.browser_ready === false ? [] : state.files;
  }
  const allowed = new Set(state.activeTool.allowed_types);
  return state.files.filter((file) => allowed.has(file.type));
}

function sanitizeSelectionForActiveTool() {
  const allowedPaths = new Set(filteredFiles().map((file) => file.relative_path));
  state.selectedFiles = new Set([...state.selectedFiles].filter((path) => allowedPaths.has(path)));
}

function renderFiles() {
  const container = document.getElementById("file-list");
  container.innerHTML = "";
  const files = filteredFiles();
  if (!files.length) {
    container.innerHTML = `<div class="muted">Nessun file compatibile con il tool selezionato.</div>`;
    return;
  }

  files.forEach((file) => {
    const wrapper = document.createElement("label");
    wrapper.className = "file-item";
    const thumb = state.thumbnails.get(file.relative_path);
    const preview = thumb
      ? `<img class="file-thumb" src="${thumb}" alt="">`
      : `<div class="file-icon file-icon-${file.type}">${iconForFile(file.type)}</div>`;
    wrapper.innerHTML = `
      <input type="checkbox" ${state.selectedFiles.has(file.relative_path) ? "checked" : ""}>
      ${preview}
      <div class="file-copy">
        <div><strong>${file.name}</strong></div>
        <div class="file-meta">${file.type} · ${file.relative_path}</div>
      </div>
    `;
    wrapper.querySelector("input").addEventListener("change", (event) => {
      if (event.target.checked) {
        state.selectedFiles.add(file.relative_path);
      } else {
        state.selectedFiles.delete(file.relative_path);
      }
      syncVideoFileSelection();
    });
    container.appendChild(wrapper);
  });
}

function renderTools() {
  const container = document.getElementById("tool-list");
  container.innerHTML = "";
  state.tools.forEach((tool) => {
    const card = document.createElement("button");
    card.type = "button";
    card.className = `tool-card ${state.activeTool?.id === tool.id ? "active" : ""} ${tool.browser_ready === false ? "is-disabled" : ""}`;
    card.innerHTML = `
      <div class="tool-project">${tool.project || "Suite"}</div>
      <div><strong>${tool.name}</strong></div>
      <div class="tool-meta">${tool.category} · ${tool.description}</div>
    `;
    card.addEventListener("click", () => {
      state.activeTool = tool;
      sanitizeSelectionForActiveTool();
      renderTools();
      renderFileFilterBanner();
      renderFiles();
      renderActiveTool();
    });
    container.appendChild(card);
  });
}

function genericFieldMarkup(field) {
  if (field.type === "file") {
    const options = filteredFiles().map((file) => {
      const selected = state.selectedFiles.has(file.relative_path) ? "selected" : "";
      return `<option value="${file.relative_path}" ${selected}>${file.relative_path}</option>`;
    }).join("");
    return `<select name="${field.name}"><option value="">Seleziona un file</option>${options}</select>`;
  }
  if (field.type === "boolean") {
    return `<input name="${field.name}" type="checkbox" ${field.default ? "checked" : ""}>`;
  }
  if (field.type === "select") {
    const options = (field.options || []).map((option) => {
      const selected = option === field.default ? "selected" : "";
      return `<option value="${option}" ${selected}>${option}</option>`;
    }).join("");
    return `<select name="${field.name}">${options}</select>`;
  }
  const value = field.default ?? "";
  const placeholder = field.placeholder || "";
  return `<input name="${field.name}" type="${field.type === "number" ? "number" : "text"}" value="${value}" placeholder="${placeholder}">`;
}

function selectedFileOfType(type) {
  for (const relativePath of state.selectedFiles) {
    const file = state.files.find((entry) => entry.relative_path === relativePath);
    if (file?.type === type) {
      return relativePath;
    }
  }
  return "";
}

function videoOptionsMarkup() {
  return filteredFiles()
    .filter((file) => file.type === "video")
    .map((file) => {
      const selected = file.relative_path === selectedFileOfType("video") ? "selected" : "";
      return `<option value="${file.relative_path}" ${selected}>${file.relative_path}</option>`;
    })
    .join("");
}

function renderVideoToolForm(tool) {
  return `
    <div class="video-tool-shell">
      <div class="video-config-grid">
        <label class="field field-wide">
          <span>video_path</span>
          <select name="video_path" id="video-path-select">
            <option value="">Seleziona un video</option>
            ${videoOptionsMarkup()}
          </select>
        </label>
        <label class="field">
          <span>start_time</span>
          <input name="start_time" id="video-start-time" type="number" value="0" min="0" step="0.01">
        </label>
        <label class="field">
          <span>end_time</span>
          <input name="end_time" id="video-end-time" type="number" value="3" min="0" step="0.01">
        </label>
      </div>
      <div class="video-stage">
        <div class="video-stage-head">
          <div id="video-info-bar" class="video-info-bar">Seleziona un video per iniziare.</div>
          <div class="video-stage-actions">
            <button type="button" class="tool-secondary-button" id="video-set-start">Usa tempo attuale come start</button>
            <button type="button" class="tool-secondary-button" id="video-set-end">Usa tempo attuale come end</button>
          </div>
        </div>
        <div class="video-preview-shell">
          <div class="video-player-wrap" id="video-player-wrap">
            <video id="video-player" class="video-player" controls preload="metadata"></video>
            <canvas id="video-roi-canvas" class="video-roi-canvas"></canvas>
          </div>
        </div>
        <div class="video-toolbar">
          <button type="button" class="tool-secondary-button" id="video-jump-start">Inizio</button>
          <button type="button" class="tool-secondary-button" id="video-backward">-5s</button>
          <button type="button" class="tool-secondary-button" id="video-forward">+5s</button>
          <button type="button" class="tool-secondary-button" id="video-jump-end">Fine</button>
          <button type="button" class="tool-secondary-button" id="video-roi-toggle">Seleziona ROI</button>
          <button type="button" class="tool-secondary-button" id="video-roi-clear">Pulisci ROI</button>
        </div>
        <div id="video-roi-status" class="video-roi-status">ROI: full frame</div>
        <input type="hidden" name="roi" id="video-roi-value" value="">
      </div>
      <div class="video-run-note">${tool.project} · UI dedicata ispirata al tool originale.</div>
    </div>
  `;
}

function renderActiveTool() {
  const box = document.getElementById("active-tool");
  const form = document.getElementById("tool-form");
  const button = document.getElementById("run-tool");
  form.innerHTML = "";

  if (!state.activeTool) {
    box.textContent = "Seleziona uno strumento.";
    box.classList.add("muted");
    button.disabled = true;
    button.textContent = "Esegui endpoint";
    return;
  }

  box.innerHTML = `
    <strong>${state.activeTool.name}</strong>
    <div class="tool-meta">${state.activeTool.project || "Suite"} · ${state.activeTool.description}</div>
  `;
  box.classList.remove("muted");

  if (state.activeTool.browser_ready === false) {
    form.innerHTML = `
      <div class="unavailable-tool-box">
        <strong>${state.activeTool.name}</strong><br>
        Questo endpoint esiste ancora nel progetto originale, ma non e' ancora stato portato nella UI browser.
      </div>
    `;
    button.disabled = true;
    button.textContent = "Non disponibile nel browser";
    return;
  }

  if (VIDEO_TOOL_IDS.has(state.activeTool.id)) {
    form.innerHTML = renderVideoToolForm(state.activeTool);
    setupVideoToolUi();
    button.textContent = state.activeTool.id === "video_make_gif" ? "Crea GIF" : "Estrai frames";
  } else {
    state.activeTool.params.forEach((field) => {
      const wrapper = document.createElement("label");
      wrapper.className = "field";
      wrapper.innerHTML = `<span>${field.name}</span>${genericFieldMarkup(field)}`;
      form.appendChild(wrapper);
    });
    button.textContent = "Esegui endpoint";
  }

  button.disabled = false;
}

function collectParams() {
  const params = {};
  const form = document.getElementById("tool-form");
  new FormData(form).forEach((value, key) => {
    params[key] = value;
  });
  form.querySelectorAll('input[type="checkbox"]').forEach((checkbox) => {
    params[checkbox.name] = checkbox.checked;
  });
  return params;
}

async function loadSession() {
  const session = await api("/api/session");
  state.currentRoot = session.root_path || "";
  renderSessionBanner(session.root_path);
  if (session.root_path) {
    document.getElementById("root-path").value = session.root_path;
    await loadFiles();
  }
}

async function loadTools() {
  state.tools = await api("/api/tools");
  if (!state.activeTool && state.tools.length) {
    state.activeTool = state.tools[0];
  }
  renderTools();
  renderFileFilterBanner();
  renderActiveTool();
}

async function fetchThumbnail(file) {
  const version = `${file.size || 0}`;
  state.thumbnails.set(file.relative_path, `/api/media/thumbnail?path=${encodeURIComponent(file.relative_path)}&v=${encodeURIComponent(version)}`);
}

function scheduleThumbnailLoading() {
  const currentJob = ++state.thumbnailJobs;
  const previewables = filteredFiles()
    .filter((file) => (file.type === "image" || file.type === "video") && !state.thumbnails.has(file.relative_path))
    .slice(0, 120);

  let index = 0;

  async function runNextBatch() {
    if (currentJob !== state.thumbnailJobs || index >= previewables.length) {
      return;
    }
    const batch = previewables.slice(index, index + THUMBNAIL_BATCH_SIZE);
    index += THUMBNAIL_BATCH_SIZE;
    batch.forEach(fetchThumbnail);
    if (currentJob === state.thumbnailJobs) {
      renderFiles();
      window.setTimeout(runNextBatch, 30);
    }
  }

  window.setTimeout(runNextBatch, 0);
}

async function loadFiles() {
  state.files = await api("/api/files");
  sanitizeSelectionForActiveTool();
  state.thumbnails.clear();
  renderFileFilterBanner();
  renderFiles();
  scheduleThumbnailLoading();
  if (state.activeTool) {
    renderActiveTool();
  }
}

function syncVideoFileSelection() {
  if (!state.activeTool || !VIDEO_TOOL_IDS.has(state.activeTool.id)) {
    return;
  }
  const select = document.getElementById("video-path-select");
  if (!select) {
    return;
  }
  const selectedVideo = selectedFileOfType("video");
  if (selectedVideo) {
    select.value = selectedVideo;
    loadVideoIntoTool();
  }
}

function setupVideoToolUi() {
  const select = document.getElementById("video-path-select");
  const player = document.getElementById("video-player");
  const startInput = document.getElementById("video-start-time");
  const endInput = document.getElementById("video-end-time");
  const roiValue = document.getElementById("video-roi-value");
  const roiCanvas = document.getElementById("video-roi-canvas");

  if (!select || !player || !startInput || !endInput || !roiValue || !roiCanvas) {
    return;
  }

  state.videoUi = {
    selecting: false,
    dragging: false,
    startX: 0,
    startY: 0,
    currentX: 0,
    currentY: 0,
    roi: null,
  };

  select.addEventListener("change", loadVideoIntoTool);
  player.addEventListener("loadedmetadata", () => {
    endInput.max = player.duration.toFixed(3);
    if (!endInput.value || Number(endInput.value) <= 0 || Number(endInput.value) > player.duration) {
      endInput.value = player.duration.toFixed(2);
    }
    updateVideoInfoBar();
    resizeRoiCanvas();
  });
  player.addEventListener("timeupdate", updateVideoInfoBar);
  player.addEventListener("loadeddata", resizeRoiCanvas);
  window.onresize = resizeRoiCanvas;

  document.getElementById("video-set-start").addEventListener("click", () => {
    startInput.value = player.currentTime.toFixed(2);
  });
  document.getElementById("video-set-end").addEventListener("click", () => {
    endInput.value = player.currentTime.toFixed(2);
  });
  document.getElementById("video-jump-start").addEventListener("click", () => {
    player.currentTime = 0;
  });
  document.getElementById("video-backward").addEventListener("click", () => {
    player.currentTime = Math.max(0, player.currentTime - 5);
  });
  document.getElementById("video-forward").addEventListener("click", () => {
    player.currentTime = Math.min(player.duration || player.currentTime + 5, player.currentTime + 5);
  });
  document.getElementById("video-jump-end").addEventListener("click", () => {
    if (player.duration) {
      player.currentTime = player.duration;
    }
  });
  document.getElementById("video-roi-toggle").addEventListener("click", toggleRoiSelectionMode);
  document.getElementById("video-roi-clear").addEventListener("click", clearVideoRoi);

  roiCanvas.addEventListener("mousedown", beginRoiDrag);
  roiCanvas.addEventListener("mousemove", updateRoiDrag);
  roiCanvas.addEventListener("mouseup", finishRoiDrag);
  roiCanvas.addEventListener("mouseleave", finishRoiDrag);

  if (select.value) {
    loadVideoIntoTool();
  } else {
    const selectedVideo = selectedFileOfType("video");
    if (selectedVideo) {
      select.value = selectedVideo;
      loadVideoIntoTool();
    }
  }
}

function updateVideoInfoBar() {
  const player = document.getElementById("video-player");
  const bar = document.getElementById("video-info-bar");
  if (!player || !bar) {
    return;
  }
  const duration = Number.isFinite(player.duration) ? player.duration.toFixed(2) : "--";
  const width = player.videoWidth || "--";
  const height = player.videoHeight || "--";
  bar.textContent = `Tempo ${player.currentTime.toFixed(2)}s · Durata ${duration}s · ${width}x${height}`;
}

function resizeRoiCanvas() {
  const player = document.getElementById("video-player");
  const canvas = document.getElementById("video-roi-canvas");
  if (!player || !canvas) {
    return;
  }
  canvas.width = player.clientWidth;
  canvas.height = player.clientHeight;
  drawRoiOverlay();
}

function toggleRoiSelectionMode() {
  state.videoUi.selecting = !state.videoUi.selecting;
  const button = document.getElementById("video-roi-toggle");
  const canvas = document.getElementById("video-roi-canvas");
  if (button) {
    button.textContent = state.videoUi.selecting ? "ROI attiva" : "Seleziona ROI";
  }
  if (canvas) {
    canvas.classList.toggle("is-active", state.videoUi.selecting);
  }
}

function clearVideoRoi() {
  state.videoUi.roi = null;
  state.videoUi.dragging = false;
  state.videoUi.selecting = false;
  const roiValue = document.getElementById("video-roi-value");
  const roiStatus = document.getElementById("video-roi-status");
  const button = document.getElementById("video-roi-toggle");
  const canvas = document.getElementById("video-roi-canvas");
  if (roiValue) {
    roiValue.value = "";
  }
  if (roiStatus) {
    roiStatus.textContent = "ROI: full frame";
  }
  if (button) {
    button.textContent = "Seleziona ROI";
  }
  if (canvas) {
    canvas.classList.remove("is-active");
  }
  drawRoiOverlay();
}

function beginRoiDrag(event) {
  if (!state.videoUi.selecting) {
    return;
  }
  const canvas = event.currentTarget;
  const rect = canvas.getBoundingClientRect();
  state.videoUi.dragging = true;
  state.videoUi.startX = event.clientX - rect.left;
  state.videoUi.startY = event.clientY - rect.top;
  state.videoUi.currentX = state.videoUi.startX;
  state.videoUi.currentY = state.videoUi.startY;
  drawRoiOverlay();
}

function updateRoiDrag(event) {
  if (!state.videoUi.selecting || !state.videoUi.dragging) {
    return;
  }
  const canvas = event.currentTarget;
  const rect = canvas.getBoundingClientRect();
  state.videoUi.currentX = event.clientX - rect.left;
  state.videoUi.currentY = event.clientY - rect.top;
  drawRoiOverlay();
}

function finishRoiDrag() {
  if (!state.videoUi.selecting || !state.videoUi.dragging) {
    return;
  }
  state.videoUi.dragging = false;
  const player = document.getElementById("video-player");
  const canvas = document.getElementById("video-roi-canvas");
  const roiStatus = document.getElementById("video-roi-status");
  const roiValue = document.getElementById("video-roi-value");
  if (!player || !canvas || !roiStatus || !roiValue) {
    return;
  }

  const x = Math.min(state.videoUi.startX, state.videoUi.currentX);
  const y = Math.min(state.videoUi.startY, state.videoUi.currentY);
  const width = Math.abs(state.videoUi.currentX - state.videoUi.startX);
  const height = Math.abs(state.videoUi.currentY - state.videoUi.startY);
  if (width < 8 || height < 8 || !player.videoWidth || !player.videoHeight) {
    drawRoiOverlay();
    return;
  }

  const scaleX = player.videoWidth / canvas.width;
  const scaleY = player.videoHeight / canvas.height;
  const roi = [
    Math.round(x * scaleX),
    Math.round(y * scaleY),
    Math.round(width * scaleX),
    Math.round(height * scaleY),
  ];
  state.videoUi.roi = roi;
  state.videoUi.selecting = false;
  roiValue.value = roi.join(",");
  roiStatus.textContent = `ROI: ${roi[2]}x${roi[3]} @ ${roi[0]},${roi[1]}`;
  document.getElementById("video-roi-toggle").textContent = "Seleziona ROI";
  canvas.classList.remove("is-active");
  drawRoiOverlay();
}

function drawRoiOverlay() {
  const canvas = document.getElementById("video-roi-canvas");
  if (!canvas) {
    return;
  }
  const context = canvas.getContext("2d");
  context.clearRect(0, 0, canvas.width, canvas.height);
  context.lineWidth = 2;
  context.strokeStyle = "#7fd0b4";
  context.fillStyle = "rgba(127, 208, 180, 0.18)";

  if (state.videoUi.dragging) {
    const x = Math.min(state.videoUi.startX, state.videoUi.currentX);
    const y = Math.min(state.videoUi.startY, state.videoUi.currentY);
    const width = Math.abs(state.videoUi.currentX - state.videoUi.startX);
    const height = Math.abs(state.videoUi.currentY - state.videoUi.startY);
    context.fillRect(x, y, width, height);
    context.strokeRect(x, y, width, height);
    return;
  }

  if (!state.videoUi.roi) {
    return;
  }
  const player = document.getElementById("video-player");
  if (!player || !player.videoWidth || !player.videoHeight) {
    return;
  }
  const scaleX = canvas.width / player.videoWidth;
  const scaleY = canvas.height / player.videoHeight;
  const [x, y, width, height] = state.videoUi.roi;
  context.fillRect(x * scaleX, y * scaleY, width * scaleX, height * scaleY);
  context.strokeRect(x * scaleX, y * scaleY, width * scaleX, height * scaleY);
}

function loadVideoIntoTool() {
  const select = document.getElementById("video-path-select");
  const player = document.getElementById("video-player");
  const infoBar = document.getElementById("video-info-bar");
  if (!select || !player || !infoBar) {
    return;
  }
  const videoPath = select.value;
  clearVideoRoi();
  if (!videoPath) {
    player.removeAttribute("src");
    player.load();
    infoBar.textContent = "Seleziona un video per iniziare.";
    return;
  }
  player.src = `/api/file?path=${encodeURIComponent(videoPath)}`;
  player.load();
  infoBar.textContent = `Carico ${videoPath}...`;
}

async function runActiveTool() {
  if (!state.activeTool || state.activeTool.browser_ready === false) {
    return;
  }
  const resultBox = document.getElementById("result-box");
  resultBox.innerHTML = "Esecuzione in corso...";
  try {
    const payload = {
      selected_files: Array.from(state.selectedFiles),
      params: collectParams(),
    };
    const result = await api(`/api/run/${state.activeTool.id}`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    resultBox.innerHTML = renderResultValue(result);
  } catch (error) {
    resultBox.innerHTML = `<code>${escapeHtml(error.message)}</code>`;
  }
}

function toggleToolsSidebar() {
  state.toolsCollapsed = !state.toolsCollapsed;
  document.body.classList.toggle("tools-collapsed", state.toolsCollapsed);
  document.getElementById("toggle-tools").textContent = state.toolsCollapsed ? "Apri" : "Chiudi";
}

document.getElementById("root-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const rootPath = document.getElementById("root-path").value.trim();
  try {
    await api("/api/session/root", {
      method: "POST",
      body: JSON.stringify({ root_path: rootPath }),
    });
    state.selectedFiles.clear();
    await loadSession();
  } catch (error) {
    document.getElementById("result-box").innerHTML = `<code>${escapeHtml(error.message)}</code>`;
  }
});

document.getElementById("pick-root").addEventListener("click", async () => {
  try {
    const result = await api("/api/session/pick-root", {
      method: "POST",
      body: JSON.stringify({}),
    });
    document.getElementById("root-path").value = result.root_path;
    state.selectedFiles.clear();
    await loadSession();
  } catch (error) {
    document.getElementById("result-box").innerHTML = `<code>${escapeHtml(error.message)}</code>`;
  }
});

document.getElementById("refresh-files").addEventListener("click", async () => {
  try {
    await loadFiles();
  } catch (error) {
    document.getElementById("result-box").innerHTML = `<code>${escapeHtml(error.message)}</code>`;
  }
});

document.getElementById("toggle-tools").addEventListener("click", toggleToolsSidebar);
document.getElementById("run-tool").addEventListener("click", runActiveTool);

loadTools();
loadSession();
