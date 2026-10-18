// RPA 錄製端 App 的頁面（M10.2）：向本機閘道的 /__desktop/ 取狀態並畫出來，按鈕 POST 到同一個地方。
// 文字一律來自訊息目錄（頁面產生時嵌入 #strings）；這裡不寫使用者看得到的字。
"use strict";
(function () {
  const S = JSON.parse(document.getElementById("strings").textContent);
  const BASE = "/__desktop/";
  const $ = (id) => document.getElementById(id);
  let state = null;
  let busy = false;
  let pending = false;
  let pairFormShown = false;
  let pairedHere = false; // 在這一頁按了「配對」：連上後直接打開管理 Portal

  function text(key, params) {
    const template = S[key] !== undefined ? S[key] : key;
    return template.replace(/\{(\w+)\}/g, (all, name) =>
      params && params[name] !== undefined ? String(params[name]) : all,
    );
  }

  function post(name, body) {
    return fetch(BASE + name, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
      credentials: "same-origin",
    })
      .then((response) => (response.ok ? response.json() : null))
      .catch((error) => {
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
    document.title = text("recorder.title");
  }

  const PHASE_COLORS = {
    online: "green",
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
      s.name && s.device && s.name !== s.device ? text("recorder.device_name", { name: s.name, device: s.device }) : s.device || "";
    $("version-value").textContent = s.version || "";
    $("storage-value").textContent = s.storage === "file" ? text("recorder.storage_file") : text("recorder.storage_keyring");
    $("home-value").textContent = s.home || "";
    show("version-warning", s.sameVersion === false);
    show("display-warning", s.display === false);
    show("stopping-hint", s.phase === "stopping");
    $("active").textContent = s.active ? text("recorder.active_count", { count: s.active }) : text("recorder.active_none");
  }

  function renderSettings(s) {
    const settings = s.settings;
    $("firefox").checked = settings.firefox;
    show("firefox-setting", s.paired); // 還沒配對時在配對表單裡選
    if (document.activeElement !== $("mirror")) $("mirror").value = settings.downloadHost || "";
    $("language").value = settings.language;
    show("reset", s.paired);
  }

  function render(s) {
    if (state && state.settings.language !== s.settings.language) {
      location.reload(); // 語言改了：重新載入這一頁（文字在頁面產生時嵌入）
      return;
    }
    state = s;
    const phase = $("phase");
    phase.textContent = text("recorder.phase." + s.phase);
    phase.className = "badge" + (PHASE_COLORS[s.phase] ? " " + PHASE_COLORS[s.phase] : "");
    const pairing = s.phase === "unpaired" || s.phase === "pairing" || (!s.paired && s.phase === "error");
    show("pair-panel", pairing);
    if (pairing && !pairFormShown) {
      $("pair-firefox").checked = s.settings.firefox;
    }
    pairFormShown = pairing;
    $("pair-button").disabled = s.phase === "pairing";
    show("download-panel", s.phase === "downloading");
    if (s.progress) {
      $("download-browser").textContent = s.progress.browser;
      const known = typeof s.progress.percent === "number";
      $("download-bar").classList.toggle("unknown", !known);
      $("download-bar").firstElementChild.style.width = known ? s.progress.percent + "%" : "";
      $("download-text").textContent = known ? s.progress.percent + "%" : text("recorder.download_unknown");
    }
    show("status-panel", s.paired);
    show("open-portal", s.paired && ["online", "offline", "connecting"].includes(s.phase));
    renderMessage(s);
    if (s.paired) renderStatus(s);
    renderSettings(s);
    if (pairedHere && s.phase === "online") {
      pairedHere = false;
      location.href = "/";
    }
  }

  function refresh() {
    if (busy) {
      pending = true;
      return Promise.resolve();
    }
    busy = true;
    return fetch(BASE + "state", { credentials: "same-origin", cache: "no-store" })
      .then((response) => (response.ok ? response.json() : null))
      .then((s) => {
        if (s) render(s);
      })
      .catch((error) => console.error("state", error))
      .finally(() => {
        busy = false;
        if (pending) {
          pending = false;
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
    const active = state && state.active;
    const ask = active ? confirmDialog(text("recorder.quit_active", { count: active })) : Promise.resolve(true);
    return ask.then((yes) => (yes ? post("quit") : null));
  }

  function setting(name, value) {
    return post("settings", { name: name, value: value }).then(refresh);
  }

  function bind() {
    $("pair-form").addEventListener("submit", (event) => {
      event.preventDefault();
      $("pair-button").disabled = true;
      pairedHere = true;
      post("pair", { invite: $("invite").value, server: $("server").value, firefox: $("pair-firefox").checked }).then(refresh);
    });
    $("retry").addEventListener("click", () => post("retry").then(refresh));
    $("firefox").addEventListener("change", (event) => setting("firefox", event.target.checked));
    $("mirror-save").addEventListener("click", () => setting("download_host", $("mirror").value));
    $("language").addEventListener("change", (event) => setting("language", event.target.value));
    $("open-logs").addEventListener("click", () => post("logs"));
    $("download").addEventListener("click", () => post("download"));
    $("reset").addEventListener("click", () =>
      confirmDialog(text("recorder.reset_confirm")).then((yes) => (yes ? post("reset").then(refresh) : null)),
    );
    $("quit").addEventListener("click", askQuit);
  }

  fillTexts();
  bind();
  refresh().then(() => post("ready", { userAgent: navigator.userAgent }));
  setInterval(refresh, 1000);
})();
