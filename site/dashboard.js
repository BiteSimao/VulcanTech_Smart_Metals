const DATA_URL = "/data/sensores_preparados.csv";
const API_URL = "http://127.0.0.1:8000";

const labels = {
  0: "Normal",
  1: "Desgaste de ferramenta",
  2: "Falha de refrigeração",
  3: "Desalinhamento / trinca",
};
const sensors = {
  temperatura_fuso_c: { name: "Temperatura do fuso", unit: "°C", digits: 1 },
  vibracao_triaxial_rms_mms: { name: "Vibração RMS", unit: "mm/s", digits: 2 },
  torque_fuso_nm: { name: "Torque do fuso", unit: "Nm", digits: 1 },
  vazao_refrigerante_lmin: { name: "Vazão de refrigerante", unit: "L/min", digits: 1 },
  corrente_estator_amp: { name: "Corrente do estator", unit: "A", digits: 1 },
  pressao_hidraulica_bar: { name: "Pressão hidráulica", unit: "bar", digits: 1 },
};
const physicalLimits = {
  temperatura_fuso_c: [30, 75],
  vibracao_triaxial_rms_mms: [0.8, 3.8],
  torque_fuso_nm: [45, 210],
  vazao_refrigerante_lmin: [15, 40],
  corrente_estator_amp: [12, 55],
  pressao_hidraulica_bar: [110, 220],
  nivel_ruido_db: [45, 85],
};
const classes = [1, 2, 3];
let records = [];
let latest = null;
let selectedDays = 7;
let apiConnected = false;
const inspectionFiles = { weld: null, thermal: null };
let toastTimer;
let liveTimer;
let liveStream = { key: "", points: [], baseValue: null, lastValue: null, lastTime: null };

const $ = (selector) => document.querySelector(selector);
const numberFormat = new Intl.NumberFormat("pt-BR");
const dateFormat = new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });

function parseCSV(text) {
  const lines = text.trim().split(/\r?\n/);
  const headers = lines.shift().split(",");
  return lines.map((line) => {
    const fields = line.split(",");
    const row = {};
    headers.forEach((header, i) => { row[header] = fields[i]; });
    row.timestamp = new Date(row.timestamp.replace(" ", "T") + (row.timestamp.includes("Z") ? "" : ""));
    for (const key of Object.keys(row)) {
      if (key !== "timestamp" && key !== "id_celula" && key !== "liga_metalica") {
        row[key] = row[key] === "" ? null : Number(row[key]);
      }
    }
    return row;
  }).filter((row) => !Number.isNaN(row.timestamp.getTime()));
}

async function loadData() {
  setConnection("Carregando dados", false);
  probeApi();
  try {
    const response = await fetch(DATA_URL, { cache: "no-store" });
    if (!response.ok) throw new Error(`Não foi possível abrir ${DATA_URL}`);
    records = parseCSV(await response.text()).sort((a, b) => a.timestamp - b.timestamp);
    if (!records.length) throw new Error("O CSV não possui registros válidos.");
    liveStream = { key: "", points: [], baseValue: null, lastValue: null, lastTime: null };
    latest = records.at(-1);
    fillFilters();
    render();
    setConnection("Dados carregados", true);
    if (!liveTimer) liveTimer = window.setInterval(appendLiveReading, 3000);
  } catch (error) {
    setConnection("Dados indisponíveis", false);
    showToast("Não encontrei o CSV. Inicie o site pela raiz do projeto; veja o README.");
    console.error(error);
  }
}

function fillFilters() {
  $("#cell-filter").innerHTML = '<option value="all">Todas as células</option>';
  $("#alloy-filter").innerHTML = '<option value="all">Todas as ligas</option>';
  $("#prediction-cell").innerHTML = "";
  const cells = [...new Set(records.map((row) => row.id_celula))].sort();
  const alloys = [...new Set(records.map((row) => row.liga_metalica))].sort();
  cells.forEach((cell) => addOption($("#cell-filter"), cell, cell));
  alloys.forEach((alloy) => addOption($("#alloy-filter"), alloy, alloy.replaceAll("_", " ")));
  cells.forEach((cell) => addOption($("#prediction-cell"), cell, cell));
  $("#last-updated").textContent = dateFormat.format(latest.timestamp);
}

