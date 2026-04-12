const state = {
  tools: [],
  files: [],
  selectedFiles: new Set(),
  activeTool: null,
  thumbnails: new Map(),
  thumbnailJobs: 0,
  toolsCollapsed: false,
  openProjects: new Set(),
  currentRoot: "",
  stereoUi: { leftPath: "", rightPath: "", leftPoint: "", rightPoint: "" },
  videoUi: { selecting: false, dragging: false, startX: 0, startY: 0, currentX: 0, currentY: 0, roi: null },
  liveLogTimer: null,
};

const THUMBNAIL_BATCH_SIZE = 12;
const VIDEO_TOOL_IDS = new Set(["video_extract_frames", "video_make_gif"]);

async function api(path, options = {}) {
  const response = await fetch(path, { headers: { "Content-Type": "application/json" }, ...options });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(payload.detail || response.statusText);
  }
  const contentType = response.headers.get("content-type") || "";
  return contentType.includes("application/json") ? response.json() : response.text();
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function normalizePath(value) {
  return String(value || "").replaceAll("/", "\\").toLowerCase();
}

function isWithinRoot(value) {
  return Boolean(state.currentRoot) && typeof value === "string" && normalizePath(value).startsWith(normalizePath(state.currentRoot));
}

function looksLikePath(value) {
  return typeof value === "string" && (/^[A-Za-z]:\\/.test(value) || value.includes("\\") || value.includes("/"));
}

function looksLikeDirectory(value) {
  return typeof value === "string" && !/\.[A-Za-z0-9]{1,6}$/.test(value.trim());
}

function selectedFileOfType(type) {
  for (const relativePath of state.selectedFiles) {
    const file = state.files.find((entry) => entry.relative_path === relativePath);
    if (file?.type === type) return relativePath;
  }
  return "";
}

function filteredFiles() {
  if (!state.activeTool) return state.files;
  if (!(state.activeTool.allowed_types || []).length) return state.activeTool.browser_ready === false ? [] : state.files;
  const allowed = new Set(state.activeTool.allowed_types);
  return state.files.filter((file) => allowed.has(file.type));
}

function sanitizeSelection() {
  const allowed = new Set(filteredFiles().map((file) => file.relative_path));
  state.selectedFiles = new Set([...state.selectedFiles].filter((path) => allowed.has(path)));
}

function setResult(html) {
  document.getElementById("result-box").innerHTML = html;
}

function iconForFile(type) {
  if (type === "audio") return "AUD";
  if (type === "video") return "VID";
  if (type === "image") return "IMG";
  return "FILE";
}

function renderResultValue(value) {
  if (Array.isArray(value)) {
    if (!value.length) return '<div class="muted">[]</div>';
    return `<div class="result-grid">${value.map((item) => `<div class="result-row">${renderResultValue(item)}</div>`).join("")}</div>`;
  }
  if (value && typeof value === "object") {
    return `<div class="result-grid">${Object.entries(value).map(([key, entry]) => `<div class="result-row"><strong>${escapeHtml(key)}</strong><br>${renderResultValue(entry)}</div>`).join("")}</div>`;
  }
  if (looksLikePath(value) && isWithinRoot(value) && !looksLikeDirectory(value)) {
    return `<a href="/api/file?path=${encodeURIComponent(value)}" target="_blank" rel="noreferrer"><code>${escapeHtml(value)}</code></a>`;
  }
  return `<code>${escapeHtml(value)}</code>`;
}

function renderSessionBanner(rootPath) {
  const banner = document.getElementById("session-banner");
  banner.textContent = rootPath || "Nessuna cartella selezionata.";
  banner.classList.toggle("muted", !rootPath);
}

function renderFileFilterBanner() {
  const banner = document.getElementById("file-filter-banner");
  if (!state.activeTool) {
    banner.textContent = "Seleziona un tool per filtrare i file compatibili.";
    banner.classList.add("muted");
    return;
  }
  const allowed = (state.activeTool.allowed_types || []).length ? state.activeTool.allowed_types.join(", ") : "nessun file richiesto";
  banner.textContent = `Tool attivo: ${state.activeTool.name} | tipi ammessi: ${allowed}`;
  banner.classList.remove("muted");
}

function renderFiles() {
  const container = document.getElementById("file-list");
  container.innerHTML = "";
  const files = filteredFiles();
  if (!files.length) {
    container.innerHTML = '<div class="muted">Nessun file compatibile con il tool selezionato.</div>';
    return;
  }
  for (const file of files) {
    const row = document.createElement("label");
    row.className = "file-item";
    const thumbnail = state.thumbnails.get(file.relative_path);
    row.innerHTML = `
      <input class="file-check" type="checkbox" ${state.selectedFiles.has(file.relative_path) ? "checked" : ""}>
      <div class="file-preview">
        ${thumbnail ? `<img class="file-thumb" src="${thumbnail}" alt="${escapeHtml(file.name)}">` : `<div class="file-icon file-icon-${file.type}">${iconForFile(file.type)}</div>`}
      </div>
      <div class="file-copy">
        <strong>${escapeHtml(file.name)}</strong>
        <div class="file-meta">${escapeHtml(file.type)} | ${escapeHtml(file.relative_path)}</div>
      </div>
    `;
    row.querySelector(".file-check").addEventListener("change", (event) => {
      if (event.target.checked) state.selectedFiles.add(file.relative_path);
      else state.selectedFiles.delete(file.relative_path);
      syncSpecializedSelections();
    });
    container.appendChild(row);
  }
}

