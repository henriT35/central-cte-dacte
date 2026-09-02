(() => {
  "use strict";

  const LOCAL_KEYS = {
    xmls: "central_cte_web_xmls_v1",
    invoices: "central_cte_web_invoices_v1",
    qa: "central_cte_web_qa_v1",
    settings: "central_cte_web_settings_v1",
    uploads: "central_cte_web_uploads_v1",
  };

  const DEFAULT_SETTINGS = {
    theme: "claro",
    density: "confortavel",
    sidebar: "padrao",
    start_page: "dashboard",
  };

  const state = {
    mode: "detecting",
    currentPage: "dashboard",
    bootstrap: null,
    app: { version: "RC27.14 WEB/WINDOWS MVP13 R12.13.8", engine_version: "RC26.6", project_root: "Modo navegador" },
    auth: { setup_required: false, authenticated: false, user: null, csrf: "", must_change_password: false, password_changed_at: "" },
    capabilities: {},
    developerFeatures: {},
    baseManagement: {},
    postgresIntegration: {},
    postgresComparison: null,
    postgresBridgeToken: "",
    systemHealth: null,
    adminUsers: [],
    backups: [],
    recoveryJobs: [],
    engine: { connected: false, status: "Ponte em preparação", ui_is_passive: true },
    processing: { xml: null, last_xml: {}, invoices: null, last_invoices: {}, dacte: null, last_dacte: {}, signature: null, last_signature: {} },
    xmls: [],
    invoices: [],
    invoiceFiles: [],
    partners: [],
    partnerRules: [],
    partnerTable: { path: null, error: "" },
    partnerFiles: [],
    reports: [],
    bases: [],
    signatures: [],
    qa: [],
    settings: { ...DEFAULT_SETTINGS },
    selectedPartner: null,
    selectedSignature: new Set(),
    selectedSignatureProfile: "",
    signatureSourceFile: null,
    signaturePdfImport: null,
    signatureCrop: { candidate: null, image: null, selection: null, drawing: false, start: null },
    dactePreview: { path: "", title: "", zoom: "FitH", signed: false, objectUrl: "" },
    complementaryTargetPaths: [],
    qaAttachmentPreviewUrl: "",
    invoiceFilePanelCollapsed: true,
    invoiceFilePanelTouched: false,
  };

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));
  const KONAMI_CODE = ["ArrowUp", "ArrowUp", "ArrowDown", "ArrowDown", "ArrowLeft", "ArrowRight", "ArrowLeft", "ArrowRight", "b", "a"];
  let konamiPosition = 0;

  const escapeHtml = (value) => String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");

  window.addEventListener("beforeunload", () => {
    const objectUrl = String(state.dactePreview?.objectUrl || "");
    if (objectUrl.startsWith("blob:")) URL.revokeObjectURL(objectUrl);
  });

  function isEditableTarget(target) {
    if (!(target instanceof Element)) return false;
    return Boolean(target.closest("input, textarea, select, [contenteditable='true']"));
  }

  function updateSpamtonAudioState(message = "") {
    const audio = $("#spamton-audio");
    const button = $("#spamton-audio-toggle");
    const status = $("#spamton-audio-status");
    if (!audio || !button || !status) return;
    const playing = !audio.paused && !audio.ended;
    button.textContent = playing ? "PAUSAR [MÚSICA]" : "TOCAR [MÚSICA]";
    status.textContent = message || (playing ? "REPRODUZINDO EM LOOP" : "MÚSICA PAUSADA");
  }

  async function playSpamtonAudio() {
    const audio = $("#spamton-audio");
    if (!audio) return;
    try {
      audio.volume = 0.78;
      await audio.play();
      updateSpamtonAudioState();
    } catch (error) {
      console.warn("O navegador bloqueou a reprodução automática do easter egg.", error);
      updateSpamtonAudioState("CLIQUE EM TOCAR PARA ATIVAR O ÁUDIO");
    }
  }

  function openSpamtonEasterEgg() {
    const page = $("#spamton-easter-egg");
    const audio = $("#spamton-audio");
    if (!page || !audio) return;
    page.classList.remove("hidden");
    page.setAttribute("aria-hidden", "false");
    document.documentElement.classList.add("spamton-active");
    audio.currentTime = 0;
    void playSpamtonAudio();
    window.setTimeout(() => $("#spamton-close")?.focus(), 0);
  }

  function closeSpamtonEasterEgg() {
    const page = $("#spamton-easter-egg");
    const audio = $("#spamton-audio");
    if (!page || page.classList.contains("hidden")) return;
    page.classList.add("hidden");
    page.setAttribute("aria-hidden", "true");
    document.documentElement.classList.remove("spamton-active");
    if (audio) {
      audio.pause();
      audio.currentTime = 0;
    }
    updateSpamtonAudioState();
  }

  function handleKonamiCode(event) {
    if (event.repeat || isEditableTarget(event.target)) return;
    const key = event.key.length === 1 ? event.key.toLowerCase() : event.key;
    const expected = KONAMI_CODE[konamiPosition];

    if (key === expected) {
      event.preventDefault();
      konamiPosition += 1;
      if (konamiPosition === KONAMI_CODE.length) {
        konamiPosition = 0;
        openSpamtonEasterEgg();
      }
      return;
    }

    konamiPosition = key === KONAMI_CODE[0] ? 1 : 0;
    if (konamiPosition === 1) event.preventDefault();
  }

  function localRead(key, fallback) {
    try {
      const raw = localStorage.getItem(key);
      return raw ? JSON.parse(raw) : fallback;
    } catch (_) {
      return fallback;
    }
  }

  function localWrite(key, value) {
    try {
      localStorage.setItem(key, JSON.stringify(value));
      return true;
    } catch (_) {
      return false;
    }
  }

  function formatMoney(value) {
    if (value === null || value === undefined || value === "") return "—";
    const number = Number(value);
    if (!Number.isFinite(number)) return "—";
    return new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(number);
  }

  function formatNumber(value) {
    if (value === null || value === undefined || value === "") return "—";
    const number = Number(value);
    return Number.isFinite(number) ? new Intl.NumberFormat("pt-BR").format(number) : "—";
  }

  function formatBytes(value) {
    const number = Number(value || 0);
    if (!number) return "0 B";
    const units = ["B", "KB", "MB", "GB"];
    const index = Math.min(Math.floor(Math.log(number) / Math.log(1024)), units.length - 1);
    return `${(number / (1024 ** index)).toLocaleString("pt-BR", { maximumFractionDigits: index ? 1 : 0 })} ${units[index]}`;
  }

  function formatDate(value) {
    if (!value) return "—";
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
  }

  function normalize(value) {
    return String(value ?? "")
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase();
  }

  function toneForStatus(status) {
    const text = normalize(status);
    if (/(erro|diverg|rejeit|recus|bloque|falha|critica)/.test(text)) return "danger";
    if (/(ok|aprov|liberad|conclu|ativo)/.test(text)) return "success";
    if (/(aguard|pend|atenc|futuro|revis|nao calculado)/.test(text)) return "warning";
    if (/(documento auxiliar|informativo)/.test(text)) return "purple";
    return "primary";
  }

  function badge(text, tone = null) {
    return `<span class="badge ${tone || toneForStatus(text)}" title="${escapeHtml(text)}">${escapeHtml(text || "Não informado")}</span>`;
  }

  function emptyRow(columns, message) {
    return `<tr class="empty-row"><td colspan="${columns}">${escapeHtml(message)}</td></tr>`;
  }

  function metricCard({ label, value, description, icon = "home.svg", tone = "primary" }) {
    return `<article class="metric-card ${tone}">
      <div class="metric-icon"><img src="icons/${icon}" alt=""></div>
      <div class="metric-copy"><small>${escapeHtml(label)}</small><strong>${escapeHtml(value)}</strong><span>${escapeHtml(description || "")}</span></div>
    </article>`;
  }

  function toast(title, message = "", tone = "primary", timeout = 4400) {
    const region = $("#toast-region");
    const item = document.createElement("div");
    item.className = `toast ${tone}`;
    item.innerHTML = `<strong>${escapeHtml(title)}</strong>${message ? `<span>${escapeHtml(message)}</span>` : ""}`;
    region.appendChild(item);
    window.setTimeout(() => item.remove(), timeout);
  }

  function setAuthError(message = "") {
    const box = $("#auth-error");
    box.textContent = message;
    box.classList.toggle("hidden", !message);
  }

  function showAuthGate(setupRequired = false) {
    state.auth.setup_required = Boolean(setupRequired);
    $("#app").classList.add("hidden");
    $("#auth-gate").classList.remove("hidden");
    $("#auth-display-name-wrap").classList.toggle("hidden", !setupRequired);
    $("#auth-confirm-wrap").classList.toggle("hidden", !setupRequired);
    $("#auth-title").textContent = setupRequired ? "Criar administrador inicial" : "Entrar no sistema";
    $("#auth-kicker").textContent = setupRequired ? "Primeiro acesso" : "Acesso local protegido";
    $("#auth-description").textContent = setupRequired
      ? "Defina o primeiro administrador. Depois você poderá cadastrar operadores e usuários de consulta."
      : "Use seu usuário e senha para acessar seu ambiente isolado.";
    $("#auth-submit").textContent = setupRequired ? "Criar administrador" : "Entrar";
    $("#auth-password").autocomplete = setupRequired ? "new-password" : "current-password";
    setAuthError("");
    window.setTimeout(() => $("#auth-username").focus(), 50);
  }

  function showApplication() {
    $("#auth-gate").classList.add("hidden");
    $("#app").classList.remove("hidden");
    const user = state.auth.user;
    const authenticated = Boolean(state.auth.authenticated && user);
    $("#user-chip").classList.toggle("hidden", !authenticated);
    $("#logout-button").classList.toggle("hidden", !authenticated || state.mode !== "server");
    if (authenticated) {
      $("#user-display-name").textContent = user.display_name || user.username || "Usuário";
      $("#user-role").textContent = user.role || "consulta";
      $("#user-avatar").textContent = String(user.display_name || user.username || "U").trim().charAt(0).toUpperCase();
      document.body.classList.toggle("role-consulta", user.role === "consulta");
      document.body.classList.toggle("role-desenvolvedor", user.role === "desenvolvedor");
      document.body.classList.toggle("role-admin", user.role === "admin");
    } else {
      document.body.classList.remove("role-consulta", "role-desenvolvedor", "role-admin");
    }
  }

  async function api(path, options = {}) {
    const controller = new AbortController();
    const timeoutMs = options.timeout || 9000;
    const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
    const method = String(options.method || "GET").toUpperCase();
    const headers = { ...(options.headers || {}) };
    if (state.auth.csrf && !["GET", "HEAD", "OPTIONS"].includes(method) && !path.startsWith("/api/auth/login") && !path.startsWith("/api/auth/setup")) {
      headers["X-CSRF-Token"] = state.auth.csrf;
    }
    try {
      const requestOptions = { ...options, method, headers, credentials: "same-origin", signal: controller.signal };
      delete requestOptions.timeout;
      const response = await fetch(path, requestOptions);
      const payload = await response.json().catch(() => ({}));
      if (!response.ok || payload.ok === false) {
        const error = new Error(payload.error || `Falha HTTP ${response.status}`);
        error.code = payload.code;
        error.status = response.status;
        error.requestId = payload.request_id;
        if (response.status === 401 && !path.startsWith("/api/auth/")) {
          state.auth = { setup_required: false, authenticated: false, user: null, csrf: "", must_change_password: false };
          showAuthGate(false);
        }
        if (error.code === "PASSWORD_CHANGE_REQUIRED") {
          state.auth.must_change_password = true;
          window.setTimeout(() => openOwnPasswordModal(true), 0);
        }
        throw error;
      }
      return payload;
    } finally {
      clearTimeout(timeout);
    }
  }

  async function loadAuthenticatedBootstrap() {
    const result = await api("/api/bootstrap", { timeout: 25000 });
    applyBootstrap(result.data);
    showApplication();
    if (!state.auth.must_change_password) await loadSecurityData(false);
  }

  async function detectMode() {
    const chip = $("#connection-chip");
    if (location.protocol === "file:") {
      state.mode = "browser-local";
      state.auth = { setup_required: false, authenticated: true, user: { username: "local", display_name: "Modo navegador", role: "operador" }, csrf: "" };
      chip.className = "connection-chip offline";
      chip.innerHTML = "<span></span>Modo navegador";
      loadBrowserState();
      showApplication();
      return true;
    }
    try {
      state.mode = "server";
      const authResult = await api("/api/auth/status", { timeout: 12000 });
      state.auth = { ...state.auth, ...(authResult.data || {}) };
      if (!state.auth.authenticated) {
        chip.className = "connection-chip warning";
        chip.innerHTML = "<span></span>Aguardando login";
        showAuthGate(Boolean(state.auth.setup_required));
        return false;
      }
      if (state.auth.must_change_password) {
        showApplication();
      } else {
        await loadAuthenticatedBootstrap();
      }
      chip.className = "connection-chip online";
      chip.innerHTML = "<span></span>Servidor seguro";
      return true;
    } catch (error) {
      state.mode = "browser-local";
      state.auth = { setup_required: false, authenticated: true, user: { username: "local", display_name: "Modo navegador", role: "operador" }, csrf: "" };
      chip.className = "connection-chip offline";
      chip.innerHTML = "<span></span>Modo navegador";
      loadBrowserState();
      showApplication();
      toast("Servidor local não respondeu", "A interface abriu no modo navegador. Os dados ficam apenas neste navegador.", "warning", 7000);
      return true;
    }
  }

  function applyBootstrap(data) {
    state.bootstrap = data;
    state.app = data.app || state.app;
    state.auth = { ...state.auth, ...(data.auth || {}) };
    state.capabilities = data.capabilities || data.auth?.capabilities || {};
    state.developerFeatures = data.developer_features || {};
    state.baseManagement = data.base_management || {};
    state.postgresIntegration = data.postgres_integration || {};
    state.engine = data.engine || state.engine;
    state.processing = data.processing || state.processing;
    state.xmls = Array.isArray(data.xmls) ? data.xmls : [];
    state.invoices = Array.isArray(data.invoices) ? data.invoices : [];
    state.invoiceFiles = Array.isArray(data.invoice_files) ? data.invoice_files : [];
    state.partners = Array.isArray(data.partners) ? data.partners : [];
    state.partnerRules = Array.isArray(data.partner_rules) ? data.partner_rules : [];
    state.partnerTable = data.partner_table || state.partnerTable;
    state.partnerFiles = Array.isArray(data.partner_files) ? data.partner_files : [];
    state.reports = Array.isArray(data.reports) ? data.reports : [];
    state.bases = Array.isArray(data.bases) ? data.bases : [];
    state.signatures = Array.isArray(data.signatures) ? data.signatures : [];
    state.qa = Array.isArray(data.qa) ? data.qa : [];
    state.settings = { ...DEFAULT_SETTINGS, ...(data.settings || {}) };
  }

  function loadBrowserState() {
    state.xmls = localRead(LOCAL_KEYS.xmls, []);
    state.invoices = localRead(LOCAL_KEYS.invoices, []);
    state.invoiceFiles = state.invoices.map((row, index) => ({
      id: `browser-${index}`, position: index + 1, file: row.file || row.invoice || "arquivo.pdf",
      size_bytes: row.size_bytes || 0, status: "received", stage: "intake", code: "RECEIVED",
      reason: "Arquivo registrado no navegador; o processamento exige o servidor local.",
      invoice_numbers: [], partners: [], received_at: row.modified_at || "", processed_at: "",
    }));
    state.qa = localRead(LOCAL_KEYS.qa, []);
    state.settings = { ...DEFAULT_SETTINGS, ...localRead(LOCAL_KEYS.settings, {}) };
    state.partners = [];
    state.partnerRules = [];
    state.reports = [];
    state.signatures = [];
    state.bases = localRead(LOCAL_KEYS.uploads, []).filter((item) => item.category === "bases");
    state.partnerTable = { path: null, error: "No modo navegador, a planilha fica registrada, mas a leitura XLSX exige o servidor local." };
    state.capabilities = { can_submit_qa: true, can_view_qa: false, can_view_infrastructure: false, is_developer: false, beta_enabled: false };
    state.developerFeatures = {};
    state.baseManagement = {};
  }

  async function refreshAll(showToast = true) {
    const button = $("#refresh-all");
    button.disabled = true;
    button.classList.add("spinning");
    try {
      if (state.mode === "server") {
        const result = await api("/api/bootstrap", { timeout: 20000 });
        applyBootstrap(result.data);
      } else {
        loadBrowserState();
      }
      applySettings(false);
      renderAll();
      if (showToast) toast("Dados atualizados", "A leitura local foi recarregada.", "success");
    } catch (error) {
      toast("Não foi possível atualizar", error.message, "danger");
    } finally {
      button.disabled = false;
      button.classList.remove("spinning");
    }
  }

  function applySettings(persist = false) {
    const settings = { ...DEFAULT_SETTINGS, ...state.settings };
    let theme = settings.theme;
    if (theme === "sistema") theme = window.matchMedia("(prefers-color-scheme: dark)").matches ? "escuro" : "claro";
    document.documentElement.dataset.theme = theme === "escuro" ? "dark" : "light";
    document.body.classList.toggle("density-compact", settings.density === "compacta");
    document.body.classList.toggle("sidebar-compact", settings.sidebar === "compacta");
    $("#sidebar").classList.toggle("compact", settings.sidebar === "compacta");
    $("#setting-theme").value = settings.theme;
    $("#setting-density").value = settings.density;
    $("#setting-sidebar").value = settings.sidebar;
    $("#setting-start-page").value = settings.start_page;
    if (persist && state.mode !== "server") localWrite(LOCAL_KEYS.settings, settings);
  }

  function navigate(page, push = true) {
    if (!$( `#page-${page}`)) page = "dashboard";
    state.currentPage = page;
    $$(".page").forEach((element) => element.classList.toggle("active", element.dataset.page === page));
    $$(".nav-item").forEach((element) => element.classList.toggle("active", element.dataset.page === page));
    if (push && location.protocol !== "file:") history.replaceState(null, "", `#${page}`);
    $("#sidebar").classList.remove("mobile-open");
    $("#mobile-overlay").classList.remove("open");
    renderPage(page);
    applyRolePermissions();
    window.scrollTo({ top: 0, behavior: "instant" });
  }

  function renderAll() {
    $("#nav-xml-count").textContent = String(state.xmls.length);
    $("#nav-invoice-count").textContent = String(state.invoiceFiles.length || state.invoices.length);
    const engineState = $("#engine-state");
    engineState.className = `engine-state ${state.engine.connected ? "success" : "warning"}`;
    engineState.innerHTML = `<span class="state-dot"></span><div><strong>Motor ${escapeHtml(state.app.engine_version || "RC26.6")}</strong><small>${escapeHtml(state.engine.connected ? "XML e faturas conectados" : "Serviços em preparação")}</small></div>`;
    renderDashboard();
    renderXml();
    renderInvoices();
    renderAudit();
    renderPartners();
    renderSignature();
    renderReports();
    renderSettings();
  }

  function renderPage(page) {
    const map = {
      dashboard: renderDashboard,
      xml: renderXml,
      invoices: renderInvoices,
      audit: renderAudit,
      partners: renderPartners,
      signature: renderSignature,
      reports: renderReports,
      settings: renderSettings,
    };
    map[page]?.();
  }

  function dashboardTotals() {
    const xmlTotal = state.xmls.reduce((sum, row) => sum + (Number(row.xml_value) || 0), 0);
    const invalid = state.xmls.filter((row) => normalize(row.status).includes("erro")).length;
    const waiting = state.xmls.filter((row) => normalize(row.status).includes("aguardando")).length;
    return { xmlTotal, invalid, waiting };
  }

  function renderDashboard() {
    const totals = dashboardTotals();
    const officialCalculated = state.xmls.filter((row) => row.expected_value !== null && row.expected_value !== undefined).length;
    const invoiceTotal = state.invoices.reduce((sum, row) => sum + (Number(row.total_value) || 0), 0);
    const cards = [
      { label: "XMLs carregados", value: formatNumber(state.xmls.length), description: `${totals.waiting} aguardando processamento`, icon: "file-search.svg", tone: "primary" },
      { label: "Validações oficiais", value: officialCalculated ? formatNumber(officialCalculated) : "—", description: officialCalculated ? "Resultados publicados pelo motor" : "Clique em Processar validação", icon: "check.svg", tone: officialCalculated ? "success" : "warning" },
      { label: "Erros de leitura", value: formatNumber(totals.invalid), description: "Falhas documentais detectadas", icon: "alert.svg", tone: totals.invalid ? "danger" : "success" },
      { label: "Valor XML lido", value: state.xmls.length ? formatMoney(totals.xmlTotal) : "—", description: "Soma documental, não valor aprovado", icon: "money.svg", tone: "primary" },
      { label: "PDFs de fatura", value: formatNumber(state.invoiceFiles.length || state.invoices.length), description: `${state.invoiceFiles.filter((row) => row.status === "rejected").length} rejeitado(s) · ${state.invoiceFiles.filter((row) => row.status === "duplicate").length} duplicado(s)`, icon: "file-invoice.svg", tone: state.invoiceFiles.some((row) => row.status === "rejected") ? "warning" : "purple" },
      { label: "Decisões financeiras", value: state.invoices.some((row) => row.payable_value !== null && row.payable_value !== undefined) ? formatMoney(state.invoices.reduce((sum, row) => sum + (Number(row.payable_value) || 0), 0)) : "—", description: state.engine.invoice_service_connected ? "Resultado oficial do motor" : "Aguardando serviço financeiro", icon: "money.svg", tone: state.invoices.some((row) => row.payable_value !== null && row.payable_value !== undefined) ? "success" : "warning" },
      { label: "Parceiros", value: state.partners.length ? formatNumber(state.partners.length) : "—", description: state.partnerTable.path ? "Tabela oficial carregada" : "Tabela não lida neste modo", icon: "users.svg", tone: "primary" },
    ];
    if (state.capabilities.can_view_qa) cards.push({ label: "Anotações QA", value: formatNumber(state.qa.length), description: `${state.qa.filter((item) => item.type === "bug").length} bug(s) registrado(s)`, icon: "alert.svg", tone: state.qa.length ? "warning" : "success" });
    $("#dashboard-cards").innerHTML = cards.map(metricCard).join("");

    const rows = state.xmls.slice(0, 8).map((row) => `<tr>
      <td><strong>${escapeHtml(row.cte || "—")}</strong></td><td title="${escapeHtml(row.partner)}">${escapeHtml(row.partner || "Não localizado")}</td><td>${escapeHtml(row.nf || row.proof || "Não localizado")}</td><td class="num">${formatMoney(row.xml_value)}</td><td>${badge(row.status)}</td>
    </tr>`).join("");
    $("#dashboard-xml-body").innerHTML = rows || emptyRow(5, "Nenhum XML carregado. Use “Importar XMLs” para iniciar o teste.");

    const readiness = [
      ["Interface web responsiva", "Oito telas reproduzidas no navegador", "done", "Pronto"],
      ["Servidor local seguro", "Login, CSRF, auditoria e sessão HttpOnly", state.mode === "server" && state.auth.authenticated ? "done" : "progress", state.mode === "server" && state.auth.authenticated ? "Ativo" : "Opcional"],
      ["Isolamento por usuário", "Uploads, resultados e assinaturas em workspaces separados", state.mode === "server" && state.app.workspace_id ? "done" : "progress", state.mode === "server" && state.app.workspace_id ? "Ativo" : "Pendente"],
      ["Importação documental", "XML e PDF com armazenamento local", "done", "Pronto"],
      ["Tabela de parceiros", "Leitura XLSX somente no servidor local", state.partners.length ? "done" : "progress", state.partners.length ? "Lida" : "Pendente"],
      ["Serviço XML oficial", "Parser, Base SSW e validador RC26.6 sem janela antiga", state.engine.xml_service_connected ? "done" : "progress", state.engine.xml_service_connected ? "Ativo" : "Pendente"],
      ["Serviço de faturas oficial", "Leitor PDF, Base SSW e decisão RC26.6 sem janela antiga", state.engine.invoice_service_connected ? "done" : "progress", state.engine.invoice_service_connected ? "Ativo" : "Pendente"],
      ["Relatórios XLSX oficiais", "XML e faturas gerados pelos consolidadores RC26.6", state.engine.report_service_connected ? "done" : "progress", state.engine.report_service_connected ? "Ativo" : "Pendente"],
      ["DACTE / PDF oficial", "Prévia, lote e arquivos individuais gerados pelo renderer RC26.6", state.engine.dacte_service_connected ? "done" : "progress", state.engine.dacte_service_connected ? "Ativo" : "Pendente"],
      ["Editor de assinatura", "Perfis, tratamento no navegador, posição e DACTE assinado", state.engine.signature_editor_connected ? "done" : "progress", state.engine.signature_editor_connected ? "Ativo" : "Pendente"],
      ["VPS", "Domínio ativo; operação manual com backup, restauração e recuperação segura", "progress", "Próxima fase"],
    ];
    $("#readiness-list").innerHTML = readiness.map(([title, description, status, label]) => `<div class="readiness-item ${status}"><div class="check-icon">${status === "done" ? "✓" : "…"}</div><div><strong>${escapeHtml(title)}</strong><small>${escapeHtml(description)}</small></div><em>${escapeHtml(label)}</em></div>`).join("");
  }

  function isXmlOk(row) {
    const status = normalize(row?.status || "").trim();
    return status === "ok" || status.startsWith("ok ") || status.startsWith("ok-") || status.startsWith("ok—");
  }

  function xmlHasManualDecision(row) {
    const manual = row?.manual_decision && typeof row.manual_decision === "object" ? row.manual_decision : {};
    return Boolean(String(manual.decision || "").trim());
  }

  function xmlAwaitsAuthorization(row) {
    const authorization = normalize(row?.authorization_status || "");
    return Boolean(row?.requires_manual_authorization) && (!authorization || authorization.includes("pendente"))
      || normalize(row?.status || "").includes("aguardando autorizacao");
  }

  function refreshXmlStatusFilterOptions() {
    const select = $("#xml-status-filter");
    if (!select) return;
    const selected = select.value;
    const aggregate = [
      ["", "Todos os status"],
      ["__not_ok__", "Não OK / requer atenção"],
      ["__ok__", "Somente OK"],
      ["__authorization_pending__", "Aguardando autorização"],
      ["__manual__", "Com baixa manual"],
    ];
    const exact = [...new Set(state.xmls.map((row) => String(row.status || "").trim()).filter(Boolean))]
      .sort((left, right) => left.localeCompare(right, "pt-BR", { sensitivity: "base" }));
    select.innerHTML = [
      ...aggregate.map(([value, label]) => `<option value="${escapeHtml(value)}">${escapeHtml(label)}</option>`),
      ...(exact.length ? ['<optgroup label="Status encontrados neste lote">', ...exact.map((value) => `<option value="${escapeHtml(value)}">${escapeHtml(value)}</option>`), '</optgroup>'] : []),
    ].join("");
    if ([...select.options].some((option) => option.value === selected)) select.value = selected;
  }

  function filteredXmlRows() {
    const query = normalize($("#xml-filter")?.value || "");
    const selectedStatus = $("#xml-status-filter")?.value || "";
    const normalizedStatus = normalize(selectedStatus);
    return state.xmls.map((row, sourceIndex) => ({ ...row, sourceIndex })).filter((row) => {
      const haystack = normalize([row.cte, row.series, row.partner, row.recipient, row.nf, row.city, row.status, row.document_type, row.file].join(" "));
      let statusMatches = true;
      if (selectedStatus === "__not_ok__") statusMatches = !isXmlOk(row);
      else if (selectedStatus === "__ok__") statusMatches = isXmlOk(row);
      else if (selectedStatus === "__authorization_pending__") statusMatches = xmlAwaitsAuthorization(row);
      else if (selectedStatus === "__manual__") statusMatches = xmlHasManualDecision(row);
      else if (selectedStatus) statusMatches = normalize(row.status) === normalizedStatus;
      return (!query || haystack.includes(query)) && statusMatches;
    });
  }

  function renderXml() {
    refreshXmlStatusFilterOptions();
    const rows = filteredXmlRows();
    const total = state.xmls.reduce((sum, row) => sum + (Number(row.xml_value) || 0), 0);
    const errors = state.xmls.filter((row) => toneForStatus(row.status) === "danger").length;
    const official = state.xmls.filter((row) => row.expected_value !== null && row.expected_value !== undefined).length;
    $("#xml-cards").innerHTML = [
      { label: "Documentos", value: formatNumber(state.xmls.length), description: "XMLs reconhecidos", icon: "file-search.svg", tone: "primary" },
      { label: "Leitura válida", value: formatNumber(state.xmls.length - errors), description: "Estrutura XML legível", icon: "check.svg", tone: "success" },
      { label: "Validação comercial", value: official ? formatNumber(official) : "—", description: official ? "Resultados oficiais" : "Pronta para processar", icon: "shield-search.svg", tone: official ? "success" : "warning" },
      { label: "Valor documental", value: state.xmls.length ? formatMoney(total) : "—", description: "Não representa aprovação", icon: "money.svg", tone: "primary" },
    ].map(metricCard).join("");

    const currentJob = state.processing?.xml;
    const lastRun = state.processing?.last_xml || state.engine?.last_run || {};
    const processingNotice = $("#xml-processing-status");
    if (currentJob && !["completed", "failed"].includes(currentJob.state)) {
      processingNotice.className = "notice warning";
      processingNotice.innerHTML = `<strong>Processamento em andamento:</strong> ${escapeHtml(currentJob.message || "Executando motor oficial")} · ${formatNumber(currentJob.processed || 0)}/${formatNumber(currentJob.total || 0)} (${escapeHtml(currentJob.percent || 0)}%)`;
    } else if (lastRun && lastRun.finished_at) {
      processingNotice.className = lastRun.errors ? "notice warning" : "notice success";
      processingNotice.innerHTML = `<strong>Última validação oficial:</strong> ${formatNumber(lastRun.processed || lastRun.total || 0)} documento(s), ${formatNumber(lastRun.ok || 0)} OK, ${formatNumber(lastRun.attention || 0)} para conferir e ${formatNumber(lastRun.errors || 0)} erro(s). Base: ${formatNumber(lastRun.base_row_count || 0)} registros.`;
    } else {
      processingNotice.className = state.engine.xml_service_connected ? "notice neutral" : "notice warning";
      processingNotice.innerHTML = state.engine.xml_service_connected
        ? "<strong>Serviço XML pronto:</strong> o processamento usa diretamente o parser, a Base SSW Web, a tabela de parceiros e o validador oficial RC26.6."
        : `<strong>Serviço XML indisponível:</strong> ${escapeHtml(state.engine.status || "Verifique os arquivos do motor.")}`;
    }

    $("#xml-selection-label").textContent = `${rows.length} de ${state.xmls.length} registro(s)`;
    $("#xml-table-body").innerHTML = rows.map((row) => `<tr data-xml-index="${row.sourceIndex}">
      <td><strong>${escapeHtml(row.cte || "—")}</strong></td><td>${escapeHtml(row.series || "—")}</td><td title="${escapeHtml(row.partner)}">${escapeHtml(row.partner || "Não localizado")}</td><td title="${escapeHtml(row.recipient)}">${escapeHtml(row.recipient || "Não localizado")}</td><td>${escapeHtml(row.nf || "Não localizado")}</td><td>${escapeHtml(row.city || "Não localizado")}</td><td>${escapeHtml(row.document_type || "Não calculado")}</td><td class="num">${formatMoney(row.xml_value)}</td><td class="num">${formatMoney(row.expected_value)}</td><td class="num">${formatMoney(row.difference)}</td><td title="Status automático: ${escapeHtml(row.automatic_status || row.status || "")}">${badge(row.status)}</td><td><button type="button" class="button compact" data-xml-detail-index="${row.sourceIndex}">${state.capabilities.can_override_xml_status ? "Revisar" : "Detalhes"}</button></td>
    </tr>`).join("") || emptyRow(12, state.xmls.length ? "Nenhum registro corresponde aos filtros." : "Nenhum XML carregado.");
  }

  function filteredInvoices() {
    const query = normalize($("#invoice-filter")?.value || "");
    return state.invoices.filter((row) => !query || normalize([
      row.invoice, row.partner, row.file, row.payment_status, ...(row.source_files || []),
    ].join(" ")).includes(query));
  }

  function invoiceFileStatusLabel(status) {
    const labels = {
      processed: "Processado",
      rejected: "Rejeitado",
      duplicate: "Duplicado — não contabilizado",
      processing: "Processando",
      received: "Aguardando",
    };
    return labels[String(status || "").toLowerCase()] || String(status || "Não informado");
  }

  function invoiceFileTone(status) {
    const value = String(status || "").toLowerCase();
    if (value === "processed") return "success";
    if (value === "rejected") return "danger";
    if (value === "duplicate") return "warning";
    if (value === "processing") return "primary";
    return "purple";
  }

  function setInvoiceFilePanelCollapsed(collapsed, { touched = false } = {}) {
    state.invoiceFilePanelCollapsed = Boolean(collapsed);
    if (touched) state.invoiceFilePanelTouched = true;
    const panel = $("#invoice-file-panel");
    const button = $("#toggle-invoice-file-panel");
    if (!panel || !button) return;
    panel.classList.toggle("collapsed", state.invoiceFilePanelCollapsed);
    button.setAttribute("aria-expanded", String(!state.invoiceFilePanelCollapsed));
    button.textContent = state.invoiceFilePanelCollapsed ? "Exibir detalhes" : "Minimizar";
  }

  function syncInvoiceFilePanel(rejected = 0, duplicates = 0) {
    if (!state.invoiceFilePanelTouched) {
      state.invoiceFilePanelCollapsed = !(rejected || duplicates);
    }
    setInvoiceFilePanelCollapsed(state.invoiceFilePanelCollapsed);
  }

  function renderInvoiceFiles() {
    const body = $("#invoice-file-table-body");
    if (!body) return;
    const order = { rejected: 0, duplicate: 1, processing: 2, received: 3, processed: 4 };
    const rows = [...state.invoiceFiles].sort((left, right) => {
      const statusOrder = (order[left.status] ?? 9) - (order[right.status] ?? 9);
      return statusOrder || Number(left.position || 0) - Number(right.position || 0);
    });
    const rejected = rows.filter((row) => row.status === "rejected").length;
    const duplicates = rows.filter((row) => row.status === "duplicate").length;
    const pending = rows.filter((row) => ["received", "processing"].includes(row.status)).length;
    $("#invoice-file-count").textContent = `${rows.length} PDF(s) · ${rejected} rejeitado(s) · ${duplicates} duplicado(s) · ${pending} pendente(s)`;
    syncInvoiceFilePanel(rejected, duplicates);
    body.innerHTML = rows.map((row) => {
      const invoices = [...(row.invoice_numbers || []), ...(row.invoice_keys || [])].filter(Boolean);
      const invoiceText = [...new Set(invoices)].join(", ") || "—";
      const reason = row.duplicate_of
        ? `${row.reason || "Duplicidade identificada."} Arquivo original mantido: ${row.duplicate_of}.`
        : (row.reason || "Sem detalhe informado.");
      const detail = row.financial_disposition ? `${reason} ${row.financial_disposition}` : reason;
      return `<tr class="invoice-file-row status-${escapeHtml(row.status || "received")}">
        <td><strong>${escapeHtml(row.file || "—")}</strong><small class="cell-subtitle">${formatBytes(row.size_bytes || 0)}</small></td>
        <td><span class="badge ${invoiceFileTone(row.status)}">${escapeHtml(invoiceFileStatusLabel(row.status))}</span></td>
        <td>${escapeHtml(row.stage || "—")}</td>
        <td>${escapeHtml(invoiceText)}</td>
        <td class="reason-cell" title="${escapeHtml(detail)}">${escapeHtml(detail)}</td>
        <td><code>${escapeHtml(row.code || "—")}</code></td>
      </tr>`;
    }).join("") || emptyRow(6, "Nenhum PDF de fatura carregado.");
  }

  function renderInvoices() {
    const rows = filteredInvoices();
    const fileRows = Array.isArray(state.invoiceFiles) ? state.invoiceFiles : [];
    const hasOfficial = state.invoices.some((row) => row.total_value !== null && row.total_value !== undefined);
    const total = state.invoices.reduce((sum, row) => sum + (Number(row.total_value) || 0), 0);
    const payable = state.invoices.reduce((sum, row) => sum + (Number(row.payable_value) || 0), 0);
    const retained = state.invoices.reduce((sum, row) => sum + (Number(row.retained_value) || 0), 0);
    const rejected = fileRows.filter((row) => row.status === "rejected").length;
    const duplicates = fileRows.filter((row) => row.status === "duplicate").length;
    const processedFiles = fileRows.filter((row) => row.status === "processed").length;
    const pendingFiles = fileRows.filter((row) => ["received", "processing"].includes(row.status)).length;
    const processing = state.processing?.invoices;
    const lastRun = state.processing?.last_invoices || state.engine.invoice_last_run || {};
    const processingNotice = $("#invoice-processing-status");
    if (processing && !["completed", "failed"].includes(processing.state)) {
      processingNotice.className = "notice primary";
      processingNotice.innerHTML = `<strong>Processamento em andamento:</strong> ${formatNumber(processing.processed || 0)} de ${formatNumber(processing.total || 0)} PDF(s). ${escapeHtml(processing.current_file || processing.message || "")}`;
    } else if (lastRun && (lastRun.uploaded_documents || lastRun.invoices || ["concluido", "concluido_com_alertas", "falhou"].includes(lastRun.status))) {
      const alertCount = Number(lastRun.rejected_files || 0) + Number(lastRun.duplicate_files || 0) + Number(lastRun.unprocessed_files || 0);
      processingNotice.className = lastRun.status === "falhou" ? "notice danger" : alertCount ? "notice warning" : "notice success";
      processingNotice.innerHTML = `<strong>Último lote:</strong> ${formatNumber(lastRun.uploaded_documents || fileRows.length || 0)} PDF(s) recebidos, ${formatNumber(lastRun.processed_files || 0)} processado(s), ${formatNumber(lastRun.rejected_files || 0)} rejeitado(s), ${formatNumber(lastRun.duplicate_files || 0)} duplicado(s) retirado(s) do cálculo e ${formatNumber(lastRun.unprocessed_files || 0)} não concluído(s). ${formatNumber(lastRun.invoices || 0)} fatura(s) identificada(s), ${formatMoney(lastRun.payable_value)} liberado.${lastRun.error ? ` <br><small>${escapeHtml(lastRun.error)}</small>` : ""}`;
    } else {
      processingNotice.className = state.engine.invoice_service_connected ? "notice neutral" : "notice warning";
      processingNotice.innerHTML = state.engine.invoice_service_connected
        ? "<strong>Serviço de faturas pronto:</strong> cada PDF será reconciliado individualmente e nenhum rejeitado desaparecerá do lote."
        : `<strong>Serviço de faturas indisponível:</strong> ${escapeHtml(state.engine.invoice_status || "Verifique a Base SSW e o leitor de PDF.")}`;
    }
    $("#invoice-cards").innerHTML = [
      { label: "PDFs recebidos", value: formatNumber(fileRows.length || state.invoices.length), description: `${processedFiles} processados · ${pendingFiles} pendentes`, icon: "file-invoice.svg", tone: "primary" },
      { label: "Faturas identificadas", value: formatNumber(hasOfficial ? state.invoices.length : 0), description: hasOfficial ? "Decisões oficiais publicadas" : "Aguardando o motor", icon: "check.svg", tone: hasOfficial ? "success" : "warning" },
      { label: "Rejeitados / duplicados", value: formatNumber(rejected + duplicates), description: `${rejected} erro(s) · ${duplicates} duplicado(s) fora do cálculo`, icon: "alert.svg", tone: rejected ? "danger" : duplicates ? "warning" : "success" },
      { label: "Valor total", value: hasOfficial ? formatMoney(total) : "—", description: hasOfficial ? "Total contabilizado" : "Aguardando decisão oficial", icon: "money.svg", tone: "primary" },
      { label: "Liberado", value: hasOfficial ? formatMoney(payable) : "—", description: "Decisão do motor", icon: "check.svg", tone: hasOfficial ? "success" : "warning" },
      { label: "Pendente", value: hasOfficial ? formatMoney(retained) : "—", description: "Futuro + problema interno", icon: "lock.svg", tone: retained > 0 ? "warning" : hasOfficial ? "success" : "warning" },
    ].map(metricCard).join("");
    $("#invoice-count").textContent = `${rows.length} fatura(s) identificada(s)`;
    $("#invoice-table-body").innerHTML = rows.map((row) => `<tr class="clickable" data-invoice-key="${escapeHtml(row.invoice_key || row.invoice || row.file)}">
      <td><strong>${escapeHtml(row.invoice || row.file)}</strong></td><td title="${escapeHtml(row.partner || "")}">${escapeHtml(row.partner || "Aguardando leitura")}</td><td>${formatNumber(row.item_count)}</td><td class="num">${formatMoney(row.total_value)}</td><td class="num">${formatMoney(row.payable_value)}</td><td class="num">${formatMoney(row.retained_value)}</td><td>${badge(row.payment_status)}</td><td title="${escapeHtml(row.financial_action || "")}">${escapeHtml(row.financial_action || "Não calculado")}</td>
    </tr>`).join("") || emptyRow(8, fileRows.length ? "Nenhuma fatura foi identificada pelo motor neste lote." : "Nenhuma fatura PDF carregada.");
    renderInvoiceFiles();
  }

  function auditRows() {
    const query = normalize($("#audit-filter")?.value || "");
    const view = $("#audit-view")?.value || "all";
    return state.xmls.map((row, sourceIndex) => ({
      ...row,
      sourceIndex,
      base_nf: row.base_nf || row.nf || "Não localizado",
      search_method: row.search_method || (row.error ? "Falha no parser XML" : "Aguardando validação"),
      partner_table: row.partner_table || (state.partners.length ? (row.partner || "Não localizado") : "Tabela não vinculada"),
      applied_rule: row.applied_rule || "Não calculado",
      calculation_base: row.calculation_base ?? null,
      percentage: row.percentage ?? null,
      operational_reason: row.operational_reason || row.error || "A validação comercial ainda não foi executada.",
      recommended_action: row.recommended_action || (row.error ? "Corrigir o XML e importar novamente." : ""),
    })).filter((row) => {
      const haystack = normalize([row.cte, row.base_nf, row.partner, row.status, row.operational_reason].join(" "));
      if (query && !haystack.includes(query)) return false;
      if (view === "missing") return !row.nf || row.nf === "Não localizado" || row.expected_value === null || row.expected_value === undefined;
      if (view === "errors") return toneForStatus(row.status) === "danger";
      if (view === "waiting") return normalize(row.status).includes("aguardando");
      return true;
    });
  }

  function renderAudit() {
    const rows = auditRows();
    const errors = state.xmls.filter((row) => toneForStatus(row.status) === "danger").length;
    const complete = state.xmls.filter((row) => row.nf && row.nf !== "Não localizado" && row.expected_value !== null && row.expected_value !== undefined).length;
    const missing = Math.max(state.xmls.length - complete, 0);
    const confidence = state.xmls.length ? (state.xmls.filter((row) => !row.error).length / state.xmls.length) * 100 : 0;
    $("#audit-cards").innerHTML = [
      { label: "Campos completos", value: formatNumber(complete), description: "Inclui resultado comercial", icon: "check.svg", tone: complete ? "success" : "warning" },
      { label: "Campos pendentes", value: formatNumber(missing), description: "Principalmente campos do motor", icon: "alert.svg", tone: missing ? "warning" : "success" },
      { label: "Erros documentais", value: formatNumber(errors), description: "Falhas de leitura XML", icon: "alert.svg", tone: errors ? "danger" : "success" },
      { label: "Confiabilidade da leitura", value: `${confidence.toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%`, description: "Somente parser documental", icon: "shield-search.svg", tone: "primary" },
    ].map(metricCard).join("");
    $("#audit-table-body").innerHTML = rows.map((row) => `<tr class="clickable" data-audit-index="${row.sourceIndex}" title="Clique para abrir os detalhes técnicos do CT-e">
      <td><strong>${escapeHtml(row.cte || "—")}</strong></td><td>${escapeHtml(row.base_nf)}</td><td>${escapeHtml(row.search_method)}</td><td>${escapeHtml(row.partner_table)}</td><td>${escapeHtml(row.applied_rule)}</td><td class="num">${formatMoney(row.calculation_base)}</td><td class="num">${row.percentage == null ? "—" : `${Number(row.percentage).toLocaleString("pt-BR", { maximumFractionDigits: 4 })}%`}</td><td class="num">${formatMoney(row.expected_value)}</td><td class="num">${formatMoney(row.difference)}</td><td>${badge(row.status)}</td><td title="${escapeHtml(row.operational_reason)}">${escapeHtml(row.operational_reason)}</td><td title="${escapeHtml(row.recommended_action)}">${escapeHtml(row.recommended_action)}</td>
    </tr>`).join("") || emptyRow(12, "Nenhum registro de auditoria disponível.");
  }

  function filteredPartners() {
    const query = normalize($("#partner-filter")?.value || "");
    return state.partners.filter((item) => !query || normalize([item.partner_id, item.name, item.alias, item.base_city, item.base_uf].join(" ")).includes(query));
  }

  function partnerRuleNeedsReview(status) {
    const value = normalize(status).replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
    if (!value || value === "nao_localizado") return false;
    const approved = new Set([
      "ok", "revisar_ok", "revisado_ok", "revisado", "validado", "conferido", "alias_ok",
    ]);
    if (approved.has(value) || value.endsWith("_ok")) return false;
    return /(pend|revis|alert|atenc|manual|erro|falha|incomplet)/.test(value);
  }

  function renderPartners() {
    const info = $("#partner-table-info");
    if (state.partnerTable.path) {
      info.className = "notice success";
      info.innerHTML = `<strong>Tabela oficial:</strong> ${escapeHtml(state.partnerTable.path)}${state.partnerTable.error ? ` — ${escapeHtml(state.partnerTable.error)}` : ""}`;
    } else {
      info.className = "notice warning";
      info.innerHTML = `<strong>Tabela ainda não disponível:</strong> ${escapeHtml(state.partnerTable.error || "Carregue a planilha oficial pelo fluxo de Validação XML.")}`;
    }
    const warnings = state.partnerRules.filter((rule) => rule.needs_review === true || (rule.needs_review == null && partnerRuleNeedsReview(rule.review_status))).length;
    const regions = new Set(state.partnerRules.map((rule) => rule.region).filter((value) => value && value !== "Não localizado"));
    $("#partner-cards").innerHTML = [
      { label: "Parceiros", value: state.partners.length ? formatNumber(state.partners.length) : "—", description: "Cadastros da tabela", icon: "users.svg", tone: "primary" },
      { label: "Regras", value: state.partnerRules.length ? formatNumber(state.partnerRules.length) : "—", description: "Regras percentuais", icon: "file-search.svg", tone: "purple" },
      { label: "Regiões", value: regions.size ? formatNumber(regions.size) : "—", description: "Bases distintas", icon: "folder.svg", tone: "primary" },
      { label: "Em revisão", value: formatNumber(warnings), description: "Pendências reais; status OK não entram", icon: "alert.svg", tone: warnings ? "warning" : "success" },
    ].map(metricCard).join("");

    const partners = filteredPartners();
    if (!state.selectedPartner && partners.length) state.selectedPartner = partners[0].partner_id;
    $("#partner-list").innerHTML = partners.map((item) => `<button class="partner-item ${item.partner_id === state.selectedPartner ? "active" : ""}" data-partner-id="${escapeHtml(item.partner_id)}"><strong>${escapeHtml(item.name)}</strong><span>${escapeHtml(item.partner_id)} · ${escapeHtml(item.alias || "Sem alias")}</span></button>`).join("") || `<div class="search-empty">Nenhum parceiro disponível.</div>`;

    const selected = state.partners.find((item) => item.partner_id === state.selectedPartner);
    const rules = state.partnerRules.filter((item) => !state.selectedPartner || item.partner_id === state.selectedPartner);
    $("#partner-rule-title").textContent = selected ? selected.name : "Regras comerciais";
    $("#partner-rule-subtitle").textContent = selected ? `${selected.partner_id} · ${selected.base_city || "Base não informada"} / ${selected.base_uf || "—"}` : "Selecione um parceiro.";
    $("#partner-rule-body").innerHTML = rules.map((rule) => `<tr>
      <td><strong>${escapeHtml(rule.rule_id)}</strong></td><td>${escapeHtml(rule.origin)}</td><td>${escapeHtml(rule.destination)}</td><td>${escapeHtml(rule.region)}</td><td class="num">${rule.percentage == null ? "—" : `${Number(rule.percentage).toLocaleString("pt-BR", { maximumFractionDigits: 4 })}%`}</td><td class="num">${formatMoney(rule.minimum)}</td><td>${escapeHtml(rule.calculation_base)}</td><td>${escapeHtml(rule.toll)}</td><td>${escapeHtml(rule.gris)}</td><td>${badge(rule.review_status)}</td>
    </tr>`).join("") || emptyRow(10, selected ? "Nenhuma regra encontrada para este parceiro." : "Selecione um parceiro.");

    const partnerFiles = $("#partner-file-list");
    if (partnerFiles) {
      partnerFiles.innerHTML = state.partnerFiles.length
        ? state.partnerFiles.map((item) => `<div class="operation-row partner-file-row"><div><strong>${escapeHtml(item.name || item.partner_id)}</strong><small>${escapeHtml(item.partner_id)} · ${formatNumber(item.rules || 0)} regra(s) · ${formatBytes(item.size_bytes)}</small></div><div class="compact-actions"><a class="text-button" href="/api/developer/partners/file?partner_id=${encodeURIComponent(item.partner_id)}">Baixar</a><button type="button" class="text-button danger-text" data-delete-partner-file="${escapeHtml(item.partner_id)}">Excluir</button></div></div>`).join("")
        : `<small>Nenhum arquivo separado de parceiro disponível.</small>`;
    }
  }

  function isOfficialCte(row) {
    const type = normalize(row?.engine_info?.tipo || "").replaceAll(" ", "");
    return Boolean(row?.path && row?.engine_info && row?.validation && (type === "ct-e" || type === "cte"));
  }

  function isCteCandidate(row) {
    if (!row?.cte) return false;
    const type = normalize(row.document_type || row.engine_info?.tipo || "");
    return !type.includes("nf-e") && !type.includes("documento auxiliar");
  }

  function selectedDacteRows() {
    const validPaths = new Set(state.xmls.filter(isOfficialCte).map((row) => String(row.path)));
    [...state.selectedSignature].forEach((path) => { if (!validPaths.has(String(path))) state.selectedSignature.delete(path); });
    return state.xmls.filter((row) => isOfficialCte(row) && state.selectedSignature.has(String(row.path)));
  }

  function updateDacteSelectionSummary() {
    const selected = selectedDacteRows();
    const summary = $("#signature-selection-summary");
    if (summary) {
      summary.textContent = selected.length
        ? `${selected.length} CT-e(s) selecionado(s): ${selected.slice(0, 4).map((row) => row.cte || "—").join(", ")}${selected.length > 4 ? "…" : ""}`
        : "Nenhum CT-e selecionado.";
    }
  }

  function currentSignatureProfile() {
    return state.signatures.find((profile) => String(profile.id) === String(state.selectedSignatureProfile)) || null;
  }

  function clampNumber(value, minimum, maximum, fallback = minimum) {
    const number = Number(value);
    if (!Number.isFinite(number)) return fallback;
    return Math.min(maximum, Math.max(minimum, number));
  }

  function defaultSignatureDate() {
    return new Date().toLocaleDateString("pt-BR");
  }

  function signatureLayoutPayload() {
    return {
      id: state.selectedSignatureProfile,
      name: $("#signature-profile-name")?.value.trim() || "",
      person_name: $("#signature-person-name")?.value.trim() || "",
      role: $("#signature-role")?.value.trim() || "",
      title: $("#signature-title")?.value.trim() || "REDESPACHO",
      threshold: Number($("#signature-threshold")?.value || 242),
      custom_x_mm: Number($("#signature-x")?.value || 117),
      custom_y_mm: Number($("#signature-y")?.value || 257),
      custom_width_mm: Number($("#signature-width")?.value || 85),
      custom_rotation_deg: Number($("#signature-rotation")?.value || 0),
      signature_scale_percent: Number($("#signature-scale")?.value || 100),
      signature_offset_x_mm: Number($("#signature-offset-x")?.value || 0),
      signature_offset_y_mm: Number($("#signature-offset-y")?.value || 0),
    };
  }

  function profileImageUrl(profile) {
    if (!profile?.processed_file || state.mode !== "server") return "";
    return `/api/file?path=${encodeURIComponent(profile.processed_file)}&inline=1&v=${encodeURIComponent(profile.processed_sha256 || profile.updated_at || Date.now())}`;
  }

  function blobToDataUrl(blob) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result || ""));
      reader.onerror = () => reject(new Error("Não foi possível ler a imagem tratada da assinatura."));
      reader.readAsDataURL(blob);
    });
  }

  const signaturePreviewDataUrlCache = new Map();

  async function signatureImageDataUrl(profile) {
    if (!profile?.ready) return "";
    const key = String(profile.processed_sha256 || profile.updated_at || profile.id || "");
    if (key && signaturePreviewDataUrlCache.has(key)) return signaturePreviewDataUrlCache.get(key);
    const response = await fetch(profileImageUrl(profile), {
      credentials: "same-origin",
      cache: "no-store",
      headers: { Accept: "image/png,image/*;q=0.9,*/*;q=0.1" },
    });
    if (!response.ok) throw new Error(`Não foi possível carregar a assinatura tratada (HTTP ${response.status}).`);
    const dataUrl = await blobToDataUrl(await response.blob());
    if (key) signaturePreviewDataUrlCache.set(key, dataUrl);
    return dataUrl;
  }

  async function updateSignatureImagePreview(profile) {
    const container = $("#signature-image-preview");
    const solidStamp = $("#signature-stamp-solid");
    if (!container) return;
    const source = profile?.ready ? profileImageUrl(profile) : "";
    if (solidStamp) solidStamp.dataset.signatureDataUrl = "";
    if (source) {
      container.classList.remove("empty");
      container.innerHTML = `<img src="${source}" alt="Assinatura tratada de ${escapeHtml(profile.person_name || profile.name || "perfil")}"><small>${escapeHtml(profile.person_name || "Responsável não informado")} · imagem pronta</small>`;
    } else {
      container.classList.add("empty");
      container.innerHTML = `<img src="icons/signature.svg" alt=""><span>Nenhuma assinatura importada.</span>`;
    }
    updateSignatureEditorVisual();
    if (!source || !profile) return;
    try {
      const dataUrl = await signatureImageDataUrl(profile);
      if (String(currentSignatureProfile()?.id || "") !== String(profile.id || "")) return;
      if (solidStamp) solidStamp.dataset.signatureDataUrl = dataUrl;
      updateSignatureEditorVisual();
    } catch (error) {
      console.error("Falha ao montar a prévia sólida do carimbo:", error);
      if (solidStamp) solidStamp.dataset.signatureDataUrl = "";
      updateSignatureEditorVisual();
    }
  }

  function escapeSvgText(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/\"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function buildSignatureStampPreviewDataUri({ imageUrl = "", title = "REDESPACHO", dateText = "", scalePercent = 100, offsetXmm = 0, offsetYmm = 0 } = {}) {
    const safeTitle = escapeSvgText(String(title || "REDESPACHO").toUpperCase().slice(0, 40));
    const safeDate = escapeSvgText(String(dateText || "").slice(0, 20));
    const safeImage = escapeSvgText(String(imageUrl || ""));
    const clampedScalePercent = clampNumber(scalePercent, 40, 250, 100);
    const scale = clampedScalePercent / 100;
    const xMm = clampNumber(offsetXmm, -15, 15, 0);
    const yMm = clampNumber(offsetYmm, -15, 15, 0);
    const offsetX = xMm * (1000 / 85);
    const offsetY = yMm * (376 / 32);
    const centerX = 560;
    const centerY = 230;
    const imageTag = safeImage
      ? `<g transform="translate(${offsetX.toFixed(2)} ${offsetY.toFixed(2)}) translate(${centerX.toFixed(2)} ${centerY.toFixed(2)}) scale(${scale.toFixed(4)}) translate(${-centerX.toFixed(2)} ${-centerY.toFixed(2)})"><image href="${safeImage}" x="165" y="128" width="790" height="204" preserveAspectRatio="xMidYMid meet"/></g>`
      : "";
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="376" viewBox="0 0 1000 376"><rect x="7" y="7" width="986" height="362" fill="white" fill-opacity="0.96" stroke="#111" stroke-width="5"/><text x="500" y="101" text-anchor="middle" font-family="Arial, sans-serif" font-size="88" font-weight="800" fill="#111">${safeTitle}</text><text x="500" y="151" text-anchor="middle" font-family="Arial, sans-serif" font-size="48" font-weight="700" fill="#111">${safeDate}</text><text x="35" y="323" font-family="Arial, sans-serif" font-size="52" font-weight="800" fill="#111">Ass:</text><line x1="160" y1="313" x2="955" y2="313" stroke="#111" stroke-width="4"/>${imageTag}</svg>`;
    return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
  }

  function updateSignatureEditorVisual() {
    const page = $("#signature-editor-page");
    const stamp = $("#signature-stamp-box");
    if (!page || !stamp) return;
    const x = clampNumber($("#signature-x")?.value, -15, 195, 117);
    const y = clampNumber($("#signature-y")?.value, -15, 285, 257);
    const width = clampNumber($("#signature-width")?.value, 42, 96, 85);
    const rotation = clampNumber($("#signature-rotation")?.value, -30, 30, 0);
    stamp.style.left = `${(x / 210) * 100}%`;
    stamp.style.top = `${(y / 297) * 100}%`;
    stamp.style.width = `${(width / 210) * 100}%`;
    stamp.style.transform = `rotate(${rotation}deg)`;
    const image = $("#signature-stamp-solid");
    if (image) {
      const previewSource = String(image.dataset.signatureDataUrl || "");
      const scalePercent = clampNumber($("#signature-scale")?.value, 40, 250, 100);
      const offsetX = clampNumber($("#signature-offset-x")?.value, -15, 15, 0);
      const offsetY = clampNumber($("#signature-offset-y")?.value, -15, 15, 0);
      image.src = buildSignatureStampPreviewDataUri({
        imageUrl: previewSource,
        title: $("#signature-title")?.value || "REDESPACHO",
        dateText: $("#signature-date-text")?.value || defaultSignatureDate(),
        scalePercent,
        offsetXmm: offsetX,
        offsetYmm: offsetY,
      });
    }
  }

  function loadSignatureProfileForm(profile) {
    const values = profile || {};
    $("#signature-profile-name").value = values.name || "";
    $("#signature-person-name").value = values.person_name || "";
    $("#signature-role").value = values.role || "";
    $("#signature-title").value = values.title || "REDESPACHO";
    $("#signature-threshold").value = String(values.threshold ?? 242);
    $("#signature-threshold-value").textContent = String(values.threshold ?? 242);
    $("#signature-x").value = String(values.custom_x_mm ?? 117);
    $("#signature-y").value = String(values.custom_y_mm ?? 257);
    $("#signature-width").value = String(values.custom_width_mm ?? 85);
    $("#signature-rotation").value = String(values.custom_rotation_deg ?? 0);
    $("#signature-scale").value = String(values.signature_scale_percent ?? 100);
    $("#signature-offset-x").value = String(values.signature_offset_x_mm ?? 0);
    $("#signature-offset-y").value = String(values.signature_offset_y_mm ?? 0);
    if (!$("#signature-date-text").value) $("#signature-date-text").value = defaultSignatureDate();
    updateSignatureImagePreview(profile);
    updateSignatureEditorVisual();
  }

  function renderSignatureProfiles() {
    const select = $("#signature-profile-select");
    if (!select) return;
    const previous = state.selectedSignatureProfile;
    if (previous && !state.signatures.some((profile) => String(profile.id) === String(previous))) state.selectedSignatureProfile = "";
    if (!state.selectedSignatureProfile && state.signatures.length) state.selectedSignatureProfile = String(state.signatures[0].id);
    select.innerHTML = state.signatures.length
      ? state.signatures.map((profile) => `<option value="${escapeHtml(profile.id)}" ${String(profile.id) === String(state.selectedSignatureProfile) ? "selected" : ""}>${escapeHtml(profile.name)} — ${escapeHtml(profile.person_name)}${profile.ready ? " · pronta" : " · sem imagem"}</option>`).join("")
      : `<option value="">Nenhum perfil cadastrado</option>`;
    select.value = state.selectedSignatureProfile || "";
    loadSignatureProfileForm(currentSignatureProfile());
  }

  function signatureFilterOptionValues(field) {
    const values = state.xmls
      .filter(isCteCandidate)
      .map((row) => String(row?.[field] || "").trim())
      .filter((value) => value && normalize(value) !== "nao localizado");
    return [...new Set(values)].sort((a, b) => a.localeCompare(b, "pt-BR", { sensitivity: "base", numeric: true }));
  }

  function refreshSignatureDynamicFilterOptions() {
    const sync = (selector, values, allLabel) => {
      const select = $(selector);
      if (!select) return;
      const previous = select.value || "all";
      select.innerHTML = [`<option value="all">${escapeHtml(allLabel)}</option>`, ...values.map((value) => `<option value="${escapeHtml(value)}">${escapeHtml(value)}</option>`)].join("");
      select.value = [...select.options].some((option) => option.value === previous) ? previous : "all";
    };
    sync("#signature-partner-filter", signatureFilterOptionValues("partner"), "Todos os parceiros");
    sync("#signature-city-filter", signatureFilterOptionValues("city"), "Todos os destinos");

    const resultSelect = $("#signature-result-filter");
    if (resultSelect) {
      const previous = resultSelect.value || "all";
      const aggregate = [
        ["all", "Todos os resultados"],
        ["__ok__", "Somente OK"],
        ["__not_ok__", "Não OK / requer atenção"],
        ["__authorization_pending__", "Aguardando autorização"],
        ["__manual__", "Com baixa manual"],
      ];
      const exact = [...new Set(state.xmls.filter(isCteCandidate).map((row) => String(row.status || "").trim()).filter(Boolean))]
        .sort((a, b) => a.localeCompare(b, "pt-BR", { sensitivity: "base", numeric: true }));
      resultSelect.innerHTML = [
        ...aggregate.map(([value, label]) => `<option value="${value}">${escapeHtml(label)}</option>`),
        ...exact.map((value) => `<option value="${escapeHtml(value)}">${escapeHtml(value)}</option>`),
      ].join("");
      resultSelect.value = [...resultSelect.options].some((option) => option.value === previous) ? previous : "all";
    }
  }

  function signatureResultMatches(row, filter) {
    if (!filter || filter === "all") return true;
    if (filter === "__ok__") return isXmlOk(row);
    if (filter === "__not_ok__") return !isXmlOk(row);
    if (filter === "__authorization_pending__") return xmlAwaitsAuthorization(row);
    if (filter === "__manual__") return xmlHasManualDecision(row);
    return String(row.status || "") === filter;
  }

  function signatureSortCandidates(items, mode) {
    const numericCte = (row) => Number(String(row?.cte || "").replace(/\D+/g, "")) || 0;
    const textCompare = (a, b) => String(a || "").localeCompare(String(b || ""), "pt-BR", { sensitivity: "base", numeric: true });
    const copy = [...items];
    copy.sort((a, b) => {
      if (mode === "cte_asc") return numericCte(a.row) - numericCte(b.row);
      if (mode === "partner") return textCompare(a.row.partner, b.row.partner) || numericCte(b.row) - numericCte(a.row);
      if (mode === "city") return textCompare(a.row.city, b.row.city) || numericCte(b.row) - numericCte(a.row);
      if (mode === "value_desc") return (Number(b.row.xml_value) || 0) - (Number(a.row.xml_value) || 0);
      if (mode === "value_asc") return (Number(a.row.xml_value) || 0) - (Number(b.row.xml_value) || 0);
      if (mode === "recent") return String(b.row.processed_at || b.row.modified_at || "").localeCompare(String(a.row.processed_at || a.row.modified_at || ""));
      return numericCte(b.row) - numericCte(a.row);
    });
    return copy;
  }

  function filteredSignatureCandidates() {
    const query = normalize($("#signature-filter")?.value || "");
    const status = $("#signature-status-filter")?.value || "ready";
    const partner = $("#signature-partner-filter")?.value || "all";
    const city = $("#signature-city-filter")?.value || "all";
    const result = $("#signature-result-filter")?.value || "all";
    const sortMode = $("#signature-sort-filter")?.value || "cte_desc";
    const filtered = state.xmls.map((row, index) => ({ row, index })).filter(({ row }) => {
      if (!isCteCandidate(row)) return false;
      const ready = isOfficialCte(row);
      const selected = ready && state.selectedSignature.has(String(row.path));
      if (status === "ready" && !ready) return false;
      if (status === "selected" && !selected) return false;
      if (status === "pending" && ready) return false;
      if (partner !== "all" && String(row.partner || "") !== partner) return false;
      if (city !== "all" && String(row.city || "") !== city) return false;
      if (!signatureResultMatches(row, result)) return false;
      if (!query) return true;
      const haystack = normalize([
        row.cte, row.numero, row.series, row.partner, row.recipient, row.nf, row.base_nf, row.city,
        row.status, row.automatic_status, row.authorization_status, row.charge_type, row.applied_rule,
        row.xml_value, row.expected_value, row.file,
      ].join(" "));
      return haystack.includes(query);
    });
    return signatureSortCandidates(filtered, sortMode);
  }

  function includeCompactBlock() {
    return $("#signature-include-compact")?.checked !== false;
  }

  function dacteJobIsActive(job) {
    return Boolean(job && !["completed", "failed", "discarded", "interrupted"].includes(String(job.state || "").toLowerCase()));
  }

  function renderDacteGenerationProgress(job = state.processing.dacte) {
    const panel = $("#dacte-generation-progress");
    if (!panel) return;
    if (!job) {
      panel.classList.add("hidden");
      panel.classList.remove("failed", "completed");
      return;
    }
    const stateName = String(job.state || "queued").toLowerCase();
    const percent = Math.max(0, Math.min(100, Number(job.percent || (stateName === "completed" ? 100 : 0))));
    const processed = Math.max(0, Number(job.processed || 0));
    const total = Math.max(0, Number(job.total || 0));
    const mode = String(job.mode || job.request?.mode || "batch").toLowerCase();
    panel.classList.remove("hidden", "failed", "completed");
    if (stateName === "failed") panel.classList.add("failed");
    if (stateName === "completed") panel.classList.add("completed");
    const title = stateName === "failed"
      ? "Falha na geração oficial"
      : stateName === "completed"
        ? "Geração oficial concluída"
        : mode === "individuals"
          ? "Gerando DACTEs oficiais individuais"
          : "Gerando lote oficial de DACTEs";
    $("#dacte-progress-title").textContent = title;
    $("#dacte-progress-percent").textContent = `${percent.toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%`;
    $("#dacte-progress-bar").style.width = `${percent}%`;
    panel.querySelector(".signature-progress-track")?.setAttribute("aria-valuenow", String(percent));
    $("#dacte-progress-count").textContent = total ? `${processed} de ${total} CT-e(s)` : "Preparando documentos";
    $("#dacte-progress-current").textContent = job.current_file || (stateName === "queued" ? "Na fila do motor" : "Processando…");
    $("#dacte-progress-message").textContent = job.error || job.message || "Gerando documentos oficiais.";
  }

  function updateDacteGenerationButtons(job = state.processing.dacte) {
    const active = dacteJobIsActive(job);
    const mode = String(job?.mode || job?.request?.mode || "").toLowerCase();
    const processed = Number(job?.processed || 0);
    const total = Number(job?.total || 0);
    const batch = $("#generate-dacte-batch");
    const individuals = $("#generate-dacte-individuals");
    if (batch) batch.innerHTML = active && mode === "batch"
      ? `<img src="icons/refresh.svg" alt="">Gerando ${processed}/${total}`
      : `<img src="icons/download.svg" alt="">Lote PDF`;
    if (individuals) individuals.innerHTML = active && mode === "individuals"
      ? `<img src="icons/refresh.svg" alt="">Gerando ${processed}/${total}`
      : `<img src="icons/folder.svg" alt="">Individuais`;
  }

  function signatureJobIsActive(job) {
    return Boolean(job && !["completed", "failed", "discarded", "interrupted"].includes(String(job.state || "").toLowerCase()));
  }

  function renderSignatureGenerationProgress(job = state.processing.signature) {
    const panel = $("#signature-generation-progress");
    if (!panel) return;
    if (!job) {
      panel.classList.add("hidden");
      panel.classList.remove("failed", "completed");
      return;
    }
    const stateName = String(job.state || "queued").toLowerCase();
    const percent = Math.max(0, Math.min(100, Number(job.percent || (stateName === "completed" ? 100 : 0))));
    const processed = Math.max(0, Number(job.processed || 0));
    const total = Math.max(0, Number(job.total || 0));
    const mode = String(job.mode || job.request?.mode || "batch").toLowerCase();
    panel.classList.remove("hidden", "failed", "completed");
    if (stateName === "failed") panel.classList.add("failed");
    if (stateName === "completed") panel.classList.add("completed");
    const title = stateName === "failed"
      ? "Falha na geração assinada"
      : stateName === "completed"
        ? "Geração assinada concluída"
        : mode === "individuals"
          ? "Gerando DACTEs assinados individuais"
          : "Gerando lote de DACTEs assinados";
    $("#signature-progress-title").textContent = title;
    $("#signature-progress-percent").textContent = `${percent.toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%`;
    $("#signature-progress-bar").style.width = `${percent}%`;
    const track = panel.querySelector(".signature-progress-track");
    track?.setAttribute("aria-valuenow", String(percent));
    $("#signature-progress-count").textContent = total ? `${processed} de ${total} CT-e(s)` : "Preparando documentos";
    $("#signature-progress-current").textContent = job.current_file || (stateName === "queued" ? "Na fila do motor" : "Processando…");
    $("#signature-progress-message").textContent = job.error || job.message || "Gerando documentos assinados.";
  }

  function updateSignatureGenerationButtons(job = state.processing.signature) {
    const active = signatureJobIsActive(job);
    const mode = String(job?.mode || job?.request?.mode || "").toLowerCase();
    const processed = Number(job?.processed || 0);
    const total = Number(job?.total || 0);
    const batch = $("#generate-signed-dacte-batch");
    const individuals = $("#generate-signed-dacte-individuals");
    if (batch) batch.innerHTML = active && mode === "batch"
      ? `<img src="icons/refresh.svg" alt="">Gerando ${processed}/${total}`
      : `<img src="icons/download.svg" alt="">Lote assinado`;
    if (individuals) individuals.innerHTML = active && mode === "individuals"
      ? `<img src="icons/refresh.svg" alt="">Gerando ${processed}/${total}`
      : `<img src="icons/folder.svg" alt="">Assinados (.zip)`;
  }

  function renderSignature() {
    const notice = $("#dacte-service-notice");
    const dacteConnected = state.mode === "server" && state.engine.dacte_service_connected;
    const signatureConnected = state.mode === "server" && state.engine.signature_editor_connected;
    if (notice) {
      notice.className = `notice ${dacteConnected && signatureConnected ? "success" : "warning"}`;
      notice.innerHTML = dacteConnected && signatureConnected
        ? `<strong>DACTE e assinatura visual conectados.</strong> Perfis: ${formatNumber(state.signatures.length)}. Tratamento: ${escapeHtml(state.engine.signature_image_backend || "Canvas do navegador")}. Conversão: ${escapeHtml((state.engine.dacte_conversion_backends || [state.engine.dacte_browser || "Edge/Chrome"]).join(", "))}.`
        : `<strong>Servidor local necessário.</strong> Abra pelo BAT, processe os XMLs e confirme Edge ou Chrome. A assinatura visual não funciona no modo arquivo local.`;
    }
    renderSignatureProfiles();
    renderSignaturePdfCandidates();
    refreshSignatureDynamicFilterOptions();
    const candidates = filteredSignatureCandidates();
    const readyVisible = candidates.filter(({ row }) => isOfficialCte(row)).length;
    const selectedVisible = candidates.filter(({ row }) => isOfficialCte(row) && state.selectedSignature.has(String(row.path))).length;
    const visibleCaption = $("#signature-visible-count");
    if (visibleCaption) visibleCaption.textContent = `${candidates.length} visível(is) · ${readyVisible} pronto(s) · ${selectedVisible} selecionado(s) neste filtro`;
    $("#signature-list").innerHTML = candidates.map(({ row, index }) => {
      const ready = isOfficialCte(row);
      const checked = ready && state.selectedSignature.has(String(row.path));
      const statusBadge = ready ? badge(row.status || "Processado") : `<span class="badge warning">Não processado</span>`;
      return `<label class="select-item signature-select-item ${ready ? "" : "disabled"}"><input type="checkbox" data-signature-index="${index}" ${checked ? "checked" : ""} ${ready ? "" : "disabled"}><div class="signature-select-content"><div class="signature-select-heading"><strong>CT-e ${escapeHtml(row.cte || "não identificado")}</strong><span>${formatMoney(row.xml_value)}</span></div><small>${escapeHtml(row.partner || "Não localizado")} · ${escapeHtml(row.city || "Destino não localizado")}</small><small>NF ${escapeHtml(row.nf || "—")} · ${escapeHtml(row.recipient || "Destinatário não localizado")}</small><div class="signature-select-badges"><span class="select-status badge ${ready ? "success" : "warning"}">${ready ? "Pronto para PDF" : "Processe a validação"}</span>${statusBadge}</div></div></label>`;
    }).join("") || `<div class="search-empty">Nenhum CT-e corresponde aos filtros atuais.</div>`;
    updateDacteSelectionSummary();
    const activeDacteJob = dacteJobIsActive(state.processing.dacte);
    const activeSignatureJob = signatureJobIsActive(state.processing.signature);
    [$("#generate-preview"), $("#generate-dacte-batch"), $("#generate-dacte-individuals")].forEach((button) => {
      if (button) button.disabled = !dacteConnected || activeDacteJob || activeSignatureJob;
    });
    const profileReady = Boolean(currentSignatureProfile()?.ready);
    [$("#generate-signed-preview"), $("#generate-signed-dacte-batch"), $("#generate-signed-dacte-individuals"), $("#download-signature-sheet"), $("#delete-signature-profile")].forEach((button) => {
      if (button) button.disabled = !signatureConnected || (!state.selectedSignatureProfile && button.id !== "generate-signed-preview");
    });
    [$("#generate-signed-preview"), $("#generate-signed-dacte-batch"), $("#generate-signed-dacte-individuals")].forEach((button) => {
      if (button) button.disabled = !signatureConnected || !profileReady || activeSignatureJob || activeDacteJob;
    });
    renderDacteGenerationProgress();
    updateDacteGenerationButtons();
    renderSignatureGenerationProgress();
    updateSignatureGenerationButtons();
  }

  function renderReports() {
    const notice = $("#report-service-notice");
    if (notice) {
      const connected = state.mode === "server" && state.engine.report_service_connected;
      notice.className = `notice ${connected ? "success" : "warning"}`;
      notice.innerHTML = connected
        ? `<strong>Serviço oficial conectado.</strong> Os XLSX são gerados pelos consolidadores RC26.6 a partir dos resultados já processados; a interface não recalcula valores.`
        : `<strong>Servidor local necessário.</strong> Abra pelo INICIAR_CENTRAL_CTE_WEB_LOCAL.bat e processe os documentos antes de gerar o XLSX oficial.`;
    }
    const allowed = state.capabilities.is_developer
      ? state.reports
      : state.reports.filter((row) => ["validacao xml", "faturas", "dacte / pdf", "relatorios operacionais"].includes(normalize(row.module)));
    $("#report-table-body").innerHTML = allowed.map((row) => `<tr><td><strong>${escapeHtml(row.name)}</strong></td><td>${escapeHtml(row.module)}</td><td>${badge(row.format, "primary")}</td><td>${formatDate(row.modified_at)}</td><td class="num">${formatBytes(row.size_bytes)}</td><td>${state.mode === "server" ? `<a class="text-button" href="/api/file?path=${encodeURIComponent(row.path)}">Baixar</a>` : ""}</td></tr>`).join("") || emptyRow(6, "Nenhum relatório operacional encontrado.");
  }

  function roleLabel(role) {
    return ({ desenvolvedor: "Desenvolvedor", admin: "Administrador", operador: "Operador", consulta: "Consulta" })[role] || role || "Não identificado";
  }

  function renderAdminUserRow(item, canEditUsers) {
    const statusTone = item.active === false ? "danger" : "success";
    const passwordBadge = item.must_change_password ? `<span class="badge warning">Troca de senha pendente</span>` : "";
    const sessions = Number(item.active_sessions || 0);
    const details = [
      item.last_login_at ? `Último acesso ${formatDate(item.last_login_at)}` : "Ainda não acessou",
      item.password_changed_at ? `Senha alterada ${formatDate(item.password_changed_at)}` : "Senha sem histórico",
      `${sessions} sessão(ões) ativa(s)`,
    ].join(" · ");
    return `<div class="admin-user-row">
      <div class="admin-user-identity"><strong>${escapeHtml(item.display_name || item.username)}</strong><small>@${escapeHtml(item.username)} · ${escapeHtml(details)}</small><div class="admin-user-badges">${passwordBadge}</div></div>
      <span class="role-pill">${escapeHtml(roleLabel(item.role))}</span>
      <span class="badge ${statusTone}">${item.active === false ? "Inativo" : "Ativo"}</span>
      ${canEditUsers ? `<button type="button" class="button compact" data-edit-user="${escapeHtml(item.id)}">Gerenciar</button>` : ""}
    </div>`;
  }

  function renderSecurity() {
    const summary = $("#security-summary");
    const user = state.auth.user || {};
    const health = state.systemHealth;
    const directoryOk = health?.directories ? Object.values(health.directories).every((item) => item.writable) : null;
    const freePercent = Number(health?.disk?.free_percent);
    const memoryBytes = Number(health?.process?.memory_bytes);
    summary.innerHTML = [
      ["Usuário", user.display_name || user.username || "Modo navegador", "ok"],
      ["Perfil", roleLabel(user.role), "ok"],
      ["Workspace isolado", state.app.workspace_id || (state.mode === "server" ? "Ativo" : "Somente navegador"), "ok"],
      ["Diretórios graváveis", directoryOk === null ? "Não verificado" : directoryOk ? "OK" : "Atenção", directoryOk === false ? "attention" : "ok"],
      ["Espaço livre", Number.isFinite(freePercent) ? `${freePercent.toFixed(1)}%` : "Não verificado", Number.isFinite(freePercent) && freePercent < 10 ? "attention" : "ok"],
      ["Memória do servidor", Number.isFinite(memoryBytes) && memoryBytes > 0 ? formatBytes(memoryBytes) : "Não disponível", "ok"],
      ["Sessão", state.mode === "server" ? "HttpOnly + CSRF" : "Sem servidor", "ok"],
    ].map(([label, value, tone]) => `<div class="security-status-row"><span>${escapeHtml(label)}</span><strong class="${tone}">${escapeHtml(value)}</strong></div>`).join("");

    const canBackups = state.mode === "server" && Boolean(state.capabilities.can_manage_backups);
    const canUsers = state.mode === "server" && Boolean(state.capabilities.can_manage_users);
    const canEditUsers = state.mode === "server" && Boolean(state.capabilities.can_edit_users);
    $("#create-backup").classList.toggle("hidden", !canBackups);
    $("#restore-backup").classList.toggle("hidden", !canBackups);
    $("#admin-users-card").classList.toggle("hidden", !canUsers);

    const backups = Array.isArray(state.backups) ? state.backups : [];
    $("#backup-history").innerHTML = backups.length
      ? `<h3>Backups recentes</h3>${backups.map((item) => `<div class="operation-row"><div><strong>${escapeHtml(item.name)}</strong><small>${escapeHtml(formatDate(item.created_at))} · ${formatBytes(item.size_bytes)} · ${formatNumber(item.files)} arquivo(s)</small></div><a class="text-button" href="/api/file?path=${encodeURIComponent(item.path)}">Baixar</a></div>`).join("")}`
      : `<small>Nenhum backup encontrado para este workspace.</small>`;

    const domain = health?.public_domain || {};
    const cloudflare = health?.cloudflare || {};
    const engine = health?.process?.engine || {};
    const operations = [
      ["Servidor local", state.mode === "server" ? "Online na porta 8765" : "Offline", state.mode === "server" ? "ok" : "attention"],
      ["Cloudflare Tunnel", cloudflare.running ? "Em execução" : cloudflare.detail || "Não verificado", cloudflare.running ? "ok" : "attention"],
      ["DNS público", domain.dns ? "Resolvido" : domain.error || "Não resolvido", domain.dns ? "ok" : "attention"],
      ["Domínio", domain.online ? `Online · HTTP ${domain.status} · ${domain.latency_ms || "—"} ms` : domain.error || "Indisponível", domain.online ? "ok" : "attention"],
      ["Motor RC26.6", engine.active ? `${engine.operation || "Em uso"} · ${engine.started_at ? formatDate(engine.started_at) : ""}` : "Livre", engine.active ? "attention" : "ok"],
      ["Fila global", `${formatNumber(engine.waiting || 0)} aguardando`, Number(engine.waiting || 0) ? "attention" : "ok"],
    ];
    $("#operations-monitor").innerHTML = operations.map(([label, value, tone]) => `<div class="security-status-row"><span>${escapeHtml(label)}</span><strong class="${tone}">${escapeHtml(value)}</strong></div>`).join("");

    const recoveries = Array.isArray(state.recoveryJobs) ? state.recoveryJobs : [];
    $("#recovery-job-list").innerHTML = recoveries.length
      ? recoveries.map((job) => `<div class="operation-row recovery-row"><div><strong>${escapeHtml(job.kind === "xml" ? "Validação XML" : job.kind === "dacte" ? "DACTE oficial" : job.kind === "signature" ? "DACTE assinado" : "Faturas")}</strong><small>${escapeHtml(job.message || job.error || "Execução interrompida")} · ${escapeHtml(formatDate(job.updated_at || job.created_at))}</small></div><div class="compact-actions"><button class="text-button" type="button" data-retry-job="${escapeHtml(job.id)}">Repetir</button><button class="text-button danger-text" type="button" data-discard-job="${escapeHtml(job.id)}">Descartar</button></div></div>`).join("")
      : `<small>Nenhuma execução interrompida ou recuperável.</small>`;

    const errors = Array.isArray(health?.recent_errors) ? health.recent_errors : [];
    if (errors.length) {
      $("#operations-monitor").insertAdjacentHTML("beforeend", `<div class="recent-errors"><h3>Erros recentes</h3>${errors.map((item) => `<div class="recent-error"><strong>${escapeHtml(item.action)}</strong><small>${escapeHtml(item.error)} · ${escapeHtml(formatDate(item.at))}</small></div>`).join("")}</div>`);
    }

    if (canUsers) {
      $("#admin-user-list").innerHTML = state.adminUsers.map((item) => renderAdminUserRow(item, canEditUsers)).join("") || `<div class="search-empty">Nenhum usuário cadastrado.</div>`;
    }
  }

  async function loadSecurityData(showToast = false) {
    if (state.mode !== "server" || !state.auth.authenticated) {
      state.systemHealth = null;
      state.adminUsers = [];
      renderSecurity();
      return;
    }
    try {
      const health = await api(`/api/system/health${showToast ? "?force=1" : ""}`, { timeout: 30000 });
      state.systemHealth = health.data || null;
      state.backups = Array.isArray(state.systemHealth?.backups) ? state.systemHealth.backups : [];
      state.recoveryJobs = Array.isArray(state.systemHealth?.recoverable_jobs) ? state.systemHealth.recoverable_jobs : [];
      if (state.capabilities.can_manage_users || state.capabilities.can_manage_backups) {
        const requests = [];
        requests.push(state.capabilities.can_manage_users ? api("/api/admin/users", { timeout: 12000 }) : Promise.resolve({ data: [] }));
        requests.push(state.capabilities.can_manage_backups ? api("/api/admin/backups", { timeout: 30000 }) : Promise.resolve({ data: [] }));
        const [users, backups] = await Promise.all(requests);
        state.adminUsers = Array.isArray(users.data) ? users.data : [];
        state.backups = Array.isArray(backups.data) ? backups.data : state.backups;
      } else {
        state.adminUsers = [];
      }
      renderSecurity();
      if (showToast) toast("Verificação concluída", "Sessão, diretórios e serviços foram conferidos.", "success");
    } catch (error) {
      renderSecurity();
      if (showToast) toast("Falha na verificação", error.message, "danger");
    }
  }

  function applyRolePermissions() {
    const readOnly = state.mode === "server" && state.auth.user?.role === "consulta";
    const caps = state.capabilities || {};
    const writeIds = [
      "add-xml", "add-xml-folder", "process-xml", "clear-xml-list", "add-complementary-info", "add-invoices", "process-invoices", "clear-invoice-list",
      "new-signature-profile", "save-signature-profile", "save-signature-layout", "restore-signature-layout", "delete-signature-profile",
      "download-signature-sheet", "upload-signature-image", "generate-preview", "generate-dacte-batch", "generate-dacte-individuals",
      "generate-signed-preview", "generate-signed-dacte-batch", "generate-signed-dacte-individuals", "generate-xml-xlsx",
      "generate-invoice-xlsx", "generate-invoice-problems-xlsx", "save-settings",
    ];
    writeIds.forEach((id) => {
      const element = $(`#${id}`);
      if (element) {
        element.disabled = readOnly;
        if (readOnly) element.title = "Perfil Consulta: acesso somente para leitura.";
      }
    });
    $$(".qa-submit-access").forEach((element) => element.classList.toggle("hidden", !caps.can_submit_qa));
    $$(".qa-view-access").forEach((element) => element.classList.toggle("hidden", !caps.can_view_qa));
    $$(".developer-only").forEach((element) => element.classList.toggle("hidden", !caps.is_developer));
    $("#dashboard-readiness-panel")?.classList.toggle("hidden", !caps.is_developer);
    $("#security-readiness-card")?.classList.toggle("hidden", !caps.can_view_security_readiness);
    $("#admin-users-card")?.classList.toggle("hidden", !caps.can_manage_users);
    $("#base-management-card")?.classList.toggle("hidden", !caps.can_import_base);
    $("#add-table")?.classList.toggle("hidden", !caps.can_manage_partner_tables);
    $("#developer-role-option")?.classList.toggle("hidden", !caps.can_create_developer);
    if ($("#open-qa")) $("#open-qa").disabled = !caps.can_submit_qa;
    if ($("#open-qa-settings")) $("#open-qa-settings").disabled = !caps.can_view_qa || readOnly;
  }

  async function submitAuthentication(event) {
    event.preventDefault();
    const setup = Boolean(state.auth.setup_required);
    const username = $("#auth-username").value.trim();
    const password = $("#auth-password").value;
    const displayName = $("#auth-display-name").value.trim();
    const confirmation = $("#auth-confirm-password").value;
    if (setup && password !== confirmation) {
      setAuthError("As duas senhas não são iguais.");
      return;
    }
    const button = $("#auth-submit");
    button.disabled = true;
    setAuthError("");
    try {
      const endpoint = setup ? "/api/auth/setup" : "/api/auth/login";
      const result = await api(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password, display_name: displayName }),
        timeout: 30000,
      });
      state.auth = { ...state.auth, ...(result.data || {}), setup_required: false };
      if (state.auth.must_change_password) {
        showApplication();
      } else {
        await loadAuthenticatedBootstrap();
        applySettings();
        renderAll();
        const startPage = state.settings.start_page || "dashboard";
        navigate(startPage, false);
      }
      const chip = $("#connection-chip");
      chip.className = "connection-chip online";
      chip.innerHTML = "<span></span>Servidor seguro";
      $("#auth-form").reset();
      ensurePasswordChangePrompt();
      if (state.auth.must_change_password) {
        toast("Troca de senha obrigatória", "Defina uma nova senha pessoal para continuar.", "warning", 7000);
      } else {
        toast(setup ? "Administrador criado" : "Acesso liberado", `Bem-vindo, ${state.auth.user?.display_name || state.auth.user?.username || "usuário"}.`, "success");
      }
    } catch (error) {
      setAuthError(error.message);
    } finally {
      button.disabled = false;
    }
  }

  async function logout() {
    try {
      await api("/api/auth/logout", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
    } catch (error) {
      console.warn(error);
    }
    state.auth = { setup_required: false, authenticated: false, user: null, csrf: "", must_change_password: false };
    state.systemHealth = null;
    state.adminUsers = [];
    showAuthGate(false);
    const chip = $("#connection-chip");
    chip.className = "connection-chip warning";
    chip.innerHTML = "<span></span>Aguardando login";
  }

  async function createAdminUser(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = Object.fromEntries(new FormData(form).entries());
    const button = form.querySelector("button[type='submit']");
    button.disabled = true;
    try {
      await api("/api/admin/users", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
        timeout: 30000,
      });
      form.reset();
      await loadSecurityData(false);
      toast("Usuário cadastrado", "O novo usuário recebeu um workspace isolado.", "success");
    } catch (error) {
      toast("Não foi possível cadastrar", error.message, "danger", 7000);
    } finally {
      button.disabled = false;
    }
  }

  function userSecuritySummaryHtml(user) {
    const rows = [
      ["Conta criada", formatDate(user.created_at)],
      ["Último acesso", user.last_login_at ? formatDate(user.last_login_at) : "Ainda não acessou"],
      ["Última alteração de senha", user.password_changed_at ? formatDate(user.password_changed_at) : "Sem histórico"],
      ["Sessões ativas", String(Number(user.active_sessions || 0))],
      ["Troca obrigatória", user.must_change_password ? "Pendente" : "Não"],
    ];
    return rows.map(([label, value]) => `<div><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`).join("");
  }

  function clearTemporaryPasswordResult() {
    $("#temporary-password-value").textContent = "";
    $("#temporary-password-result").classList.add("hidden");
  }

  function openUserEditModal(userId) {
    if (!state.capabilities.can_edit_users) return;
    const user = state.adminUsers.find((item) => String(item.id) === String(userId));
    if (!user) return toast("Usuário não encontrado", "Atualize a lista e tente novamente.", "warning");
    const form = $("#user-edit-form");
    form.reset();
    form.elements.user_id.value = user.id;
    form.elements.username.value = user.username || "";
    form.elements.display_name.value = user.display_name || user.username || "";
    form.elements.role.value = user.role || "consulta";
    form.elements.active.checked = user.active !== false;
    form.elements.must_change_password.checked = user.must_change_password !== false;
    $("#user-edit-security-summary").innerHTML = userSecuritySummaryHtml(user);
    const ownAccount = String(user.id) === String(state.auth.user?.id);
    $("#delete-user").disabled = ownAccount;
    $("#user-password-management").classList.toggle("hidden", ownAccount);
    [$("#reset-user-password"), $("#generate-temporary-password")].forEach((button) => { if (button) button.disabled = user.active === false; });
    $("#revoke-user-sessions").disabled = Number(user.active_sessions || 0) < 1;
    clearTemporaryPasswordResult();
    $("#user-edit-modal").classList.remove("hidden");
    window.setTimeout(() => form.elements.display_name.focus(), 50);
  }

  function closeUserEditModal() {
    $("#user-edit-modal").classList.add("hidden");
    $("#user-edit-form").reset();
    clearTemporaryPasswordResult();
  }

  async function saveUserEdit(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const payload = {
      user_id: form.elements.user_id.value,
      username: form.elements.username.value.trim(),
      display_name: form.elements.display_name.value.trim(),
      role: form.elements.role.value,
      active: form.elements.active.checked,
    };
    const button = form.querySelector("button[type='submit']");
    const editingSelf = String(payload.user_id) === String(state.auth.user?.id);
    const selfUsernameChanged = editingSelf && payload.username !== state.auth.user?.username;
    button.disabled = true;
    try {
      await api("/api/developer/users/update", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        timeout: 30000,
      });
      closeUserEditModal();
      if (selfUsernameChanged) {
        toast("Usuário atualizado", "Seu nome de acesso mudou. Entre novamente com o novo usuário.", "success", 7000);
        await logout();
        return;
      }
      await loadSecurityData(false);
      toast("Usuário atualizado", "Dados, perfil e situação da conta foram salvos.", "success");
    } catch (error) {
      toast("Não foi possível editar", error.message, "danger", 8000);
    } finally {
      button.disabled = false;
    }
  }

  function editedUserContext() {
    const form = $("#user-edit-form");
    const userId = form.elements.user_id.value;
    const user = state.adminUsers.find((item) => String(item.id) === String(userId));
    if (!user) throw new Error("Usuário não encontrado. Atualize a lista.");
    return { form, userId, user };
  }

  async function resetEditedUserPassword(generateTemporary = false) {
    let context;
    try { context = editedUserContext(); } catch (error) { return toast("Usuário não encontrado", error.message, "warning"); }
    const { form, userId, user } = context;
    if (String(userId) === String(state.auth.user?.id)) return toast("Use Minha conta", "Altere sua própria senha pelo botão do perfil no topo.", "warning", 6000);
    const password = form.elements.new_password.value;
    const confirmation = form.elements.confirm_password.value;
    if (!generateTemporary) {
      if (password !== confirmation) return toast("Senhas diferentes", "A confirmação da nova senha não corresponde.", "warning");
      if (password.length < 10) return toast("Senha inválida", "Informe pelo menos 10 caracteres, incluindo letra e número.", "warning");
    }
    const button = generateTemporary ? $("#generate-temporary-password") : $("#reset-user-password");
    button.disabled = true;
    try {
      const result = await api("/api/admin/users/password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_id: userId,
          password: generateTemporary ? "" : password,
          generate_temporary: generateTemporary,
          must_change_password: form.elements.must_change_password.checked,
        }),
        timeout: 30000,
      });
      if (generateTemporary) {
        $("#temporary-password-value").textContent = result.data?.temporary_password || "";
        $("#temporary-password-result").classList.remove("hidden");
      } else {
        form.elements.new_password.value = "";
        form.elements.confirm_password.value = "";
        clearTemporaryPasswordResult();
      }
      await loadSecurityData(false);
      const refreshed = state.adminUsers.find((item) => String(item.id) === String(userId));
      if (refreshed) $("#user-edit-security-summary").innerHTML = userSecuritySummaryHtml(refreshed);
      toast(generateTemporary ? "Senha temporária gerada" : "Senha redefinida", `As sessões de @${user.username} foram encerradas.`, "success", 7000);
    } catch (error) {
      toast("Não foi possível redefinir", error.message, "danger", 8000);
    } finally {
      button.disabled = false;
    }
  }

  async function copyTemporaryPassword() {
    const value = $("#temporary-password-value").textContent.trim();
    if (!value) return;
    try {
      await navigator.clipboard.writeText(value);
      toast("Senha copiada", "Compartilhe por um canal seguro e feche esta janela depois.", "success");
    } catch (_) {
      window.prompt("Copie a senha temporária:", value);
    }
  }

  async function revokeEditedUserSessions() {
    let context;
    try { context = editedUserContext(); } catch (error) { return toast("Usuário não encontrado", error.message, "warning"); }
    const { userId, user } = context;
    if (!window.confirm(`Encerrar todas as sessões abertas de @${user.username}?`)) return;
    const button = $("#revoke-user-sessions");
    button.disabled = true;
    try {
      await api("/api/developer/users/sessions/revoke", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ user_id: userId }), timeout: 30000,
      });
      await loadSecurityData(false);
      const refreshed = state.adminUsers.find((item) => String(item.id) === String(userId));
      if (refreshed) $("#user-edit-security-summary").innerHTML = userSecuritySummaryHtml(refreshed);
      toast("Sessões encerradas", `O usuário @${user.username} precisará entrar novamente.`, "success");
    } catch (error) {
      toast("Não foi possível encerrar", error.message, "danger", 8000);
    } finally {
      button.disabled = false;
    }
  }

  function setOwnPasswordError(message = "") {
    const box = $("#own-password-error");
    box.textContent = message;
    box.classList.toggle("hidden", !message);
  }

  function openOwnPasswordModal(forced = false) {
    if (!state.auth.authenticated || state.mode !== "server") return;
    const modal = $("#own-password-modal");
    const isForced = Boolean(forced || state.auth.must_change_password);
    modal.dataset.forced = isForced ? "1" : "0";
    $("#own-password-kicker").textContent = isForced ? "Ação obrigatória" : "Minha conta";
    $("#own-password-title").textContent = isForced ? "Atualize sua senha para continuar" : "Alterar minha senha";
    $("#own-password-description").textContent = isForced
      ? "Entre com a senha temporária atual e defina uma nova senha pessoal antes de acessar o sistema."
      : "Informe a senha atual e defina uma nova senha para sua conta.";
    $$(".own-password-close").forEach((button) => button.classList.toggle("hidden", isForced));
    $("#own-password-logout").classList.toggle("hidden", !isForced);
    $("#own-password-form").reset();
    setOwnPasswordError("");
    modal.classList.remove("hidden");
    window.setTimeout(() => $("#own-password-form").elements.current_password.focus(), 50);
  }

  function closeOwnPasswordModal() {
    const modal = $("#own-password-modal");
    if (modal.dataset.forced === "1" || state.auth.must_change_password) return;
    modal.classList.add("hidden");
    $("#own-password-form").reset();
    setOwnPasswordError("");
  }

  function ensurePasswordChangePrompt() {
    if (state.mode === "server" && state.auth.authenticated && state.auth.must_change_password) openOwnPasswordModal(true);
  }

  async function submitOwnPasswordChange(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const currentPassword = form.elements.current_password.value;
    const newPassword = form.elements.new_password.value;
    const confirmation = form.elements.confirm_password.value;
    if (newPassword !== confirmation) return setOwnPasswordError("A confirmação da nova senha não corresponde.");
    const button = form.querySelector("button[type='submit']");
    button.disabled = true;
    setOwnPasswordError("");
    try {
      const result = await api("/api/auth/password/change", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }), timeout: 30000,
      });
      state.auth = { ...state.auth, ...(result.data || {}), must_change_password: false };
      $("#own-password-modal").dataset.forced = "0";
      $("#own-password-modal").classList.add("hidden");
      form.reset();
      await loadAuthenticatedBootstrap();
      applySettings();
      renderAll();
      toast("Senha alterada", "As sessões anteriores foram encerradas e esta sessão foi renovada.", "success", 7000);
    } catch (error) {
      setOwnPasswordError(error.message);
    } finally {
      button.disabled = false;
    }
  }

  async function deleteEditedUser() {
    const userId = $("#user-edit-form").elements.user_id.value;
    const user = state.adminUsers.find((item) => String(item.id) === String(userId));
    if (!user) return;
    if (!window.confirm(`Excluir o usuário @${user.username}? A conta será removida, mas o workspace e os documentos permanecerão preservados.`)) return;
    const button = $("#delete-user");
    button.disabled = true;
    try {
      await api("/api/developer/users/delete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: userId }),
        timeout: 30000,
      });
      closeUserEditModal();
      await loadSecurityData(false);
      toast("Usuário excluído", "A conta foi arquivada e as sessões foram encerradas. O workspace foi preservado.", "success");
    } catch (error) {
      toast("Não foi possível excluir", error.message, "danger", 8000);
    } finally {
      button.disabled = false;
    }
  }

  async function createBackup() {
    const button = $("#create-backup");
    button.disabled = true;
    try {
      const result = await api("/api/admin/backup", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}", timeout: 180000 });
      const backup = result.data || {};
      toast("Backup criado", `${formatBytes(backup.size_bytes)} · ${formatNumber(backup.files)} arquivo(s).`, "success", 7000);
      if (backup.path) window.location.href = `/api/file?path=${encodeURIComponent(backup.path)}`;
    } catch (error) {
      toast("Falha ao criar backup", error.message, "danger", 8000);
    } finally {
      button.disabled = false;
    }
  }

  async function restoreBackupFile(file) {
    if (!file) return;
    if (!/\.zip$/i.test(file.name)) return toast("Arquivo inválido", "Selecione um backup ZIP criado pelo próprio sistema.", "warning");
    const confirmation = window.confirm("A restauração substituirá os XMLs, faturas, resultados, relatórios e assinaturas deste workspace. Um backup de emergência será criado antes. Deseja continuar?");
    if (!confirmation) return;
    const button = $("#restore-backup");
    button.disabled = true;
    try {
      const result = await api("/api/admin/backup/restore", {
        method: "POST",
        headers: { "Content-Type": "application/zip", "X-Filename": file.name },
        body: file,
        timeout: 15 * 60 * 1000,
      });
      toast("Backup restaurado", `${formatNumber(result.data?.files || 0)} arquivo(s) recuperados. A página será atualizada.`, "success", 9000);
      window.setTimeout(() => location.reload(), 1600);
    } catch (error) {
      toast("Falha na restauração", error.message, "danger", 10000);
    } finally {
      button.disabled = false;
      $("#restore-backup-file").value = "";
    }
  }

  async function recoverJob(jobId, action) {
    try {
      await api(`/api/jobs/${action}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ job_id: jobId }),
        timeout: 30000,
      });
      toast(action === "retry" ? "Processamento reiniciado" : "Registro descartado", action === "retry" ? "A execução entrou na fila segura do motor." : "O aviso foi removido.", "success");
      await loadSecurityData(false);
      if (action === "retry") beginPolling();
    } catch (error) {
      toast("Não foi possível atualizar a recuperação", error.message, "danger", 8000);
    }
  }

  function renderSettings() {
    const currentUser = state.auth.user || {};
    const accountSummary = $("#my-account-summary");
    if (accountSummary) {
      accountSummary.innerHTML = [
        ["Usuário", currentUser.username ? `@${currentUser.username}` : "Não identificado"],
        ["Nome", currentUser.display_name || "Não informado"],
        ["Perfil", roleLabel(currentUser.role)],
        ["Senha alterada", state.auth.password_changed_at ? formatDate(state.auth.password_changed_at) : "Sem histórico"],
      ].map(([label, value]) => `<div class="security-status-row"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`).join("");
    }
    const values = [
      ["Versão web", state.app.version || "RC27.14 WEB/WINDOWS MVP13 R12.13.8"],
      ["Motor oficial", state.app.engine_version || "RC26.6"],
      ["Modo de execução", state.mode === "server" ? "Servidor local HTTP" : "Navegador sem servidor"],
      ["Raiz do projeto", state.app.project_root || "Não disponível no navegador"],
      ["Segurança", state.mode === "server" ? "Login, CSRF e workspace por usuário" : "Arquivo local"],
      ["Serviço XML oficial", state.engine.xml_service_connected ? "Conectado" : "Indisponível"],
      ["Serviço de faturas", state.engine.invoice_service_connected ? "Conectado" : "Indisponível"],
      ["Relatórios XLSX oficiais", state.engine.report_service_connected ? "Conectado" : "Indisponível"],
      ["DACTE / PDF oficial", state.engine.dacte_service_connected ? "Conectado" : "Indisponível"],
      ["Assinatura visual", state.engine.signature_editor_connected ? `Conectada (${state.signatures.length} perfil(is))` : "Indisponível"],
      ["Tratamento da assinatura", state.engine.signature_image_backend || "Canvas do navegador"],
      ["Conversores PDF", (state.engine.dacte_conversion_backends || []).join(", ") || "Não localizado"],
    ];
    $("#environment-details").innerHTML = values.map(([key, value]) => `<div><dt>${escapeHtml(key)}</dt><dd>${escapeHtml(value)}</dd></div>`).join("");
    const counts = {
      bug: state.qa.filter((item) => item.type === "bug").length,
      melhoria: state.qa.filter((item) => item.type === "melhoria").length,
      open: state.qa.filter((item) => item.status !== "concluido").length,
      critical: state.qa.filter((item) => item.severity === "crítica").length,
    };
    if ($("#qa-summary")) $("#qa-summary").innerHTML = `<div class="qa-kpis"><div class="qa-kpi"><strong>${counts.bug}</strong><span>Bugs</span></div><div class="qa-kpi"><strong>${counts.melhoria}</strong><span>Melhorias</span></div><div class="qa-kpi"><strong>${counts.open}</strong><span>Em aberto</span></div><div class="qa-kpi"><strong>${counts.critical}</strong><span>Críticos</span></div></div>`;
    const qaList = $("#qa-note-list");
    if (qaList) {
      qaList.innerHTML = state.qa.length
        ? state.qa.slice(0, 80).map((item) => {
            const attachment = item.attachment;
            const evidence = attachment?.url
              ? `<a class="qa-note-attachment" href="${escapeHtml(attachment.url)}" target="_blank" rel="noopener"><img src="${escapeHtml(attachment.url)}" alt="Evidência anexada a ${escapeHtml(item.title || item.id)}"><span>${escapeHtml(attachment.name || "Abrir imagem")}</span></a>`
              : "";
            const details = [item.observed && `<div><b>Observado:</b> ${escapeHtml(item.observed)}</div>`, item.expected && `<div><b>Esperado:</b> ${escapeHtml(item.expected)}</div>`].filter(Boolean).join("");
            return `<article class="qa-note-item"><div class="qa-note-heading"><div><small>${escapeHtml(item.id || "QA")} · ${escapeHtml(item.page || "Geral")}</small><strong>${escapeHtml(item.title || "Sem título")}</strong></div><div>${badge(item.type || "item", item.type === "bug" ? "danger" : "primary")} ${badge(item.severity || "média", item.severity === "crítica" ? "danger" : "warning")}</div></div>${details ? `<div class="qa-note-details">${details}</div>` : ""}${evidence}<footer><span>${escapeHtml(item.created_by?.display_name || item.created_by?.username || "Usuário")}</span><span>${formatDate(item.updated_at || item.created_at)}</span><span>${escapeHtml(item.status || "aberto")}</span></footer></article>`;
          }).join("")
        : `<small class="settings-hint">Nenhum relato global registrado.</small>`;
    }
    const base = state.baseManagement || {};
    if ($("#base-management-summary")) {
      $("#base-management-summary").innerHTML = [
        ["Fonte ativa", base.source === "importada" ? "Base importada" : "Base embutida"],
        ["Arquivos ativos", formatNumber(base.active_file_count || 0)],
        ["Modo", base.replace_mode || "conjunto completo"],
      ].map(([label, value]) => `<div class="security-status-row"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`).join("") + `<small class="settings-hint">${escapeHtml(base.message || "")}</small>`;
    }
    renderPostgresIntegration();
    $$('[data-feature]').forEach((input) => { input.checked = Boolean(state.developerFeatures[input.dataset.feature]); });
    renderSecurity();
    applyRolePermissions();
  }

  let xmlTaskHideTimer = null;

  function updateXmlTaskProgress({ title = "Executando tarefa", percent = 0, processed = 0, total = 0, current = "", message = "", stateName = "running", autoHide = false } = {}) {
    const panel = $("#xml-task-progress");
    if (!panel) return;
    if (xmlTaskHideTimer) {
      window.clearTimeout(xmlTaskHideTimer);
      xmlTaskHideTimer = null;
    }
    const safePercent = Math.max(0, Math.min(100, Number(percent || 0)));
    panel.classList.remove("hidden", "completed", "failed");
    if (stateName === "completed") panel.classList.add("completed");
    if (stateName === "failed") panel.classList.add("failed");
    $("#xml-task-title").textContent = title;
    $("#xml-task-percent").textContent = `${safePercent.toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%`;
    $("#xml-task-bar").style.width = `${safePercent}%`;
    panel.querySelector(".signature-progress-track")?.setAttribute("aria-valuenow", String(safePercent));
    $("#xml-task-count").textContent = total ? `${processed} de ${total}` : (processed ? `${processed} concluído(s)` : "Preparando…");
    $("#xml-task-current").textContent = current || (stateName === "completed" ? "Concluído" : "Processando…");
    $("#xml-task-message").textContent = message || "Aguarde a conclusão da operação.";
    if (autoHide) {
      xmlTaskHideTimer = window.setTimeout(() => panel.classList.add("hidden"), stateName === "failed" ? 6500 : 2200);
    }
  }

  function hideXmlTaskProgress(delay = 0) {
    const panel = $("#xml-task-progress");
    if (!panel) return;
    if (xmlTaskHideTimer) window.clearTimeout(xmlTaskHideTimer);
    xmlTaskHideTimer = window.setTimeout(() => panel.classList.add("hidden"), Math.max(0, delay));
  }

  async function uploadFiles(category, files) {
    const list = Array.from(files || []);
    if (!list.length) return;
    let uploaded = 0;
    const duplicateFiles = [];
    const failedFiles = [];
    const showXmlProgress = category === "xml";
    if (showXmlProgress) {
      updateXmlTaskProgress({
        title: "Importando XMLs",
        percent: 0,
        processed: 0,
        total: list.length,
        current: list[0]?.name || "Preparando arquivos",
        message: "Validando e enviando os documentos para o workspace.",
      });
    }
    for (let index = 0; index < list.length; index += 1) {
      const file = list[index];
      if (showXmlProgress) {
        updateXmlTaskProgress({
          title: "Importando XMLs",
          percent: (index / list.length) * 100,
          processed: index,
          total: list.length,
          current: file.name,
          message: `Enviando arquivo ${index + 1} de ${list.length}.`,
        });
      }
      try {
        if (state.mode === "server") {
          await api("/api/upload", {
            method: "POST",
            body: file,
            timeout: 120000,
            headers: { "X-Category": category, "X-Filename": file.name, "Content-Type": "application/octet-stream" },
          });
        } else {
          await storeBrowserFile(category, file);
        }
        uploaded += 1;
      } catch (error) {
        if (category === "xml" && error.code === "DUPLICATE_XML") {
          duplicateFiles.push(file.name);
          toast("XML duplicado bloqueado", error.message, "warning", 7000);
        } else {
          failedFiles.push(file.name);
          toast(`Falha ao importar ${file.name}`, error.message, "danger", 6500);
        }
      }
      if (showXmlProgress) {
        updateXmlTaskProgress({
          title: "Importando XMLs",
          percent: ((index + 1) / list.length) * 100,
          processed: index + 1,
          total: list.length,
          current: file.name,
          message: `${uploaded} arquivo(s) recebido(s) até agora.`,
        });
      }
    }
    if (uploaded) await refreshAll(false);
    const duplicateCount = duplicateFiles.length;
    const failureCount = failedFiles.length;
    const summaryParts = [`${uploaded} recebido(s)`];
    if (duplicateCount) summaryParts.push(`${duplicateCount} duplicado(s) bloqueado(s)`);
    if (failureCount) summaryParts.push(`${failureCount} falha(s)`);
    toast(
      duplicateCount || failureCount ? "Importação concluída com alertas" : "Importação concluída",
      summaryParts.join(" · "),
      failureCount ? "warning" : duplicateCount ? "warning" : "success",
      6500,
    );
    if (showXmlProgress) {
      const completedCleanly = uploaded === list.length;
      const alertCount = duplicateCount + failureCount;
      updateXmlTaskProgress({
        title: completedCleanly ? "Importação concluída" : "Importação concluída com alertas",
        percent: 100,
        processed: uploaded,
        total: list.length,
        current: completedCleanly ? "Todos os XMLs foram recebidos" : `${alertCount} arquivo(s) não foram adicionados`,
        message: duplicateCount
          ? `${duplicateCount} XML(s) duplicado(s) foram bloqueados e não entrarão novamente no lote.${failureCount ? ` ${failureCount} arquivo(s) apresentaram outra falha.` : ""}`
          : "Os XMLs recebidos já estão disponíveis para a validação oficial.",
        stateName: failureCount ? "failed" : "completed",
        autoHide: true,
      });
    }
  }

  async function storeBrowserFile(category, file) {
    if (category === "xml") {
      const parsed = parseXmlText(await file.text(), file);
      const existing = localRead(LOCAL_KEYS.xmls, []);
      const identity = parsed.key || `${parsed.file}:${parsed.cte}:${parsed.xml_value}`;
      const duplicate = existing.find((item) => (item.key || `${item.file}:${item.cte}:${item.xml_value}`) === identity);
      if (duplicate) {
        const error = new Error(`O arquivo ${file.name} não foi adicionado porque corresponde a ${duplicate.file || "um XML já carregado"}${parsed.cte ? ` (CT-e ${parsed.cte})` : ""}.`);
        error.code = "DUPLICATE_XML";
        throw error;
      }
      existing.unshift(parsed);
      localWrite(LOCAL_KEYS.xmls, existing.slice(0, 1000));
      return;
    }
    if (category === "faturas") {
      const existing = localRead(LOCAL_KEYS.invoices, []);
      const row = {
        invoice: file.name.replace(/\.pdf$/i, ""), file: file.name, partner: "Aguardando leitura", item_count: null,
        total_value: null, payable_value: null, retained_value: null, payment_status: "Aguardando motor",
        financial_action: "Não calculado", size_bytes: file.size, modified_at: new Date(file.lastModified || Date.now()).toISOString(),
      };
      const next = existing.filter((item) => item.file !== file.name);
      next.unshift(row);
      localWrite(LOCAL_KEYS.invoices, next.slice(0, 500));
      return;
    }
    const existing = localRead(LOCAL_KEYS.uploads, []);
    existing.unshift({ category, name: file.name, size_bytes: file.size, modified_at: new Date(file.lastModified || Date.now()).toISOString() });
    localWrite(LOCAL_KEYS.uploads, existing.slice(0, 200));
    if (category === "tabelas") state.partnerTable = { path: file.name, error: "Planilha registrada. Inicie pelo servidor local para ler as regras XLSX." };
  }

  function xmlElements(root, name) {
    return Array.from(root.getElementsByTagName("*")).filter((element) => element.localName === name);
  }

  function xmlFirst(root, name) {
    return xmlElements(root, name)[0] || null;
  }

  function xmlChildText(parent, name) {
    if (!parent) return "";
    const child = Array.from(parent.children || []).find((element) => element.localName === name);
    return child?.textContent?.trim() || "";
  }

  function parseXmlText(raw, file) {
    const base = {
      file: file.name, path: file.name, source: "browser-local", cte: "", series: "", partner: "Não localizado", recipient: "Não localizado",
      nf: "Não localizado", city: "Não localizado", proof: "Não localizado", document_type: "Não calculado", charge_type: "Não calculado",
      xml_value: null, expected_value: null, difference: null, status: "Aguardando motor",
      diagnosis: "Documento lido no navegador. A validação comercial oficial ainda não foi executada.", compact_calculation: "Aguardando motor RC26.6.",
      modified_at: new Date(file.lastModified || Date.now()).toISOString(), error: "",
    };
    const documentXml = new DOMParser().parseFromString(raw, "application/xml");
    const parserError = documentXml.querySelector("parsererror");
    if (parserError) return { ...base, document_type: "XML inválido", status: "Erro de leitura", error: parserError.textContent.trim(), diagnosis: parserError.textContent.trim() };
    const infCte = xmlFirst(documentXml, "infCte");
    if (infCte) {
      const ide = xmlFirst(documentXml, "ide");
      const emit = xmlFirst(documentXml, "emit");
      const dest = xmlFirst(documentXml, "dest");
      const vPrest = xmlFirst(documentXml, "vPrest");
      const keys = xmlElements(documentXml, "infNFe").map((element) => xmlChildText(element, "chave")).filter(Boolean);
      const nfs = keys.map((key) => {
        const digits = key.replace(/\D/g, "");
        return digits.length >= 34 ? String(Number(digits.slice(25, 34))) : "";
      }).filter(Boolean);
      xmlElements(documentXml, "infNF").forEach((element) => { const value = xmlChildText(element, "nDoc"); if (value) nfs.push(value); });
      const tp = xmlChildText(ide, "tpCTe");
      const tpMap = { "0": "NORMAL", "1": "COMPLEMENTO", "2": "ANULAÇÃO", "3": "SUBSTITUIÇÃO" };
      const city = [xmlChildText(ide, "xMunFim"), xmlChildText(ide, "UFFim")].filter(Boolean).join(" / ");
      return {
        ...base, cte: xmlChildText(ide, "nCT"), series: xmlChildText(ide, "serie"), partner: xmlChildText(emit, "xNome") || "Não localizado",
        recipient: xmlChildText(dest, "xNome") || "Não localizado", nf: [...new Set(nfs)].join(", ") || "Não localizado", proof: [...new Set(nfs)].join(", ") || "Não localizado",
        city: city || "Não localizado", document_type: tpMap[tp] || tp || "CT-e", charge_type: tpMap[tp] || tp || "Não calculado",
        xml_value: Number(String(xmlChildText(vPrest, "vTPrest") || "").replace(",", ".")) || null,
        key: String(infCte.getAttribute("Id") || "").replace(/^CTe/, ""), issue_date: xmlChildText(ide, "dhEmi"),
        origin: [xmlChildText(ide, "xMunIni"), xmlChildText(ide, "UFIni")].filter(Boolean).join(" / "), destination: city,
      };
    }
    const infNFe = xmlFirst(documentXml, "infNFe");
    if (infNFe) {
      const ide = xmlFirst(documentXml, "ide");
      const total = xmlFirst(documentXml, "ICMSTot");
      const emit = xmlFirst(documentXml, "emit");
      const dest = xmlFirst(documentXml, "dest");
      return { ...base, cte: xmlChildText(ide, "nNF"), series: xmlChildText(ide, "serie"), partner: xmlChildText(emit, "xNome") || "Não localizado", recipient: xmlChildText(dest, "xNome") || "Não localizado", nf: xmlChildText(ide, "nNF") || "Não localizado", proof: xmlChildText(ide, "nNF") || "Não localizado", document_type: "NF-e", charge_type: "Documento fiscal", xml_value: Number(String(xmlChildText(total, "vNF") || "").replace(",", ".")) || null, status: "Documento auxiliar" };
    }
    return { ...base, document_type: "XML", status: "Formato não reconhecido" };
  }

  function manualDecisionLabel(decision) {
    const labels = { approved: "Aprovado", rejected: "Recusado", pending: "Pendente" };
    return labels[String(decision || "").toLowerCase()] || "Sem baixa manual";
  }

  async function saveXmlManualDecision(row, decision) {
    if (!row || !state.capabilities.can_override_xml_status || state.mode !== "server") return;
    const reason = decision === "clear" ? "" : String($("#xml-manual-reason")?.value || "").trim();
    if (decision !== "clear" && reason.length < 3) {
      toast("Justificativa obrigatória", "Informe o motivo da aprovação, pendência ou recusa.", "warning", 6000);
      $("#xml-manual-reason")?.focus();
      return;
    }
    const buttons = $$("[data-xml-manual-decision]", $("#drawer-content"));
    buttons.forEach((button) => { button.disabled = true; });
    try {
      const result = await api("/api/process/xml/manual-status", {
        method: "POST",
        timeout: 20000,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: row.path, decision, reason }),
      });
      const updated = result.data;
      const index = state.xmls.findIndex((item) => String(item.path || "") === String(updated.path || row.path || ""));
      if (index >= 0) state.xmls[index] = updated;
      renderXml();
      renderAudit();
      showXmlDetail(updated);
      toast(
        decision === "clear" ? "Baixa manual removida" : "Status manual registrado",
        `CT-e ${updated.cte || ""}: ${updated.status || "status atualizado"}.`,
        decision === "rejected" ? "warning" : "success",
        5500,
      );
    } catch (error) {
      toast("Não foi possível alterar o status", error.message, "danger", 7500);
      buttons.forEach((button) => { button.disabled = false; });
    }
  }

  function showXmlDetail(row) {
    if (!row) return;
    $("#drawer-title").textContent = `CT-e ${row.cte || "não identificado"}`;
    const fields = [
      ["Arquivo", row.file], ["Série", row.series], ["Parceiro", row.partner], ["Destinatário", row.recipient],
      ["NF / comprovante", row.nf], ["Cidade", row.city], ["Origem", row.origin], ["Destino", row.destination],
      ["Tipo", row.document_type], ["Valor XML", formatMoney(row.xml_value)], ["Valor esperado", formatMoney(row.expected_value)], ["Diferença", formatMoney(row.difference)],
    ];
    const manual = row.manual_decision && typeof row.manual_decision === "object" ? row.manual_decision : {};
    const authorizationStatus = row.authorization_status || (row.requires_manual_authorization ? "PENDENTE" : "Não exigida");
    const authorizationReason = row.manual_reason || manual.reason || "Sem justificativa registrada.";
    const canOverride = state.mode === "server" && Boolean(state.capabilities.can_override_xml_status);
    const manualSection = canOverride ? `<section class="detail-section manual-decision-section">
        <h3>Baixa e autorização manual</h3>
        <div class="notice neutral"><strong>O cálculo automático não será apagado.</strong> A decisão manual ficará registrada separadamente com usuário, data e justificativa.</div>
        <div class="detail-grid">
          <div class="detail-field"><small>Status automático</small>${badge(row.automatic_status || row.engine_status || row.status)}</div>
          <div class="detail-field"><small>Decisão atual</small><strong>${escapeHtml(manualDecisionLabel(manual.decision))}</strong></div>
          <div class="detail-field"><small>Status da autorização</small><strong>${escapeHtml(authorizationStatus)}</strong></div>
          <div class="detail-field"><small>Responsável</small><strong>${escapeHtml(manual.actor_name || "—")}</strong></div>
        </div>
        <label class="manual-decision-reason">Justificativa<textarea id="xml-manual-reason" rows="4" placeholder="Ex.: custo extra autorizado pelo coordenador...">${escapeHtml(row.manual_reason || manual.reason || "")}</textarea></label>
        <div class="action-buttons manual-decision-actions">
          <button type="button" class="button primary" data-xml-manual-decision="approved">Aprovar / dar baixa</button>
          <button type="button" class="button" data-xml-manual-decision="pending">Manter pendente</button>
          <button type="button" class="button danger" data-xml-manual-decision="rejected">Recusar</button>
          ${manual.decision ? '<button type="button" class="button" data-xml-manual-decision="clear">Remover baixa manual</button>' : ""}
        </div>
      </section>` : "";
    $("#drawer-content").innerHTML = `<section class="detail-section"><h3>Resumo</h3><div class="detail-grid">${fields.map(([key, value]) => `<div class="detail-field"><small>${escapeHtml(key)}</small><strong>${escapeHtml(value || "Não localizado")}</strong></div>`).join("")}</div></section>
      <section class="detail-section"><h3>Status e diagnóstico</h3><div class="detail-field"><small>Status atual</small>${badge(row.status)}</div><div class="detail-field" style="margin-top:8px"><small>Diagnóstico</small><strong>${escapeHtml(row.diagnosis || "Não informado")}</strong></div><div class="detail-field" style="margin-top:8px"><small>Ação recomendada</small><strong>${escapeHtml(row.recommended_action || "Não informada")}</strong></div></section>
      ${manualSection}
      <section class="detail-section"><h3>Cálculo compacto</h3>
        <div class="compact-authorization-summary">
          <div class="detail-field"><small>Status da autorização</small><strong>${escapeHtml(authorizationStatus)}</strong></div>
          <div class="detail-field"><small>Justificativa</small><strong id="compact-authorization-justification">${escapeHtml(authorizationReason)}</strong></div>
        </div>
        <div class="detail-code">${escapeHtml(row.compact_calculation || "Aguardando publicação pelo motor oficial.")}</div>
      </section>
      <section class="detail-section"><h3>Informação complementar</h3><div class="detail-code">${escapeHtml(row.complementary_information || "Nenhuma informação complementar aplicada.")}</div></section>
      <section class="detail-section"><h3>Dados técnicos</h3><div class="detail-code">${escapeHtml(JSON.stringify(row, null, 2))}</div></section>`;
    $$('[data-xml-manual-decision]', $("#drawer-content")).forEach((button) => {
      button.addEventListener("click", () => saveXmlManualDecision(row, button.dataset.xmlManualDecision));
    });
    $("#xml-manual-reason")?.addEventListener("input", (event) => {
      const target = $("#compact-authorization-justification");
      if (target) target.textContent = String(event.target.value || "").trim() || "Sem justificativa registrada.";
    });
    $("#detail-drawer").classList.add("open");
    $("#detail-drawer").setAttribute("aria-hidden", "false");
    $("#drawer-backdrop").classList.add("open");
  }

  function showInvoiceDetail(row) {
    if (!row) return;
    $("#drawer-title").textContent = `Fatura ${row.invoice || row.file || "não identificada"}`;
    const fields = [
      ["Parceiro", row.partner], ["Arquivos", Array.isArray(row.source_files) ? row.source_files.map((value) => value.split(/[\\/]/).pop()).join(", ") : row.file],
      ["Itens", formatNumber(row.item_count)], ["Itens liberados", formatNumber(row.ok_count)], ["Itens pendentes", formatNumber(row.pending_count)],
      ["Valor total", formatMoney(row.total_value)], ["Liberado agora", formatMoney(row.payable_value)], ["Pagamento futuro", formatMoney(row.future_value)],
      ["Problema interno", formatMoney(row.internal_problem_value)], ["Total pendente", formatMoney(row.retained_value)],
    ];
    const details = Array.isArray(row.details) ? row.details : [];
    const detailRows = details.map((item) => `<tr><td><strong>${escapeHtml(item.cte || "—")}</strong></td><td>${escapeHtml(item.nf || "—")}</td><td class="num">${formatMoney(item.billed_value)}</td><td class="num">${formatMoney(item.payable_value)}</td><td class="num">${formatMoney((Number(item.future_value) || 0) + (Number(item.internal_problem_value) || 0))}</td><td>${badge(item.status)}</td><td title="${escapeHtml(item.reason || "")}">${escapeHtml(item.reason || "—")}</td></tr>`).join("");
    $("#drawer-content").innerHTML = `<section class="detail-section"><h3>Resumo financeiro</h3><div class="detail-grid">${fields.map(([key, value]) => `<div class="detail-field"><small>${escapeHtml(key)}</small><strong>${escapeHtml(value ?? "—")}</strong></div>`).join("")}</div></section>
      <section class="detail-section"><h3>Status e ação</h3><div class="detail-field"><small>Status</small>${badge(row.payment_status)}</div><div class="detail-field" style="margin-top:8px"><small>Ação financeira</small><strong>${escapeHtml(row.financial_action || "Conferir decisão detalhada")}</strong></div></section>
      <section class="detail-section"><h3>CT-es da fatura</h3><div class="table-wrap"><table><thead><tr><th>CT-e</th><th>NF</th><th class="num">Cobrado</th><th class="num">Pagar</th><th class="num">Pendente</th><th>Status</th><th>Motivo</th></tr></thead><tbody>${detailRows || emptyRow(7, "A fatura ainda não possui decisão detalhada.")}</tbody></table></div></section>
      <section class="detail-section"><h3>Dados técnicos</h3><div class="detail-code">${escapeHtml(JSON.stringify(row, null, 2))}</div></section>`;
    $("#detail-drawer").classList.add("open");
    $("#detail-drawer").setAttribute("aria-hidden", "false");
    $("#drawer-backdrop").classList.add("open");
  }

  function closeDrawer() {
    $("#detail-drawer").classList.remove("open");
    $("#detail-drawer").setAttribute("aria-hidden", "true");
    $("#drawer-backdrop").classList.remove("open");
  }

  const wait = (milliseconds) => new Promise((resolve) => window.setTimeout(resolve, milliseconds));

  async function processAction(kind) {
    const isXml = kind === "xml";
    const label = isXml ? "validação de XML" : "processamento de faturas";
    const connected = isXml ? state.engine.xml_service_connected : state.engine.invoice_service_connected;
    if (state.mode !== "server") {
      toast("Servidor local necessário", `Abra pelo INICIAR_CENTRAL_CTE_WEB_LOCAL.bat para executar ${label} pelo motor oficial.`, "warning", 7500);
      return;
    }
    if (!connected) {
      toast(`O ${label} não está pronto`, isXml ? (state.engine.status || "Verifique o motor, a Base SSW e a tabela de parceiros.") : (state.engine.invoice_status || "Verifique a Base SSW e o leitor de PDF."), "warning", 8000);
      return;
    }

    const button = isXml ? $("#process-xml") : $("#process-invoices");
    const original = button.innerHTML;
    button.disabled = true;
    try {
      const started = await api(isXml ? "/api/process/xml" : "/api/process/invoices", {
        method: "POST", body: "{}", timeout: 30000, headers: { "Content-Type": "application/json" },
      });
      let job = started.data;
      state.processing[kind] = job;
      isXml ? renderXml() : renderInvoices();
      if (isXml) updateXmlTaskProgress({ title: "Validando XMLs", percent: job.percent || 0, processed: job.processed || 0, total: job.total || 0, current: job.current_file || "Na fila do motor", message: job.message || "Iniciando o motor oficial RC26.6." });
      toast(isXml ? "Validação oficial iniciada" : "Processamento de faturas iniciado", `${job.total || 0} documento(s) serão processados pelo motor RC26.6.`, "primary", 4500);

      while (job && !["completed", "failed"].includes(job.state)) {
        button.innerHTML = `<img src="icons/refresh.svg" alt="">Processando ${job.processed || 0}/${job.total || 0}`;
        await wait(650);
        const response = await api(`/api/jobs/${encodeURIComponent(job.id)}`, { timeout: 15000 });
        job = response.data;
        state.processing[kind] = job;
        isXml ? renderXml() : renderInvoices();
        if (isXml) updateXmlTaskProgress({ title: "Validando XMLs", percent: job.percent || 0, processed: job.processed || 0, total: job.total || 0, current: job.current_file || "Processando lote", message: job.message || "Aplicando parser, Base SSW e regras oficiais." });
      }

      if (job.state === "failed") throw new Error(job.error || `O ${label} falhou.`);
      const result = job.result || {};
      state.processing[kind] = null;
      state.processing[isXml ? "last_xml" : "last_invoices"] = result;
      await refreshAll(false);
      if (isXml) {
        updateXmlTaskProgress({ title: "Validação concluída", percent: 100, processed: result.processed || job.total || 0, total: job.total || result.processed || 0, current: `${result.ok || 0} OK · ${result.attention || 0} atenção`, message: `${result.errors || 0} erro(s). Os resultados oficiais já foram atualizados.`, stateName: result.errors ? "failed" : "completed", autoHide: true });
        toast("Validação oficial concluída", `${result.processed || 0} documento(s): ${result.ok || 0} OK, ${result.attention || 0} para conferir e ${result.errors || 0} erro(s).`, result.errors ? "warning" : "success", 8500);
      } else {
        const alerts = Number(result.rejected_files || 0) + Number(result.duplicate_files || 0) + Number(result.unprocessed_files || 0);
        toast("Faturas processadas pelo motor oficial", `${result.uploaded_documents || job.total || 0} PDF(s): ${result.processed_files || 0} processado(s), ${result.rejected_files || 0} rejeitado(s), ${result.duplicate_files || 0} duplicado(s) retirado(s) do cálculo. ${result.invoices || 0} fatura(s) identificada(s) e ${formatMoney(result.payable_value)} liberado.`, alerts ? "warning" : "success", 11000);
      }
    } catch (error) {
      state.processing[kind] = null;
      if (isXml) updateXmlTaskProgress({ title: "Falha na validação", percent: 0, current: "Processamento interrompido", message: error.message, stateName: "failed", autoHide: true });
      toast(isXml ? "Não foi possível processar os XMLs" : "Não foi possível processar as faturas", error.message, "danger", 9000);
      isXml ? renderXml() : renderInvoices();
    } finally {
      button.disabled = false;
      button.innerHTML = original;
    }
  }

  async function clearXmlList() {
    const count = state.xmls.length;
    const message = count
      ? `Remover ${count} XML(s) do lote atual? Os relatórios já gerados, a Base SSW e a tabela de parceiros serão preservados.`
      : "A lista já está vazia. Deseja limpar também a fotografia de processamento anterior?";
    if (!window.confirm(message)) return;

    if (state.mode !== "server") {
      localWrite(LOCAL_KEYS.xmls, []);
      state.xmls = [];
      state.processing.xml = null;
      state.processing.last_xml = {};
      state.selectedSignature.clear();
      resetDactePreview();
      renderAll();
      toast("Lista XML limpa", "O lote local foi removido.", "success");
      return;
    }

    const button = $("#clear-xml-list");
    const original = button.innerHTML;
    button.disabled = true;
    button.innerHTML = `<img src="icons/refresh.svg" alt="">Limpando…`;
    updateXmlTaskProgress({ title: "Limpando lote XML", percent: 15, processed: 0, total: count, current: "Removendo arquivos e snapshots", message: "Relatórios, Base SSW e tabelas serão preservados." });
    try {
      const response = await api("/api/xml/clear", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}",
        timeout: 60000,
      });
      const result = response.data || {};
      state.selectedSignature.clear();
      state.processing.xml = null;
      state.processing.last_xml = {};
      resetDactePreview();
      $("#xml-filter").value = "";
      $("#xml-status-filter").value = "";
      updateXmlTaskProgress({ title: "Lote XML limpo", percent: 100, processed: result.deleted_xml_count || count, total: count || result.deleted_xml_count || 0, current: "Arquivos e snapshots removidos", message: "Relatórios e bases foram preservados.", stateName: "completed", autoHide: true });
      await refreshAll(false);
      toast(
        "Lista XML limpa",
        `${result.deleted_xml_count || 0} arquivo(s) removido(s). Relatórios e bases foram preservados.`,
        "success",
        8000,
      );
    } catch (error) {
      updateXmlTaskProgress({ title: "Falha ao limpar lote", percent: 0, current: "Operação interrompida", message: error.message, stateName: "failed", autoHide: true });
      toast("Não foi possível limpar a lista", error.message, "danger", 10000);
    } finally {
      button.disabled = false;
      button.innerHTML = original;
    }
  }

  async function clearInvoiceList() {
    const count = state.invoiceFiles.length || state.invoices.length;
    const message = count
      ? `Remover ${count} fatura(s) PDF do lote atual? Os relatórios já gerados e a Base SSW serão preservados.`
      : "A lista já está vazia. Deseja limpar também a fotografia de processamento anterior?";
    if (!window.confirm(message)) return;

    if (state.mode !== "server") {
      localWrite(LOCAL_KEYS.invoices, []);
      state.invoices = [];
      state.invoiceFiles = [];
      state.processing.invoices = null;
      state.processing.last_invoices = {};
      $("#invoice-filter").value = "";
      renderAll();
      toast("Lista de faturas limpa", "O lote local foi removido.", "success");
      return;
    }

    const button = $("#clear-invoice-list");
    const original = button.innerHTML;
    button.disabled = true;
    button.innerHTML = `<img src="icons/refresh.svg" alt="">Limpando…`;
    try {
      const response = await api("/api/invoices/clear", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: "{}", timeout: 60000,
      });
      const result = response.data || {};
      state.processing.invoices = null;
      state.processing.last_invoices = {};
      $("#invoice-filter").value = "";
      await refreshAll(false);
      toast(
        "Lista de faturas limpa",
        `${result.deleted_invoice_count || 0} PDF(s) removido(s). Relatórios e Base SSW foram preservados.`,
        "success", 8000,
      );
    } catch (error) {
      toast("Não foi possível limpar as faturas", error.message, "danger", 10000);
    } finally {
      button.disabled = false;
      button.innerHTML = original;
    }
  }

  function complementaryTargetRows() {
    return filteredXmlRows().filter(isCteCandidate);
  }

  function updateComplementaryCounter() {
    const text = $("#complementary-text")?.value || "";
    const counter = $("#complementary-counter");
    if (!counter) return;
    counter.textContent = `${text.length}/600 caracteres`;
    counter.classList.toggle("limit", text.length >= 600);
  }

  function openComplementaryModal() {
    const rows = complementaryTargetRows();
    if (!rows.length) {
      toast("Nenhum CT-e disponível", "Adicione CT-es ou ajuste os filtros antes de incluir a informação complementar.", "warning", 7000);
      return;
    }
    state.complementaryTargetPaths = rows.map((row) => String(row.path || row.file || "")).filter(Boolean);
    const existing = [...new Set(rows.map((row) => String(row.complementary_information || "").trim()).filter(Boolean))];
    $("#complementary-text").value = existing.length === 1 ? existing[0] : "";
    $("#complementary-target-summary").textContent = `A informação será aplicada a ${rows.length} CT-e(s) exibido(s) pelos filtros atuais.`;
    $("#remove-complementary-info").disabled = !existing.length;
    $("#complementary-modal").classList.remove("hidden");
    updateComplementaryCounter();
    window.setTimeout(() => $("#complementary-text").focus(), 50);
  }

  function closeComplementaryModal() {
    $("#complementary-modal").classList.add("hidden");
    state.complementaryTargetPaths = [];
  }

  async function saveComplementaryInformation(event) {
    event.preventDefault();
    const text = $("#complementary-text").value.trim();
    if (!text) {
      toast("Digite a informação", "O texto complementar não pode ficar vazio.", "warning");
      return;
    }
    if (text.length > 600) {
      toast("Texto muito longo", "O limite é de 600 caracteres.", "danger");
      return;
    }
    const paths = [...state.complementaryTargetPaths];
    if (!paths.length) return;
    try {
      if (state.mode === "server") {
        const response = await api("/api/xml/complementary", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ paths, text, action: "apply" }), timeout: 60000,
        });
        await refreshAll(false);
        closeComplementaryModal();
        toast("Informação complementar aplicada", `${response.data?.documents || paths.length} CT-e(s) atualizado(s). O XML fiscal permaneceu intacto.`, "success", 8000);
      } else {
        state.xmls.forEach((row) => { if (paths.includes(String(row.path || row.file || ""))) row.complementary_information = text; });
        localWrite(LOCAL_KEYS.xmls, state.xmls);
        closeComplementaryModal();
        renderAll();
        toast("Informação complementar aplicada", `${paths.length} CT-e(s) atualizado(s) no modo local.`, "success");
      }
    } catch (error) {
      toast("Não foi possível aplicar", error.message, "danger", 10000);
    }
  }

  async function removeComplementaryInformation() {
    const paths = [...state.complementaryTargetPaths];
    if (!paths.length || !window.confirm(`Remover a informação complementar de ${paths.length} CT-e(s) filtrado(s)?`)) return;
    try {
      if (state.mode === "server") {
        await api("/api/xml/complementary", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ paths, action: "remove" }), timeout: 60000,
        });
        await refreshAll(false);
      } else {
        state.xmls.forEach((row) => { if (paths.includes(String(row.path || row.file || ""))) row.complementary_information = ""; });
        localWrite(LOCAL_KEYS.xmls, state.xmls);
        renderAll();
      }
      closeComplementaryModal();
      toast("Informação complementar removida", `${paths.length} CT-e(s) atualizado(s).`, "success");
    } catch (error) {
      toast("Não foi possível remover", error.message, "danger", 10000);
    }
  }

  function openQaModal() {
    $("#qa-modal").classList.remove("hidden");
    const currentLabel = $(".nav-item.active span")?.textContent || "Geral";
    const select = $("#qa-form [name=page]");
    if ([...select.options].some((option) => option.value === currentLabel)) select.value = currentLabel;
    window.setTimeout(() => $("#qa-form [name=title]").focus(), 50);
  }

  function closeQaModal() {
    $("#qa-modal").classList.add("hidden");
    if (state.qaAttachmentPreviewUrl) URL.revokeObjectURL(state.qaAttachmentPreviewUrl);
    state.qaAttachmentPreviewUrl = "";
    const preview = $("#qa-attachment-preview");
    if (preview) { preview.classList.add("hidden"); preview.innerHTML = ""; }
  }

  function readFileAsDataUrl(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result || ""));
      reader.onerror = () => reject(new Error("Não foi possível ler a imagem selecionada."));
      reader.readAsDataURL(file);
    });
  }

  function updateQaAttachmentPreview(file) {
    const preview = $("#qa-attachment-preview");
    if (!preview) return;
    if (state.qaAttachmentPreviewUrl) URL.revokeObjectURL(state.qaAttachmentPreviewUrl);
    state.qaAttachmentPreviewUrl = "";
    if (!file) {
      preview.classList.add("hidden");
      preview.innerHTML = "";
      return;
    }
    if (!/^image\/(png|jpeg|webp)$/i.test(file.type || "")) {
      $("#qa-attachment").value = "";
      preview.classList.add("hidden");
      preview.innerHTML = "";
      return toast("Imagem não suportada", "Use PNG, JPG ou WEBP.", "warning");
    }
    if (file.size > 6 * 1024 * 1024) {
      $("#qa-attachment").value = "";
      preview.classList.add("hidden");
      preview.innerHTML = "";
      return toast("Imagem muito grande", "O anexo deve ter no máximo 6 MB.", "warning");
    }
    state.qaAttachmentPreviewUrl = URL.createObjectURL(file);
    preview.innerHTML = `<img src="${state.qaAttachmentPreviewUrl}" alt="Prévia da evidência"><div><strong>${escapeHtml(file.name)}</strong><small>${formatBytes(file.size)}</small></div><button type="button" class="text-button" id="remove-qa-attachment">Remover</button>`;
    preview.classList.remove("hidden");
  }

  async function saveQa(form) {
    const formData = new FormData(form);
    const file = formData.get("attachment");
    formData.delete("attachment");
    const data = Object.fromEntries(formData.entries());
    const note = { ...data, id: `QA-${Date.now()}`, status: "aberto", created_at: new Date().toISOString() };
    const button = form.querySelector("button[type='submit']");
    if (button) button.disabled = true;
    try {
      if (file instanceof File && file.size) {
        if (!/^image\/(png|jpeg|webp)$/i.test(file.type || "")) throw new Error("Use uma imagem PNG, JPG ou WEBP.");
        if (file.size > 6 * 1024 * 1024) throw new Error("A imagem deve ter no máximo 6 MB.");
        note.attachment = { name: file.name, type: file.type, data_url: await readFileAsDataUrl(file) };
      }
      if (state.mode === "server") {
        const result = await api("/api/qa", { method: "POST", body: JSON.stringify(note), headers: { "Content-Type": "application/json" }, timeout: 45000 });
        if (state.capabilities.can_view_qa) state.qa.unshift(result.data);
      } else {
        if (note.attachment) note.attachment = { name: note.attachment.name, mime: note.attachment.type, local_only: true };
        state.qa.unshift(note);
        localWrite(LOCAL_KEYS.qa, state.qa);
      }
      form.reset();
      closeQaModal();
      renderDashboard();
      renderSettings();
      toast("Anotação enviada", "O item e sua evidência foram adicionados ao caderno global de homologação.", "success");
    } catch (error) {
      toast("Não foi possível salvar", error.message, "danger", 9000);
    } finally {
      if (button) button.disabled = false;
    }
  }

  function downloadBlob(filename, content, type) {
    const blob = new Blob([content], { type });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(link.href), 1000);
  }

  function exportXmlCsv() {
    const headers = ["CT-e", "Série", "Parceiro", "Destinatário", "NF", "Cidade", "Tipo", "Valor XML", "Valor esperado", "Diferença", "Status", "Status automático", "Decisão manual", "Justificativa", "Responsável", "Data da decisão"];
    const lines = [headers, ...state.xmls.map((row) => {
      const manual = row.manual_decision && typeof row.manual_decision === "object" ? row.manual_decision : {};
      return [row.cte, row.series, row.partner, row.recipient, row.nf, row.city, row.document_type, row.xml_value ?? "", row.expected_value ?? "", row.difference ?? "", row.status, row.automatic_status || row.engine_status || "", manual.decision || "", row.manual_reason || manual.reason || "", manual.actor_name || "", row.manual_decided_at || manual.decided_at || ""];
    })];
    const csv = lines.map((line) => line.map((value) => `"${String(value ?? "").replaceAll('"', '""')}"`).join(";")).join("\r\n");
    downloadBlob(`central_cte_xml_${new Date().toISOString().slice(0, 10)}.csv`, `\ufeff${csv}`, "text/csv;charset=utf-8");
    toast("Relatório gerado", "O CSV contém apenas os campos disponíveis; ausências não foram convertidas em R$ 0,00.", "success");
  }

  function globalSearch(query) {
    const normalized = normalize(query).trim();
    const container = $("#global-results");
    if (normalized.length < 2) {
      container.classList.add("hidden");
      return;
    }
    const results = [];
    state.xmls.forEach((row, index) => {
      if (normalize([row.cte, row.partner, row.nf, row.city, row.file].join(" ")).includes(normalized)) results.push({ page: "audit", icon: "shield-search.svg", title: `CT-e ${row.cte || "não identificado"}`, detail: `${row.partner || "Não localizado"} · NF ${row.nf || "—"}`, kind: "XML", index });
    });
    state.invoices.forEach((row) => {
      if (normalize([row.invoice, row.partner, row.file].join(" ")).includes(normalized)) results.push({ page: "invoices", icon: "file-invoice.svg", title: row.invoice || row.file, detail: row.partner || "Aguardando leitura", kind: "Fatura" });
    });
    state.partners.forEach((row) => {
      if (normalize([row.partner_id, row.name, row.alias].join(" ")).includes(normalized)) results.push({ page: "partners", icon: "users.svg", title: row.name, detail: `${row.partner_id} · ${row.alias || "Sem alias"}`, kind: "Parceiro", partnerId: row.partner_id });
    });
    state.reports.forEach((row) => {
      if (normalize([row.name, row.module, row.format].join(" ")).includes(normalized)) results.push({ page: "reports", icon: "report.svg", title: row.name, detail: `${row.module} · ${row.format}`, kind: "Relatório" });
    });
    const limited = results.slice(0, 15);
    container.innerHTML = limited.length ? limited.map((item, index) => `<button class="search-result" data-result-index="${index}"><img src="icons/${item.icon}" alt=""><div><strong>${escapeHtml(item.title)}</strong><span>${escapeHtml(item.detail)}</span></div><em>${escapeHtml(item.kind)}</em></button>`).join("") : `<div class="search-empty">Nenhum resultado em XMLs, faturas, parceiros ou relatórios.</div>`;
    container.dataset.results = JSON.stringify(limited);
    container.classList.remove("hidden");
  }

  async function generateOfficialReport(module, onlyProblemInvoices = false) {
    const isXml = module === "xml";
    const button = isXml
      ? $("#generate-xml-xlsx")
      : (onlyProblemInvoices ? $("#generate-invoice-problems-xlsx") : $("#generate-invoice-xlsx"));
    if (state.mode !== "server") {
      toast("Servidor local necessário", "Abra pelo INICIAR_CENTRAL_CTE_WEB_LOCAL.bat para gerar o XLSX oficial.", "warning", 7500);
      return;
    }
    if (!state.engine.report_service_connected) {
      toast("Gerador oficial indisponível", state.engine.report_status || "Os módulos RC26.6 de relatório não foram encontrados.", "warning", 8000);
      return;
    }
    const original = button?.innerHTML || "Gerar XLSX";
    if (button) {
      button.disabled = true;
      button.setAttribute("aria-busy", "true");
      button.innerHTML = `<img src="icons/refresh.svg" alt="">Gerando…`;
    }
    try {
      const response = await api("/api/reports/generate", {
        method: "POST",
        timeout: 180000,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ module, only_problem_invoices: Boolean(onlyProblemInvoices) }),
      });
      const result = response.data || {};
      await refreshAll(false);
      renderReports();
      const link = document.createElement("a");
      link.href = `/api/file?path=${encodeURIComponent(result.path || "")}`;
      link.style.display = "none";
      document.body.appendChild(link);
      link.click();
      link.remove();
      if (isXml) {
        toast("Relatório XML oficial gerado", `${result.documents || 0} documento(s) incluído(s). O download foi iniciado.`, "success", 8500);
      } else {
        const rejectedRows = Number(result.rejected_file_rows || 0);
        toast("Relatório de faturas gerado", `${result.invoices || 0} fatura(s), ${result.items || 0} CT-e(s), ${formatMoney(result.payable_value)} liberado${rejectedRows ? ` e ${rejectedRows} arquivo(s) na aba ARQUIVOS_REJEITADOS` : ""}.`, rejectedRows ? "warning" : "success", 10000);
      }
    } catch (error) {
      toast("Não foi possível gerar o relatório", error.message, "danger", 10000);
    } finally {
      if (button) {
        button.disabled = false;
        button.removeAttribute("aria-busy");
        button.innerHTML = original;
      }
    }
  }

  function startServerDownload(path) {
    const link = document.createElement("a");
    link.href = `/api/file?path=${encodeURIComponent(path || "")}`;
    link.style.display = "none";
    document.body.appendChild(link);
    link.click();
    link.remove();
  }

  function dactePreviewFragment(zoom = "FitH") {
    return /^\d+$/.test(String(zoom || ""))
      ? `zoom=${encodeURIComponent(zoom)}`
      : `view=${encodeURIComponent(zoom || "FitH")}`;
  }

  function dactePreviewSource(path, zoom = "FitH") {
    return `/api/file?path=${encodeURIComponent(path || "")}&inline=1&v=${Date.now()}#toolbar=1&navpanes=0&${dactePreviewFragment(zoom)}`;
  }

  function dacteBlobPreviewSource(objectUrl, zoom = "FitH") {
    return `${objectUrl}#toolbar=1&navpanes=0&${dactePreviewFragment(zoom)}`;
  }

  function revokeDactePreviewObjectUrl() {
    const objectUrl = String(state.dactePreview?.objectUrl || "");
    if (objectUrl.startsWith("blob:")) URL.revokeObjectURL(objectUrl);
  }

  async function loadDactePreviewObjectUrl(path) {
    const response = await fetch(`/api/file?path=${encodeURIComponent(path || "")}&inline=1&v=${Date.now()}`, {
      credentials: "same-origin",
      cache: "no-store",
      headers: { Accept: "application/pdf" },
    });
    if (!response.ok) {
      const detail = await response.json().catch(() => ({}));
      throw new Error(detail.error || `Não foi possível abrir o PDF da prévia (HTTP ${response.status}).`);
    }
    const blob = await response.blob();
    if (!blob.size) throw new Error("O PDF gerado está vazio.");
    return URL.createObjectURL(blob.type === "application/pdf" ? blob : blob.slice(0, blob.size, "application/pdf"));
  }

  async function renderDactePdfPreview(result, { signed = false, fallbackCte = "" } = {}) {
    const path = String(result?.path || "");
    if (!path) throw new Error("O serviço não informou o caminho da prévia.");
    const cte = String(result?.cte || fallbackCte || "");
    const title = `${signed ? "DACTE assinado" : "DACTE oficial"}${cte ? ` · CT-e ${cte}` : ""}`;
    const zoom = state.dactePreview.zoom || "FitH";
    const toolbar = $("#dacte-preview-toolbar");
    toolbar.classList.remove("hidden");
    $("#dacte-preview-title").textContent = title;
    $("#dacte-preview-status").textContent = `${result.pages || 1} página(s) · ${signed ? "assinatura visual" : "sem assinatura"}`;
    $("#dacte-preview-zoom").value = zoom;
    const preview = $("#dacte-preview");
    preview.classList.add("has-pdf");
    preview.innerHTML = `<div class="preview-loading"><img src="icons/refresh.svg" alt=""><strong>Carregando PDF…</strong></div>`;
    const objectUrl = await loadDactePreviewObjectUrl(path);
    revokeDactePreviewObjectUrl();
    state.dactePreview = { path, title, zoom, signed, objectUrl };
    preview.innerHTML = `<iframe title="${escapeHtml(title)}" src="${dacteBlobPreviewSource(objectUrl, zoom)}" allow="fullscreen"></iframe>`;
  }

  function resetDactePreview() {
    revokeDactePreviewObjectUrl();
    state.dactePreview = { path: "", title: "", zoom: "FitH", signed: false, objectUrl: "" };
    const toolbar = $("#dacte-preview-toolbar");
    if (toolbar) toolbar.classList.add("hidden");
    const shell = $("#dacte-preview-shell");
    if (shell) shell.classList.remove("preview-expanded");
    const preview = $("#dacte-preview");
    if (!preview) return;
    preview.classList.remove("has-pdf");
    preview.innerHTML = `<img src="icons/file-invoice.svg" alt=""><strong>Nenhum CT-e selecionado</strong><span>A interface não recalcula frete ou valores comerciais.</span>`;
  }

  function updateDactePreviewZoom() {
    const zoom = String($("#dacte-preview-zoom")?.value || "FitH");
    state.dactePreview.zoom = zoom;
    const iframe = $("#dacte-preview iframe");
    if (!iframe || !state.dactePreview.path) return;
    iframe.src = state.dactePreview.objectUrl
      ? dacteBlobPreviewSource(state.dactePreview.objectUrl, zoom)
      : dactePreviewSource(state.dactePreview.path, zoom);
  }

  function openDactePreviewInNewTab() {
    if (!state.dactePreview.path) return toast("Gere uma prévia primeiro", "Nenhum documento está aberto.", "warning");
    const source = state.dactePreview.objectUrl
      ? dacteBlobPreviewSource(state.dactePreview.objectUrl, state.dactePreview.zoom)
      : dactePreviewSource(state.dactePreview.path, state.dactePreview.zoom);
    window.open(source, "_blank", "noopener,noreferrer");
  }

  function downloadDactePreview() {
    if (!state.dactePreview.path) return toast("Gere uma prévia primeiro", "Nenhum documento está aberto.", "warning");
    startServerDownload(state.dactePreview.path);
  }

  async function toggleDactePreviewFullscreen() {
    const shell = $("#dacte-preview-shell");
    if (!shell || !state.dactePreview.path) return toast("Gere uma prévia primeiro", "Nenhum documento está aberto.", "warning");
    try {
      if (!document.fullscreenElement && shell.requestFullscreen) {
        await shell.requestFullscreen();
      } else if (document.fullscreenElement && document.exitFullscreen) {
        await document.exitFullscreen();
      } else {
        shell.classList.toggle("preview-expanded");
      }
    } catch (_) {
      shell.classList.toggle("preview-expanded");
    }
  }

  function readFileAsDataUrl(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result || ""));
      reader.onerror = () => reject(new Error("Não foi possível ler a imagem selecionada."));
      reader.readAsDataURL(file);
    });
  }

  function loadBrowserImage(source) {
    return new Promise((resolve, reject) => {
      const image = new Image();
      image.onload = () => resolve(image);
      image.onerror = () => reject(new Error("O navegador não conseguiu abrir a imagem da assinatura."));
      image.src = source;
    });
  }

  async function processSignatureDataUrlInBrowser(sourceDataUrl, threshold) {
    const image = await loadBrowserImage(sourceDataUrl);
    const maxSide = 1800;
    const ratio = Math.min(1, maxSide / Math.max(image.naturalWidth || image.width, image.naturalHeight || image.height));
    const width = Math.max(1, Math.round((image.naturalWidth || image.width) * ratio));
    const height = Math.max(1, Math.round((image.naturalHeight || image.height) * ratio));
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const context = canvas.getContext("2d", { willReadFrequently: true });
    if (!context) throw new Error("O navegador não disponibilizou o tratamento de imagem.");
    context.drawImage(image, 0, 0, width, height);
    const pixels = context.getImageData(0, 0, width, height);
    const data = pixels.data;
    const limit = clampNumber(threshold, 205, 252, 242);
    const softness = Math.max(6, 255 - limit);
    let left = width, top = height, right = -1, bottom = -1;
    for (let y = 0; y < height; y += 1) {
      for (let x = 0; x < width; x += 1) {
        const index = (y * width + x) * 4;
        const red = data[index], green = data[index + 1], blue = data[index + 2];
        const light = Math.max(red, green, blue);
        const minimum = Math.min(red, green, blue);
        let alpha = 0;
        if (!(light >= limit && minimum >= limit - 10)) {
          const luminance = Math.round(0.2126 * red + 0.7152 * green + 0.0722 * blue);
          alpha = Math.max(0, Math.min(255, Math.round((255 - luminance) * (255 / softness))));
          if (light - minimum > 18) alpha = Math.max(alpha, 170);
          if (luminance < 225) alpha = Math.max(alpha, 38);
        }
        data[index + 3] = alpha;
        if (alpha > 12) {
          left = Math.min(left, x); top = Math.min(top, y); right = Math.max(right, x); bottom = Math.max(bottom, y);
        }
      }
    }
    if (right < left || bottom < top) throw new Error("Nenhum traço de assinatura foi encontrado após remover o fundo.");
    context.putImageData(pixels, 0, 0);
    const pad = Math.max(8, Math.round(Math.min(width, height) * 0.025));
    const cropLeft = Math.max(0, left - pad), cropTop = Math.max(0, top - pad);
    const cropRight = Math.min(width, right + pad + 1), cropBottom = Math.min(height, bottom + pad + 1);
    const output = document.createElement("canvas");
    output.width = cropRight - cropLeft;
    output.height = cropBottom - cropTop;
    const outputContext = output.getContext("2d");
    if (!outputContext) throw new Error("O navegador não conseguiu concluir o recorte da assinatura.");
    outputContext.drawImage(canvas, cropLeft, cropTop, output.width, output.height, 0, 0, output.width, output.height);
    return {
      processedDataUrl: output.toDataURL("image/png"),
      width: output.width,
      height: output.height,
      threshold: limit,
    };
  }

  async function processSignatureImageInBrowser(file, threshold) {
    if (!file || !/^image\/(png|jpeg|jpg|webp|bmp)$/i.test(file.type || "")) {
      throw new Error("Use uma imagem PNG, JPG, WEBP ou BMP.");
    }
    if (file.size > 20 * 1024 * 1024) throw new Error("A imagem ultrapassa o limite de 20 MB.");
    const originalDataUrl = await readFileAsDataUrl(file);
    return { originalDataUrl, ...(await processSignatureDataUrlInBrowser(originalDataUrl, threshold)) };
  }

  function renderSignaturePdfCandidates() {
    const container = $("#signature-pdf-candidates");
    const current = state.signaturePdfImport;
    if (!container) return;
    if (!current || !Array.isArray(current.candidates) || !current.candidates.length) {
      container.classList.add("hidden");
      container.innerHTML = "";
      return;
    }
    container.classList.remove("hidden");
    const warning = current.warnings?.length ? `<small class="pdf-candidate-warning">${escapeHtml(current.warnings.join(" "))}</small>` : "";
    container.innerHTML = `<div class="pdf-candidate-heading"><div><strong>Imagens encontradas no PDF</strong><small>Escolha a página ou imagem e depois desenhe um recorte somente ao redor da assinatura.</small></div><button type="button" class="text-button" data-cancel-pdf-import>Cancelar</button></div>${warning}<div class="pdf-candidate-grid">${current.candidates.map((candidate, index) => `<button type="button" class="pdf-candidate" data-pdf-candidate-index="${index}"><img src="${candidate.data_url}" alt="Imagem ${index + 1} do PDF"><span>Página ${candidate.page} · ${candidate.width || "?"} × ${candidate.height || "?"} px</span><small>${escapeHtml(candidate.name || `Imagem ${index + 1}`)} · ${formatBytes(candidate.size_bytes)}</small></button>`).join("")}</div>`;
  }

  function closeSignatureCrop() {
    $("#signature-crop-modal")?.classList.add("hidden");
    state.signatureCrop = { candidate: null, image: null, selection: null, drawing: false, start: null };
    const selection = $("#signature-crop-selection");
    if (selection) selection.classList.add("hidden");
  }

  function cropCanvasPoint(event) {
    const canvas = $("#signature-crop-canvas");
    const rect = canvas.getBoundingClientRect();
    return {
      x: Math.max(0, Math.min(canvas.width, (event.clientX - rect.left) * (canvas.width / rect.width))),
      y: Math.max(0, Math.min(canvas.height, (event.clientY - rect.top) * (canvas.height / rect.height))),
    };
  }

  function renderSignatureCropSelection() {
    const selection = state.signatureCrop.selection;
    const overlay = $("#signature-crop-selection");
    const canvas = $("#signature-crop-canvas");
    if (!selection || selection.width < 2 || selection.height < 2) {
      overlay.classList.add("hidden");
      $("#signature-crop-status").textContent = "Nenhuma área selecionada.";
      return;
    }
    const scaleX = canvas.clientWidth / canvas.width;
    const scaleY = canvas.clientHeight / canvas.height;
    overlay.style.left = `${canvas.offsetLeft + selection.x * scaleX}px`;
    overlay.style.top = `${canvas.offsetTop + selection.y * scaleY}px`;
    overlay.style.width = `${selection.width * scaleX}px`;
    overlay.style.height = `${selection.height * scaleY}px`;
    overlay.classList.remove("hidden");
    $("#signature-crop-status").textContent = `Área selecionada: ${Math.round(selection.width)} × ${Math.round(selection.height)} px.`;
  }

  async function openSignatureCrop(candidate, index) {
    const image = new Image();
    image.decoding = "async";
    await new Promise((resolve, reject) => {
      image.onload = resolve;
      image.onerror = () => reject(new Error("Não foi possível abrir a imagem extraída do PDF."));
      image.src = candidate.data_url;
    });
    const maxDimension = 3200;
    const factor = Math.min(1, maxDimension / Math.max(image.naturalWidth, image.naturalHeight));
    const canvas = $("#signature-crop-canvas");
    canvas.width = Math.max(1, Math.round(image.naturalWidth * factor));
    canvas.height = Math.max(1, Math.round(image.naturalHeight * factor));
    canvas.getContext("2d", { alpha: false }).drawImage(image, 0, 0, canvas.width, canvas.height);
    state.signatureCrop = { candidate: { ...candidate, index }, image, selection: null, drawing: false, start: null };
    $("#signature-crop-selection").classList.add("hidden");
    $("#signature-crop-status").textContent = "Arraste sobre o bloco da assinatura.";
    $("#signature-crop-modal").classList.remove("hidden");
    const stage = $("#signature-crop-stage");
    stage.scrollLeft = 0;
    stage.scrollTop = 0;
    window.requestAnimationFrame(renderSignatureCropSelection);
  }

  function beginSignatureCrop(event) {
    if (!state.signatureCrop.candidate) return;
    const point = cropCanvasPoint(event);
    state.signatureCrop.drawing = true;
    state.signatureCrop.start = point;
    state.signatureCrop.selection = { x: point.x, y: point.y, width: 0, height: 0 };
    event.currentTarget.setPointerCapture?.(event.pointerId);
    renderSignatureCropSelection();
    event.preventDefault();
  }

  function moveSignatureCrop(event) {
    if (!state.signatureCrop.drawing || !state.signatureCrop.start) return;
    const point = cropCanvasPoint(event);
    const start = state.signatureCrop.start;
    state.signatureCrop.selection = {
      x: Math.min(start.x, point.x),
      y: Math.min(start.y, point.y),
      width: Math.abs(point.x - start.x),
      height: Math.abs(point.y - start.y),
    };
    renderSignatureCropSelection();
    event.preventDefault();
  }

  function endSignatureCrop(event) {
    if (!state.signatureCrop.drawing) return;
    state.signatureCrop.drawing = false;
    renderSignatureCropSelection();
    event.preventDefault();
  }

  function resetSignatureCrop() {
    state.signatureCrop.selection = null;
    renderSignatureCropSelection();
  }

  async function applySignatureCrop() {
    const current = state.signaturePdfImport;
    const profile = currentSignatureProfile();
    const candidate = state.signatureCrop.candidate;
    const selection = state.signatureCrop.selection;
    if (!current || !profile || !candidate || !selection || selection.width < 12 || selection.height < 12) {
      return toast("Recorte obrigatório", "Arraste uma área somente ao redor da assinatura antes de continuar.", "warning", 8000);
    }
    const source = $("#signature-crop-canvas");
    const x = Math.max(0, Math.floor(selection.x));
    const y = Math.max(0, Math.floor(selection.y));
    const width = Math.min(source.width - x, Math.max(1, Math.ceil(selection.width)));
    const height = Math.min(source.height - y, Math.max(1, Math.ceil(selection.height)));
    const output = document.createElement("canvas");
    output.width = width;
    output.height = height;
    output.getContext("2d").drawImage(source, x, y, width, height, 0, 0, width, height);
    const button = $("#apply-signature-crop");
    button.disabled = true;
    try {
      const sourceDataUrl = output.toDataURL("image/png");
      closeSignatureCrop();
      await saveProcessedSignature({
        profile,
        originalName: current.file.name,
        originalDataUrl: current.originalDataUrl,
        sourceDataUrl,
        sourceLabel: `PDF página ${candidate.page || 1}, recorte ${width} × ${height} px`,
      });
    } catch (error) {
      toast("Não foi possível aplicar o recorte", error.message, "danger", 10000);
    } finally {
      button.disabled = false;
    }
  }

  async function saveProcessedSignature({
    profile, originalName, originalDataUrl, sourceDataUrl = "", sourceLabel = "imagem",
    processedDataUrl = "", processedWidth = 0, processedHeight = 0, processedThreshold = 0,
    successTitle = "Assinatura tratada",
  }) {
    const threshold = Number(processedThreshold || $("#signature-threshold").value || 242);
    const treated = processedDataUrl
      ? { processedDataUrl, threshold, width: Number(processedWidth || 0), height: Number(processedHeight || 0) }
      : await processSignatureDataUrlInBrowser(sourceDataUrl, threshold);
    const response = await api("/api/signatures/import", {
      method: "POST", timeout: 180000, headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        profile_id: profile.id,
        original_name: originalName,
        original_data_url: originalDataUrl,
        processed_data_url: treated.processedDataUrl,
        threshold: treated.threshold,
      }),
    });
    state.selectedSignatureProfile = String(response.data?.profile?.id || profile.id);
    state.signaturePdfImport = null;
    renderSignaturePdfCandidates();
    await refreshAll(false);
    const dimensions = treated.width && treated.height ? ` · ${treated.width} × ${treated.height} px` : "";
    toast(successTitle, `${sourceLabel}${dimensions}, com fundo transparente.`, "success", 9000);
  }

  async function importSignaturePdf(file, profile) {
    if (file.size > 30 * 1024 * 1024) throw new Error("O PDF ultrapassa o limite de 30 MB.");
    const originalDataUrl = await readFileAsDataUrl(file);
    const response = await api("/api/signatures/pdf-images", {
      method: "POST",
      timeout: 180000,
      headers: { "Content-Type": "application/pdf", "X-Filename": file.name },
      body: file,
    });
    const result = response.data || {};
    const automatic = result.automatic_signature || null;
    if (automatic?.processed_data_url) {
      await saveProcessedSignature({
        profile,
        originalName: file.name,
        originalDataUrl,
        processedDataUrl: automatic.processed_data_url,
        processedWidth: automatic.width,
        processedHeight: automatic.height,
        processedThreshold: automatic.threshold,
        sourceLabel: automatic.detection || "assinatura localizada dentro do quadro da folha de cadastro",
        successTitle: "Assinatura lida automaticamente",
      });
      return;
    }
    const candidates = Array.isArray(result.candidates) ? result.candidates : [];
    if (!candidates.length) throw new Error("Nenhuma assinatura foi localizada automaticamente. Confirme que a folha foi assinada dentro do quadro e digitalizada com nitidez.");
    state.signaturePdfImport = {
      profileId: profile.id,
      file,
      originalDataUrl,
      candidates,
      warnings: result.warnings || [],
      pages: result.pages || 1,
    };
    renderSignaturePdfCandidates();
    toast("PDF lido", `${candidates.length} opção(ões) encontrada(s). Escolha uma e recorte somente o bloco da assinatura.`, "primary", 9000);
  }

  async function chooseSignaturePdfCandidate(index) {
    const current = state.signaturePdfImport;
    const profile = currentSignatureProfile();
    const candidate = current?.candidates?.[Number(index)];
    if (!current || !profile || String(profile.id) !== String(current.profileId) || !candidate) {
      return toast("Seleção inválida", "Reabra o PDF e escolha novamente.", "warning");
    }
    await openSignatureCrop(candidate, Number(index));
  }

  async function saveSignatureProfile() {
    if (state.mode !== "server") return toast("Servidor local necessário", "Perfis não podem ser salvos no modo arquivo.", "warning");
    const payload = signatureLayoutPayload();
    if (!payload.name || !payload.person_name) return toast("Preencha o perfil", "Informe o nome do perfil e o responsável.", "warning");
    const button = $("#save-signature-profile");
    const original = button.textContent;
    button.disabled = true;
    button.textContent = "Salvando…";
    try {
      const response = await api("/api/signatures/profile", {
        method: "POST", timeout: 30000, headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
      });
      state.selectedSignatureProfile = String(response.data?.id || state.selectedSignatureProfile || "");
      await refreshAll(false);
      toast("Perfil salvo", "Os dados e o posicionamento foram registrados.", "success");
    } catch (error) {
      toast("Não foi possível salvar o perfil", error.message, "danger", 9000);
    } finally {
      button.disabled = false;
      button.textContent = original;
    }
  }

  function newSignatureProfile() {
    state.selectedSignatureProfile = "";
    state.signatureSourceFile = null;
    state.signaturePdfImport = null;
    renderSignaturePdfCandidates();
    $("#signature-profile-select").value = "";
    loadSignatureProfileForm(null);
    $("#signature-profile-name").focus();
  }

  async function deleteSignatureProfile() {
    const profile = currentSignatureProfile();
    if (!profile) return;
    if (!window.confirm(`Excluir o perfil “${profile.name}” e a imagem armazenada?`)) return;
    try {
      await api("/api/signatures/profile/delete", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ profile_id: profile.id }),
      });
      state.selectedSignatureProfile = "";
      state.signatureSourceFile = null;
      state.signaturePdfImport = null;
      renderSignaturePdfCandidates();
      await refreshAll(false);
      toast("Perfil excluído", "O cadastro e a imagem local foram removidos.", "success");
    } catch (error) {
      toast("Não foi possível excluir", error.message, "danger", 9000);
    }
  }

  async function importSignatureImage(file) {
    const profile = currentSignatureProfile();
    if (!profile) return toast("Crie o perfil primeiro", "Salve o responsável antes de importar a assinatura.", "warning");
    if (state.mode !== "server") return toast("Servidor local necessário", "Abra pelo BAT para armazenar a assinatura.", "warning");
    const button = $("#upload-signature-image");
    const original = button.innerHTML;
    button.disabled = true;
    button.innerHTML = `<img src="icons/refresh.svg" alt="">Lendo…`;
    try {
      state.signatureSourceFile = file;
      if (/application\/pdf/i.test(file.type || "") || /\.pdf$/i.test(file.name || "")) {
        await importSignaturePdf(file, profile);
      } else {
        if (!/^image\/(png|jpeg|jpg|webp|bmp)$/i.test(file.type || "")) throw new Error("Use PNG, JPG, WEBP, BMP ou PDF.");
        if (file.size > 20 * 1024 * 1024) throw new Error("A imagem ultrapassa o limite de 20 MB.");
        const originalDataUrl = await readFileAsDataUrl(file);
        await saveProcessedSignature({
          profile,
          originalName: file.name,
          originalDataUrl,
          sourceDataUrl: originalDataUrl,
          sourceLabel: "imagem",
        });
      }
    } catch (error) {
      toast("Não foi possível importar a assinatura", error.message, "danger", 10000);
    } finally {
      button.disabled = false;
      button.innerHTML = original;
    }
  }

  async function saveSignatureLayout() {
    const profile = currentSignatureProfile();
    if (!profile) return toast("Selecione um perfil", "Crie ou selecione um cadastro de assinatura.", "warning");
    await saveSignatureProfile();
  }

  function restoreSignatureLayout() {
    $("#signature-x").value = "117";
    $("#signature-y").value = "257";
    $("#signature-width").value = "85";
    $("#signature-rotation").value = "0";
    $("#signature-scale").value = "100";
    $("#signature-offset-x").value = "0";
    $("#signature-offset-y").value = "0";
    updateSignatureEditorVisual();
  }

  async function downloadSignatureSheet() {
    const profile = currentSignatureProfile();
    if (!profile) return toast("Selecione um perfil", "A folha precisa de um cadastro salvo.", "warning");
    try {
      const response = await api("/api/signatures/registration-sheet", {
        method: "POST", timeout: 180000, headers: { "Content-Type": "application/json" }, body: JSON.stringify({ profile_id: profile.id }),
      });
      startServerDownload(response.data?.path);
      toast("Folha de cadastro gerada", "Imprima, assine no quadro e depois fotografe ou digitalize.", "success", 8000);
    } catch (error) {
      toast("Não foi possível gerar a folha", error.message, "danger", 9000);
    }
  }

  let signaturePointerAction = null;

  function beginSignaturePointerAction(event) {
    const page = $("#signature-editor-page");
    const stamp = $("#signature-stamp-box");
    if (!page || !stamp || !currentSignatureProfile()) return;
    const resize = Boolean(event.target.closest(".signature-resize-handle"));
    const rect = page.getBoundingClientRect();
    signaturePointerAction = {
      type: resize ? "resize" : "move",
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      x: Number($("#signature-x").value || 117),
      y: Number($("#signature-y").value || 257),
      width: Number($("#signature-width").value || 85),
      mmPerPixelX: 210 / rect.width,
      mmPerPixelY: 297 / rect.height,
    };
    stamp.setPointerCapture?.(event.pointerId);
    event.preventDefault();
  }

  function moveSignaturePointerAction(event) {
    if (!signaturePointerAction || event.pointerId !== signaturePointerAction.pointerId) return;
    const deltaX = (event.clientX - signaturePointerAction.startX) * signaturePointerAction.mmPerPixelX;
    const deltaY = (event.clientY - signaturePointerAction.startY) * signaturePointerAction.mmPerPixelY;
    if (signaturePointerAction.type === "move") {
      $("#signature-x").value = clampNumber(signaturePointerAction.x + deltaX, -15, 195, 117).toFixed(1);
      $("#signature-y").value = clampNumber(signaturePointerAction.y + deltaY, -15, 285, 257).toFixed(1);
    } else {
      $("#signature-width").value = clampNumber(signaturePointerAction.width + deltaX, 42, 96, 85).toFixed(1);
    }
    updateSignatureEditorVisual();
    event.preventDefault();
  }

  function endSignaturePointerAction(event) {
    if (!signaturePointerAction || event.pointerId !== signaturePointerAction.pointerId) return;
    signaturePointerAction = null;
  }

  function signatureRequestContext() {
    const selected = selectedDacteRows();
    const profile = currentSignatureProfile();
    if (!selected.length) throw new Error("Selecione pelo menos um CT-e já processado.");
    if (!profile) throw new Error("Selecione um perfil de assinatura.");
    if (!profile.ready) throw new Error("Importe a imagem da assinatura para este perfil.");
    return { selected, profile, dateText: $("#signature-date-text").value.trim() || defaultSignatureDate() };
  }

  async function generateSignedDactePreview() {
    if (state.mode !== "server") return toast("Servidor local necessário", "Abra pelo BAT para gerar o PDF assinado.", "warning");
    let context;
    try { context = signatureRequestContext(); } catch (error) { return toast("Assinatura incompleta", error.message, "warning"); }
    const button = $("#generate-signed-preview");
    const original = button.innerHTML;
    button.disabled = true;
    button.innerHTML = `<img src="icons/refresh.svg" alt="">Gerando…`;
    try {
      const response = await api("/api/signatures/preview", {
        method: "POST", timeout: 240000, headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: context.selected[0].path, profile_id: context.profile.id, date_text: context.dateText, include_compact: includeCompactBlock() }),
      });
      const result = response.data || {};
      await renderDactePdfPreview(result, { signed: true, fallbackCte: context.selected[0].cte || "" });
      toast("Prévia assinada gerada", `${result.profile_name || context.profile.name} · ${result.pages || 1} página(s).`, "success", 9000);
    } catch (error) {
      toast("Não foi possível gerar a prévia assinada", error.message, "danger", 11000);
    } finally {
      button.disabled = false;
      button.innerHTML = original;
    }
  }

  async function generateSignedDacteFiles(mode) {
    if (state.mode !== "server") return toast("Servidor local necessário", "Abra pelo BAT para gerar os PDFs assinados.", "warning");
    let context;
    try { context = signatureRequestContext(); } catch (error) { return toast("Assinatura incompleta", error.message, "warning"); }
    if (signatureJobIsActive(state.processing.signature) || dacteJobIsActive(state.processing.dacte)) {
      return toast("Geração já em andamento", "Aguarde a conclusão da operação atual do motor.", "warning", 6500);
    }
    try {
      const response = await api("/api/signatures/generate-job", {
        method: "POST", timeout: 30000, headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ paths: context.selected.map((row) => row.path), profile_id: context.profile.id, date_text: context.dateText, mode, include_compact: includeCompactBlock() }),
      });
      let job = response.data || {};
      state.processing.signature = job;
      renderSignature();
      toast(
        mode === "individuals" ? "Geração dos assinados iniciada" : "Geração do lote assinado iniciada",
        `${job.total || context.selected.length} CT-e(s) serão processados.`,
        "primary", 5000,
      );
      while (job && !["completed", "failed", "discarded", "interrupted"].includes(String(job.state || "").toLowerCase())) {
        await wait(650);
        const status = await api(`/api/jobs/${encodeURIComponent(job.id)}`, { timeout: 15000 });
        job = status.data || job;
        state.processing.signature = job;
        renderSignatureGenerationProgress(job);
        updateSignatureGenerationButtons(job);
      }
      if (String(job.state).toLowerCase() !== "completed") throw new Error(job.error || job.message || "A geração assinada não foi concluída.");
      const result = job.result || {};
      if (result.path) startServerDownload(result.path);
      state.processing.last_signature = result;
      await refreshAll(false);
      state.processing.signature = job;
      renderSignature();
      toast(mode === "individuals" ? "DACTEs assinados gerados" : "Lote assinado gerado", `${result.documents || context.selected.length} documento(s). Download iniciado.`, "success", 8000);
      window.setTimeout(() => {
        if (state.processing.signature?.id === job.id) {
          state.processing.signature = null;
          renderSignature();
        }
      }, 1800);
    } catch (error) {
      const failed = state.processing.signature || { state: "failed", percent: 0, processed: 0, total: context.selected.length, mode };
      failed.state = "failed";
      failed.error = error.message;
      failed.message = "A geração dos DACTEs assinados foi interrompida.";
      state.processing.signature = failed;
      renderSignature();
      toast("Não foi possível gerar os DACTEs assinados", error.message, "danger", 12000);
    }
  }

  async function generateDactePreview() {
    const selected = selectedDacteRows();
    if (!selected.length) return toast("Selecione pelo menos um CT-e", "A prévia exige um documento já processado.", "warning");
    if (state.mode !== "server") return toast("Servidor local necessário", "Abra a Central pelo BAT para usar o renderer oficial.", "warning");
    const button = $("#generate-preview");
    const original = button.innerHTML;
    button.disabled = true;
    button.setAttribute("aria-busy", "true");
    button.innerHTML = `<img src="icons/refresh.svg" alt="">Gerando…`;
    try {
      const response = await api("/api/dacte/preview", {
        method: "POST", timeout: 180000, headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: selected[0].path, include_compact: includeCompactBlock() }),
      });
      const result = response.data || {};
      await renderDactePdfPreview(result, { signed: false, fallbackCte: selected[0].cte || "" });
      toast("Prévia oficial gerada", `CT-e ${result.cte || selected[0].cte || "—"} · ${result.pages || 1} página(s).`, "success", 8000);
    } catch (error) {
      toast("Não foi possível gerar a prévia", error.message, "danger", 10000);
    } finally {
      button.disabled = false;
      button.removeAttribute("aria-busy");
      button.innerHTML = original;
    }
  }

  async function generateDacteFiles(mode) {
    const selected = selectedDacteRows();
    if (!selected.length) return toast("Selecione pelo menos um CT-e", "O PDF exige documentos já processados.", "warning");
    if (state.mode !== "server") return toast("Servidor local necessário", "Abra a Central pelo BAT para gerar os PDFs oficiais.", "warning");
    if (dacteJobIsActive(state.processing.dacte) || signatureJobIsActive(state.processing.signature)) {
      return toast("Geração já em andamento", "Aguarde a conclusão da operação atual do motor.", "warning", 6500);
    }
    try {
      const response = await api("/api/dacte/generate-job", {
        method: "POST", timeout: 30000, headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ paths: selected.map((row) => row.path), mode, include_compact: includeCompactBlock() }),
      });
      let job = response.data || {};
      state.processing.dacte = job;
      renderSignature();
      toast(mode === "individuals" ? "Geração dos DACTEs iniciada" : "Geração do lote iniciada", `${job.total || selected.length} CT-e(s) serão processados.`, "primary", 5000);
      while (job && !["completed", "failed", "discarded", "interrupted"].includes(String(job.state || "").toLowerCase())) {
        await wait(650);
        const status = await api(`/api/jobs/${encodeURIComponent(job.id)}`, { timeout: 15000 });
        job = status.data || job;
        state.processing.dacte = job;
        renderDacteGenerationProgress(job);
        updateDacteGenerationButtons(job);
      }
      if (String(job.state).toLowerCase() !== "completed") throw new Error(job.error || job.message || "A geração oficial não foi concluída.");
      const result = job.result || {};
      if (result.path) startServerDownload(result.path);
      state.processing.last_dacte = result;
      await refreshAll(false);
      state.processing.dacte = job;
      renderSignature();
      toast(mode === "individuals" ? "DACTEs individuais gerados" : "Lote oficial de DACTEs gerado", `${result.documents || selected.length} documento(s). Download iniciado.`, "success", 8000);
      window.setTimeout(() => {
        if (state.processing.dacte?.id === job.id) {
          state.processing.dacte = null;
          renderSignature();
        }
      }, 1800);
    } catch (error) {
      const failed = state.processing.dacte || { state: "failed", percent: 0, processed: 0, total: selected.length, mode };
      failed.state = "failed";
      failed.error = error.message;
      failed.message = "A geração dos DACTEs oficiais foi interrompida.";
      state.processing.dacte = failed;
      renderSignature();
      toast("Não foi possível gerar os DACTEs", error.message, "danger", 12000);
    }
  }

  async function saveSettings() {
    const settings = {
      theme: $("#setting-theme").value,
      density: $("#setting-density").value,
      sidebar: $("#setting-sidebar").value,
      start_page: $("#setting-start-page").value,
    };
    try {
      if (state.mode === "server") {
        const result = await api("/api/settings", { method: "POST", body: JSON.stringify(settings), headers: { "Content-Type": "application/json" } });
        state.settings = result.data;
      } else {
        state.settings = settings;
        localWrite(LOCAL_KEYS.settings, settings);
      }
      applySettings();
      toast("Preferências salvas", "A aparência foi atualizada.", "success");
    } catch (error) {
      toast("Não foi possível salvar", error.message, "danger");
    }
  }

  async function replaceBaseSet(files) {
    const list = Array.from(files || []).filter((file) => /\.sswweb$/i.test(file.name));
    if (!list.length) return toast("Base inválida", "Selecione todo o conjunto de arquivos .sswweb.", "warning");
    if (list.length !== Array.from(files || []).length) return toast("Base inválida", "A Base SSW aceita somente arquivos .sswweb.", "warning");
    const confirmed = window.confirm(`A nova Base possui ${list.length} arquivo(s). O conjunto importado anterior será substituído depois da validação. Deseja continuar?`);
    if (!confirmed) return;
    const batchId = `base_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
    const button = $("#replace-base-set");
    if (button) button.disabled = true;
    try {
      for (let index = 0; index < list.length; index += 1) {
        const file = list[index];
        if (button) button.textContent = `Enviando ${index + 1}/${list.length}…`;
        await api("/api/base/stage", { method: "POST", body: file, timeout: 10 * 60 * 1000, headers: { "Content-Type": "application/octet-stream", "X-Batch-ID": batchId, "X-Filename": file.name } });
      }
      if (button) button.textContent = "Validando e substituindo…";
      const result = await api("/api/base/commit", { method: "POST", timeout: 15 * 60 * 1000, headers: { "Content-Type": "application/json" }, body: JSON.stringify({ batch_id: batchId, expected_count: list.length }) });
      state.baseManagement = result.data || {};
      toast("Base SSW atualizada", `${formatNumber(result.data?.active_file_count || list.length)} arquivo(s) ativos. Reprocesse XMLs e faturas.`, "success", 10000);
      await refreshAll(false);
    } catch (error) {
      toast("Não foi possível substituir a Base", error.message, "danger", 12000);
    } finally {
      if (button) { button.disabled = false; button.innerHTML = '<img src="icons/upload.svg" alt="">Importar e substituir base'; }
    }
  }

  async function replacePartnerTable(file) {
    if (!file || !/\.xlsx$/i.test(file.name)) return toast("Planilha inválida", "Selecione um arquivo XLSX.", "warning");
    if (!window.confirm("O arquivo deve conter exatamente um parceiro. Se o Parceiro ID já existir, somente aquele arquivo será arquivado e substituído após a validação. Continuar?")) return;
    const button = $("#replace-partner-table");
    button.disabled = true;
    updateXmlTaskProgress({ title: "Atualizando tabela de parceiro", percent: 12, processed: 0, total: 1, current: file.name, message: "Enviando e validando a planilha antes da publicação." });
    try {
      const result = await api("/api/developer/partners/import", { method: "POST", body: file, timeout: 10 * 60 * 1000, headers: { "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "X-Filename": file.name } });
      updateXmlTaskProgress({ title: "Tabela de parceiro atualizada", percent: 100, processed: 1, total: 1, current: result.data?.name || result.data?.partner_id || file.name, message: `${formatNumber(result.data?.rules || 0)} regra(s) validadas e compiladas.`, stateName: "completed", autoHide: true });
      toast("Arquivo do parceiro atualizado", `${result.data?.name || result.data?.partner_id || "Parceiro"} · ${formatNumber(result.data?.rules || 0)} regra(s).`, "success", 10000);
      await refreshAll(false);
    } catch (error) {
      updateXmlTaskProgress({ title: "Falha ao atualizar parceiro", percent: 0, current: file.name, message: error.message, stateName: "failed", autoHide: true });
      toast("Não foi possível importar o parceiro", error.message, "danger", 12000);
    } finally {
      button.disabled = false;
    }
  }

  async function deletePartnerFile(partnerId) {
    const partner = state.partnerFiles.find((item) => item.partner_id === partnerId);
    if (!partner) return;
    if (!window.confirm(`Excluir a tabela separada de ${partner.name || partnerId}? Uma cópia será arquivada e a tabela compilada será validada antes da exclusão definitiva.`)) return;
    try {
      await api("/api/developer/partners/delete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ partner_id: partnerId }),
        timeout: 10 * 60 * 1000,
      });
      toast("Parceiro excluído", "O arquivo foi arquivado e removido da tabela compilada.", "success", 9000);
      await refreshAll(false);
    } catch (error) {
      toast("Não foi possível excluir", error.message, "danger", 12000);
    }
  }

  function renderPostgresIntegration() {
    const root = $("#postgres-integration-summary");
    if (!root) return;
    const integration = state.postgresIntegration || {};
    const direct = integration.direct || {};
    const bridge = integration.bridge || {};
    const snapshot = integration.snapshot || {};
    const directTest = direct.last_test || {};
    const directStatus = directTest.checked_at
      ? (directTest.ok ? `Conectado · ${formatNumber(directTest.latency_ms || 0)} ms` : `Falhou · ${directTest.error || "sem resposta"}`)
      : (direct.enabled ? "Habilitado, ainda não testado" : "Desativado — use a ponte local");
    const snapshotStatus = snapshot.available
      ? `${formatNumber(snapshot.row_count || 0)} registros · recebido ${formatDate(snapshot.received_at || snapshot.generated_at)}`
      : "Nenhum snapshot recebido";
    root.innerHTML = [
      ["Modo", integration.mode === "sombra" ? "Sombra / somente leitura" : (integration.mode || "sombra")],
      ["Fonte", integration.source || "staging.stg_ssw_455_fretes"],
      ["Acesso direto", directStatus],
      ["Ponte local", bridge.token_configured ? "Token configurado" : "Token ainda não criado"],
      ["Snapshot", snapshotStatus],
      ["Última carga no banco", snapshot.last_data_carga ? formatDate(snapshot.last_data_carga) : "—"],
      ["Arquivos 455", formatNumber(snapshot.arquivo_origem_count || 0)],
      ["SUBC encontrados", formatNumber(snapshot.subc_count || 0)],
    ].map(([label, value]) => `<div class="security-status-row"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`).join("")
      + `<small class="settings-hint">${escapeHtml(snapshot.compatibility_warning || integration.message || "")}</small>`;

    const directConfigured = Boolean(direct.configured && direct.enabled);
    $("#postgres-test-direct").disabled = !directConfigured;
    $("#postgres-sync-direct").disabled = !directConfigured;
    $("#postgres-compare-base").disabled = !snapshot.available;

    const tokenBox = $("#postgres-bridge-token-box");
    const tokenCode = $("#postgres-bridge-token");
    if (state.postgresBridgeToken) {
      tokenBox.classList.remove("hidden");
      tokenCode.textContent = state.postgresBridgeToken;
    } else {
      tokenBox.classList.add("hidden");
      tokenCode.textContent = "";
    }

    const comparison = state.postgresComparison;
    const comparisonRoot = $("#postgres-comparison-summary");
    if (!comparisonRoot) return;
    comparisonRoot.innerHTML = comparison ? [
      ["Registros PostgreSQL", formatNumber(comparison.postgres_rows || 0)],
      ["Registros Base SSW", formatNumber(comparison.base_rows || 0)],
      ["Correspondências", formatNumber(comparison.matched || 0)],
      ["Fretes iguais", formatNumber(comparison.freight_equal || 0)],
      ["Fretes divergentes", formatNumber(comparison.freight_different || 0)],
      ["Compatibilidade de frete", `${Number(comparison.freight_compatibility_percent || 0).toFixed(2)}%`],
    ].map(([label, value]) => `<div class="security-status-row"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`).join("")
      + `<small class="settings-hint">${escapeHtml(comparison.message || "")}</small>` : "";
  }

  async function refreshPostgresStatus(showToast = false) {
    try {
      const result = await api("/api/developer/postgres/status", { timeout: 20000 });
      state.postgresIntegration = result.data || {};
      renderPostgresIntegration();
      if (showToast) toast("PostgreSQL atualizado", "Status da integração somente leitura recarregado.", "success");
    } catch (error) {
      if (showToast) toast("Falha ao consultar PostgreSQL", error.message, "danger", 9000);
    }
  }

  async function rotatePostgresBridgeToken() {
    if (!window.confirm("Gerar um novo token invalida imediatamente o token anterior da ponte PostgreSQL. Continuar?")) return;
    const button = $("#postgres-rotate-bridge-token");
    button.disabled = true;
    try {
      const result = await api("/api/developer/postgres/bridge-token/rotate", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}", timeout: 30000 });
      state.postgresBridgeToken = String(result.data?.token || "");
      state.postgresIntegration = result.data?.status || state.postgresIntegration;
      renderPostgresIntegration();
      toast("Token da ponte criado", "Copie o token agora. Ele não será exibido novamente após recarregar a página.", "warning", 10000);
    } catch (error) {
      toast("Não foi possível gerar o token", error.message, "danger", 9000);
    } finally {
      button.disabled = false;
    }
  }

  async function copyPostgresBridgeToken() {
    if (!state.postgresBridgeToken) return;
    try {
      await navigator.clipboard.writeText(state.postgresBridgeToken);
      toast("Token copiado", "Cole-o na ponte PowerShell do computador da empresa.", "success");
    } catch (error) {
      toast("Não foi possível copiar", "Selecione o token exibido e copie manualmente.", "warning");
    }
  }

  async function testPostgresDirect() {
    const button = $("#postgres-test-direct");
    button.disabled = true;
    try {
      const result = await api("/api/developer/postgres/test", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}", timeout: 45000 });
      await refreshPostgresStatus(false);
      toast("PostgreSQL conectado", `Banco ${result.data?.database || "—"} em modo ${result.data?.transaction_read_only || "read-only"}.`, "success", 8000);
    } catch (error) {
      await refreshPostgresStatus(false);
      toast("Acesso direto indisponível", `${error.message} Se a VPS não alcança 192.168.0.247, utilize a ponte local.`, "warning", 12000);
    } finally {
      renderPostgresIntegration();
    }
  }

  async function syncPostgresDirect() {
    if (!window.confirm("Sincronizar agora cria apenas um snapshot sombra. A Base SSW oficial não será substituída. Continuar?")) return;
    const button = $("#postgres-sync-direct");
    button.disabled = true;
    try {
      const result = await api("/api/developer/postgres/sync-direct", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ max_rows: 300000 }), timeout: 15 * 60 * 1000 });
      await refreshPostgresStatus(false);
      toast("Snapshot PostgreSQL criado", `${formatNumber(result.data?.row_count || 0)} registro(s) recebidos em modo sombra.`, "success", 9000);
    } catch (error) {
      toast("Não foi possível sincronizar", error.message, "danger", 12000);
    } finally {
      renderPostgresIntegration();
    }
  }

  async function comparePostgresWithBase() {
    const button = $("#postgres-compare-base");
    button.disabled = true;
    state.postgresComparison = null;
    renderPostgresIntegration();
    try {
      const result = await api("/api/developer/postgres/compare", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}", timeout: 15 * 60 * 1000 });
      state.postgresComparison = result.data || null;
      renderPostgresIntegration();
      toast("Comparação concluída", `${Number(result.data?.freight_compatibility_percent || 0).toFixed(2)}% dos fretes correspondentes estão iguais.`, "success", 10000);
    } catch (error) {
      toast("Não foi possível comparar", error.message, "danger", 12000);
    } finally {
      renderPostgresIntegration();
    }
  }

  async function clearQaNotebook() {
    if (!window.confirm(`Apagar ${state.qa.length} anotação(ões) do caderno? Uma cópia será arquivada para auditoria.`)) return;
    try {
      const result = await api("/api/developer/qa/clear", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
      state.qa = [];
      renderAll();
      toast("Caderno limpo", `${formatNumber(result.data?.deleted || 0)} anotação(ões) arquivada(s) e removida(s).`, "success");
    } catch (error) {
      toast("Não foi possível limpar o caderno", error.message, "danger", 9000);
    }
  }

  async function saveDeveloperFeatures() {
    const payload = {};
    $$('[data-feature]').forEach((input) => { payload[input.dataset.feature] = input.checked; });
    const button = $("#save-developer-features");
    button.disabled = true;
    try {
      const result = await api("/api/developer/features", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
      state.developerFeatures = result.data || {};
      toast("Configuração extra salva", "As permissões serão aplicadas no próximo carregamento de cada usuário.", "success");
    } catch (error) {
      toast("Não foi possível salvar", error.message, "danger");
    } finally {
      button.disabled = false;
    }
  }

  function bindEvents() {
    $("#auth-form").addEventListener("submit", submitAuthentication);
    $("#logout-button").addEventListener("click", logout);
    $("#user-chip").addEventListener("click", () => openOwnPasswordModal(false));
    $("#open-own-password").addEventListener("click", () => openOwnPasswordModal(false));
    $("#own-password-logout").addEventListener("click", logout);
    $("#own-password-form").addEventListener("submit", submitOwnPasswordChange);
    $$(".own-password-close").forEach((button) => button.addEventListener("click", closeOwnPasswordModal));
    $("#own-password-modal").addEventListener("click", (event) => { if (event.target === $("#own-password-modal")) closeOwnPasswordModal(); });
    $("#refresh-system-health").addEventListener("click", () => loadSecurityData(true));
    $("#create-backup").addEventListener("click", createBackup);
    $("#restore-backup").addEventListener("click", () => $("#restore-backup-file").click());
    $("#restore-backup-file").addEventListener("change", (event) => restoreBackupFile(event.target.files?.[0]));
    $("#recovery-job-list").addEventListener("click", (event) => {
      const retry = event.target.closest("[data-retry-job]");
      const discard = event.target.closest("[data-discard-job]");
      if (retry) recoverJob(retry.dataset.retryJob, "retry");
      if (discard && window.confirm("Descartar este aviso de recuperação?")) recoverJob(discard.dataset.discardJob, "discard");
    });
    $("#admin-user-form").addEventListener("submit", createAdminUser);
    $("#admin-user-list").addEventListener("click", (event) => {
      const edit = event.target.closest("[data-edit-user]");
      if (edit) openUserEditModal(edit.dataset.editUser);
    });
    $("#user-edit-form").addEventListener("submit", saveUserEdit);
    $$(".user-edit-close").forEach((button) => button.addEventListener("click", closeUserEditModal));
    $("#user-edit-modal").addEventListener("click", (event) => { if (event.target === $("#user-edit-modal")) closeUserEditModal(); });
    $("#delete-user").addEventListener("click", deleteEditedUser);
    $("#reset-user-password").addEventListener("click", () => resetEditedUserPassword(false));
    $("#generate-temporary-password").addEventListener("click", () => resetEditedUserPassword(true));
    $("#copy-temporary-password").addEventListener("click", copyTemporaryPassword);
    $("#revoke-user-sessions").addEventListener("click", revokeEditedUserSessions);
    $("#replace-base-set").addEventListener("click", () => $("#developer-base-input").click());
    $("#developer-base-input").addEventListener("change", (event) => replaceBaseSet(event.target.files).finally(() => { event.target.value = ""; }));
    $("#postgres-refresh-status").addEventListener("click", () => refreshPostgresStatus(true));
    $("#postgres-test-direct").addEventListener("click", testPostgresDirect);
    $("#postgres-sync-direct").addEventListener("click", syncPostgresDirect);
    $("#postgres-compare-base").addEventListener("click", comparePostgresWithBase);
    $("#postgres-rotate-bridge-token").addEventListener("click", rotatePostgresBridgeToken);
    $("#postgres-copy-bridge-token").addEventListener("click", copyPostgresBridgeToken);
    $("#download-partner-model").addEventListener("click", () => { window.location.href = "/api/developer/partners/model"; });
    $("#download-partner-template").addEventListener("click", () => { window.location.href = "/api/developer/partners/template"; });
    $("#replace-partner-table").addEventListener("click", () => $("#developer-partner-input").click());
    $("#developer-partner-input").addEventListener("change", (event) => replacePartnerTable(event.target.files?.[0]).finally(() => { event.target.value = ""; }));
    $("#partner-file-list").addEventListener("click", (event) => {
      const button = event.target.closest("[data-delete-partner-file]");
      if (button) deletePartnerFile(button.dataset.deletePartnerFile);
    });
    $("#clear-qa-notebook").addEventListener("click", clearQaNotebook);
    $("#save-developer-features").addEventListener("click", saveDeveloperFeatures);
    $("#main-nav").addEventListener("click", (event) => {
      const button = event.target.closest("[data-page]");
      if (button) navigate(button.dataset.page);
    });
    document.addEventListener("click", (event) => {
      const nav = event.target.closest("[data-nav]");
      if (nav) navigate(nav.dataset.nav);
      if (!event.target.closest(".global-search-wrap")) $("#global-results").classList.add("hidden");
    });

    $("#collapse-sidebar").addEventListener("click", () => {
      state.settings.sidebar = state.settings.sidebar === "compacta" ? "padrao" : "compacta";
      applySettings(true);
    });
    $("#mobile-menu").addEventListener("click", () => { $("#sidebar").classList.add("mobile-open"); $("#mobile-overlay").classList.add("open"); });
    $("#mobile-overlay").addEventListener("click", () => { $("#sidebar").classList.remove("mobile-open"); $("#mobile-overlay").classList.remove("open"); });
    $("#refresh-all").addEventListener("click", () => refreshAll());

    $("#add-xml").addEventListener("click", () => $("#xml-input").click());
    $("#add-xml-folder").addEventListener("click", () => $("#xml-folder-input").click());
    $("#add-table").addEventListener("click", () => $("#table-input").click());
    $("#add-invoices").addEventListener("click", () => $("#invoice-input").click());
    $("#xml-input").addEventListener("change", (event) => uploadFiles("xml", event.target.files).finally(() => { event.target.value = ""; }));
    $("#xml-folder-input").addEventListener("change", (event) => uploadFiles("xml", event.target.files).finally(() => { event.target.value = ""; }));
    $("#table-input").addEventListener("change", (event) => replacePartnerTable(event.target.files?.[0]).finally(() => { event.target.value = ""; }));
    $("#invoice-input").addEventListener("change", (event) => uploadFiles("faturas", event.target.files).finally(() => { event.target.value = ""; }));
    $("#process-xml").addEventListener("click", () => processAction("xml"));
    $("#clear-xml-list").addEventListener("click", clearXmlList);
    $("#add-complementary-info").addEventListener("click", openComplementaryModal);
    $("#process-invoices").addEventListener("click", () => processAction("invoices"));
    $("#clear-invoice-list").addEventListener("click", clearInvoiceList);

    $("#xml-filter").addEventListener("input", renderXml);
    $("#xml-status-filter").addEventListener("change", renderXml);
    $("#invoice-filter").addEventListener("input", renderInvoices);
    $("#toggle-invoice-file-panel")?.addEventListener("click", () => setInvoiceFilePanelCollapsed(!state.invoiceFilePanelCollapsed, { touched: true }));
    $("#audit-filter").addEventListener("input", renderAudit);
    $("#audit-view").addEventListener("change", renderAudit);
    $("#audit-table-body").addEventListener("click", (event) => {
      const row = event.target.closest("[data-audit-index]");
      if (row) showXmlDetail(state.xmls[Number(row.dataset.auditIndex)]);
    });
    $("#partner-filter").addEventListener("input", renderPartners);
    $("#reload-partners").addEventListener("click", () => refreshAll());
    $("#signature-filter").addEventListener("input", renderSignature);
    ["#signature-status-filter", "#signature-partner-filter", "#signature-city-filter", "#signature-result-filter", "#signature-sort-filter"].forEach((selector) => {
      $(selector)?.addEventListener("change", renderSignature);
    });
    $("#reset-signature-filters")?.addEventListener("click", () => {
      $("#signature-filter").value = "";
      $("#signature-status-filter").value = "ready";
      $("#signature-partner-filter").value = "all";
      $("#signature-city-filter").value = "all";
      $("#signature-result-filter").value = "all";
      $("#signature-sort-filter").value = "cte_desc";
      renderSignature();
    });
    $("#signature-include-compact").addEventListener("change", () => {
      resetDactePreview();
      toast("Modelo do DACTE atualizado", includeCompactBlock() ? "O bloco compacto será exibido." : "O bloco compacto será removido dos próximos PDFs.", "primary", 3500);
    });

    $("#xml-table-body").addEventListener("click", (event) => {
      const button = event.target.closest("[data-xml-detail-index]");
      const tableRow = event.target.closest("[data-xml-index]");
      const index = Number(button?.dataset.xmlDetailIndex ?? tableRow?.dataset.xmlIndex);
      if (Number.isInteger(index) && state.xmls[index]) showXmlDetail(state.xmls[index]);
    });

    $("#invoice-table-body").addEventListener("click", (event) => {
      const tableRow = event.target.closest("[data-invoice-key]");
      if (!tableRow) return;
      const key = tableRow.dataset.invoiceKey;
      const row = state.invoices.find((item) => String(item.invoice_key || item.invoice || item.file) === key);
      if (row) showInvoiceDetail(row);
    });
    $("#partner-list").addEventListener("click", (event) => {
      const button = event.target.closest("[data-partner-id]");
      if (button) { state.selectedPartner = button.dataset.partnerId; renderPartners(); }
    });
    $("#signature-list").addEventListener("change", (event) => {
      const input = event.target.closest("[data-signature-index]");
      if (!input || input.disabled) return;
      const row = state.xmls[Number(input.dataset.signatureIndex)];
      const path = String(row?.path || "");
      if (!path) return;
      if (input.checked) state.selectedSignature.add(path); else state.selectedSignature.delete(path);
      updateDacteSelectionSummary();
    });
    $("#select-all-dactes").addEventListener("click", () => {
      filteredSignatureCandidates().filter(({ row }) => isOfficialCte(row)).forEach(({ row }) => state.selectedSignature.add(String(row.path)));
      renderSignature();
    });
    $("#unselect-visible-dactes")?.addEventListener("click", () => {
      filteredSignatureCandidates().filter(({ row }) => isOfficialCte(row)).forEach(({ row }) => state.selectedSignature.delete(String(row.path)));
      resetDactePreview();
      renderSignature();
    });
    $("#clear-dacte-selection").addEventListener("click", () => {
      state.selectedSignature.clear();
      resetDactePreview();
      renderSignature();
    });
    $("#generate-preview").addEventListener("click", generateDactePreview);
    $("#generate-dacte-batch").addEventListener("click", () => generateDacteFiles("batch"));
    $("#generate-dacte-individuals").addEventListener("click", () => generateDacteFiles("individuals"));
    $("#generate-signed-preview").addEventListener("click", generateSignedDactePreview);
    $("#generate-signed-dacte-batch").addEventListener("click", () => generateSignedDacteFiles("batch"));
    $("#generate-signed-dacte-individuals").addEventListener("click", () => generateSignedDacteFiles("individuals"));

    $("#new-signature-profile").addEventListener("click", newSignatureProfile);
    $("#save-signature-profile").addEventListener("click", saveSignatureProfile);
    $("#save-signature-layout").addEventListener("click", saveSignatureLayout);
    $("#restore-signature-layout").addEventListener("click", restoreSignatureLayout);
    $("#delete-signature-profile").addEventListener("click", deleteSignatureProfile);
    $("#download-signature-sheet").addEventListener("click", downloadSignatureSheet);
    $("#signature-profile-select").addEventListener("change", (event) => {
      state.selectedSignatureProfile = String(event.target.value || "");
      state.signatureSourceFile = null;
      state.signaturePdfImport = null;
      renderSignaturePdfCandidates();
      loadSignatureProfileForm(currentSignatureProfile());
      renderSignature();
    });
    $("#upload-signature-image").addEventListener("click", () => $("#signature-image-input").click());
    $("#signature-image-input").addEventListener("change", (event) => {
      const file = event.target.files?.[0];
      if (file) importSignatureImage(file);
      event.target.value = "";
    });
    $("#signature-pdf-candidates").addEventListener("click", (event) => {
      const candidate = event.target.closest("[data-pdf-candidate-index]");
      if (candidate) chooseSignaturePdfCandidate(candidate.dataset.pdfCandidateIndex);
      if (event.target.closest("[data-cancel-pdf-import]")) {
        state.signaturePdfImport = null;
        renderSignaturePdfCandidates();
      }
    });
    $("#signature-crop-canvas").addEventListener("pointerdown", beginSignatureCrop);
    $("#signature-crop-canvas").addEventListener("pointermove", moveSignatureCrop);
    $("#signature-crop-canvas").addEventListener("pointerup", endSignatureCrop);
    $("#signature-crop-canvas").addEventListener("pointercancel", endSignatureCrop);
    $("#reset-signature-crop").addEventListener("click", resetSignatureCrop);
    $("#apply-signature-crop").addEventListener("click", applySignatureCrop);
    $$(".signature-crop-close").forEach((button) => button.addEventListener("click", closeSignatureCrop));
    $("#signature-crop-modal").addEventListener("click", (event) => { if (event.target === $("#signature-crop-modal")) closeSignatureCrop(); });
    $("#dacte-preview-zoom").addEventListener("change", updateDactePreviewZoom);
    $("#open-dacte-preview").addEventListener("click", openDactePreviewInNewTab);
    $("#download-dacte-preview").addEventListener("click", downloadDactePreview);
    $("#fullscreen-dacte-preview").addEventListener("click", toggleDactePreviewFullscreen);
    document.addEventListener("fullscreenchange", () => {
      const button = $("#fullscreen-dacte-preview");
      if (button) button.innerHTML = document.fullscreenElement
        ? `<img src="icons/expand.svg" alt="">Sair da tela cheia`
        : `<img src="icons/expand.svg" alt="">Tela cheia`;
    });
    $("#signature-threshold").addEventListener("input", (event) => {
      $("#signature-threshold-value").textContent = String(event.target.value);
    });
    ["#signature-x", "#signature-y", "#signature-width", "#signature-rotation", "#signature-scale", "#signature-offset-x", "#signature-offset-y", "#signature-title", "#signature-date-text"].forEach((selector) => {
      $(selector).addEventListener("input", updateSignatureEditorVisual);
    });
    $("#signature-stamp-box").addEventListener("pointerdown", beginSignaturePointerAction);
    window.addEventListener("pointermove", moveSignaturePointerAction, { passive: false });
    window.addEventListener("pointerup", endSignaturePointerAction);
    window.addEventListener("pointercancel", endSignaturePointerAction);
    $("#signature-stamp-box").addEventListener("keydown", (event) => {
      const step = event.shiftKey ? 5 : 0.5;
      if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)) return;
      const x = Number($("#signature-x").value || 117);
      const y = Number($("#signature-y").value || 257);
      if (event.key === "ArrowLeft") $("#signature-x").value = clampNumber(x - step, -15, 195, 117).toFixed(1);
      if (event.key === "ArrowRight") $("#signature-x").value = clampNumber(x + step, -15, 195, 117).toFixed(1);
      if (event.key === "ArrowUp") $("#signature-y").value = clampNumber(y - step, -15, 285, 257).toFixed(1);
      if (event.key === "ArrowDown") $("#signature-y").value = clampNumber(y + step, -15, 285, 257).toFixed(1);
      updateSignatureEditorVisual();
      event.preventDefault();
    });

    $("#close-drawer").addEventListener("click", closeDrawer);
    $("#drawer-backdrop").addEventListener("click", closeDrawer);

    $("#open-qa").addEventListener("click", openQaModal);
    $("#open-qa-settings").addEventListener("click", openQaModal);
    $$(".modal-close").forEach((button) => button.addEventListener("click", closeQaModal));
    $("#qa-modal").addEventListener("click", (event) => { if (event.target === $("#qa-modal")) closeQaModal(); });
    $$(".complementary-close").forEach((button) => button.addEventListener("click", closeComplementaryModal));
    $("#complementary-modal").addEventListener("click", (event) => { if (event.target === $("#complementary-modal")) closeComplementaryModal(); });
    $("#complementary-form").addEventListener("submit", saveComplementaryInformation);
    $("#complementary-text").addEventListener("input", updateComplementaryCounter);
    $("#remove-complementary-info").addEventListener("click", removeComplementaryInformation);
    $("#qa-form").addEventListener("submit", (event) => { event.preventDefault(); saveQa(event.currentTarget); });
    $("#qa-attachment").addEventListener("change", (event) => updateQaAttachmentPreview(event.target.files?.[0]));
    $("#qa-attachment-preview").addEventListener("click", (event) => {
      if (!event.target.closest("#remove-qa-attachment")) return;
      $("#qa-attachment").value = "";
      updateQaAttachmentPreview(null);
    });

    $("#generate-xml-xlsx").addEventListener("click", () => generateOfficialReport("xml"));
    $("#generate-invoice-xlsx").addEventListener("click", () => generateOfficialReport("invoices"));
    $("#generate-invoice-problems-xlsx").addEventListener("click", () => generateOfficialReport("invoices", true));
    $("#export-xml-csv").addEventListener("click", exportXmlCsv);
    $("#export-qa-json").addEventListener("click", () => {
      if (state.mode !== "server") {
        downloadBlob(`central_cte_qa_${new Date().toISOString().slice(0, 10)}.json`, JSON.stringify(state.qa, null, 2), "application/json;charset=utf-8");
        return toast("JSON exportado", "No modo local do navegador não existem arquivos de imagem no servidor.", "warning", 7000);
      }
      window.location.href = "/api/developer/qa/export";
      toast("Preparando ZIP", `${state.qa.length} ocorrência(s) e as imagens disponíveis serão incluídas.`, "primary", 5000);
    });
    $("#save-settings").addEventListener("click", saveSettings);

    $("#global-search").addEventListener("input", (event) => globalSearch(event.target.value));
    $("#global-results").addEventListener("click", (event) => {
      const button = event.target.closest("[data-result-index]");
      if (!button) return;
      const results = JSON.parse($("#global-results").dataset.results || "[]");
      const item = results[Number(button.dataset.resultIndex)];
      if (!item) return;
      if (item.partnerId) state.selectedPartner = item.partnerId;
      navigate(item.page);
      $("#global-results").classList.add("hidden");
      if (item.page === "audit" && Number.isInteger(item.index)) showXmlDetail(state.xmls[item.index]);
    });

    $("#spamton-close")?.addEventListener("click", closeSpamtonEasterEgg);
    $("#spamton-audio-toggle")?.addEventListener("click", () => {
      const audio = $("#spamton-audio");
      if (!audio) return;
      if (audio.paused) void playSpamtonAudio();
      else {
        audio.pause();
        updateSpamtonAudioState();
      }
    });
    $("#spamton-audio")?.addEventListener("play", () => updateSpamtonAudioState());
    $("#spamton-audio")?.addEventListener("pause", () => updateSpamtonAudioState());
    $("#spamton-audio")?.addEventListener("error", () => updateSpamtonAudioState("NÃO FOI POSSÍVEL CARREGAR O ÁUDIO"));

    document.addEventListener("keydown", (event) => {
      handleKonamiCode(event);
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault(); $("#global-search").focus(); $("#global-search").select();
      }
      if (event.key === "Escape") { closeSpamtonEasterEgg(); closeDrawer(); closeQaModal(); closeComplementaryModal(); closeSignatureCrop(); closeOwnPasswordModal(); $("#global-results").classList.add("hidden"); }
    });
  }

  async function init() {
    bindEvents();
    const ready = await detectMode();
    if (!ready) return;
    applySettings();
    renderAll();
    const hashPage = location.hash.replace("#", "");
    const startPage = $( `#page-${hashPage}`) ? hashPage : state.settings.start_page;
    navigate(startPage || "dashboard", false);
    ensurePasswordChangePrompt();
  }

  init().catch((error) => {
    console.error(error);
    toast("Falha ao iniciar a interface", error.message, "danger", 10000);
  });
})();