function addOption(select, value, text) {
  const option = document.createElement("option");
  option.value = value;
  option.textContent = text;
  select.append(option);
}

function filteredRows() {
  const cell = $("#cell-filter").value;
  const alloy = $("#alloy-filter").value;
  const cutoff = selectedDays === "all" ? new Date(0) : new Date(latest.timestamp.getTime() - selectedDays * 86400000);
  return records.filter((row) => row.timestamp >= cutoff && (cell === "all" || row.id_celula === cell) && (alloy === "all" || row.liga_metalica === alloy));
}

function render() {
  const data = filteredRows();
  renderKpis(data);
  renderTrend(data);
  renderFailures(data);
  renderCells(data);
  renderEvents(data);
}

function renderKpis(data) {
  const failures = data.filter((row) => row.tipo_falha > 0).length;
  const cells = new Set(data.map((row) => row.id_celula)).size;
  $("#kpi-records").textContent = numberFormat.format(data.length);
  $("#kpi-failures").textContent = numberFormat.format(failures);
  $("#kpi-failures-foot").innerHTML = `<span class="${failures ? "neutral-dot" : "green-dot"}"></span><span>${data.length ? `${(failures / data.length * 100).toFixed(1).replace(".", ",")}% dos registros no recorte` : "Sem registros"}</span>`;
  $("#kpi-cells").textContent = `${cells} / ${new Set(records.map((row) => row.id_celula)).size}`;
  $("#kpi-oee-foot").innerHTML = `<span class="neutral-dot"></span><span>Estimativa disponível após treino</span>`;
  fetch("/data/metricas_modelo.json", { cache: "no-store" }).then((r) => r.ok ? r.json() : null).then((metrics) => {
    if (metrics?.oee_simulado?.oee !== undefined) {
      $("#kpi-oee").textContent = `${(metrics.oee_simulado.oee * 100).toFixed(1).replace(".", ",")}%`;
      $("#kpi-oee-foot").innerHTML = `<span class="neutral-dot"></span><span>Simulação didática, não OEE real</span>`;
    }
  }).catch(() => {});
}

function renderTrend(data) {
  const key = $("#sensor-filter").value;
  const setting = sensors[key];
  $("#chart-series-name").textContent = setting.name;
  $("#chart-unit").textContent = setting.unit;
  const buckets = new Map();
  data.forEach((row) => {
    const value = row[key];
    if (value === null || !Number.isFinite(value)) return;
    const hour = new Date(row.timestamp);
    hour.setMinutes(0, 0, 0);
    const stamp = hour.getTime();
    if (!buckets.has(stamp)) buckets.set(stamp, { sum: 0, count: 0 });
    const b = buckets.get(stamp);
    b.sum += value;
    b.count += 1;
  });
  const historicalPoints = [...buckets.entries()].sort((a, b) => a[0] - b[0]).map(([time, b]) => ({ time, value: b.sum / b.count }));
  const canvas = $("#trend-chart");
  const empty = $("#chart-empty");
  if (!historicalPoints.length) { canvas.classList.add("hidden"); $("#chart-tooltip").classList.remove("visible"); empty.classList.remove("hidden"); return; }
  const streamKey = [key, $("#cell-filter").value, $("#alloy-filter").value, selectedDays].join("|");
  if (liveStream.key !== streamKey) {
    liveStream = { key: streamKey, points: [], baseValue: historicalPoints.at(-1).value, lastValue: historicalPoints.at(-1).value, lastTime: historicalPoints.at(-1).time };
  }
  const points = [...historicalPoints, ...liveStream.points];
  canvas.classList.remove("hidden"); empty.classList.add("hidden");
  drawChart(canvas, points, setting);
  const first = new Date(points[0].time), last = new Date(points.at(-1).time);
  $("#chart-range").textContent = first.toLocaleDateString("pt-BR", { day: "2-digit", month: "short" }) + " – " + last.toLocaleDateString("pt-BR", { day: "2-digit", month: "short" });
}