function renderTools() {
  const container = document.getElementById("tool-list");
  container.innerHTML = "";
  const grouped = new Map();
  for (const tool of state.tools) {
    const project = tool.project || "Suite";
    if (!grouped.has(project)) grouped.set(project, []);
    grouped.get(project).push(tool);
  }
  if (!state.openProjects.size) grouped.forEach((_, project) => state.openProjects.add(project));
  grouped.forEach((tools, project) => {
    const section = document.createElement("section");
    section.className = "tool-group";
    const isOpen = state.openProjects.has(project);
    const header = document.createElement("button");
    header.type = "button";
    header.className = `tool-group-header ${isOpen ? "is-open" : ""}`;
    header.innerHTML = `<span class="tool-group-title">${escapeHtml(project)}</span><span class="tool-group-arrow">${isOpen ? "-" : "+"}</span>`;
    header.addEventListener("click", () => {
      if (state.openProjects.has(project)) state.openProjects.delete(project);
      else state.openProjects.add(project);
      renderTools();
    });
    section.appendChild(header);
    if (isOpen) {
      const list = document.createElement("div");
      list.className = "tool-sublist";
      for (const tool of tools) {
        const item = document.createElement("button");
        item.type = "button";
        item.className = `tool-subitem ${state.activeTool?.id === tool.id ? "active" : ""}`;
        item.innerHTML = `<span class="tool-subitem-name">${escapeHtml(tool.name)}</span><span class="tool-subitem-meta">${escapeHtml(tool.category)}</span>`;
        item.addEventListener("click", () => {
          state.activeTool = tool;
          sanitizeSelection();
          stopLiveLogPolling();
          renderTools();
          renderFileFilterBanner();
          renderFiles();
          renderActiveTool();
        });
        list.appendChild(item);
      }
      section.appendChild(list);
    }
    container.appendChild(section);
  });
}

function genericField(field) {
  if (field.type === "file") {
    return `<select name="${field.name}"><option value="">Seleziona un file</option>${filteredFiles().map((file) => `<option value="${file.relative_path}">${escapeHtml(file.relative_path)}</option>`).join("")}</select>`;
  }
  if (field.type === "boolean") {
    return `<input name="${field.name}" type="checkbox" ${field.default ? "checked" : ""}>`;
  }
  if (field.type === "select") {
    return `<select name="${field.name}">${(field.options || []).map((option) => `<option value="${option}" ${option === field.default ? "selected" : ""}>${escapeHtml(option)}</option>`).join("")}</select>`;
  }
  return `<input name="${field.name}" type="${field.type === "number" ? "number" : "text"}" value="${field.default ?? ""}" placeholder="${field.placeholder || ""}">`;
}

function imageOptions(selected = "") {
  return filteredFiles().filter((file) => file.type === "image").map((file) => `<option value="${file.relative_path}" ${file.relative_path === selected ? "selected" : ""}>${escapeHtml(file.relative_path)}</option>`).join("");
}

function videoOptions() {
  return filteredFiles().filter((file) => file.type === "video").map((file) => `<option value="${file.relative_path}" ${file.relative_path === selectedFileOfType("video") ? "selected" : ""}>${escapeHtml(file.relative_path)}</option>`).join("");
}

function audioOptions(selected = "") {
  return filteredFiles().filter((file) => file.type === "audio").map((file) => `<option value="${file.relative_path}" ${file.relative_path === selected ? "selected" : ""}>${escapeHtml(file.relative_path)}</option>`).join("");
}

function renderPhotoForm() {
  return `
    <div class="special-tool-shell">
      <div class="special-note">Workflow Photography Tools: modalita definitiva per output finale, modalita test per varianti da confrontare.</div>
      <label class="field">
        <span>mode</span>
        <select name="mode" id="photo-mode-select">
          <option value="definitive">definitive</option>
          <option value="test">test</option>
        </select>
      </label>
      <div id="photo-definitive-fields" class="special-grid-two">
        <label class="field">
          <span>denoise</span>
          <input name="denoise" type="number" value="1.4" step="0.1">
        </label>
        <label class="field">
          <span>sharpen</span>
          <input name="sharpen" type="number" value="1.4" step="0.1">
        </label>
      </div>
      <div id="photo-test-fields" class="special-grid-two" hidden>
        <label class="field">
          <span>probe_margin</span>
          <input name="probe_margin" type="number" value="0.1" step="0.05">
        </label>
        <div class="special-note">In test vengono generate le combinazioni agli estremi del range.</div>
      </div>
      <label class="field">
        <span>test_crops</span>
        <input name="test_crops" type="checkbox">
      </label>
    </div>
  `;
}

