'use strict';
// 管理 Portal 的頁面互動：呼叫 /api、輪詢執行狀態、對話框。
// 共用的外殼、對話框 modal()、提示 toast()、跳脫 esc() 來自設計系統的 shell.js。
(() => {
  const messages = JSON.parse(document.getElementById('messages').textContent);
  const qs = (selector, root = document) => root.querySelector(selector);
  const qsa = (selector, root = document) => [...root.querySelectorAll(selector)];
  const path = value => encodeURIComponent(value);
  // 訊息裡的 {名稱} 換成值；字詞順序與標點由各語言的訊息決定，程式不拼接
  const fill = (template, values) =>
    template.replace(/\{(\w+)\}/g, (whole, key) => (key in values ? String(values[key]) : whole));

  async function api(method, url, body) {
    const options = {method, headers: {Accept: 'application/json'}};
    if (body !== undefined) {
      options.headers['Content-Type'] = 'application/json';
      options.body = JSON.stringify(body);
    }
    let response;
    try {
      response = await fetch(url, options);
    } catch {
      return {ok: false, status: 0, data: null};
    }
    let data = null;
    try {
      data = await response.json();
    } catch {
      data = null;
    }
    return {ok: response.ok, status: response.status, data};
  }

  function errorMessage(result) {
    if (result.status === 0) return messages.network_error;
    const error = result.data && result.data.error;
    if (error && error.message) return error.message;
    const detail = result.data && result.data.detail;
    if (Array.isArray(detail) && detail.length) return detail.map(item => item.msg).join('；');
    return messages.save_failed;
  }

  // 重新載入後才顯示的提示
  function flash(text) {
    try { sessionStorage.setItem('rpa-flash', text); } catch { /* 無法儲存就不顯示 */ }
  }
  function showFlash() {
    let text = null;
    try {
      text = sessionStorage.getItem('rpa-flash');
      sessionStorage.removeItem('rpa-flash');
    } catch { text = null; }
    if (text) toast(text);
  }

  function confirmDialog(title, body, label, run) {
    modal(title, '<p>' + esc(body) + '</p>', {label, run});
  }

  function listItems(list, items) {
    list.innerHTML = items.map(item => '<li>' + esc(item) + '</li>').join('');
    list.closest('section').hidden = items.length === 0;
    if (items.length) list.closest('section').scrollIntoView({block: 'nearest'});
  }

  function newKey() {
    if (window.crypto && typeof crypto.randomUUID === 'function') return crypto.randomUUID();
    return Date.now().toString(36) + Math.random().toString(36).slice(2);
  }

  // ---------------------------------------------------------------- 共用

  function localizeTimes() {
    const lang = document.documentElement.lang;
    qsa('time[datetime]').forEach(element => {
      const value = new Date(element.getAttribute('datetime'));
      if (!Number.isNaN(value.getTime())) element.textContent = value.toLocaleString(lang);
    });
  }

  function bindLanguage() {
    const select = qs('#language');
    if (!select) return;
    select.addEventListener('change', () => {
      const next = location.pathname + location.search;
      location.href = '/lang/' + path(select.value) + '?next=' + encodeURIComponent(next);
    });
  }

  // ---------------------------------------------------------------- 篩選選單

  // 每個選單是 <details>：點開勾選，按「套用」或關閉選單（點外面、Esc、再點一次按鈕）時有變動就套用
  function bindFilters() {
    qsa('form[data-filters]').forEach(form => {
      const menus = qsa('[data-filter-menu]', form);
      const state = menu => qsa('input[type=checkbox]', menu).map(box => box.checked).join();
      menus.forEach(menu => {
        let opened = state(menu);
        menu.addEventListener('toggle', () => {
          if (menu.open) {
            menus.filter(other => other !== menu).forEach(other => { other.open = false; });
            opened = state(menu);
            const search = qs('[data-filter-search]', menu);
            (search || qs('input', menu) || menu).focus();
          } else if (state(menu) !== opened) {
            form.requestSubmit();
          }
        });
        qs('[data-filter-clear]', menu).addEventListener('click', () => {
          qsa('input[type=checkbox]', menu).forEach(box => { box.checked = false; });
        });
        const search = qs('[data-filter-search]', menu);
        if (search) {
          search.addEventListener('input', () => {
            const words = search.value.trim().toLowerCase();
            qsa('.filter-options label', menu).forEach(label => {
              label.hidden = words !== '' && !label.textContent.toLowerCase().includes(words);
            });
          });
          // 搜尋框裡按 Enter 不送出表單
          search.addEventListener('keydown', event => { if (event.key === 'Enter') event.preventDefault(); });
        }
      });
      document.addEventListener('click', event => {
        menus.filter(menu => menu.open && !menu.contains(event.target)).forEach(menu => { menu.open = false; });
      });
      document.addEventListener('keydown', event => {
        if (event.key !== 'Escape') return;
        menus.filter(menu => menu.open).forEach(menu => {
          menu.open = false;
          qs('summary', menu).focus();
        });
      });
    });
  }

  function bindPublish() {
    qsa('[data-action="publish"]').forEach(button => {
      button.addEventListener('click', () => {
        const scene = button.dataset.scene;
        const number = button.dataset.revision;
        confirmDialog(messages.publish_title + ' v' + number, messages.publish_body, messages.publish_action, async () => {
          const result = await api('POST', '/api/scenes/' + path(scene) + '/revisions/' + path(number) + '/publish');
          $('#dialog').close();
          if (!result.ok) return toast(errorMessage(result));
          flash(messages.published);
          location.href = '/scenes/' + path(scene);
        });
      });
    });
  }

  // ---------------------------------------------------------------- 場景清單

  function bindScenes() {
    const importButton = qs('[data-action="import"]');
    if (importButton) {
      importButton.addEventListener('click', async () => {
        importButton.disabled = true;
        const result = await api('POST', '/api/scenes/import', {domainId: importButton.dataset.domain || null});
        importButton.disabled = false;
        if (!result.ok) return toast(errorMessage(result));
        flash(fill(messages.imported, {ids: result.data.imported.join(messages.list_separator) || '—'}));
        location.reload();
      });
    }
    const newButton = qs('[data-action="new-scene"]');
    if (newButton) {
      newButton.addEventListener('click', () => {
        modal(messages.create_title, qs('#new-scene-form').innerHTML, {
          label: messages.create_action,
          run: async () => {
            const dialog = qs('#dialog-content');
            const value = name => qs('[name="' + name + '"]', dialog).value.trim();
            const result = await api('POST', '/api/scenes', {
              id: value('id'), name: value('name'), category: value('category') || null,
              domainId: newButton.dataset.domain || null,
            });
            if (!result.ok) {
              qs('.form-error', dialog).textContent = errorMessage(result);
              return;
            }
            location.href = '/scenes/' + path(result.data.id) + '/edit';
          },
        });
        const first = qs('#dialog-content input');
        if (first) first.focus();
      });
    }
  }

  // ---------------------------------------------------------------- 場景詳情

  function bindSceneSettings() {
    const form = qs('form[data-action="scene-settings"]');
    if (!form) return;
    form.addEventListener('submit', async event => {
      event.preventDefault();
      const value = form.elements.namedItem('baseUrl').value.trim();
      const domain = form.elements.namedItem('domainId').value;
      const result = await api('PATCH', '/api/scenes/' + path(form.dataset.scene), {baseUrl: value || null, domainId: domain || null});
      if (!result.ok) return toast(errorMessage(result));
      flash(messages.saved);
      location.reload();
    });
  }

  // ---------------------------------------------------------------- 領域管理

  function domainDialog(title, values, run) {
    modal(title, qs('#domain-form').innerHTML, {label: messages.save, run});
    const dialog = qs('#dialog-content');
    const editing = values !== null;
    qsa('[data-new-only]', dialog).forEach(element => { element.hidden = editing; });
    if (editing) {
      qs('[name="name"]', dialog).value = values.name;
      qs('[name="description"]', dialog).value = values.description;
    }
    const first = qs(editing ? '[name="name"]' : '[name="id"]', dialog);
    if (first) first.focus();
    return dialog;
  }

  function bindDomains() {
    const create = qs('[data-action="new-domain"]');
    if (create) {
      create.addEventListener('click', () => {
        const dialog = domainDialog(messages.domain_create_title, null, async () => {
          const value = name => qs('[name="' + name + '"]', dialog).value.trim();
          const result = await api('POST', '/api/domains', {id: value('id'), name: value('name'), description: value('description') || null});
          if (!result.ok) {
            qs('.form-error', dialog).textContent = errorMessage(result);
            return;
          }
          location.href = '/domains/' + path(result.data.id);
        });
      });
    }
    qsa('[data-action="edit-domain"]').forEach(button => {
      button.addEventListener('click', () => {
        const values = {name: button.dataset.name, description: button.dataset.description};
        const dialog = domainDialog(messages.domain_edit_title, values, async () => {
          const value = name => qs('[name="' + name + '"]', dialog).value.trim();
          const result = await api('PATCH', '/api/domains/' + path(button.dataset.domain), {name: value('name'), description: value('description')});
          if (!result.ok) {
            qs('.form-error', dialog).textContent = errorMessage(result);
            return;
          }
          flash(messages.saved);
          location.reload();
        });
      });
    });
    qsa('[data-action="delete-domain"]').forEach(button => {
      button.addEventListener('click', () => {
        confirmDialog(fill(messages.domain_delete_title, {name: button.dataset.name}), messages.domain_delete_body, messages.domain_delete_action, async () => {
          const result = await api('DELETE', '/api/domains/' + path(button.dataset.domain));
          $('#dialog').close();
          if (!result.ok) return toast(errorMessage(result));
          location.reload();
        });
      });
    });
  }

  // ---------------------------------------------------------------- 編輯版本

  function bindEditor() {
    const form = qs('#revision-form');
    if (!form) return;
    qsa('[data-file-tab]').forEach(tab => {
      tab.addEventListener('click', () => {
        qsa('[data-file-tab]').forEach(other => {
          const active = other === tab;
          other.classList.toggle('active', active);
          other.setAttribute('aria-selected', String(active));
        });
        qsa('[data-file]', form).forEach(section => { section.hidden = section.dataset.file !== tab.dataset.fileTab; });
      });
    });
    // 從卡片的「斷言腳本」等連結進來：跳到 YAML 裡對應的段落
    const focus = form.dataset.focus;
    const area = qs('section:not([hidden]) textarea.code-editor', form);
    if (focus && area) {
      const match = new RegExp('^' + focus + ':', 'm').exec(area.value);
      if (match) {
        area.focus();
        area.setSelectionRange(match.index, match.index + focus.length);
        const lines = area.value.slice(0, match.index).split('\n').length - 1;
        area.scrollTop = Math.max(0, lines - 2) * parseFloat(getComputedStyle(area).lineHeight || '20');
        area.closest('section').scrollIntoView({block: 'start'});
      }
    }
    const save = qs('[data-action="save-revision"]');
    form.addEventListener('submit', event => event.preventDefault());
    save.addEventListener('click', async () => {
      const files = {};
      qsa('textarea.code-editor', form).forEach(area => { files[area.name] = area.value; });
      const note = form.elements.namedItem('note').value.trim() || null;
      save.disabled = true;
      const result = await api('POST', '/api/scenes/' + path(form.dataset.scene) + '/revisions', {
        baseRevision: Number(form.dataset.base), files, note,
      });
      save.disabled = false;
      if (result.ok) {
        flash(messages.saved + ' v' + result.data.number);
        location.href = '/scenes/' + path(form.dataset.scene);
        return;
      }
      const error = result.data && result.data.error;
      if (result.status === 409 && error && error.code === 'stale_base') return toast(messages.stale_base);
      const issues = error && Array.isArray(error.issues) ? error.issues : [];
      const lines = issues.map(issue => (issue.line ? 'L' + issue.line + ':' + issue.column + '  ' : '') + issue.text);
      listItems(qs('#issue-list'), lines.length ? lines : [errorMessage(result)]);
    });
  }

  // ---------------------------------------------------------------- 執行表單

  function bindRunForm() {
    const form = qs('#run-form');
    if (!form) return;
    const key = newKey();
    const button = qs('[data-action="submit-run"]', form);
    form.addEventListener('submit', async event => {
      event.preventDefault();
      const field = name => form.elements.namedItem(name);
      let inputs;
      try {
        inputs = JSON.parse(field('inputs').value.trim() || '{}');
      } catch {
        inputs = null;
      }
      if (inputs === null || typeof inputs !== 'object' || Array.isArray(inputs)) {
        return listItems(qs('#problem-list'), [messages.json_invalid]);
      }
      const scene = path(form.dataset.scene);
      const url = form.dataset.purpose === 'validation'
        ? '/api/scenes/' + scene + '/revisions/' + path(form.dataset.revision) + '/validate'
        : '/api/scenes/' + scene + '/runs';
      button.disabled = true;
      const result = await api('POST', url, {
        inputs,
        engine: field('engine').value || null,
        baseUrl: field('baseUrl').value.trim() || null,
        headless: field('headless').value === '1',
        idempotencyKey: key,
      });
      if (result.ok) {
        location.href = '/runs/' + path(result.data.id);
        return;
      }
      button.disabled = false;
      const error = result.data && result.data.error;
      const problems = error && Array.isArray(error.problems) ? error.problems.map(item => item.message) : [];
      listItems(qs('#problem-list'), problems.length ? problems : [errorMessage(result)]);
    });
  }

  // ---------------------------------------------------------------- 執行詳情

  function bindRun() {
    const root = qs('#run');
    if (!root) return;
    const cancel = qs('[data-action="cancel-run"]');
    if (cancel) {
      cancel.addEventListener('click', () => {
        confirmDialog(messages.cancel_title, messages.cancel_body, messages.cancel_action, async () => {
          const result = await api('POST', '/api/runs/' + path(root.dataset.run) + '/cancel');
          $('#dialog').close();
          if (!result.ok) return toast(errorMessage(result));
          flash(messages.cancel_requested);
          location.reload();
        });
      });
    }
    if (!root.hasAttribute('data-poll')) return;
    const timer = setInterval(async () => {
      const result = await api('GET', '/api/runs/' + path(root.dataset.run));
      if (!result.ok) return;
      if (result.data.status !== root.dataset.status || (result.data.stage || '') !== root.dataset.stage) {
        clearInterval(timer);
        location.reload();
      }
    }, 1000);
  }

  localizeTimes();
  bindLanguage();
  bindFilters();
  bindPublish();
  bindScenes();
  bindDomains();
  bindSceneSettings();
  bindEditor();
  bindRunForm();
  bindRun();
  showFlash();
})();