function appendLiveReading() {
  if (!records.length) return;
  const data = filteredRows();
  const key = $("#sensor-filter").value;
  const bounds = physicalLimits[key];
  if (!data.length || !bounds || liveStream.baseValue === null) return;

  const [minimum, maximum] = bounds;
  const span = maximum - minimum;
  const drift = (liveStream.baseValue - liveStream.lastValue) * 0.06;
  const amplitude = Math.random() < 0.18 ? 0.24 : 0.14;
  const noise = (Math.random() - 0.5) * span * amplitude;
  const value = Math.max(minimum, Math.min(maximum, liveStream.lastValue + drift + noise));
  const point = { time: liveStream.lastTime + 60 * 60 * 1000, value };
  liveStream.points.push(point);
  if (liveStream.points.length > 168) liveStream.points.shift();
  liveStream.lastValue = value;
  liveStream.lastTime = point.time;
  renderTrend(data);
}

function drawChart(canvas, points, setting) {
  const rect = canvas.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  canvas.width = rect.width * dpr; canvas.height = rect.height * dpr;
  const ctx = canvas.getContext("2d");
  const w = rect.width, h = rect.height, pad = { left: 35, right: 8, top: 12, bottom: 25 };
  const values = points.map((p) => p.value);
  let min = Math.min(...values), max = Math.max(...values);
  if (min === max) { min -= 1; max += 1; }
  const gutter = (max - min) * .14; min -= gutter; max += gutter;
  const x = (i) => pad.left + i * (w - pad.left - pad.right) / Math.max(points.length - 1, 1);
  const y = (v) => pad.top + (max - v) * (h - pad.top - pad.bottom) / (max - min);
  const tooltip = $("#chart-tooltip");
  const render = (highlight = -1) => {
    const dark = document.documentElement.dataset.theme === "dark";
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    ctx.font = "9px DM Sans, Arial"; ctx.textAlign = "right"; ctx.textBaseline = "middle";
    for (let i = 0; i < 4; i++) {
      const val = min + (max - min) * i / 3, yy = y(val);
      ctx.strokeStyle = dark ? "#344354" : "#edf0f3"; ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(pad.left, yy); ctx.lineTo(w - pad.right, yy); ctx.stroke();
      ctx.fillStyle = dark ? "#9eacba" : "#a1abb5"; ctx.fillText(val.toFixed(setting.digits), pad.left - 7, yy);
    }
    const tickCount = Math.min(5, points.length);
    ctx.textAlign = "center"; ctx.textBaseline = "top"; ctx.fillStyle = dark ? "#9eacba" : "#a1abb5";
    for (let i = 0; i < tickCount; i++) {
      const idx = Math.round(i * (points.length - 1) / Math.max(tickCount - 1, 1));
      const date = new Date(points[idx].time);
      ctx.fillText(date.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" }), x(idx), h - pad.bottom + 8);
    }
    const gradient = ctx.createLinearGradient(0, pad.top, 0, h - pad.bottom);
    gradient.addColorStop(0, "rgba(68,125,222,.17)"); gradient.addColorStop(1, "rgba(68,125,222,0)");
    ctx.beginPath(); points.forEach((p, i) => i ? ctx.lineTo(x(i), y(p.value)) : ctx.moveTo(x(i), y(p.value)));
    ctx.lineTo(x(points.length - 1), h - pad.bottom); ctx.lineTo(x(0), h - pad.bottom); ctx.closePath(); ctx.fillStyle = gradient; ctx.fill();
    ctx.beginPath(); points.forEach((p, i) => i ? ctx.lineTo(x(i), y(p.value)) : ctx.moveTo(x(i), y(p.value)));
    ctx.strokeStyle = "#4b80dc"; ctx.lineWidth = 2; ctx.lineJoin = "round"; ctx.lineCap = "round"; ctx.stroke();
    if (points.length < 50) points.forEach((p, i) => { ctx.beginPath(); ctx.arc(x(i), y(p.value), 2.3, 0, Math.PI * 2); ctx.fillStyle = "#fff"; ctx.fill(); ctx.strokeStyle = "#4b80dc"; ctx.lineWidth = 1.5; ctx.stroke(); });
    ctx.beginPath(); ctx.arc(x(points.length - 1), y(points.at(-1).value), 4, 0, Math.PI * 2); ctx.fillStyle = "#4bc39a"; ctx.fill(); ctx.strokeStyle = dark ? "#1b2632" : "#fff"; ctx.lineWidth = 2; ctx.stroke();
    if (highlight >= 0) {
      ctx.beginPath(); ctx.setLineDash([3, 3]); ctx.moveTo(x(highlight), pad.top); ctx.lineTo(x(highlight), h - pad.bottom); ctx.strokeStyle = "#91a7c6"; ctx.lineWidth = 1; ctx.stroke(); ctx.setLineDash([]);
      ctx.beginPath(); ctx.arc(x(highlight), y(points[highlight].value), 5, 0, Math.PI * 2); ctx.fillStyle = "#fff"; ctx.fill(); ctx.strokeStyle = "#477bd6"; ctx.lineWidth = 2; ctx.stroke();
    }
  };
  render();
  canvas.onmousemove = (event) => {
    const bounds = canvas.getBoundingClientRect();
    const mouseX = event.clientX - bounds.left;
    if (mouseX < pad.left || mouseX > w - pad.right) {
      render();
      tooltip.classList.remove("visible");
      return;
    }
    const ratio = (mouseX - pad.left) / (w - pad.left - pad.right);
    const index = Math.max(0, Math.min(points.length - 1, Math.round(ratio * (points.length - 1))));
    render(index);
    const point = points[index];
    const start = new Date(point.time), end = new Date(point.time + 60 * 60 * 1000);
    const day = start.toLocaleDateString("pt-BR", { weekday: "long", day: "2-digit", month: "long", year: "numeric" });
    const hour = `${start.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}–${end.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}`;
    tooltip.replaceChildren();
    const dateLine = document.createElement("strong"); dateLine.textContent = `${day} · ${hour}`;
    const valueLine = document.createElement("span"); valueLine.textContent = `${setting.name}: ${point.value.toFixed(setting.digits).replace(".", ",")} ${setting.unit}`;
    tooltip.append(dateLine, valueLine);
    const left = Math.max(4, Math.min(w - 196, mouseX + 14));
    const top = Math.max(4, Math.min(h - 57, event.clientY - bounds.top - 58));
    tooltip.style.left = `${left}px`; tooltip.style.top = `${top}px`;
    tooltip.classList.add("visible");
  };
  canvas.onmouseleave = () => { render(); tooltip.classList.remove("visible"); };
}

function renderFailures(data) {
  const counts = Object.fromEntries(classes.map((n) => [n, 0]));
  data.forEach((row) => { if (counts[row.tipo_falha] !== undefined) counts[row.tipo_falha]++; });
  const total = classes.reduce((sum, n) => sum + counts[n], 0);
  const max = Math.max(...classes.map((n) => counts[n]), 1);
  const rows = classes.map((n) => `<div class="fault-row"><span class="fault-label" title="${labels[n]}">${labels[n]}</span><div class="fault-track"><div class="fault-fill c${n}" style="width:${(counts[n] / max * 100).toFixed(1)}%"></div></div><span class="fault-value">${numberFormat.format(counts[n])}</span></div>`);
  $("#fault-chart").innerHTML = rows.join("");
  $("#fault-total").textContent = numberFormat.format(total);
}

function setTheme(theme) {
  const dark = theme === "dark";
  document.documentElement.dataset.theme = dark ? "dark" : "light";
  const button = $("#theme-toggle");
  button.textContent = dark ? "☀" : "☾";
  button.title = dark ? "Ativar tema claro" : "Ativar tema escuro";
  button.setAttribute("aria-label", button.title);
  button.setAttribute("aria-pressed", String(dark));
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", dark ? "#121a24" : "#f4f6f8");
  try { localStorage.setItem("vulcantech-theme", dark ? "dark" : "light"); } catch {}
  if (records.length) renderTrend(filteredRows());
}

const navigationSections = [
  { hash: "#inicio", targets: [$(".page-heading")] },
  { hash: "#analise", targets: [$("#analise")] },
  { hash: "#qualidade", targets: [$("#qualidade"), $("#previsao")] },
].map((section) => ({ ...section, targets: section.targets.filter(Boolean) })).filter((section) => section.targets.length);
let navigationFrame = 0;

function updateActiveNavigation() {
  navigationFrame = 0;
  const marker = window.innerHeight * 0.28;
  let current = navigationSections[0];
  navigationSections.forEach((section) => {
    if (section.targets.some((target) => target.getBoundingClientRect().top <= marker)) current = section;
  });
  document.querySelectorAll(".side-nav a").forEach((link) => {
    const active = link.getAttribute("href") === current.hash;
    link.classList.toggle("active", active);
    if (active) link.setAttribute("aria-current", "location");
    else link.removeAttribute("aria-current");
  });
}

function scheduleNavigationUpdate() {
  if (!navigationFrame) navigationFrame = window.requestAnimationFrame(updateActiveNavigation);
}

function renderCells(data) {
  const cellNames = [...new Set(data.map((r) => r.id_celula))].sort();
  const latestByCell = cellNames.map((name) => data.filter((r) => r.id_celula === name).at(-1));
  $("#cell-count").textContent = `${latestByCell.length} células`;
  $("#cell-table").innerHTML = latestByCell.map((r) => {
    const outside = Object.entries(physicalLimits).filter(([key, [min, max]]) => r[key] !== null && (r[key] < min || r[key] > max));
    const status = outside.length ? `<span class="condition attention"><i></i>Atenção</span>` : `<span class="condition ok"><i></i>Faixa física</span>`;
    const cell = `<strong class="cell-name">${r.id_celula}</strong><br><span class="cell-sub">${r.liga_metalica.replaceAll("_", " ")}</span>`;
    return `<tr><td>${cell}</td><td>${dateFormat.format(r.timestamp)}</td><td>${fmt(r.temperatura_fuso_c, 1)} °C</td><td>${fmt(r.vibracao_triaxial_rms_mms, 2)} mm/s</td><td>${fmt(r.vazao_refrigerante_lmin, 1)} L/min</td><td title="${outside.map(([key]) => sensors[key]?.name || key).join(", ")}">${status}</td></tr>`;
  }).join("");
}

function renderEvents(data) {
  const events = data.filter((r) => r.tipo_falha > 0).slice(-6).reverse();
  $("#events-list").innerHTML = events.map((r) => `<div class="event-row"><span class="event-icon">⌁</span><span class="event-copy"><strong>${labels[r.tipo_falha]}</strong><small>${r.id_celula} · ${r.liga_metalica.replaceAll("_", " ")}</small></span><span class="event-time">${dateFormat.format(r.timestamp)}</span></div>`).join("");
  $("#events-empty").classList.toggle("hidden", events.length > 0);
}

function fmt(value, digits = 1) { return value === null || !Number.isFinite(value) ? "—" : value.toFixed(digits).replace(".", ","); }
function setConnection(text, online) { const pill = $("#connection-pill"); pill.innerHTML = `<i></i>${text}`; pill.classList.toggle("online", online); }
function showToast(text) { const toast = $("#toast"); toast.textContent = text; toast.classList.add("show"); clearTimeout(toastTimer); toastTimer = setTimeout(() => toast.classList.remove("show"), 3600); }

async function probeApi() {
  const badge = $("#api-status");
  try {
    const response = await fetch(`${API_URL}/`, { signal: AbortSignal.timeout(1600) });
    if (!response.ok) throw new Error("API offline");
    apiConnected = true;
    badge.classList.remove("offline"); badge.classList.add("online"); badge.innerHTML = "<i></i>API conectada";
    $("#predict-button").disabled = false;
    $("#inspect-weld").disabled = !inspectionFiles.weld;
    $("#inspect-thermal").disabled = !inspectionFiles.thermal;
    if (!inspectionFiles.weld) $("#weld-result").textContent = "A decisão aparece após o envio da imagem.";
    if (!inspectionFiles.thermal) $("#thermal-result").textContent = "A decisão aparece após o envio da imagem.";
  } catch {
    apiConnected = false;
    badge.classList.remove("online"); badge.classList.add("offline"); badge.innerHTML = "<i></i>API não conectada";
    $("#predict-button").disabled = true;
    $("#inspect-weld").disabled = !inspectionFiles.weld;
    $("#inspect-thermal").disabled = !inspectionFiles.thermal;
    $("#weld-result").textContent = "Imagem pronta; inicie a API FastAPI para analisar.";
    $("#thermal-result").textContent = "Imagem pronta; inicie a API FastAPI para analisar.";
  }
}

function prepareUpload(inputId, previewId, key) {
  const input = $(inputId);
  input.addEventListener("change", () => {
    const file = input.files?.[0];
    if (!file) return;
    if (!file.type.startsWith("image/")) { showToast("Selecione um arquivo de imagem."); input.value = ""; return; }
    if (file.size > 12 * 1024 * 1024) { showToast("A imagem deve ter no máximo 12 MB."); input.value = ""; return; }
    inspectionFiles[key] = file;
    $(previewId).src = URL.createObjectURL(file);
    $(`#${key}-dropzone`).classList.add("has-image");
    $(`#${key}-empty`).classList.add("hidden");
    const button = $(key === "weld" ? "#inspect-weld" : "#inspect-thermal");
    button.textContent = key === "weld" ? "Analisar imagem" : "Analisar termografia";
    button.disabled = false;
    setInspectionStatus(key, apiConnected ? "Imagem recebida; análise iniciada." : "Imagem recebida; aguardando conexão com a API.");
    if (apiConnected) inspectImage(key);
  });
}

function setInspectionStatus(key, text, state = "") {
  const target = key === "weld" ? "#weld-result" : "#thermal-result";
  $(target).className = `inspection-result ${state}`;
  $(target).textContent = text;
}

async function inspectImage(key) {
  const file = inspectionFiles[key];
  if (!file) { showToast("Selecione uma imagem ou aguarde o carregamento da referência."); return; }
  const weld = key === "weld";
  const button = $(weld ? "#inspect-weld" : "#inspect-thermal");
  const resultBox = $(weld ? "#weld-result" : "#thermal-result");
  button.disabled = true;
  button.textContent = "Processando imagem…";
  resultBox.className = "inspection-result loading";
  resultBox.textContent = "Enviando para a API OpenCV…";
  const form = new FormData();
  form.append("imagem", file, file.name);
  const brightness = $("#thermal-threshold").value;
  const endpoint = weld ? "/inspecionar-solda" : `/inspecionar-termica?brilho_minimo=${brightness}`;
  try {
    const response = await fetch(`${API_URL}${endpoint}`, { method: "POST", body: form });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Não foi possível processar a imagem.");
    if (typeof data.aprovado !== "boolean" || data.versao_criterios !== "conservadora-2") throw new Error("Reinicie a API para carregar os critérios mais rigorosos de aprovação.");
    $(weld ? "#weld-preview" : "#thermal-preview").src = data.imagem_anotada;
    renderInspectionResult(key, data);
  } catch (error) {
    resultBox.className = "inspection-result error";
    resultBox.textContent = `${error.message} Verifique se a API e as dependências estão ativas.`;
  } finally {
    button.disabled = !inspectionFiles[key];
    button.innerHTML = weld ? 'Reanalisar imagem <b>→</b>' : 'Reanalisar termografia <b>→</b>';
  }
}

function renderInspectionResult(key, data) {
  const target = $(key === "weld" ? "#weld-result" : "#thermal-result");
  const approved = data.aprovado === true;
  target.className = `inspection-result ${approved ? "approved" : "rejected"}`;
  if (key === "weld") {
    const motivos = (data.motivos_reprovacao || []).map((motivo) => `<li>${motivo}</li>`).join("");
    target.innerHTML = `<strong>${approved ? "APROVADO" : "REPROVADO"}</strong><div class="inspection-metrics"><span><b>${data.candidatos_por_porosidade}</b> candidatos a poro</span><span><b>${data.continuidade_estimada_percentual}%</b> continuidade</span></div>${motivos ? `<ul class="inspection-reasons">${motivos}</ul>` : ""}<small>${data.observacao}</small>`;
  } else {
    const motivos = (data.motivos_reprovacao || []).map((motivo) => `<li>${motivo}</li>`).join("");
    target.innerHTML = `<strong>${approved ? "APROVADO" : "REPROVADO"}</strong><div class="inspection-metrics"><span><b>${data.cobertura_quente_percentual}%</b> área quente</span><span><b>${data.regioes_quentes}</b> regiões</span></div>${motivos ? `<ul class="inspection-reasons">${motivos}</ul>` : ""}<small>${data.observacao}</small>`;
  }
}

async function predictLatest() {
  const cell = $("#prediction-cell").value;
  const row = records.filter((r) => r.id_celula === cell).at(-1);
  if (!row) return showToast("Não há leitura recente para esta célula.");
  const payload = {
    id_celula: row.id_celula, liga_metalica: row.liga_metalica,
    temperatura_fuso_c: row.temperatura_fuso_c,
    vibracao_triaxial_rms_mms: row.vibracao_triaxial_rms_mms,
    torque_fuso_nm: row.torque_fuso_nm,
    vazao_refrigerante_lmin: row.vazao_refrigerante_lmin,
    corrente_estator_amp: row.corrente_estator_amp,
    pressao_hidraulica_bar: row.pressao_hidraulica_bar,
    nivel_ruido_db: row.nivel_ruido_db,
  };
  const button = $("#predict-button"), box = $("#prediction-result");
  button.disabled = true; button.innerHTML = "<span>⌁</span> Analisando leitura…";
  try {
    const response = await fetch(`${API_URL}/prever`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "Falha na inferência");
    box.className = "prediction-result has-result";
    box.innerHTML = `<div class="result-title">${result.diagnostico}</div><div class="result-copy">${result.acao_sugerida}</div>`;
  } catch (error) {
    box.className = "prediction-result has-error";
    box.innerHTML = `<div class="result-title">Inferência indisponível</div><div class="result-copy">${error.message}. Treine o modelo e mantenha a API ativa.</div>`;
  } finally {
    button.disabled = false; button.innerHTML = "<span>⌁</span> Analisar última leitura <b>→</b>";
  }
}

$("#cell-filter").addEventListener("change", render);
$("#alloy-filter").addEventListener("change", render);
$("#sensor-filter").addEventListener("change", render);
document.querySelectorAll(".segmented button").forEach((button) => button.addEventListener("click", () => {
  document.querySelector(".segmented .selected")?.classList.remove("selected");
  button.classList.add("selected");
  selectedDays = button.dataset.days === "all" ? "all" : Number(button.dataset.days);
  render();
}));
$("#refresh-button").addEventListener("click", loadData);
$("#theme-toggle").addEventListener("click", () => setTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark"));
$("#predict-button").addEventListener("click", predictLatest);
prepareUpload("#weld-file", "#weld-preview", "weld");
prepareUpload("#thermal-file", "#thermal-preview", "thermal");
$("#inspect-weld").addEventListener("click", () => inspectImage("weld"));
$("#inspect-thermal").addEventListener("click", () => inspectImage("thermal"));
$("#thermal-threshold").addEventListener("input", (event) => { $("#thermal-threshold-value").value = event.target.value; $("#thermal-threshold-value").textContent = event.target.value; });
window.addEventListener("resize", () => renderTrend(filteredRows()));
window.addEventListener("scroll", scheduleNavigationUpdate, { passive: true });
window.addEventListener("resize", scheduleNavigationUpdate);
updateActiveNavigation();
try { setTheme(localStorage.getItem("vulcantech-theme") || "light"); } catch { setTheme("light"); }
loadData();
