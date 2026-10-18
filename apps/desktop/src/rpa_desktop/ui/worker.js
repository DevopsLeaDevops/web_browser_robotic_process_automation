// RPA Worker 狀態視窗（M10.1）：向 Python（pywebview 的 js_api）取狀態並畫出來，按鈕呼叫 Python 的動作。
// 文字一律來自訊息目錄（頁面產生時嵌入 #strings）；這裡不寫使用者看得到的字。
"use strict";
(function () {
  const S = JSON.parse(document.getElementById("strings").textContent);
  const lang = document.documentElement.lang;
  const $ = (id) => document.getElementById(id);
  let state = null;
  let busy = false;
  let pending = null;

  function text(key, params) {
    const template = S[key] !== undefined ? S[key] : key;
    return template.replace(/\{(\w+)\}/g, (all, name) =>
      params && params[name] !== undefined ? String(params[name]) : all,
    );
  }

  function api() {
    return window.pywebview && window.pywebview.api ? window.pywebview.api : null;
  }

  function call(name, ...args) {
    const bridge = api();
    if (!bridge || typeof bridge[name] !== "function") {
      return Promise.resolve(null);
    }
    return bridge[name](...args).catch((error) => {
      console.error(name, error);
      return null;
    });
  }

  function fillTexts() {
    document.querySelectorAll("[data-text]").forEach((node) => {
      node.textContent = text(node.dataset.text);
    });
    document.querySelectorAll("[data-placeholder]").forEach((node) => {
      node.placeholder = text(node.dataset.placeholder);
    });
    document.title = text("window.title");
  }

  const PHASE_COLORS = {
    online: "green",
    paused: "amber",
    offline: "red",
    error: "red",
    downloading: "blue",
    connecting: "blue",
    pairing: "blue",
    stopping: "amber",
  };

  function show(id, visible) {
    $(id).hidden = !visible;
  }

  function time(ms) {
    if (!ms) return "";
    const date = new Date(ms);
    const options = { hour: "2-digit", minute: "2-digit", second: "2-digit" };
    if (date.toDateString() !== new Date().toDateString()) {
      options.month = "2-digit";
      options.day = "2-digit";
    }
    return date.toLocaleString(lang, options);
  }

  function statusLabel(status) {
    return text("window.status." + (status || "running"));
  }

  function statusColor(status) {
    if (!status) return "blue";
    if (status === "passed") return "green";
    if (status === "cancelled" || status === "abandoned") return "";
    return "red";
  }

  function badge(label, color) {
    const span = document.createElement("span");
    span.className = "badge" + (color ? " " + color : "");
    span.textContent = label;
    return span;
  }

  function renderMessage(s) {
    const box = $("message");
    if (!s.message) {
      box.hidden = true;
      return;
    }
    box.hidden = false;
    box.className = "notice" + (s.message.level === "info" ? "" : " " + s.message.level);
    $("message-text").textContent = s.message.text;
    show("retry", s.phase === "error" && s.paired);
  }

  function renderStatus(s) {
    $("server-value").textContent = s.server || "";
    $("device-value").textContent =
      s.name && s.device && s.name !== s.device ? text("window.device_name", { name: s.name, device: s.device }) : s.device || "";
    $("version-value").textContent = s.version || "";
    $("storage-value").textContent = s.storage === "file" ? text("window.storage_file") : text("window.storage_keyring");
    $("home-value").textContent = s.home || "";
    show("version-warning", s.sameVersion === false);
    show("paused-hint", s.paused && s.phase !== "stopping");
    show("stopping-hint", s.phase === "stopping");
    const current = $("current");
    current.replaceChildren();
    if (s.current) {
      const id = document.createElement("span");
      id.className = "mono";
      id.textContent = s.current.run;
      current.append(id, badge(s.current.headless ? text("window.headless") : text("window.headed"), ""), " ", time(s.current.started));
    } else {
      current.textContent = text("window.idle");
    }
  }

  function renderRecent(s) {
    const body = $("recent");
    body.replaceChildren();
    for (const run of s.recent) {
      const row = document.createElement("tr");
      const cells = [run.run, time(run.started), run.headless ? text("window.headless") : text("window.headed")];
      for (const value of cells) {
        const cell = document.createElement("td");
        cell.textContent = value;
        row.append(cell);
      }
      const result = document.createElement("td");
      result.append(badge(statusLabel(run.status), statusColor(run.status)));
      row.append(result);
      body.append(row);
    }
    show("recent-empty", s.recent.length === 0);
  }

  function renderSettings(s) {
    const settings = s.settings;
    const autostart = $("autostart");
    autostart.checked = settings.autostart;
    autostart.disabled = !settings.autostartSupported;
    show("autostart-unsupported", !settings.autostartSupported);
    $("firefox").checked = settings.firefox;
    show("firefox-setting", s.paired); // 還沒配對時在配對表單裡選
    if (document.activeElement !== $("mirror")) $("mirror").value = settings.downloadHost || "";
    $("language").value = settings.language;
    show("reset", s.paired);
  }

  function render(s) {
    state = s;
    const phase = $("phase");
    phase.textContent = text("window.phase." + s.phase);
    phase.className = "badge" + (PHASE_COLORS[s.phase] ? " " + PHASE_COLORS[s.phase] : "");
    const pairing = s.phase === "unpaired" || s.phase === "pairing" || (!s.paired && s.phase === "error");
    show("pair-panel", pairing);
    $("pair-button").disabled = s.phase === "pairing";
    show("download-panel", s.phase === "downloading");
    if (s.progress) {
      $("download-browser").textContent = s.progress.browser;
      const known = typeof s.progress.percent === "number";
      $("download-bar").classList.toggle("unknown", !known);
      $("download-bar").firstElementChild.style.width = known ? s.progress.percent + "%" : "";
      $("download-text").textContent = known ? s.progress.percent + "%" : text("window.download_unknown");
    }
    show("status-panel", s.paired);
    show("recent-panel", s.paired);
    const connected = ["online", "offline", "paused", "connecting"].includes(s.phase);
    const pause = $("pause");
    pause.hidden = !(s.paired && connected);
    pause.textContent = s.paused ? text("window.resume") : text("window.pause");
    renderMessage(s);
    if (s.paired) {
      renderStatus(s);
      renderRecent(s);
    }
    renderSettings(s);
  }

  function refresh() {
    if (busy) {
      pending = true;
      return Promise.resolve();
    }
    busy = true;
    return call("state")
      .then((s) => {
        if (s) render(s);
      })
      .finally(() => {
        busy = false;
        if (pending) {
          pending = null;
          refresh();
        }
      });
  }

  function confirmDialog(message) {
    const dialog = $("dialog");
    $("dialog-text").textContent = message;
    return new Promise((resolve) => {
      const done = (answer) => {
        $("dialog-ok").onclick = null;
        $("dialog-cancel").onclick = null;
        dialog.close();
        resolve(answer);
      };
      $("dialog-ok").onclick = () => done(true);
      $("dialog-cancel").onclick = () => done(false);
      dialog.oncancel = (event) => {
        event.preventDefault();
        done(false);
      };
      dialog.showModal();
    });
  }

  function askQuit() {
    const ask = state && state.current ? confirmDialog(text("window.quit_confirm")) : Promise.resolve(true);
    return ask.then((yes) => (yes ? call("quit", true) : null));
  }

  function bind() {
    $("pair-form").addEventListener("submit", (event) => {
      event.preventDefault();
      $("pair-button").disabled = true;
      call("pair", $("invite").value, $("server").value, $("pair-firefox").checked).then(refresh);
    });
    $("pause").addEventListener("click", () => call("pause", !(state && state.paused)).then(refresh));
    $("retry").addEventListener("click", () => call("retry").then(refresh));
    $("autostart").addEventListener("change", (event) => call("set_setting", "autostart", event.target.checked).then(refresh));
    $("firefox").addEventListener("change", (event) => call("set_setting", "firefox", event.target.checked).then(refresh));
    $("mirror-save").addEventListener("click", () => call("set_setting", "download_host", $("mirror").value).then(refresh));
    $("language").addEventListener("change", (event) => call("set_setting", "language", event.target.value));
    $("open-logs").addEventListener("click", () => call("open_logs"));
    $("reset").addEventListener("click", () =>
      confirmDialog(text("window.reset_confirm")).then((yes) => (yes ? call("reset_pairing").then(refresh) : null)),
    );
    $("quit").addEventListener("click", askQuit);
  }

  window.rpa = { refresh: refresh, askQuit: askQuit };
  fillTexts();
  bind();
  function ready() {
    refresh().then(() => call("ready", navigator.userAgent));
    setInterval(refresh, 1000);
  }
  if (api()) {
    ready();
  } else {
    window.addEventListener("pywebviewready", ready, { once: true });
  }
})();