function renderStereoForm() {
  return `
    <div class="special-tool-shell stereo-shell">
      <div class="special-note">Workflow StereoImage: scegli due immagini, clicca il punto di riferimento su ciascuna e genera l'allineamento.</div>
      <div class="stereo-grid">
        <label class="field">
          <span>left_path</span>
          <select id="stereo-left-path" name="left_path">
            <option value="">Seleziona immagine</option>
            ${imageOptions(state.stereoUi.leftPath)}
          </select>
        </label>
        <label class="field">
          <span>right_path</span>
          <select id="stereo-right-path" name="right_path">
            <option value="">Seleziona immagine</option>
            ${imageOptions(state.stereoUi.rightPath)}
          </select>
        </label>
      </div>
      <div class="stereo-grid">
        <label class="field">
          <span>left_point</span>
          <input id="stereo-left-point" name="left_point" type="text" value="${escapeHtml(state.stereoUi.leftPoint)}" placeholder="x,y">
        </label>
        <label class="field">
          <span>right_point</span>
          <input id="stereo-right-point" name="right_point" type="text" value="${escapeHtml(state.stereoUi.rightPoint)}" placeholder="x,y">
        </label>
      </div>
      <div class="stereo-grid">
        <label class="field">
          <span>mode</span>
          <select name="mode">
            <option value="alpha">alpha</option>
            <option value="add">add</option>
            <option value="diff">diff</option>
          </select>
        </label>
        <label class="field">
          <span>alpha</span>
          <input name="alpha" type="number" value="0.5" step="0.05">
        </label>
      </div>
      <div class="stereo-preview-grid">
        <div class="stereo-pane">
          <div class="stereo-pane-head">Left</div>
          <div class="stereo-preview-wrap">
            <img id="stereo-left-image" class="stereo-preview-image" alt="">
            <div id="stereo-left-marker" class="stereo-marker" hidden></div>
          </div>
        </div>
        <div class="stereo-pane">
          <div class="stereo-pane-head">Right</div>
          <div class="stereo-preview-wrap">
            <img id="stereo-right-image" class="stereo-preview-image" alt="">
            <div id="stereo-right-marker" class="stereo-marker" hidden></div>
          </div>
        </div>
      </div>
    </div>
  `;
}

function renderVideoForm(tool) {
  const extra = tool.id === "video_extract_frames"
    ? `
      <label class="field"><span>remove_blurry</span><input name="remove_blurry" type="checkbox"></label>
      <label class="field"><span>keep_best</span><input name="keep_best" type="number" value="0" min="0" step="1"></label>
    `
    : `
      <label class="field"><span>make_optimized</span><input name="make_optimized" type="checkbox" checked></label>
    `;

  return `
    <div class="video-tool-shell">
      <div class="special-note">Interfaccia derivata da Video Capture: player, start/end, salti temporali e ROI su canvas.</div>
      <div class="video-config-grid">
        <label class="field field-wide">
          <span>video_path</span>
          <select name="video_path" id="video-path-select">
            <option value="">Seleziona un video</option>
            ${videoOptions()}
          </select>
        </label>
        <label class="field"><span>start_time</span><input name="start_time" id="video-start-time" type="number" value="0" min="0" step="0.01"></label>
        <label class="field"><span>end_time</span><input name="end_time" id="video-end-time" type="number" value="3" min="0" step="0.01"></label>
      </div>
      <div class="video-config-grid">
        ${extra}
        <label class="field">
          <span>speed</span>
          <select id="video-speed-select">
            <option value="0.25">0.25x</option>
            <option value="0.5">0.5x</option>
            <option value="0.75" selected>0.75x</option>
            <option value="1">1x</option>
            <option value="1.5">1.5x</option>
            <option value="2">2x</option>
          </select>
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
          <div class="video-player-wrap">
            <video id="video-player" class="video-player" controls preload="metadata"></video>
            <canvas id="video-roi-canvas" class="video-roi-canvas"></canvas>
          </div>
        </div>
        <div class="video-toolbar">
          <button type="button" class="tool-secondary-button" id="video-jump-start">Start</button>
          <button type="button" class="tool-secondary-button" id="video-backward">-5s</button>
          <button type="button" class="tool-secondary-button" id="video-forward">+5s</button>
          <button type="button" class="tool-secondary-button" id="video-jump-end">End</button>
          <button type="button" class="tool-secondary-button" id="video-roi-toggle">Seleziona ROI</button>
          <button type="button" class="tool-secondary-button" id="video-roi-clear">Pulisci ROI</button>
        </div>
        <div id="video-roi-status" class="video-roi-status">ROI: full frame</div>
        <input type="hidden" name="roi" id="video-roi-value" value="">
      </div>
    </div>
  `;
}

function renderVideoConvertForm() {
  return `
    <div class="special-tool-shell">
      <div class="special-note">Conversione batch stile Video Capture. Se il file e gia compatibile, puo essere lasciato invariato.</div>
      <label class="field"><span>force</span><input name="force" type="checkbox"></label>
    </div>
  `;
}

