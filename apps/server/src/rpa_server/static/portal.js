'use strict';
// 管理 Portal 的頁面互動：呼叫 /api、輪詢執行狀態、對話框；M4 加上登入與憑證、錄製、逐步調試、入參出參表單。
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

  // ---------------------------------------------------------------- 共用（M4）

  function issueLines(result) {
    const error = result.data && result.data.error;
    const issues = error && Array.isArray(error.issues) ? error.issues : [];
    const lines = issues.map(issue => (issue.line ? 'L' + issue.line + ':' + issue.column + '  ' : '') + (issue.text || issue.message || ''));
    const problems = error && Array.isArray(error.problems) ? error.problems.map(item => item.message) : [];
    return [...lines, ...problems];
  }

  function showIssues(list, result) {
    const lines = issueLines(result);
    const all = lines.length ? [errorMessage(result), ...lines] : [errorMessage(result)];
    list.innerHTML = all.map(item => '<li>' + esc(item) + '</li>').join('');
    list.hidden = false;
    list.scrollIntoView({block: 'nearest'});
  }

  // 每秒問一次，狀態變了就重新載入頁面（伺服器端渲染，不在前端重建畫面）
  function pollUntilChanged(url, current, read) {
    const timer = setInterval(async () => {
      const result = await api('GET', url);
      if (!result.ok) return;
      if (read(result.data) !== current) {
        clearInterval(timer);
        location.reload();
      }
    }, 1000);
  }

  function busy(button, running) {
    if (!button) return;
    if (running) {
      button.dataset.label = button.textContent;
      button.textContent = messages.working;
      button.disabled = true;
    } else {
      button.textContent = button.dataset.label || button.textContent;
      button.disabled = false;
    }
  }

  // ---------------------------------------------------------------- 登入與憑證

  function roleDialog(title, values, run) {
    modal(title, qs('#role-form').innerHTML, {label: messages.save, run});
    const dialog = qs('#dialog-content');
    const editing = values !== null;
    qsa('[data-new-only]', dialog).forEach(element => { element.hidden = editing; });
    if (editing) {
      Object.entries(values).forEach(([name, value]) => {
        const field = qs('[name="' + name + '"]', dialog);
        if (field) field.value = value;
      });
    }
    const first = qs(editing ? '[name="name"]' : '[name="id"]', dialog);
    if (first) first.focus();
    return dialog;
  }

  function roleBody(dialog) {
    const value = name => qs('[name="' + name + '"]', dialog).value;
    return {
      name: value('name').trim(),
      description: value('description').trim(),
      loginUrl: value('loginUrl').trim(),
      checkUrl: value('checkUrl').trim(),
      check: value('check').trim(),
      engine: value('engine'),
      autoLogin: value('autoLogin'),
    };
  }

  function dialogError(dialog, result) {
    const list = qs('.form-issues', dialog);
    const lines = issueLines(result);
    if (list) list.innerHTML = lines.map(item => '<li>' + esc(item) + '</li>').join('');
    qs('.form-error', dialog).textContent = errorMessage(result);
  }

  function secretDialog(title, name) {
    modal(title, qs('#secret-form').innerHTML, {
      label: messages.save,
      run: async () => {
        const dialog = qs('#dialog-content');
        const key = qs('[name="name"]', dialog).value.trim();
        const value = qs('[name="value"]', dialog).value;
        const result = await api('PUT', '/api/secrets/' + path(key), {value});
        if (!result.ok) return dialogError(dialog, result);
        flash(messages.saved);
        location.reload();
      },
    });
    const dialog = qs('#dialog-content');
    const field = qs('[name="name"]', dialog);
    if (name) {
      field.value = name;
      field.readOnly = true;
      qs('[name="value"]', dialog).focus();
    } else {
      field.focus();
    }
  }

  function bindRoles() {
    const root = qs('#roles');
    if (!root) return;
    const create = qs('[data-action="new-role"]');
    if (create) {
      create.addEventListener('click', () => {
        const dialog = roleDialog(messages.role_create_title, null, async () => {
          const result = await api('POST', '/api/roles', {id: qs('[name="id"]', dialog).value.trim(), ...roleBody(dialog)});
          if (!result.ok) return dialogError(dialog, result);
          flash(messages.saved);
          location.reload();
        });
      });
    }
    qsa('[data-action="edit-role"]').forEach(button => {
      button.addEventListener('click', () => {
        const values = JSON.parse(button.dataset.values);
        const dialog = roleDialog(messages.role_edit_title, values, async () => {
          const result = await api('PATCH', '/api/roles/' + path(button.dataset.role), roleBody(dialog));
          if (!result.ok) return dialogError(dialog, result);
          flash(messages.saved);
          location.reload();
        });
      });
    });
    const post = async (button, url) => {
      busy(button, true);
      const result = await api('POST', url);
      if (!result.ok) {
        busy(button, false);
        return toast(errorMessage(result));
      }
      location.reload();
    };
    qsa('[data-action="login"]').forEach(button => {
      button.addEventListener('click', () => post(button, '/api/roles/' + path(button.dataset.role) + '/login'));
    });
    qsa('[data-action="check-role"]').forEach(button => {
      button.addEventListener('click', () => post(button, '/api/roles/' + path(button.dataset.role) + '/check'));
    });
    qsa('[data-action="finish-login"]').forEach(button => {
      button.addEventListener('click', () => post(button, '/api/roles/' + path(button.dataset.role) + '/login/finish'));
    });
    qsa('[data-action="cancel-login"]').forEach(button => {
      button.addEventListener('click', () => post(button, '/api/roles/' + path(button.dataset.role) + '/login/cancel'));
    });
    qsa('[data-action="clear-role"]').forEach(button => {
      button.addEventListener('click', () => {
        confirmDialog(fill(messages.role_clear_title, {name: button.dataset.name}), messages.role_clear_body, messages.role_clear_action, async () => {
          const result = await api('DELETE', '/api/roles/' + path(button.dataset.role) + '/state');
          $('#dialog').close();
          if (!result.ok) return toast(errorMessage(result));
          location.reload();
        });
      });
    });
    qsa('[data-action="delete-role"]').forEach(button => {
      button.addEventListener('click', () => {
        confirmDialog(fill(messages.role_delete_title, {name: button.dataset.name}), messages.role_delete_body, messages.role_delete_action, async () => {
          const result = await api('DELETE', '/api/roles/' + path(button.dataset.role));
          $('#dialog').close();
          if (!result.ok) return toast(errorMessage(result));
          location.reload();
        });
      });
    });
    const newSecret = qs('[data-action="new-secret"]');
    if (newSecret) newSecret.addEventListener('click', () => secretDialog(messages.secret_create_title, ''));
    qsa('[data-action="edit-secret"]').forEach(button => {
      button.addEventListener('click', () => secretDialog(messages.secret_edit_title, button.dataset.name));
    });
    qsa('[data-action="delete-secret"]').forEach(button => {
      button.addEventListener('click', () => {
        confirmDialog(fill(messages.secret_delete_title, {name: button.dataset.name}), messages.secret_delete_body, messages.secret_delete_action, async () => {
          const result = await api('DELETE', '/api/secrets/' + path(button.dataset.name));
          $('#dialog').close();
          if (!result.ok) return toast(errorMessage(result));
          location.reload();
        });
      });
    });
    // 登入或檢查進行中：狀態改變時重新載入
    if (root.hasAttribute('data-poll')) {
      const states = () => qsa('tr[data-role]').map(row => row.dataset.state).join('|');
      const current = states();
      pollUntilChanged('/api/roles', current, data => data.roles.map(role => [role.activity || '', role.session ? role.session.status : '', role.status].join(':')).join('|'));
    }
  }

  // ---------------------------------------------------------------- 錄製

  function bindRecording() {
    const form = qs('#recording-form');
    if (!form) return;
    let mode = 'record';
    const field = name => form.elements.namedItem(name);
    const showMode = next => {
      mode = next;
      qsa('[data-mode]', form).forEach(tab => {
        const active = tab.dataset.mode === mode;
        tab.classList.toggle('active', active);
        tab.setAttribute('aria-selected', String(active));
      });
      qsa('[data-for]', form).forEach(element => { element.hidden = element.dataset.for !== mode; });
    };
    qsa('[data-mode]', form).forEach(tab => tab.addEventListener('click', () => showMode(tab.dataset.mode)));
    const showTarget = () => {
      const kind = form.querySelector('[name="targetKind"]:checked').value;
      qsa('[data-target]', form).forEach(element => { element.hidden = element.dataset.target !== kind; });
    };
    qsa('[name="targetKind"]', form).forEach(radio => radio.addEventListener('change', showTarget));
    showTarget();
    form.addEventListener('submit', async event => {
      event.preventDefault();
      const kind = form.querySelector('[name="targetKind"]:checked').value;
      const target = kind === 'new'
        ? {sceneId: field('sceneId').value.trim(), new: true, name: field('name').value.trim(), domainId: field('domainId').value || null, category: field('category').value.trim() || null}
        : {sceneId: field('existingId').value, new: false};
      const body = {target, url: field('url').value.trim() || null, engine: field('engine').value, roleId: field('roleId').value || null};
      const button = qs('[data-for="' + mode + '"][type="submit"]', form);
      const list = qs('.form-issues', form);
      list.hidden = true;
      busy(button, true);
      const result = mode === 'record'
        ? await api('POST', '/api/recordings', body)
        : await api('POST', '/api/recordings/import', {...body, source: field('source').value});
      if (!result.ok) {
        busy(button, false);
        return showIssues(list, result);
      }
      flash(mode === 'record' ? messages.recording_started : messages.converted);
      location.href = '/recordings/' + path(result.data.id);
    });
    const root = qs('#recording');
    if (root && root.dataset.poll) {
      pollUntilChanged('/api/recordings/' + path(root.dataset.poll), 'recording', data => data.status);
    }
  }

  function bindRecordingDetail() {
    qsa('[data-action="cancel-recording"]').forEach(button => {
      button.addEventListener('click', async () => {
        busy(button, true);
        const result = await api('POST', '/api/recordings/' + path(button.dataset.recording) + '/cancel');
        if (!result.ok) {
          busy(button, false);
          return toast(errorMessage(result));
        }
        location.reload();
      });
    });
    const root = qs('#recording-detail');
    if (root && root.hasAttribute('data-poll')) {
      pollUntilChanged('/api/recordings/' + path(root.dataset.recording), root.dataset.status, data => data.status);
    }
  }

  // ---------------------------------------------------------------- 逐步調試

  function bindDebug() {
    const root = qs('#debug');
    if (!root) return;
    const scene = root.dataset.scene;
    const session = root.dataset.session;
    const start = qs('#debug-start');
    if (start) {
      start.addEventListener('submit', async event => {
        event.preventDefault();
        const field = name => start.elements.namedItem(name);
        let inputs;
        try {
          inputs = JSON.parse(field('inputs').value.trim() || '{}');
        } catch {
          inputs = null;
        }
        if (inputs === null || typeof inputs !== 'object' || Array.isArray(inputs)) {
          return listItems(qs('#problem-list'), [messages.json_invalid]);
        }
        const button = qs('[type="submit"]', start);
        busy(button, true);
        const result = await api('POST', '/api/scenes/' + path(scene) + '/debug', {
          revision: Number(field('revision').value),
          inputs,
          engine: field('engine').value || null,
          headless: field('headless').value === '1',
          baseUrl: field('baseUrl').value.trim() || null,
          restart: true,
        });
        if (!result.ok) {
          busy(button, false);
          const error = result.data && result.data.error;
          const problems = error && Array.isArray(error.problems) ? error.problems.map(item => item.message) : [];
          return listItems(qs('#problem-list'), problems.length ? problems : [errorMessage(result)]);
        }
        location.href = '/scenes/' + path(scene) + '/debug';
      });
    }
    if (!session) return;
    if (root.hasAttribute('data-poll')) {
      pollUntilChanged('/api/debug/' + path(session), root.dataset.status, data => data.status);
      return;
    }
    const base = '/api/debug/' + path(session);
    const command = async (button, method, url, body) => {
      qsa('#debug button, #page-actions button').forEach(element => { element.disabled = true; });
      busy(button, true);
      const result = await api(method, url, body);
      if (!result.ok) {
        const error = result.data && result.data.error;
        if (result.status === 409 && error && error.code === 'confirm_required') {
          return confirmDialog(messages.debug_confirm_title, error.message, messages.debug_confirm_action, async () => {
            $('#dialog').close();
            await command(button, method, url, {...(body || {}), force: true});
          });
        }
        flash(errorMessage(result));
      }
      location.reload();
    };
    qsa('[data-action="debug-step"]').forEach(button => {
      button.addEventListener('click', () => command(button, 'POST', base + '/steps/' + button.dataset.index, {force: false}));
    });
    qsa('[data-action="debug-run-to"]').forEach(button => {
      button.addEventListener('click', () => command(button, 'POST', base + '/run-to/' + button.dataset.index));
    });
    const screenshot = qs('[data-action="debug-screenshot"]');
    if (screenshot) screenshot.addEventListener('click', () => command(screenshot, 'POST', base + '/screenshot'));
    const reset = qs('[data-action="debug-reset"]');
    if (reset) reset.addEventListener('click', () => command(reset, 'POST', base + '/reset'));
    const close = qs('[data-action="debug-close"]');
    if (close) {
      close.addEventListener('click', () => {
        confirmDialog(messages.debug_close_title, messages.debug_close_body, messages.debug_close_action, async () => {
          $('#dialog').close();
          await api('DELETE', base);
          location.reload();
        });
      });
    }
    const locator = qs('#locator-form');
    if (locator) {
      locator.addEventListener('submit', async event => {
        event.preventDefault();
        const button = qs('[type="submit"]', locator);
        busy(button, true);
        const result = await api('POST', base + '/locate', {locator: locator.elements.namedItem('locator').value});
        if (!result.ok) {
          busy(button, false);
          qs('.form-error', locator).textContent = errorMessage(result);
          return;
        }
        location.reload();
      });
    }
    const yaml = qs('#debug-yaml');
    if (yaml) {
      yaml.addEventListener('submit', async event => {
        event.preventDefault();
        const button = qs('[type="submit"]', yaml);
        const list = qs('.form-issues', yaml);
        list.hidden = true;
        busy(button, true);
        const saved = await api('POST', '/api/scenes/' + path(scene) + '/revisions', {
          baseRevision: Number(yaml.dataset.base),
          files: {'scenario.yaml': yaml.elements.namedItem('scenario.yaml').value},
          note: yaml.elements.namedItem('note').value.trim() || null,
        });
        if (!saved.ok) {
          busy(button, false);
          if (saved.status === 409 && saved.data && saved.data.error && saved.data.error.code === 'stale_base') return toast(messages.stale_base);
          return showIssues(list, saved);
        }
        const reloaded = await api('POST', base + '/reload', {revision: saved.data.number});
        flash(reloaded.ok ? messages.saved + ' v' + saved.data.number : errorMessage(reloaded));
        location.reload();
      });
    }
  }

  // ---------------------------------------------------------------- 入參與出參的表單

  // 表單上的文字 → 型別正確的值；轉不了就保留原文，讓伺服器的校驗說明哪裡不對
  function typed(text, type) {
    const value = text.trim();
    if (value === '') return null;
    if (type === 'integer' && /^[-+]?\d+$/.test(value)) return Number(value);
    if (type === 'number' && value !== '' && !Number.isNaN(Number(value))) return Number(value);
    if (type === 'boolean' && (value === 'true' || value === 'false')) return value === 'true';
    return value;
  }

  function enumValues(text, type) {
    const value = text.trim();
    if (!value) return null;
    if (value.startsWith('[')) {
      try { return JSON.parse(value); } catch { /* 交給下面當成逗號分隔 */ }
    }
    return value.split(/[,，\n]/).map(item => item.trim()).filter(Boolean).map(item => typed(item, type));
  }

  function contractRow(row) {
    const get = name => {
      const field = qs('[name="' + name + '"]', row);
      return field ? field.value : '';
    };
    const number = name => (get(name).trim() === '' ? null : Number(get(name)));
    const type = get('type');
    const item = {
      name: get('name').trim(),
      previous: row.dataset.previous || null,
      type,
      description: get('description').trim() || null,
      enum: enumValues(get('enum'), type),
      minLength: number('minLength'),
      maxLength: number('maxLength'),
      pattern: get('pattern').trim() || null,
      minimum: number('minimum'),
      maximum: number('maximum'),
    };
    if (row.dataset.kind === 'input') {
      const required = qs('[name="required"]', row).checked;
      item.default = required ? null : typed(get('default'), type);
    } else if (qs('[name="from"]', row)) {
      item.from = get('from').trim() || null;
    }
    return item;
  }

  function bindContract() {
    const editor = qs('#contract-editor');
    if (!editor) return;
    const form = qs('#contract-form');
    qsa('[data-action="edit-contract"]').forEach(button => {
      button.addEventListener('click', () => {
        editor.hidden = false;
        editor.scrollIntoView({block: 'start'});
        const first = qs('input', form);
        if (first) first.focus();
      });
    });
    qs('[data-action="close-contract"]', form).addEventListener('click', () => { editor.hidden = true; });
    form.addEventListener('click', event => {
      const remove = event.target.closest('[data-action="remove-contract-row"]');
      if (remove) remove.closest('.contract-row').remove();
      const add = event.target.closest('[data-action="add-contract-row"]');
      if (add) {
        const template = qs('#contract-' + add.dataset.kind + '-row');
        qs('[data-rows="' + add.dataset.kind + '"]', form).insertAdjacentHTML('beforeend', template.innerHTML);
        const rows = qsa('[data-rows="' + add.dataset.kind + '"] .contract-row', form);
        qs('[name="name"]', rows[rows.length - 1]).focus();
      }
    });
    form.addEventListener('submit', async event => {
      event.preventDefault();
      const list = qs('.form-issues', form);
      list.hidden = true;
      const rows = kind => qsa('[data-rows="' + kind + '"] .contract-row', form).map(contractRow);
      const button = qs('[type="submit"]', form);
      busy(button, true);
      const result = await api('PUT', '/api/scenes/' + path(form.dataset.scene) + '/contract', {
        baseRevision: Number(form.dataset.base),
        inputs: rows('input'),
        outputs: rows('output'),
        note: form.elements.namedItem('note').value.trim() || null,
      });
      if (!result.ok) {
        busy(button, false);
        if (result.status === 409 && result.data && result.data.error && result.data.error.code === 'stale_base') return toast(messages.stale_base);
        return showIssues(list, result);
      }
      flash(messages.contract_saved + ' v' + result.data.number);
      location.href = '/scenes/' + path(form.dataset.scene);
    });
  }

  // ---------------------------------------------------------------- 重新執行

  function bindRerun() {
    qsa('[data-action="rerun"]').forEach(button => {
      button.addEventListener('click', async () => {
        busy(button, true);
        const result = await api('POST', '/api/runs/' + path(button.dataset.run) + '/rerun', {idempotencyKey: newKey()});
        if (!result.ok) {
          busy(button, false);
          return toast(errorMessage(result));
        }
        flash(messages.rerun_started);
        location.href = '/runs/' + path(result.data.id);
      });
    });
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
  bindRoles();
  bindRecording();
  bindRecordingDetail();
  bindDebug();
  bindContract();
  bindRerun();
  showFlash();
})();
