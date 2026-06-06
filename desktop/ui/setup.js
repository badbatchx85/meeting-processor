// Build-less page: use the injected global bridge (app.withGlobalTauri = true).
const { invoke } = window.__TAURI__.core;
const { listen } = window.__TAURI__.event;

const statusEl = document.getElementById("status");
const checksEl = document.getElementById("checks");
const actionEl = document.getElementById("action");
const logEl = document.getElementById("log");

const LABELS = { brew: "Homebrew", python311: "Python 3.11", ffmpeg: "ffmpeg", venv: "Ambiente Python" };

listen("setup://log", (e) => {
  logEl.hidden = false;
  logEl.textContent += e.payload + "\n";
  logEl.scrollTop = logEl.scrollHeight;
});

function renderChecks(p) {
  checksEl.innerHTML = "";
  for (const [key, label] of Object.entries(LABELS)) {
    const li = document.createElement("li");
    const ok = p[key] === "ok";
    li.className = ok ? "ok" : "missing";
    li.textContent = `${label}: ${p[key] === "ok" ? "pronto" : p[key] === "wrong_version" ? "versão incorreta" : "faltando"}`;
    checksEl.appendChild(li);
  }
}

function missingList(p) {
  // venv is produced by bootstrap, not installed; brew/python311/ffmpeg are installable.
  return ["brew", "python311", "ffmpeg"].filter((k) => p[k] !== "ok");
}

async function launchServer() {
  statusEl.textContent = "Iniciando o servidor…";
  actionEl.hidden = true;
  try {
    const uiUrl = await invoke("start_server");
    window.location.replace(uiUrl); // hand off to the existing SPA
  } catch (err) {
    showError(String(err));
  }
}

function showError(msg) {
  statusEl.textContent = "Algo deu errado.";
  logEl.hidden = false;
  logEl.textContent += "ERRO: " + msg + "\n";
  actionEl.hidden = false;
  actionEl.textContent = "Tentar novamente";
  actionEl.disabled = false;
  actionEl.onclick = detect;
}

async function runSetup(missing) {
  actionEl.disabled = true;
  statusEl.textContent = "Instalando dependências…";
  try {
    if (missing.includes("brew")) await invoke("install_prerequisite", { name: "brew" });
    if (missing.includes("python311")) await invoke("install_prerequisite", { name: "python311" });
    if (missing.includes("ffmpeg")) await invoke("install_prerequisite", { name: "ffmpeg" });
    await invoke("bootstrap_venv");
    await launchServer();
  } catch (err) {
    showError(String(err));
  }
}

async function detect() {
  statusEl.textContent = "Verificando o sistema…";
  actionEl.hidden = true;
  logEl.hidden = true;
  logEl.textContent = "";
  let p;
  try {
    p = await invoke("check_prerequisites");
  } catch (err) {
    return showError(String(err));
  }
  renderChecks(p);

  const missing = missingList(p);
  const needsVenv = p.venv !== "ok";

  if (missing.length === 0 && !needsVenv) {
    return launchServer();
  }
  if (missing.length === 0 && needsVenv) {
    statusEl.textContent = "Configurando o ambiente pela primeira vez…";
    return runSetup([]);
  }
  statusEl.textContent = "Alguns componentes precisam ser instalados.";
  actionEl.hidden = false;
  actionEl.textContent = "Instalar e configurar";
  actionEl.disabled = false;
  actionEl.onclick = () => runSetup(missing);
}

detect();