function renderGoproForm() {
  return `
    <div class="special-tool-shell">
      <div class="special-note">Workflow Gopro Exporter: selezione file singolo, risoluzione target e parametri ffmpeg.</div>
      <label class="field">
        <span>video_path</span>
        <select name="video_path"><option value="">Seleziona un video</option>${videoOptions()}</select>
      </label>
      <div class="special-grid-two">
        <label class="field">
          <span>resolution</span>
          <select name="resolution">
            <option value="4k">4k</option>
            <option value="2k">2k</option>
            <option value="1080" selected>1080</option>
            <option value="720">720</option>
            <option value="480">480</option>
          </select>
        </label>
        <label class="field">
          <span>preset</span>
          <select name="preset">
            <option value="ultrafast">ultrafast</option>
            <option value="fast">fast</option>
            <option value="medium" selected>medium</option>
            <option value="slow">slow</option>
          </select>
        </label>
      </div>
      <div class="special-grid-two">
        <label class="field"><span>codec</span><input name="codec" type="text" value="libx264"></label>
        <label class="field"><span>crf</span><input name="crf" type="number" value="23" step="1"></label>
      </div>
    </div>
  `;
}

function renderBirdBatchForm() {
  return `
    <div class="special-tool-shell">
      <div class="special-note">Workflow Bird Audio batch: analisi BirdNET su uno o piu file audio con export opzionale delle clip.</div>
      <div class="special-note">File selezionati: ${state.selectedFiles.size || 0}</div>
      <div class="special-grid-two">
        <label class="field"><span>lat</span><input name="lat" type="number" value="45.65423642845939" step="0.000001"></label>
        <label class="field"><span>lon</span><input name="lon" type="number" value="13.812502298723128" step="0.000001"></label>
      </div>
      <div class="special-grid-two">
        <label class="field"><span>min_confidence</span><input name="min_confidence" type="number" value="0.7" step="0.01"></label>
        <label class="field">
          <span>clip_span</span>
          <select name="clip_span">
            <option value="detection" selected>detection</option>
            <option value="from_detection">from_detection</option>
            <option value="full_slice">full_slice</option>
          </select>
        </label>
      </div>
      <label class="field"><span>export_clips</span><input name="export_clips" type="checkbox" checked></label>
    </div>
  `;
}

function renderBirdDenoiseForm() {
  return `
    <div class="special-tool-shell">
      <div class="special-note">Denoiser Bird Audio su singolo WAV.</div>
      <label class="field">
        <span>audio_path</span>
        <select name="audio_path"><option value="">Seleziona un file audio</option>${audioOptions(selectedFileOfType("audio"))}</select>
      </label>
      <div class="special-grid-two">
        <label class="field"><span>high_pass_hz</span><input name="high_pass_hz" type="number" value="500" step="10"></label>
        <label class="field"><span>noise_reduction_factor</span><input name="noise_reduction_factor" type="number" value="2.0" step="0.1"></label>
      </div>
    </div>
  `;
}

function renderLiveForm() {
  return `
    <div class="bird-live-minimal">
      <div class="bird-live-controls">
        <button type="button" class="bird-btn-start" data-live-action="start">▶ Start</button>
        <button type="button" class="bird-btn-stop" data-live-action="stop">⏹ Stop</button>
      </div>

      <div class="bird-settings-wrapper">
        <button type="button" class="bird-settings-toggle" id="bird-settings-toggle">⚙ Impostazioni</button>
        <div class="bird-settings-box" id="bird-settings-box">
          <label class="field">Confidence Threshold
            <input name="min_confidence" type="number" value="0.1" step="0.01" min="0" max="1">
          </label>
          <label class="field">Slice Interval (sec)
            <input name="slice_interval" type="number" value="300">
          </label>
          <label class="field">Backend Audio
            <select name="backend">
              <option value="sounddevice" selected>sounddevice</option>
              <option value="pvrecorder">pvrecorder</option>
              <option value="auto">auto</option>
            </select>
          </label>
          <label class="field">Device Index
            <input name="device_index" type="number" value="16">
          </label>
          <label class="field checkbox">
            <input name="disable_denoise" type="checkbox" checked>
            <span>Denoise</span>
          </label>
        </div>
      </div>

      <div class="bird-detections-box">
        <div class="bird-detections-title">🐦 Uccelli Rilevati</div>
        <div id="bird-detections-live" class="bird-detections-list">In attesa di avviare...</div>
      </div>

      <input type="hidden" name="action" value="status" id="live-action-field">
    </div>
  `;
}

function renderUnavailableToolBox() {
  return '<div class="unavailable-tool-box">Tool non disponibile nel browser.</div>';
}

