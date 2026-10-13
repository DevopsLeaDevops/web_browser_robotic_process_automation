'use strict';
// 管理 Portal 的頁面互動：呼叫 /api、輪詢執行狀態、對話框；M4 加上登入與憑證、錄製、逐步調試、入參出參表單；
// M6 加上自由試驗場（序列清單、編輯序列、序列的執行）；M9a 加上遠端 worker 頁與執行位置。
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

  // ---------------------------------------------------------------- 執行位置（M9a）

  function chosenTarget(root) {
    const checked = qs('[name="target"]:checked', root);
    return checked ? checked.value : null;
  }

  // 換執行位置時，有頭模式能不能選跟著那個位置（本機看這台電腦，遠端看 worker）
  function bindTargetChoice(root) {
    const choice = qs('[data-target-choice]', root);
    if (!choice) return;
    const display = JSON.parse(choice.dataset.display || '{}');
    const update = () => {
      const target = chosenTarget(root);
      const headed = qs('[name="headless"][value="0"]', root);
      const headless = qs('[name="headless"][value="1"]', root);
      if (!target || !headed || !headless) return;
      const allowed = display[target] === true;
      headed.disabled = !allowed;
      if (!allowed && headed.checked) headless.checked = true;
      const hint = qs('[data-window-hint]', root);
      if (hint) hint.textContent = allowed ? hint.dataset.hint : hint.dataset.unavailable;
    };
    qsa('[name="target"]', root).forEach(input => input.addEventListener('change', update));
    update();
  }

  function bindRunForm() {
    const form = qs('#run-form');
    if (!form) return;
    bindTargetChoice(form);
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
        target: chosenTarget(form),
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
    const defaults = JSON.parse((qs('#recording-defaults') || {}).textContent || '{}');
    const checked = name => form.querySelector('[name="' + name + '"]:checked');
    // 既有場景：顯示對應的說明；接著錄製時不用起始網址（從現有步驟最後的畫面開始）
    const showTarget = () => {
      const kind = checked('targetKind').value;
      qsa('[data-target]', form).forEach(element => { element.hidden = element.dataset.target !== kind; });
      const scene = defaults[field('existingId') ? field('existingId').value : ''] || {};
      const continueRadio = form.querySelector('[name="existingMode"][value="continue"]');
      if (continueRadio) {
        continueRadio.disabled = Boolean(scene.script);
        if (scene.script) form.querySelector('[name="existingMode"][value="replace"]').checked = true;
      }
      const existingMode = kind === 'existing' && checked('existingMode') ? checked('existingMode').value : '';
      const hint = existingMode === 'continue' ? 'continue-' + mode : existingMode;
      qsa('[data-hint]', form).forEach(element => {
        element.hidden = element.dataset.hint !== hint && !(element.dataset.hint === 'script' && kind === 'existing' && scene.script);
      });
      const continuing = existingMode === 'continue';
      qs('[data-url]', form).hidden = continuing;
      qs('[data-url-continue]', form).hidden = !continuing;
    };
    // 選既有場景時，預先填入它的起始網址、瀏覽器與登入角色
    const fillDefaults = () => {
      if (checked('targetKind').value !== 'existing') return;
      const scene = defaults[field('existingId').value];
      if (!scene) return;
      field('url').value = scene.url || '';
      if (scene.engine && qs('option[value="' + scene.engine + '"]', field('engine'))) field('engine').value = scene.engine;
      field('roleId').value = scene.roleId && qs('option[value="' + scene.roleId + '"]', field('roleId')) ? scene.roleId : '';
    };
    qsa('[data-mode]', form).forEach(tab => tab.addEventListener('click', () => { showMode(tab.dataset.mode); showTarget(); }));
    qsa('[name="targetKind"]', form).forEach(radio => radio.addEventListener('change', () => { fillDefaults(); showTarget(); }));
    qsa('[name="existingMode"]', form).forEach(radio => radio.addEventListener('change', showTarget));
    if (field('existingId')) field('existingId').addEventListener('change', () => { fillDefaults(); showTarget(); });
    fillDefaults();
    showTarget();
    form.addEventListener('submit', async event => {
      event.preventDefault();
      const kind = checked('targetKind').value;
      const target = kind === 'new'
        ? {sceneId: field('sceneId').value.trim(), new: true, name: field('name').value.trim(), domainId: field('domainId').value || null, category: field('category').value.trim() || null}
        : {sceneId: field('existingId').value, new: false, mode: checked('existingMode').value};
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
      const controls = qsa('#debug button, #page-actions button');
      const before = controls.map(element => element.disabled);
      controls.forEach(element => { element.disabled = true; });
      busy(button, true);
      const result = await api(method, url, body);
      if (!result.ok) {
        const error = result.data && result.data.error;
        if (result.status === 409 && error && error.code === 'confirm_required') {
          // 先把畫面還原：使用者關掉確認對話框（不再執行）時，頁面要能繼續操作
          busy(button, false);
          controls.forEach((element, index) => { element.disabled = before[index]; });
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

  // ---------------------------------------------------------------- 自動化腳本、斷言腳本（只編輯一段）

  // 在文字框游標的位置插入文字，插入後選取插入的內容
  function insertAt(area, text) {
    const start = area.selectionStart;
    const end = area.selectionEnd;
    area.setRangeText(text, start, end, 'end');
    area.focus();
    area.dispatchEvent(new Event('input'));
  }

  // 第 line 行（從 1 開始）整行選取並捲到看得見的位置
  function selectLine(area, line) {
    const lines = area.value.split('\n');
    const start = lines.slice(0, line - 1).reduce((sum, item) => sum + item.length + 1, 0);
    area.focus();
    area.setSelectionRange(start, start + (lines[line - 1] || '').length);
    const height = parseFloat(getComputedStyle(area).lineHeight) || 20;
    area.scrollTop = Math.max(0, (line - 4) * height);
  }

  // 校驗問題：落在這一段的標出段落裡的行號，點一下選到那一行
  function showSectionIssues(list, result, area) {
    const error = result.data && result.data.error;
    const issues = error && Array.isArray(error.issues) ? error.issues : [];
    list.innerHTML = '<li>' + esc(errorMessage(result)) + '</li>' + issues.map((issue, index) => {
      const where = issue.sectionLine ? fill(messages.section_line, {line: issue.sectionLine}) + '  ' : '';
      return '<li><button type="button" class="text-btn" data-issue="' + index + '">' + esc(where + (issue.message || issue.text || '')) + '</button></li>';
    }).join('');
    list.closest('section').hidden = false;
    qsa('[data-issue]', list).forEach(button => {
      const issue = issues[Number(button.dataset.issue)];
      button.disabled = !issue.sectionLine;
      button.addEventListener('click', () => selectLine(area, issue.sectionLine));
    });
    list.closest('section').scrollIntoView({block: 'nearest'});
  }

  function bindSection() {
    const form = qs('#section-form');
    if (!form) return;
    const area = form.elements.namedItem('text');
    const key = form.dataset.key;
    qsa('[data-insert]').forEach(chip => chip.addEventListener('click', () => insertAt(area, chip.dataset.insert)));
    // 斷言範本：接在最後，縮排跟著現有的項目
    const rules = {notEmpty: 'notEmpty: true', equals: 'equals: ""', contains: 'contains: ""', matches: 'matches: "^$"'};
    qsa('[data-insert-check]').forEach(button => button.addEventListener('click', () => {
      const found = /^( *)- /m.exec(area.value.replace(/^verify:.*$/m, ''));
      const indent = found ? found[1] : '  ';
      let text = area.value.replace(/\s+$/, '');
      if (!/^verify\s*:/m.test(text)) text = (text ? text + '\n' : '') + 'verify:';
      const item = [indent + '- name: ', indent + '  value: "{{ facts. }}"', indent + '  ' + rules[button.dataset.insertCheck]];
      area.value = text + '\n' + item.join('\n') + '\n';
      const position = area.value.lastIndexOf('- name: ') + '- name: '.length;
      area.focus();
      area.setSelectionRange(position, position);
    }));
    const save = qs('[data-action="save-section"]');
    const list = qs('#issue-list');
    const submit = async () => {
      qs('#issues').hidden = true;
      busy(save, true);
      const result = await api('PUT', '/api/scenes/' + path(form.dataset.scene) + '/sections/' + path(key), {
        baseRevision: Number(form.dataset.base),
        text: area.value,
        note: form.elements.namedItem('note').value.trim() || null,
      });
      if (!result.ok) {
        busy(save, false);
        if (result.status === 409 && result.data && result.data.error && result.data.error.code === 'stale_base') return toast(messages.stale_base);
        return showSectionIssues(list, result, area);
      }
      flash(messages.saved + ' v' + result.data.number);
      location.href = '/scenes/' + path(form.dataset.scene) + '/edit?part=' + path(key);
    };
    if (save) save.addEventListener('click', submit);
    form.addEventListener('submit', event => { event.preventDefault(); submit(); });
  }

  // ---------------------------------------------------------------- 入參與出參的表單

  // 表單上的文字 → 型別正確的值；轉不了就保留原文，讓伺服器的校驗說明哪裡不對
  function typed(text, type) {
    const value = text.trim();
    if (value === '') return null;
    if (type === 'integer' && /^[-+]?\d+$/.test(value)) return Number(value);
    if (type === 'number' && !Number.isNaN(Number(value))) return Number(value);
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

  const RULE_KEYS = ['minLength', 'maxLength', 'pattern', 'minimum', 'maximum', 'enum'];

  // 一列的限制摘要（DSL 的寫法，各語言相同）；沒有限制時顯示 —
  function ruleSummary(row) {
    const parts = RULE_KEYS.filter(key => {
      const field = qs('[name="' + key + '"]', row.nextElementSibling);
      return field && !field.closest('label').hidden && field.value.trim() !== '';
    });
    return parts.length ? parts.join(' · ') : '—';
  }

  // 依型別只顯示用得到的限制；預設值的輸入框跟著型別換
  function applyType(row) {
    const type = qs('[name="type"]', row).value;
    const rules = row.nextElementSibling;
    qsa('[data-types]', rules).forEach(item => { item.hidden = !item.dataset.types.split(' ').includes(type); });
    const fallback = qs('[name="default"]', row);
    if (fallback) {
      fallback.inputMode = type === 'integer' || type === 'number' ? 'decimal' : 'text';
      fallback.placeholder = type === 'boolean' ? 'true / false' : fallback.dataset.placeholder;
    }
    qs('[data-rule-summary]', row).textContent = ruleSummary(row);
  }

  function setRequired(row) {
    const required = qs('[name="required"]', row);
    const fallback = qs('[name="default"]', row);
    if (!required || !fallback) return;
    fallback.disabled = required.checked;
    if (required.checked) fallback.value = '';
  }

  function contractRowFrom(editor, name, spec) {
    const fragment = qs('template[data-row]', editor).content.cloneNode(true);
    const row = qs('tr.edit-row', fragment);
    const rules = qs('tr.rule-row', fragment);
    const set = (root, key, value) => {
      const field = qs('[name="' + key + '"]', root);
      if (field && value !== undefined && value !== null) field.value = typeof value === 'string' ? value : JSON.stringify(value);
    };
    row.dataset.previous = name || '';
    set(row, 'name', name);
    set(row, 'type', spec.type || 'string');
    set(row, 'description', spec.description);
    set(row, 'from', spec.from);
    const fallback = qs('[name="default"]', row);
    if (fallback) {
      fallback.dataset.placeholder = fallback.placeholder;
      qs('[name="required"]', row).checked = name !== '' && (spec.default === undefined || spec.default === null);
      set(row, 'default', spec.default);
    }
    RULE_KEYS.forEach(key => set(rules, key, key === 'enum' && Array.isArray(spec.enum) ? spec.enum.join(', ') : spec[key]));
    return fragment;
  }

  function contractItem(row) {
    const rules = row.nextElementSibling;
    const get = (root, name) => {
      const field = qs('[name="' + name + '"]', root);
      return field && !(field.closest('label') && field.closest('label').hidden) ? field.value : '';
    };
    const number = name => (get(rules, name).trim() === '' ? null : Number(get(rules, name)));
    const type = get(row, 'type');
    const item = {
      name: get(row, 'name').trim(),
      previous: row.dataset.previous || null,
      type,
      description: get(row, 'description').trim() || null,
      enum: enumValues(get(rules, 'enum'), type),
      minLength: number('minLength'),
      maxLength: number('maxLength'),
      pattern: get(rules, 'pattern').trim() || null,
      minimum: number('minimum'),
      maximum: number('maximum'),
    };
    const required = qs('[name="required"]', row);
    if (required) {
      // 必填＝沒有預設值；不是必填的文字入參，預設值可以是空字串
      const text = get(row, 'default');
      item.default = required.checked ? null : (text.trim() === '' && type === 'string' ? '' : typed(text, type));
    }
    if (qs('[name="from"]', row)) item.from = get(row, 'from').trim() || null;
    return item;
  }

  function bindContract() {
    const host = qs('.contract-editors');
    if (!host) return;
    const data = JSON.parse(qs('#contract-data').textContent || '{}');
    const scene = host.dataset.scene;
    const base = Number(host.dataset.base);
    const fillRows = (editor, specs) => {
      const body = qs('[data-rows]', editor);
      body.innerHTML = '';
      // 頁面帶的初始資料是 [名稱, 規格] 的清單（保留順序）；原文切回表格時是物件
      (Array.isArray(specs) ? specs : Object.entries(specs || {})).forEach(([name, spec]) => body.appendChild(contractRowFrom(editor, name, spec)));
      qsa('tr.edit-row', body).forEach(row => { applyType(row); setRequired(row); });
    };
    const items = editor => qsa('tr.edit-row', editor).map(contractItem);
    const view = editor => qs('[data-view].active', editor).dataset.view;
    const issues = (editor, result) => {
      const list = qs('.form-issues', editor);
      const error = result.data && result.data.error;
      const found = error && Array.isArray(error.issues) ? error.issues : [];
      const lines = found.map(issue => (issue.sectionLine ? fill(messages.section_line, {line: issue.sectionLine}) + '  ' : '') + (issue.message || issue.text || ''));
      const problems = error && Array.isArray(error.problems) ? error.problems.map(item => item.message) : [];
      list.innerHTML = [errorMessage(result), ...lines, ...problems].map(item => '<li>' + esc(item) + '</li>').join('');
      list.hidden = false;
    };
    const showView = async (editor, next) => {
      if (view(editor) === next) return;
      const kind = editor.dataset.kind;
      const area = qs('[name="yaml"]', editor);
      qs('.form-issues', editor).hidden = true;
      // 表格 → YAML：由伺服器產生和存檔一樣的寫法；YAML → 表格：先校驗，再用結果重建表格
      const result = next === 'yaml'
        ? await api('POST', '/api/contract/render', {key: kind, items: items(editor)})
        : await api('POST', '/api/scenes/' + path(scene) + '/sections/' + kind + '/preview', {baseRevision: base, text: area.value});
      if (!result.ok) return issues(editor, result);
      if (next === 'yaml') area.value = result.data.text;
      else fillRows(editor, result.data.items);
      qsa('[data-view]', editor).forEach(tab => {
        const active = tab.dataset.view === next;
        tab.classList.toggle('active', active);
        tab.setAttribute('aria-selected', String(active));
      });
      qsa('[data-view-panel]', editor).forEach(panel => { panel.hidden = panel.dataset.viewPanel !== next; });
    };
    qsa('.contract-editor').forEach(editor => {
      const kind = editor.dataset.kind;
      fillRows(editor, data[kind]);
      qsa('[data-view]', editor).forEach(tab => tab.addEventListener('click', () => showView(editor, tab.dataset.view)));
      editor.addEventListener('change', event => {
        const row = event.target.closest('tr.edit-row') || (event.target.closest('tr.rule-row') || {}).previousElementSibling;
        if (!row) return;
        if (event.target.name === 'type') applyType(row);
        if (event.target.name === 'required') setRequired(row);
        qs('[data-rule-summary]', row).textContent = ruleSummary(row);
      });
      editor.addEventListener('click', event => {
        const button = event.target.closest('button[data-action]');
        if (!button) return;
        const row = button.closest('tr.edit-row');
        const action = button.dataset.action;
        if (action === 'toggle-rules') {
          const rules = row.nextElementSibling;
          rules.hidden = !rules.hidden;
          button.setAttribute('aria-expanded', String(!rules.hidden));
        } else if (action === 'remove-row') {
          row.nextElementSibling.remove();
          row.remove();
        } else if (action === 'move-up' && row.previousElementSibling) {
          const before = row.previousElementSibling.previousElementSibling;
          before.before(row, row.nextElementSibling);
        } else if (action === 'move-down' && row.nextElementSibling.nextElementSibling) {
          const after = row.nextElementSibling.nextElementSibling.nextElementSibling;
          after.after(row, row.nextElementSibling);
        } else if (action === 'add-row') {
          const body = qs('[data-rows]', editor);
          body.appendChild(contractRowFrom(editor, '', {type: 'string'}));
          const added = qsa('tr.edit-row', body).pop();
          applyType(added);
          qs('[name="name"]', added).focus();
        } else if (action === 'close-contract') {
          editor.hidden = true;
          fillRows(editor, data[kind]);
        } else if (action === 'save-contract') {
          save(editor, button);
        }
      });
    });
    const save = async (editor, button) => {
      const kind = editor.dataset.kind;
      qs('.form-issues', editor).hidden = true;
      const note = qs('[name="note"]', editor).value.trim() || null;
      busy(button, true);
      const result = view(editor) === 'yaml'
        ? await api('PUT', '/api/scenes/' + path(scene) + '/sections/' + kind, {baseRevision: base, text: qs('[name="yaml"]', editor).value, note})
        : await api('PUT', '/api/scenes/' + path(scene) + '/contract', {baseRevision: base, [kind]: items(editor), note});
      if (!result.ok) {
        busy(button, false);
        if (result.status === 409 && result.data && result.data.error && result.data.error.code === 'stale_base') return toast(messages.stale_base);
        return issues(editor, result);
      }
      flash(messages.contract_saved + ' v' + result.data.number);
      location.href = '/scenes/' + path(scene) + '#' + kind;
    };
    qsa('[data-action="edit-contract"]').forEach(button => {
      button.addEventListener('click', () => {
        const editor = qs('#contract-' + button.dataset.kind);
        editor.hidden = false;
        editor.scrollIntoView({block: 'start', behavior: 'smooth'});
        const first = qs('input[name="name"]', editor);
        if (first) first.focus({preventScroll: true});
      });
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

  // ---------------------------------------------------------------- 自由試驗場（M6）

  // 試驗場頁面的文字（訊息目錄的 wfjs.*），放在頁面的 #workflow-messages
  function pageText() {
    const element = qs('#workflow-messages');
    return element ? JSON.parse(element.textContent) : {};
  }

  function problemLines(result) {
    const error = result.data && result.data.error;
    return error && Array.isArray(error.problems) ? error.problems.map(item => item.message) : [];
  }

  function workflowDialog(title, values, label, run) {
    modal(title, qs('#workflow-form').innerHTML, {label, run});
    const dialog = qs('#dialog-content');
    if (values) {
      qs('[name="name"]', dialog).value = values.name;
      qs('[name="description"]', dialog).value = values.description || '';
    }
    qs('[name="name"]', dialog).focus();
    return dialog;
  }

  function bindPlayground() {
    if (!qs('#playground')) return;
    const text = pageText();
    qs('[data-action="create-workflow"]').addEventListener('click', () => {
      const dialog = workflowDialog(text.create_title, null, text.create_action, async () => {
        const value = name => qs('[name="' + name + '"]', dialog).value.trim();
        const result = await api('POST', '/api/workflows', {name: value('name'), description: value('description') || null});
        if (!result.ok) {
          qs('.form-error', dialog).textContent = errorMessage(result);
          return;
        }
        location.href = '/playground/' + path(result.data.id);
      });
    });
    qs('[data-action="import-workflow"]').addEventListener('click', () => {
      modal(text.import_title, qs('#workflow-import-form').innerHTML, {label: text.import_action, run: async () => {
        const dialog = qs('#dialog-content');
        const error = qs('.form-error', dialog);
        let data = null;
        try {
          data = JSON.parse(qs('[name="text"]', dialog).value);
        } catch {
          data = null;
        }
        if (!data || typeof data !== 'object' || Array.isArray(data)) {
          error.textContent = text.import_invalid;
          return;
        }
        // 匯出的檔案是 {name, description, …定義}；名稱與說明另外送
        const {name, description, ...definition} = data;
        const given = qs('[name="name"]', dialog).value.trim();
        const result = await api('POST', '/api/workflows', {
          name: given || (typeof name === 'string' && name.trim()) || text.imported_name,
          description: typeof description === 'string' ? description : null,
          definition,
        });
        if (!result.ok) {
          error.textContent = [errorMessage(result), ...problemLines(result)].join('\n');
          return;
        }
        location.href = '/playground/' + path(result.data.id);
      }});
      const dialog = qs('#dialog-content');
      qs('[name="file"]', dialog).addEventListener('change', async event => {
        const file = event.target.files[0];
        if (file) qs('[name="text"]', dialog).value = await file.text();
      });
    });
    qsa('[data-action="delete-workflow"]').forEach(button => {
      button.addEventListener('click', () => {
        confirmDialog(fill(text.delete_title, {name: button.dataset.name}), text.delete_body, text.delete_action, async () => {
          const result = await api('DELETE', '/api/workflows/' + path(button.dataset.workflow));
          $('#dialog').close();
          if (!result.ok) return toast(errorMessage(result));
          location.reload();
        });
      });
    });
  }

  // 編輯序列：左邊場景庫、中間序列、右邊節點設定；改動先留在頁面上，按「儲存」才存檔
  function bindWorkflowEditor() {
    const root = qs('#workflow');
    if (!root) return;
    const text = pageText();
    const data = JSON.parse(qs('#workflow-data').textContent);
    const library = new Map(data.library.map(scene => [scene.id, scene]));
    const definition = JSON.parse(JSON.stringify(data.definition));
    let version = data.version;
    let selected = definition.nodes.length ? 0 : -1;
    let problems = data.problems;
    let dirty = false;
    let checkTimer = null;
    let checkSeq = 0;
    const saveButton = qs('[data-action="workflow-save"]');
    const json = value => JSON.stringify(value);
    const hasDefault = spec => spec.default !== undefined && spec.default !== null;
    const compatible = (output, input) => output === input || (output === 'integer' && input === 'number');

    const sceneOf = node => library.get(node.sceneId) || null;
    function revisionOf(node) {
      const scene = sceneOf(node);
      return scene ? scene.revisions.find(item => item.number === node.revision) || null : null;
    }

    function newNodeId() {
      const used = new Set(definition.nodes.map(node => node.id));
      let number = definition.nodes.length + 1;
      while (used.has('n' + number)) number += 1;
      return 'n' + number;
    }

    // 新節點：入參名稱與前面某個節點的出參相同、型別相容時，自動接上最近的那一個
    function autoBind(node, index) {
      const revision = revisionOf(node);
      if (!revision) return;
      for (const [name, spec] of revision.inputs) {
        for (let i = index - 1; i >= 0; i -= 1) {
          const upstream = revisionOf(definition.nodes[i]);
          const output = upstream && upstream.outputs.find(([key]) => key === name);
          if (output && compatible(output[1].type, spec.type)) {
            node.inputs[name] = {node: definition.nodes[i].id, output: name};
            break;
          }
        }
      }
    }

    function bindingText(node, name, spec) {
      const binding = node.inputs[name];
      if (binding && 'value' in binding) return fill(text.binding_value, {name, value: json(binding.value)});
      if (binding) return fill(text.binding_output, {name, node: binding.node, output: binding.output});
      if (hasDefault(spec)) return fill(text.binding_default, {name, value: json(spec.default)});
      return fill(text.binding_missing, {name});
    }

    function renderLibrary() {
      const words = qs('#library-search').value.trim().toLowerCase();
      const scenes = data.library.filter(scene => !scene.archived && scene.revisions.length);
      const shown = scenes.filter(scene => {
        const haystack = [scene.id, scene.name, scene.domainName || '', scene.category || ''].join(' ').toLowerCase();
        return !words || haystack.includes(words);
      });
      const groups = new Map();
      shown.forEach(scene => {
        const key = scene.domainName || text.no_domain;
        if (!groups.has(key)) groups.set(key, []);
        groups.get(key).push(scene);
      });
      const list = qs('#library-list');
      if (!shown.length) {
        list.innerHTML = '<div class="empty">' + esc(scenes.length ? text.no_match : text.library_empty) + '</div>';
        return;
      }
      list.innerHTML = [...groups].map(([group, items]) => '<h3 class="library-group">' + esc(group) + '</h3>' + items.map(scene =>
        '<button type="button" class="library-item" data-add="' + esc(scene.id) + '"><strong>' + esc(scene.id) + '</strong>' +
        '<span>' + esc(scene.name) + '</span><small>' + esc(fill(text.add, {number: scene.publishedRevision || scene.revisions[0].number})) + '</small></button>').join('')).join('');
    }

    function renderBoard() {
      const stage = qs('#flow-stage');
      if (!definition.nodes.length) {
        stage.innerHTML = '<div class="empty">' + esc(text.board_empty) + '</div>';
        return;
      }
      stage.innerHTML = definition.nodes.map((node, index) => {
        const scene = sceneOf(node);
        const revision = revisionOf(node);
        const count = problems.filter(item => item.node === node.id).length;
        const lines = revision ? revision.inputs.map(([name, spec]) => {
          const missing = !node.inputs[name] && !hasDefault(spec);
          return '<li' + (missing ? ' class="text-danger"' : '') + '>' + esc(bindingText(node, name, spec)) + '</li>';
        }).join('') : '';
        const title = revision ? revision.name : (scene ? scene.name : node.sceneId);
        return '<div class="flow-node' + (index === selected ? ' selected' : '') + '" data-index="' + index + '" role="button" tabindex="0" aria-pressed="' + (index === selected) + '">' +
          '<span class="flow-node-head"><span class="tag mono">' + esc(node.id) + '</span> ' + esc(fill(text.node_label, {number: index + 1})) +
          ' · <code>' + esc(node.sceneId) + '</code> <span class="muted">v' + esc(node.revision) + '</span></span>' +
          '<strong>' + esc(title) + '</strong>' +
          (lines ? '<ul class="flow-bindings">' + lines + '</ul>' : '') +
          (count ? '<span class="badge red">' + esc(fill(text.problem_count, {count})) + '</span>' : '') +
          '</div>' + (index < definition.nodes.length - 1 ? '<div class="flow-arrow" aria-hidden="true">↓</div>' : '');
      }).join('');
    }

    function sourceOf(node, name, spec) {
      const binding = node.inputs[name];
      if (!binding) return hasDefault(spec) ? 'default' : '';
      return 'value' in binding ? 'value' : 'out:' + binding.node + ':' + binding.output;
    }

    function valueField(name, spec, binding) {
      const current = binding && 'value' in binding ? binding.value : '';
      const attrs = ' data-value="' + esc(name) + '" aria-label="' + esc(fill(text.value_label, {name})) + '"';
      if (spec.type === 'boolean' || Array.isArray(spec.enum)) {
        const values = spec.type === 'boolean' ? [true, false] : spec.enum;
        return '<select' + attrs + '>' + values.map((value, index) =>
          '<option value="' + index + '"' + (json(value) === json(current) ? ' selected' : '') + '>' + esc(json(value)) + '</option>').join('') + '</select>';
      }
      const type = spec.type === 'integer' || spec.type === 'number' ? 'number' : 'text';
      const step = spec.type === 'number' ? ' step="any"' : '';
      return '<input type="' + type + '"' + step + attrs + ' value="' + esc(current === '' ? '' : String(current)) + '">';
    }

    function inputRow(node, index, name, spec) {
      const binding = node.inputs[name];
      const current = sourceOf(node, name, spec);
      const option = (value, label, disabled) => '<option value="' + esc(value) + '"' + (value === current ? ' selected' : '') + (disabled ? ' disabled' : '') + '>' + esc(label) + '</option>';
      let options = hasDefault(spec)
        ? option('default', fill(text.source_default, {value: json(spec.default)}))
        : option('', text.source_missing, true);
      options += option('value', text.source_value);
      let outputs = '';
      let found = current === '' || current === 'default' || current === 'value';
      definition.nodes.slice(0, index).forEach(upstream => {
        const revision = revisionOf(upstream);
        (revision ? revision.outputs : []).forEach(([output, outSpec]) => {
          const value = 'out:' + upstream.id + ':' + output;
          found = found || value === current;
          const label = fill(text.source_output, {node: upstream.id, scene: upstream.sceneId, output, type: outSpec.type});
          outputs += option(value, label, !compatible(outSpec.type, spec.type) && value !== current);
        });
      });
      if (!found) options += option(current, fill(text.source_broken, {node: binding.node, output: binding.output}));
      if (outputs) options += '<optgroup label="' + esc(text.source_outputs) + '">' + outputs + '</optgroup>';
      const required = hasDefault(spec) ? '' : ' <span class="tag">' + esc(text.required) + '</span>';
      const description = spec.description ? '<span class="cell-sub">' + esc(spec.description) + '</span>' : '';
      return '<div class="input-source" data-input="' + esc(name) + '">' +
        '<label class="field"><span><code>' + esc(name) + '</code> <span class="muted">' + esc(spec.type) + '</span>' + required + description + '</span>' +
        '<select data-source="' + esc(name) + '">' + options + '</select></label>' +
        (current === 'value' ? valueField(name, spec, binding) : '') + '</div>';
    }

    function renderSettings() {
      const box = qs('#node-settings');
      const node = definition.nodes[selected];
      if (!node) {
        box.innerHTML = '<p class="muted">' + esc(text.settings_empty) + '</p>';
        return;
      }
      const scene = sceneOf(node);
      const revision = revisionOf(node);
      const options = (scene ? scene.revisions : [{number: node.revision}]).map(item => {
        const label = scene && item.number === scene.publishedRevision ? text.revision_current : text.revision_option;
        return '<option value="' + item.number + '"' + (item.number === node.revision ? ' selected' : '') + '>' + esc(fill(label, {number: item.number})) + '</option>';
      });
      if (scene && !scene.revisions.some(item => item.number === node.revision)) {
        options.push('<option value="' + node.revision + '" selected>' + esc(fill(text.revision_option, {number: node.revision})) + '</option>');
      }
      let html = '<div class="stack">';
      html += '<div><span class="tag mono">' + esc(node.id) + '</span> <a href="/scenes/' + path(node.sceneId) + '">' + esc(node.sceneId) + '</a>' +
        (revision ? '<span class="cell-sub">' + esc(revision.name) + '</span>' : '') +
        (scene && scene.archived ? ' <span class="badge amber">' + esc(text.archived) + '</span>' : '') + '</div>';
      html += '<label class="field">' + esc(text.revision) + '<select data-field="revision">' + options.join('') + '</select></label>';
      if (scene && scene.publishedRevision && scene.publishedRevision !== node.revision) {
        html += '<p class="cell-sub">' + esc(fill(text.newer_revision, {number: scene.publishedRevision, current: node.revision})) + '</p>';
      }
      if (revision && revision.role) html += '<p class="cell-sub">' + esc(fill(text.role, {role: revision.role})) + '</p>';
      html += '<h3 class="section-title">' + esc(text.inputs) + '</h3>';
      if (!revision) html += '<p class="muted">' + esc(text.no_contract) + '</p>';
      else if (!revision.inputs.length) html += '<p class="muted">' + esc(text.no_inputs) + '</p>';
      else html += revision.inputs.map(([name, spec]) => inputRow(node, selected, name, spec)).join('');
      if (revision) {
        html += '<h3 class="section-title">' + esc(text.outputs) + '</h3>';
        html += revision.outputs.length
          ? '<ul class="io-list">' + revision.outputs.map(([name, spec]) => '<li><code>' + esc(name) + '</code> <span class="muted">' + esc(spec.type) + '</span></li>').join('') + '</ul>'
          : '<p class="muted">' + esc(text.no_outputs) + '</p>';
      }
      const last = definition.nodes.length - 1;
      html += '<div class="actions">' +
        '<button type="button" class="button" data-move="-1"' + (selected === 0 ? ' disabled' : '') + '>' + esc(text.move_up) + '</button>' +
        '<button type="button" class="button" data-move="1"' + (selected === last ? ' disabled' : '') + '>' + esc(text.move_down) + '</button>' +
        '<button type="button" class="button danger" data-remove>' + esc(text.remove) + '</button></div>';
      box.innerHTML = html + '</div>';
    }

    function renderProblems() {
      const panel = qs('#workflow-problems');
      qs('.count', panel).textContent = problems.length;
      qs('ul', panel).innerHTML = problems.map(item => '<li>' + esc(item.message) + '</li>').join('');
      panel.hidden = problems.length === 0;
    }

    function render({settings = true} = {}) {
      renderBoard();
      if (settings) renderSettings();
      renderProblems();
      saveButton.disabled = !dirty;
      saveButton.title = dirty ? text.unsaved : '';
    }

    // 每次修改後（稍等一下）請伺服器檢查，問題列在上方與節點上
    function scheduleCheck() {
      clearTimeout(checkTimer);
      checkTimer = setTimeout(async () => {
        const sequence = ++checkSeq;
        const result = await api('POST', '/api/workflows/check', {definition});
        if (!result.ok || sequence !== checkSeq) return;
        problems = result.data.problems;
        render({settings: false});
      }, 300);
    }

    function changed(options) {
      dirty = true;
      render(options);
      scheduleCheck();
    }

    async function save() {
      busy(saveButton, true);
      const result = await api('PUT', '/api/workflows/' + path(data.id), {baseVersion: version, definition});
      busy(saveButton, false);
      if (!result.ok) {
        saveButton.disabled = false;
        if (result.status === 409) toast(text.stale);
        else toast(errorMessage(result));
        return false;
      }
      version = result.data.version;
      problems = result.data.problems;
      dirty = false;
      render({settings: false});
      toast(text.saved);
      return true;
    }

    qs('#library-search').addEventListener('input', renderLibrary);
    qs('#library-list').addEventListener('click', event => {
      const button = event.target.closest('[data-add]');
      if (!button) return;
      const scene = library.get(button.dataset.add);
      const node = {id: newNodeId(), sceneId: scene.id, revision: scene.publishedRevision || scene.revisions[0].number, inputs: {}};
      autoBind(node, definition.nodes.length);
      definition.nodes.push(node);
      selected = definition.nodes.length - 1;
      changed();
    });
    const stage = qs('#flow-stage');
    const pick = target => {
      const card = target.closest('[data-index]');
      if (!card) return;
      selected = Number(card.dataset.index);
      render();
    };
    stage.addEventListener('click', event => pick(event.target));
    stage.addEventListener('keydown', event => {
      if (event.key !== 'Enter' && event.key !== ' ') return;
      event.preventDefault();
      pick(event.target);
    });

    const settings = qs('#node-settings');
    settings.addEventListener('change', event => {
      const node = definition.nodes[selected];
      if (!node) return;
      const target = event.target;
      if (target.dataset.field === 'revision') {
        node.revision = Number(target.value);
        const revision = revisionOf(node);
        if (revision) {
          const names = new Set(revision.inputs.map(([name]) => name));
          Object.keys(node.inputs).forEach(name => { if (!names.has(name)) delete node.inputs[name]; });
        }
        changed();
      } else if (target.dataset.source !== undefined) {
        const name = target.dataset.source;
        const spec = new Map((revisionOf(node) || {inputs: []}).inputs).get(name) || {};
        const value = target.value;
        if (value === 'default' || value === '') {
          delete node.inputs[name];
        } else if (value === 'value') {
          const initial = hasDefault(spec) ? spec.default
            : spec.type === 'boolean' ? false
            : Array.isArray(spec.enum) ? spec.enum[0]
            : spec.type === 'integer' || spec.type === 'number' ? 0 : '';
          node.inputs[name] = {value: initial};
        } else {
          const [, upstream, output] = value.split(':');
          node.inputs[name] = {node: upstream, output};
        }
        changed();
      } else if (target.dataset.value !== undefined && target.tagName === 'SELECT') {
        const name = target.dataset.value;
        const spec = new Map(revisionOf(node).inputs).get(name);
        const values = spec.type === 'boolean' ? [true, false] : spec.enum;
        node.inputs[name] = {value: values[Number(target.value)]};
        changed({settings: false});
      }
    });
    // 打字時只更新序列與檢查，不重畫設定（游標才不會跳走）
    settings.addEventListener('input', event => {
      const target = event.target;
      const node = definition.nodes[selected];
      if (!node || target.dataset.value === undefined || target.tagName !== 'INPUT') return;
      const name = target.dataset.value;
      const spec = new Map(revisionOf(node).inputs).get(name);
      let value = target.value;
      if (spec.type === 'integer' && /^-?\d+$/.test(value.trim())) value = parseInt(value, 10);
      else if (spec.type === 'number' && value.trim() !== '' && !Number.isNaN(Number(value))) value = Number(value);
      node.inputs[name] = {value};
      changed({settings: false});
    });
    settings.addEventListener('click', event => {
      const move = event.target.closest('[data-move]');
      const remove = event.target.closest('[data-remove]');
      if (move) {
        const next = selected + Number(move.dataset.move);
        if (next < 0 || next >= definition.nodes.length) return;
        [definition.nodes[next], definition.nodes[selected]] = [definition.nodes[selected], definition.nodes[next]];
        selected = next;
        changed();
      } else if (remove) {
        definition.nodes.splice(selected, 1);
        selected = Math.min(selected, definition.nodes.length - 1);
        changed();
      }
    });

    saveButton.addEventListener('click', save);

    qs('[data-action="workflow-rename"]').addEventListener('click', () => {
      const dialog = workflowDialog(text.rename_title, {name: data.name, description: data.description}, messages.save, async () => {
        const value = name => qs('[name="' + name + '"]', dialog).value.trim();
        const result = await api('PUT', '/api/workflows/' + path(data.id), {baseVersion: version, name: value('name'), description: value('description')});
        if (!result.ok) {
          qs('.form-error', dialog).textContent = result.status === 409 ? text.stale : errorMessage(result);
          return;
        }
        version = result.data.version;
        data.name = result.data.name;
        data.description = result.data.description || '';
        qs('#title').textContent = data.name;
        qs('#description').textContent = data.description || text.description;
        $('#dialog').close();
        toast(text.saved);
      });
    });

    qs('[data-action="workflow-export"]').addEventListener('click', () => {
      const exported = {name: data.name, description: data.description || undefined, ...definition};
      download('workflow-' + data.id + '.json', JSON.stringify(exported, null, 2) + '\n');
    });

    qs('[data-action="workflow-run"]').addEventListener('click', async () => {
      if (dirty && !(await save())) return;
      if (problems.length) {
        qs('#workflow-problems').scrollIntoView({block: 'nearest'});
        return toast(text.fix_problems);
      }
      const key = newKey();
      modal(text.run_title, qs('#workflow-run-form').innerHTML, {label: text.run_action, run: async () => {
        const dialog = qs('#dialog-content');
        const engine = qs('[name="engine"]', dialog).value || null;
        const headless = (qs('[name="headless"]:checked', dialog) || {value: '1'}).value === '1';
        const target = chosenTarget(dialog);
        busy($('#dialog-action'), true);
        const result = await api('POST', '/api/workflows/' + path(data.id) + '/runs', {engine, headless, target, idempotencyKey: key});
        busy($('#dialog-action'), false);
        if (!result.ok) {
          qs('.form-error', dialog).textContent = errorMessage(result);
          const list = qs('.form-issues', dialog);
          const lines = problemLines(result);
          list.innerHTML = lines.map(line => '<li>' + esc(line) + '</li>').join('');
          list.hidden = lines.length === 0;
          return;
        }
        location.href = '/playground/runs/' + path(result.data.id);
      }});
      bindTargetChoice(qs('#dialog-content'));
    });

    window.addEventListener('beforeunload', event => {
      if (!dirty) return;
      event.preventDefault();
      event.returnValue = '';
    });

    renderLibrary();
    render();
  }

  function bindWorkflowRun() {
    const root = qs('#workflow-run');
    if (!root) return;
    const text = pageText();
    const run = root.dataset.run;
    const cancel = qs('[data-action="cancel-workflow-run"]');
    if (cancel) {
      cancel.addEventListener('click', () => {
        confirmDialog(text.cancel_title, text.cancel_body, text.cancel_action, async () => {
          const result = await api('POST', '/api/workflow-runs/' + path(run) + '/cancel');
          $('#dialog').close();
          if (!result.ok) return toast(errorMessage(result));
          flash(messages.cancel_requested);
          location.reload();
        });
      });
    }
    qsa('[data-action="rerun-workflow"]').forEach(button => {
      button.addEventListener('click', async () => {
        const resume = button.dataset.resume === '1';
        busy(button, true);
        const result = await api('POST', '/api/workflow-runs/' + path(run) + '/rerun', {resume, idempotencyKey: newKey()});
        if (!result.ok) {
          busy(button, false);
          return toast([errorMessage(result), ...problemLines(result)].join(messages.list_separator));
        }
        flash(resume ? text.resumed : messages.rerun_started);
        location.href = '/playground/runs/' + path(result.data.id);
      });
    });
    if (root.hasAttribute('data-poll')) {
      pollUntilChanged('/api/workflow-runs/' + path(run), root.dataset.signature,
        data => data.status + '|' + data.nodes.map(node => node.status).join(','));
    }
  }

  localizeTimes();
  // ---------------------------------------------------------------- 遠端 worker（M9a）

  function showToken(worker, token) {
    modal(fill(messages.worker_token_title, {name: worker.name}), qs('#worker-token').innerHTML, null);
    const dialog = qs('#dialog-content');
    const root = qs('#workers');
    const server = root.dataset.apiUrl || 'http://<IP>:8081';
    qs('[name="token"]', dialog).value = token;
    const run = 'uv run rpa worker --server ' + server + ' --name ' + worker.id;
    qs('[data-command="windows"]', dialog).textContent = '$env:RPA_WORKER_TOKEN = "' + token + '"\n' + run;
    qs('[data-command="unix"]', dialog).textContent = "export RPA_WORKER_TOKEN='" + token + "'\n" + run;
    const field = qs('[name="token"]', dialog);
    field.focus();
    field.select();
    $('#dialog').addEventListener('close', () => location.reload(), {once: true});
  }

  function bindWorkers() {
    const root = qs('#workers');
    if (!root) return;
    qs('[data-action="new-worker"]').addEventListener('click', () => {
      modal(messages.worker_create_title, qs('#worker-form').innerHTML, {label: messages.worker_create_action, run: async () => {
        const dialog = qs('#dialog-content');
        const value = name => qs('[name="' + name + '"]', dialog).value.trim();
        const result = await api('POST', '/api/workers', {id: value('id'), name: value('name') || null});
        if (!result.ok) return dialogError(dialog, result);
        showToken(result.data.worker, result.data.token);
      }});
      qs('[name="id"]', qs('#dialog-content')).focus();
    });
    const patch = async (button, disabled) => {
      busy(button, true);
      const result = await api('PATCH', '/api/workers/' + path(button.dataset.worker), {disabled});
      if (!result.ok) {
        busy(button, false);
        return toast(errorMessage(result));
      }
      flash(disabled ? messages.worker_disabled : messages.worker_enabled);
      location.reload();
    };
    qsa('[data-action="disable-worker"]').forEach(button => button.addEventListener('click', () => patch(button, true)));
    qsa('[data-action="enable-worker"]').forEach(button => button.addEventListener('click', () => patch(button, false)));
    qsa('[data-action="rotate-worker"]').forEach(button => {
      button.addEventListener('click', () => {
        confirmDialog(fill(messages.worker_rotate_title, {name: button.dataset.name}), messages.worker_rotate_body, messages.worker_rotate_action, async () => {
          const result = await api('POST', '/api/workers/' + path(button.dataset.worker) + '/token');
          if (!result.ok) {
            $('#dialog').close();
            return toast(errorMessage(result));
          }
          showToken(result.data.worker, result.data.token);
        });
      });
    });
    qsa('[data-action="delete-worker"]').forEach(button => {
      button.addEventListener('click', () => {
        confirmDialog(fill(messages.worker_delete_title, {name: button.dataset.name}), messages.worker_delete_body, messages.worker_delete_action, async () => {
          const result = await api('DELETE', '/api/workers/' + path(button.dataset.worker));
          $('#dialog').close();
          if (!result.ok) return toast(errorMessage(result));
          location.reload();
        });
      });
    });
    qsa('[name="default-target"]').forEach(input => {
      input.addEventListener('change', async () => {
        const result = await api('PUT', '/api/settings/default-target', {target: input.value});
        toast(result.ok ? messages.saved : errorMessage(result));
      });
    });
    // 狀態（上線、忙碌、離線）改變時重新載入；對話框開著時不打擾
    if (root.hasAttribute('data-poll')) {
      const states = () => qsa('tr[data-worker]').map(row => row.dataset.state).join('|');
      const current = states();
      const timer = setInterval(async () => {
        if ($('#dialog').open) return;
        const result = await api('GET', '/api/workers');
        if (!result.ok) return;
        const next = result.data.workers.map(worker => worker.status + ':' + (worker.currentRun || '')).join('|');
        if (next !== current) {
          clearInterval(timer);
          location.reload();
        }
      }, 5000);
    }
  }

  bindLanguage();
  bindFilters();
  bindPublish();
  bindScenes();
  bindDomains();
  bindSceneSettings();
  bindEditor();
  bindSection();
  bindRunForm();
  bindRun();
  bindRoles();
  bindRecording();
  bindRecordingDetail();
  bindDebug();
  bindContract();
  bindRerun();
  bindPlayground();
  bindWorkflowEditor();
  bindWorkflowRun();
  bindWorkers();
  showFlash();
})();