function renderActiveTool() {
  const activeToolBox = document.getElementById("active-tool");
  const form = document.getElementById("tool-form");
  const runButton = document.getElementById("run-tool");
  form.innerHTML = "";

  if (!state.activeTool) {
    activeToolBox.textContent = "Seleziona uno strumento.";
    activeToolBox.classList.add("muted");
    runButton.disabled = true;
    return;
  }

  activeToolBox.innerHTML = `<strong>${escapeHtml(state.activeTool.name)}</strong><div class="tool-meta">${escapeHtml(state.activeTool.project || "Suite")} | ${escapeHtml(state.activeTool.description)}</div>`;
  activeToolBox.classList.remove("muted");

  if (state.activeTool.browser_ready === false) {
    form.innerHTML = renderUnavailableToolBox();
    runButton.textContent = "Non disponibile";
    runButton.disabled = true;
    return;
  }

  switch (state.activeTool.id) {
    case "photo_naturalize":
      form.innerHTML = renderPhotoForm();
      setupPhotoUi();
      runButton.textContent = "Elabora foto";
      break;
    case "stereo_overlay":
      form.innerHTML = renderStereoForm();
      setupStereoUi();
      runButton.textContent = "Crea overlay";
      break;
    case "video_extract_frames":
      form.innerHTML = renderVideoForm(state.activeTool);
      setupVideoUi();
      runButton.textContent = "Estrai frames";
      break;
    case "video_make_gif":
      form.innerHTML = renderVideoForm(state.activeTool);
      setupVideoUi();
      runButton.textContent = "Crea GIF";
      break;
    case "video_convert_web":
      form.innerHTML = renderVideoConvertForm();
      runButton.textContent = "Converti per web";
      break;
    case "gopro_convert":
      form.innerHTML = renderGoproForm();
      runButton.textContent = "Converti GoPro";
      break;
    case "bird_audio_batch":
      form.innerHTML = renderBirdBatchForm();
      runButton.textContent = "Analizza audio";
      break;
    case "bird_audio_denoise":
      form.innerHTML = renderBirdDenoiseForm();
      runButton.textContent = "Denoise audio";
      break;
    case "bird_audio_live":
      form.innerHTML = renderLiveForm();
      setupLiveUi();
      runButton.style.display = "none";  // Nascondi il tasto Esegui per Bird Live
      break;
    default:
      for (const field of state.activeTool.params) {
        const wrapper = document.createElement("label");
        wrapper.className = "field";
        wrapper.innerHTML = `<span>${field.name}</span>${genericField(field)}`;
        form.appendChild(wrapper);
      }
      runButton.textContent = "Esegui endpoint";
      break;
  }

  runButton.disabled = false;
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

function setupPhotoUi() {
  const modeSelect = document.getElementById("photo-mode-select");
  const definitiveFields = document.getElementById("photo-definitive-fields");
  const testFields = document.getElementById("photo-test-fields");
  if (!modeSelect || !definitiveFields || !testFields) return;
  const sync = () => {
    const isTest = modeSelect.value === "test";
    definitiveFields.hidden = isTest;
    testFields.hidden = !isTest;
  };
  modeSelect.addEventListener("change", sync);
  sync();
}

function setupStereoSelections() {
  const selectedImages = [...state.selectedFiles].filter((path) => state.files.find((file) => file.relative_path === path)?.type === "image");
  if (selectedImages[0]) state.stereoUi.leftPath = selectedImages[0];
  if (selectedImages[1]) state.stereoUi.rightPath = selectedImages[1];
}

function placeStereoMarker(side) {
  const image = document.getElementById(`stereo-${side}-image`);
  const marker = document.getElementById(`stereo-${side}-marker`);
  const point = side === "left" ? state.stereoUi.leftPoint : state.stereoUi.rightPoint;
  if (!image || !marker || !point) {
    if (marker) marker.hidden = true;
    return;
  }
  const [rawX, rawY] = point.split(",").map((value) => Number(value.trim()));
  if (!Number.isFinite(rawX) || !Number.isFinite(rawY) || !image.naturalWidth || !image.naturalHeight) {
    marker.hidden = true;
    return;
  }
  const rect = image.getBoundingClientRect();
  marker.style.left = `${(rawX / image.naturalWidth) * rect.width}px`;
  marker.style.top = `${(rawY / image.naturalHeight) * rect.height}px`;
  marker.hidden = false;
}

function updateStereoPreview(side) {
  const image = document.getElementById(`stereo-${side}-image`);
  const marker = document.getElementById(`stereo-${side}-marker`);
  const path = side === "left" ? state.stereoUi.leftPath : state.stereoUi.rightPath;
  if (!image || !marker) return;
  if (!path) {
    image.removeAttribute("src");
    marker.hidden = true;
    return;
  }
  image.src = `/api/file?path=${encodeURIComponent(path)}`;
  image.onload = () => placeStereoMarker(side);
  placeStereoMarker(side);
}

function setupStereoUi() {
  setupStereoSelections();
  const leftPath = document.getElementById("stereo-left-path");
  const rightPath = document.getElementById("stereo-right-path");
  const leftPoint = document.getElementById("stereo-left-point");
  const rightPoint = document.getElementById("stereo-right-point");

  if (leftPath) {
    leftPath.value = state.stereoUi.leftPath;
    leftPath.addEventListener("change", () => {
      state.stereoUi.leftPath = leftPath.value;
      updateStereoPreview("left");
    });
  }
  if (rightPath) {
    rightPath.value = state.stereoUi.rightPath;
    rightPath.addEventListener("change", () => {
      state.stereoUi.rightPath = rightPath.value;
      updateStereoPreview("right");
    });
  }
  if (leftPoint) {
    leftPoint.addEventListener("input", () => {
      state.stereoUi.leftPoint = leftPoint.value;
      placeStereoMarker("left");
    });
  }
  if (rightPoint) {
    rightPoint.addEventListener("input", () => {
      state.stereoUi.rightPoint = rightPoint.value;
      placeStereoMarker("right");
    });
  }

  ["left", "right"].forEach((side) => {
    const image = document.getElementById(`stereo-${side}-image`);
    image?.addEventListener("click", (event) => {
      if (!image.naturalWidth || !image.naturalHeight) return;
      const rect = image.getBoundingClientRect();
      const point = `${Math.round(((event.clientX - rect.left) / rect.width) * image.naturalWidth)},${Math.round(((event.clientY - rect.top) / rect.height) * image.naturalHeight)}`;
      state.stereoUi[`${side}Point`] = point;
      document.getElementById(`stereo-${side}-point`).value = point;
      placeStereoMarker(side);
    });
    updateStereoPreview(side);
  });
}

function updateVideoInfoBar() {
  const player = document.getElementById("video-player");
  const bar = document.getElementById("video-info-bar");
  if (!player || !bar) return;
  bar.textContent = `Tempo ${player.currentTime.toFixed(2)}s | Durata ${Number.isFinite(player.duration) ? player.duration.toFixed(2) : "--"}s | ${player.videoWidth || "--"}x${player.videoHeight || "--"}`;
}

function resizeRoiCanvas() {
  const player = document.getElementById("video-player");
  const canvas = document.getElementById("video-roi-canvas");
  if (!player || !canvas) return;
  canvas.width = player.clientWidth;
  canvas.height = player.clientHeight;
  drawRoiOverlay();
}

function drawRoiOverlay() {
  const canvas = document.getElementById("video-roi-canvas");
  if (!canvas) return;
  const context = canvas.getContext("2d");
  context.clearRect(0, 0, canvas.width, canvas.height);
  context.lineWidth = 2;
  context.strokeStyle = "#7fd0b4";
  context.fillStyle = "rgba(127, 208, 180, 0.18)";
  if (state.videoUi.dragging) {
    const x = Math.min(state.videoUi.startX, state.videoUi.currentX);
    const y = Math.min(state.videoUi.startY, state.videoUi.currentY);
    const w = Math.abs(state.videoUi.currentX - state.videoUi.startX);
    const h = Math.abs(state.videoUi.currentY - state.videoUi.startY);
    context.fillRect(x, y, w, h);
    context.strokeRect(x, y, w, h);
    return;
  }
  if (!state.videoUi.roi) return;
  const player = document.getElementById("video-player");
  if (!player || !player.videoWidth || !player.videoHeight) return;
  const [x, y, w, h] = state.videoUi.roi;
  context.fillRect((x * canvas.width) / player.videoWidth, (y * canvas.height) / player.videoHeight, (w * canvas.width) / player.videoWidth, (h * canvas.height) / player.videoHeight);
  context.strokeRect((x * canvas.width) / player.videoWidth, (y * canvas.height) / player.videoHeight, (w * canvas.width) / player.videoWidth, (h * canvas.height) / player.videoHeight);
}

function clearVideoRoi() {
  state.videoUi = { ...state.videoUi, roi: null, dragging: false, selecting: false };
  const value = document.getElementById("video-roi-value");
  const status = document.getElementById("video-roi-status");
  const button = document.getElementById("video-roi-toggle");
  const canvas = document.getElementById("video-roi-canvas");
  if (value) value.value = "";
  if (status) status.textContent = "ROI: full frame";
  if (button) button.textContent = "Seleziona ROI";
  if (canvas) canvas.classList.remove("is-active");
  drawRoiOverlay();
}

function toggleRoiSelectionMode() {
  state.videoUi.selecting = !state.videoUi.selecting;
  const button = document.getElementById("video-roi-toggle");
  const canvas = document.getElementById("video-roi-canvas");
  if (button) button.textContent = state.videoUi.selecting ? "ROI attiva" : "Seleziona ROI";
  if (canvas) canvas.classList.toggle("is-active", state.videoUi.selecting);
}

function beginRoiDrag(event) {
  if (!state.videoUi.selecting) return;
  const rect = event.currentTarget.getBoundingClientRect();
  state.videoUi.dragging = true;
  state.videoUi.startX = event.clientX - rect.left;
  state.videoUi.startY = event.clientY - rect.top;
  state.videoUi.currentX = state.videoUi.startX;
  state.videoUi.currentY = state.videoUi.startY;
  drawRoiOverlay();
}

function updateRoiDrag(event) {
  if (!state.videoUi.selecting || !state.videoUi.dragging) return;
  const rect = event.currentTarget.getBoundingClientRect();
  state.videoUi.currentX = event.clientX - rect.left;
  state.videoUi.currentY = event.clientY - rect.top;
  drawRoiOverlay();
}

function finishRoiDrag() {
  if (!state.videoUi.selecting || !state.videoUi.dragging) return;
  state.videoUi.dragging = false;
  const player = document.getElementById("video-player");
  const canvas = document.getElementById("video-roi-canvas");
  const status = document.getElementById("video-roi-status");
  const value = document.getElementById("video-roi-value");
  if (!player || !canvas || !status || !value || !player.videoWidth || !player.videoHeight) return;
  const x = Math.min(state.videoUi.startX, state.videoUi.currentX);
  const y = Math.min(state.videoUi.startY, state.videoUi.currentY);
  const w = Math.abs(state.videoUi.currentX - state.videoUi.startX);
  const h = Math.abs(state.videoUi.currentY - state.videoUi.startY);
  if (w < 8 || h < 8) {
    drawRoiOverlay();
    return;
  }
  const roi = [
    Math.round((x * player.videoWidth) / canvas.width),
    Math.round((y * player.videoHeight) / canvas.height),
    Math.round((w * player.videoWidth) / canvas.width),
    Math.round((h * player.videoHeight) / canvas.height),
  ];
  state.videoUi.roi = roi;
  state.videoUi.selecting = false;
  value.value = roi.join(",");
  status.textContent = `ROI: ${roi[2]}x${roi[3]} @ ${roi[0]},${roi[1]}`;
  document.getElementById("video-roi-toggle").textContent = "Seleziona ROI";
  canvas.classList.remove("is-active");
  drawRoiOverlay();
}

function loadVideoIntoTool() {
  const select = document.getElementById("video-path-select");
  const player = document.getElementById("video-player");
  const info = document.getElementById("video-info-bar");
  if (!select || !player || !info) return;
  const path = select.value;
  clearVideoRoi();
  if (!path) {
    player.removeAttribute("src");
    player.load();
    info.textContent = "Seleziona un video per iniziare.";
    return;
  }
  player.src = `/api/file?path=${encodeURIComponent(path)}`;
  player.load();
  info.textContent = `Carico ${path}...`;
}

function setupVideoUi() {
  const select = document.getElementById("video-path-select");
  const player = document.getElementById("video-player");
  const start = document.getElementById("video-start-time");
  const end = document.getElementById("video-end-time");
  const canvas = document.getElementById("video-roi-canvas");
  const speed = document.getElementById("video-speed-select");
  if (!select || !player || !start || !end || !canvas || !speed) return;
  const selected = selectedFileOfType("video");
  if (selected) select.value = selected;
  select.addEventListener("change", loadVideoIntoTool);
  player.addEventListener("loadedmetadata", () => {
    end.max = player.duration.toFixed(3);
    if (!end.value || Number(end.value) <= 0 || Number(end.value) > player.duration) end.value = player.duration.toFixed(2);
    updateVideoInfoBar();
    resizeRoiCanvas();
    player.playbackRate = Number(speed.value);
  });
  player.addEventListener("timeupdate", updateVideoInfoBar);
  player.addEventListener("loadeddata", resizeRoiCanvas);
  speed.addEventListener("change", () => {
    player.playbackRate = Number(speed.value);
  });
  document.getElementById("video-set-start").addEventListener("click", () => {
    start.value = player.currentTime.toFixed(2);
  });
  document.getElementById("video-set-end").addEventListener("click", () => {
    end.value = player.currentTime.toFixed(2);
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
    if (player.duration) player.currentTime = player.duration;
  });
  document.getElementById("video-roi-toggle").addEventListener("click", toggleRoiSelectionMode);
  document.getElementById("video-roi-clear").addEventListener("click", clearVideoRoi);
  canvas.addEventListener("mousedown", beginRoiDrag);
  canvas.addEventListener("mousemove", updateRoiDrag);
  canvas.addEventListener("mouseup", finishRoiDrag);
  canvas.addEventListener("mouseleave", finishRoiDrag);
  if (select.value) loadVideoIntoTool();
}

function syncSpecializedSelections() {
  if (state.activeTool?.id === "stereo_overlay") setupStereoSelections();
  if (VIDEO_TOOL_IDS.has(state.activeTool?.id)) {
    const select = document.getElementById("video-path-select");
    const selected = selectedFileOfType("video");
    if (select && selected) {
      select.value = selected;
      loadVideoIntoTool();
    }
  }
}

async function refreshLiveLog() {
  const box = document.getElementById("live-log-box");
  if (!box) return;
  try {
    const payload = await api("/api/live/log");
    box.textContent = payload.log || "Nessun log disponibile.";
  } catch {
    box.textContent = "Log live non disponibile.";
  }
}

function stopLiveLogPolling() {
  if (state.liveLogTimer) {
    window.clearInterval(state.liveLogTimer);
    state.liveLogTimer = null;
  }
}

function setupLiveUi() {
  // Setup dei pulsanti Start/Stop
  document.querySelectorAll("[data-live-action]").forEach((button) => {
    button.addEventListener("click", async () => {
      const action = button.dataset.liveAction;
      document.getElementById("live-action-field").value = action;
      
      if (action === "start") {
        // Pulisci i rilevamenti precedenti
        document.getElementById("bird-detections-live").innerHTML = "Avvio in corso...";
      } else if (action === "stop") {
        document.getElementById("bird-detections-live").innerHTML = "Stoppato";
      }
      
      await runActiveTool();
    });
  });

  // Setup del toggle Impostazioni
  const settingsToggle = document.getElementById("bird-settings-toggle");
  const settingsBox = document.getElementById("bird-settings-box");
  settingsBox.classList.add("hidden");
  
  settingsToggle.addEventListener("click", () => {
    settingsBox.classList.toggle("hidden");
  });

  // Setup del polling dei rilevamenti di uccelli
  stopLiveLogPolling();
  pollBirdDetections();
  state.liveLogTimer = window.setInterval(pollBirdDetections, 3000);
}

function pollBirdDetections() {
  const detectionsBox = document.getElementById("bird-detections-live");
  if (!detectionsBox) return;
  
  refreshLiveLog().then(() => {
    const logBox = document.getElementById("live-log-box");
    if (!logBox) return;
    
    const logText = logBox.textContent || "";
    const detections = extractBirdDetections(logText);
    
    if (detections.length === 0) {
      detectionsBox.innerHTML = "<div class=\"bird-notice\">Nessun uccello rilevato</div>";
    } else {
      const html = detections.map(d => `
        <div class="bird-detection-item">
          <div class="bird-name">${d.name}</div>
          <div class="bird-confidence">${(d.confidence * 100).toFixed(0)}%</div>
        </div>
      `).join("");
      detectionsBox.innerHTML = html;
    }
  }).catch(() => {
    detectionsBox.innerHTML = "<div class=\"bird-notice\">Errore caricamento dati</div>";
  });
}

function extractBirdDetections(logText) {
  const detections = {};
  // Cerchiamo linee tipo: "rilevato: Turdus merula (confidence: 0.85)"
  const regex = /rilevato[:\s]+([^(]+)\s*\(.*?confidence[:\s]*([0-9.]+)[)%]*/gi;
  
  let match;
  while ((match = regex.exec(logText)) !== null) {
    const name = match[1].trim();
    const confidence = parseFloat(match[2]);
    
    if (name && !isNaN(confidence)) {
      if (!detections[name] || detections[name].confidence < confidence) {
        detections[name] = { name, confidence };
      }
    }
  }
  
  return Object.values(detections).sort((a, b) => b.confidence - a.confidence);
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
  if (!state.activeTool && state.tools.length) state.activeTool = state.tools[0];
  renderTools();
  renderFileFilterBanner();
  renderActiveTool();
}

function fetchThumbnail(file) {
  state.thumbnails.set(file.relative_path, `/api/media/thumbnail?path=${encodeURIComponent(file.relative_path)}&v=${encodeURIComponent(file.size || 0)}`);
}

function scheduleThumbnailLoading() {
  const jobId = ++state.thumbnailJobs;
  const previewables = filteredFiles().filter((file) => (file.type === "image" || file.type === "video") && !state.thumbnails.has(file.relative_path)).slice(0, 120);
  let index = 0;
  function next() {
    if (jobId !== state.thumbnailJobs || index >= previewables.length) return;
    previewables.slice(index, index + THUMBNAIL_BATCH_SIZE).forEach(fetchThumbnail);
    index += THUMBNAIL_BATCH_SIZE;
    renderFiles();
    window.setTimeout(next, 30);
  }
  window.setTimeout(next, 0);
}

async function loadFiles() {
  state.files = await api("/api/files");
  sanitizeSelection();
  state.thumbnails.clear();
  renderFileFilterBanner();
  renderFiles();
  scheduleThumbnailLoading();
  if (state.activeTool) renderActiveTool();
}

async function runActiveTool() {
  if (!state.activeTool || state.activeTool.browser_ready === false) return;
  setResult("Esecuzione in corso...");
  try {
    const result = await api(`/api/run/${state.activeTool.id}`, {
      method: "POST",
      body: JSON.stringify({ selected_files: Array.from(state.selectedFiles), params: collectParams() }),
    });
    setResult(renderResultValue(result));
    if (state.activeTool.id === "bird_audio_live") refreshLiveLog();
  } catch (error) {
    setResult(`<code>${escapeHtml(error.message)}</code>`);
  }
}

function toggleToolsSidebar() {
  state.toolsCollapsed = !state.toolsCollapsed;
  document.body.classList.toggle("tools-collapsed", state.toolsCollapsed);
  document.getElementById("toggle-tools").textContent = state.toolsCollapsed ? "Apri" : "Chiudi";
}

document.getElementById("root-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    await api("/api/session/root", { method: "POST", body: JSON.stringify({ root_path: document.getElementById("root-path").value.trim() }) });
    state.selectedFiles.clear();
    await loadSession();
  } catch (error) {
    setResult(`<code>${escapeHtml(error.message)}</code>`);
  }
});

document.getElementById("pick-root").addEventListener("click", async () => {
  try {
    const result = await api("/api/session/pick-root", { method: "POST", body: JSON.stringify({}) });
    document.getElementById("root-path").value = result.root_path;
    state.selectedFiles.clear();
    await loadSession();
  } catch (error) {
    setResult(`<code>${escapeHtml(error.message)}</code>`);
  }
});

document.getElementById("refresh-files").addEventListener("click", async () => {
  try {
    await loadFiles();
  } catch (error) {
    setResult(`<code>${escapeHtml(error.message)}</code>`);
  }
});

document.getElementById("toggle-tools").addEventListener("click", toggleToolsSidebar);
document.getElementById("run-tool").addEventListener("click", runActiveTool);

loadTools();
loadSession();
