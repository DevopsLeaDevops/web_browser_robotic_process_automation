'use strict';
// 管理 Portal 的頁面互動：呼叫 /api、輪詢執行狀態、對話框；M4 加上登入與憑證、錄製、逐步調試、入參出參表單；
// M6 加上自由試驗場（DAG 畫布、組合場景管理與執行）；M9a 加上遠端 worker 頁與執行位置。
// M10.1：遠端 worker 頁改為裝置頁，新增與重新邀請都產生邀請（一次性、24 小時內有效）。
// M10.2：裝置頁也登記錄製端（/api/recorders），邀請的用法依裝置種類不同。
// 三段分工：領域管理的上移、下移；裝置頁替錄製端打開叢集管理、管理後台的選單。
// M14：管理後台的 API 用戶端（金鑰只顯示一次）；裝置頁的「允許 Agent 調試」「只允許無頭」。
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

  async function refreshSceneSummary(scene) {
    if (!qs('#scene-versions')) return;
    const response = await fetch('/scenes/' + path(scene));
    if (!response.ok) return;
    const page = new DOMParser().parseFromString(await response.text(), 'text/html');
    for (const id of ['scene-versions', 'scene-release-status', 'page-actions', 'script-count-steps', 'script-count-verify', 'attachments']) {
      const next = qs('#' + id, page), current = qs('#' + id);
      if (next && current) current.replaceWith(next);
    }
    bindPublish(); localizeTimes();
  }

  function bindPublish() {
    qsa('[data-action="publish"]').forEach(button => {
      if (button.dataset.bound) return;
      button.dataset.bound = '1';
      button.addEventListener('click', () => {
        const scene = button.dataset.scene;
        const number = button.dataset.revision;
        confirmDialog(messages.publish_title + ' v' + number, messages.publish_body, messages.publish_action, async () => {
          const result = await api('POST', '/api/scenes/' + path(scene) + '/revisions/' + path(number) + '/publish');
          $('#dialog').close();
          if (!result.ok) return toast(errorMessage(result));
          button.disabled = true;
          button.textContent = messages.published;
          let notice = qs('#publish-result');
          if (!notice) { notice = document.createElement('div'); notice.id = 'publish-result'; notice.className = 'notice contract-next'; qs('#main').append(notice); }
          notice.innerHTML = '<span>' + esc(messages.published + ' · ' + scene + ' v' + number) + '</span><a class="button primary" href="/scenes/' + path(scene) + '/run?purpose=execution">' + esc(messages.run_published) + '</a>';
          await refreshSceneSummary(scene);
          notice.scrollIntoView({block: 'nearest'});
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
    // 重新載入領域資料夾（M11）：在資料夾外面改了檔案之後
    const reloadButton = qs('[data-action="reload-domain"]');
    if (reloadButton) {
      reloadButton.addEventListener('click', async () => {
        busy(reloadButton, true);
        const result = await api('POST', '/api/domains/' + path(reloadButton.dataset.domain) + '/reload');
        if (!result.ok) {
          busy(reloadButton, false);
          return toast(errorMessage(result));
        }
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

  // 領域與專案共用：新增時多一個代號欄位，編輯時預填名稱與說明
  function nameDialog(template, title, values, run) {
    modal(title, qs(template).innerHTML, {label: messages.save, run});
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

  // 清單的順序（領域、專案）：上移、下移立刻儲存；一次存一個，送出當下的整個順序
  function bindOrder(table, action, key, url) {
    if (!table) return;
    const rows = () => qsa('tbody tr[data-' + key + ']', table);
    const refresh = () => rows().forEach((row, index, all) => {
      qs('[data-order-number]', row).textContent = String(index + 1);
      qs('[data-direction="up"]', row).disabled = index === 0;
      qs('[data-direction="down"]', row).disabled = index === all.length - 1;
    });
    let saving = Promise.resolve();
    table.addEventListener('click', event => {
      const button = event.target.closest('[data-action="' + action + '"]');
      if (!button || button.disabled) return;
      const row = button.closest('tr');
      const up = button.dataset.direction === 'up';
      const other = up ? row.previousElementSibling : row.nextElementSibling;
      if (!other) return;
      if (up) other.before(row); else other.after(row);
      refresh();
      // 移動後焦點會掉：留在同一個按鈕，到頂或到底時換到另一個
      (button.disabled ? qs('[data-action="' + action + '"]:not(:disabled)', row) : button).focus();
      const ids = rows().map(item => item.dataset[key]);
      saving = saving.then(async () => {
        const result = await api('PUT', url, {ids});
        if (!result.ok) {
          flash(errorMessage(result));
          location.reload();
          return;
        }
        toast(messages.saved);
      });
    });
  }

  function bindDomains() {
    const create = qs('[data-action="new-domain"]');
    if (create) {
      create.addEventListener('click', () => {
        const dialog = nameDialog('#domain-form', messages.domain_create_title, null, async () => {
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
    // 從 git 新增領域（M11 PR 3）：先測試連線，遠端有 pack.yaml 就預填代號與名稱
    const fromGit = qs('[data-action="new-domain-git"]');
    if (fromGit) {
      fromGit.addEventListener('click', () => {
        modal(messages.domain_git_title, qs('#domain-git-form').innerHTML, {
          label: messages.domain_git_action,
          run: async () => {
            const dialog = qs('#dialog-content');
            const action = $('#dialog-action');
            const body = sourceBody(dialog);
            body.id = qs('[name="id"]', dialog).value.trim();
            body.name = qs('[name="name"]', dialog).value.trim() || null;
            delete body.privateKey;
            action.disabled = true;
            const result = await api('POST', '/api/domains/from-git', body);
            action.disabled = false;
            if (!result.ok) {
              qs('.form-error', dialog).textContent = syncError(result);
              return;
            }
            location.href = '/domains/' + path(result.data.id) + '/sync';
          },
        });
        const dialog = qs('#dialog-content');
        showAuth(dialog);
        const probe = qs('[data-action="probe-git"]', dialog);
        probe.addEventListener('click', async () => {
          const output = qs('[data-probe-result]', dialog);
          busy(probe, true);
          output.textContent = '';
          const body = sourceBody(dialog);
          delete body.privateKey;
          const result = await api('POST', '/api/git/probe', body);
          busy(probe, false);
          if (!result.ok) {
            qs('.form-error', dialog).textContent = errorMessage(result);
            return;
          }
          qs('.form-error', dialog).textContent = '';
          output.textContent = result.data.message;
          const id = qs('[name="id"]', dialog);
          const name = qs('[name="name"]', dialog);
          if (result.data.packId) id.value = result.data.packId;
          if (result.data.packName && !name.value.trim()) name.value = result.data.packName;
          if (!id.value.trim()) id.value = qs('[name="directory"]', dialog).value.trim().split('/').pop().toLowerCase();
        });
        qs('[name="url"]', dialog).focus();
      });
      // 組合場景的依賴提示「從 git 新增」帶著 pack.yaml 記的倉庫與目錄過來（M11 收尾）
      const wanted = new URLSearchParams(location.search);
      if (wanted.get('from-git') === '1') {
        fromGit.click();
        const dialog = qs('#dialog-content');
        ['url', 'directory', 'branch', 'id'].forEach(name => {
          const field = qs('[name="' + name + '"]', dialog);
          if (field && wanted.get(name)) field.value = wanted.get(name);
        });
        history.replaceState(null, '', location.pathname);
      }
    }
    const rename = qs('[data-action="rename-server"]');
    if (rename) {
      rename.addEventListener('click', () => {
        const html = '<label>' + esc(messages.server_name) + '<input name="name" maxlength="100" value="' + esc(rename.dataset.name) + '"></label><p class="form-error" role="alert"></p>';
        modal(messages.server_rename_title, html, {
          label: messages.save,
          run: async () => {
            const dialog = qs('#dialog-content');
            const result = await api('PUT', '/api/settings/server', {name: qs('[name="name"]', dialog).value.trim()});
            if (!result.ok) {
              qs('.form-error', dialog).textContent = errorMessage(result);
              return;
            }
            flash(messages.saved);
            location.reload();
          },
        });
        qs('#dialog-content input').focus();
      });
    }
    qsa('[data-action="edit-domain"]').forEach(button => {
      button.addEventListener('click', () => {
        const values = {name: button.dataset.name, description: button.dataset.description};
        const dialog = nameDialog('#domain-form', messages.domain_edit_title, values, async () => {
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
    // 領域的順序（三段分工）：場景管理的領域選單照這個順序
    bindOrder(qs('#domain-order'), 'move-domain', 'domain', '/api/domains/order');
  }

  // ---------------------------------------------------------------- 專案管理（專案空間）

  function bindProjects() {
    const create = qs('[data-action="new-project"]');
    if (create) {
      create.addEventListener('click', () => {
        const dialog = nameDialog('#project-form', messages.project_create_title, null, async () => {
          const value = name => qs('[name="' + name + '"]', dialog).value.trim();
          const result = await api('POST', '/api/projects', {id: value('id'), name: value('name'), description: value('description') || null});
          if (!result.ok) {
            qs('.form-error', dialog).textContent = errorMessage(result);
            return;
          }
          location.href = '/projects/' + path(result.data.id);
        });
      });
    }
    qsa('[data-action="edit-project"]').forEach(button => {
      button.addEventListener('click', () => {
        const values = {name: button.dataset.name, description: button.dataset.description};
        const dialog = nameDialog('#project-form', messages.project_edit_title, values, async () => {
          const value = name => qs('[name="' + name + '"]', dialog).value.trim();
          const result = await api('PATCH', '/api/projects/' + path(button.dataset.project), {name: value('name'), description: value('description')});
          if (!result.ok) {
            qs('.form-error', dialog).textContent = errorMessage(result);
            return;
          }
          flash(messages.saved);
          location.reload();
        });
      });
    });
    qsa('[data-action="delete-project"]').forEach(button => {
      button.addEventListener('click', () => {
        confirmDialog(fill(messages.project_delete_title, {name: button.dataset.name}), messages.project_delete_body, messages.project_delete_action, async () => {
          const result = await api('DELETE', '/api/projects/' + path(button.dataset.project));
          $('#dialog').close();
          if (!result.ok) return toast(errorMessage(result));
          location.reload();
        });
      });
    });
    // 專案的順序：專案空間的選單與 /workspace 轉到的第一個專案照這個順序
    bindOrder(qs('#project-order'), 'move-project', 'project', '/api/projects/order');
  }

  // ---------------------------------------------------------------- 資料來源與同步（M11 PR 3）

  // 認證方式切換時只顯示那一種要填的欄位
  function showAuth(root) {
    const select = qs('select[name="auth"]', root);
    if (!select) return;
    const update = () => qsa('[data-auth-section]', root).forEach(section => {
      section.hidden = section.dataset.authSection !== select.value;
    });
    select.addEventListener('change', update);
    update();
  }

  // 錯誤訊息加上衝突的檔案或擋下推送的原因
  function syncError(result) {
    const lines = [errorMessage(result)];
    const error = result.data && result.data.error;
    if (error && Array.isArray(error.conflicts)) lines.push(...error.conflicts);
    if (error && Array.isArray(error.problems)) {
      lines.push(...error.problems.map(item => (typeof item === 'string' ? item : (item && item.message) || '')));
    }
    return lines.filter(Boolean).join('\n');
  }

  function sourceBody(root) {
    const value = name => {
      const field = qs('[name="' + name + '"]', root);
      return field ? field.value.trim() : '';
    };
    const autoPull = qs('[name="autoPull"]', root);
    return {
      url: value('url'), directory: value('directory'), branch: value('branch') || null,
      auth: value('auth') || 'none', username: value('username') || null, token: value('token') || null,
      privateKey: value('privateKey') || null, committerName: value('committerName') || null,
      committerEmail: value('committerEmail') || null, autoPull: autoPull ? autoPull.checked : true,
    };
  }

  function fillList(root, items) {
    qs('[data-list]', root).innerHTML = items.map(item => '<li>' + esc(item) + '</li>').join('');
    root.hidden = items.length === 0;
  }

  function bindSync() {
    const root = qs('#sync');
    if (!root) return;
    const base = '/api/domains/' + path(root.dataset.domain);
    const form = qs('form[data-action="sync-save"]');
    if (form) {
      showAuth(form);
      form.addEventListener('submit', async event => {
        event.preventDefault();
        const button = qs('button[type="submit"]', form);
        busy(button, true);
        const result = await api('PUT', base + '/source', sourceBody(form));
        busy(button, false);
        if (!result.ok) {
          qs('.form-error', form).textContent = errorMessage(result);
          return;
        }
        flash(messages.saved);
        location.reload();
      });
    }
    // 測試連線與拉取：結果（含衝突、錯誤）記在同步狀態，重新整理就看得到
    [['sync-test', '/sync/test'], ['sync-pull', '/sync/pull']].forEach(([action, url]) => {
      const button = qs('[data-action="' + action + '"]');
      if (!button) return;
      button.addEventListener('click', async () => {
        busy(button, true);
        const result = await api('POST', base + url);
        if (!result.ok) {
          busy(button, false);
          if (result.status === 409 || result.status === 502) {
            flash(syncError(result));
            location.reload();
            return;
          }
          return toast(syncError(result));
        }
        flash(action === 'sync-test' ? result.data.message : messages.sync_pulled);
        location.reload();
      });
    });
    const keyButton = qs('[data-action="sync-key"]');
    if (keyButton) {
      keyButton.addEventListener('click', async () => {
        busy(keyButton, true);
        const result = await api('POST', base + '/source/key');
        busy(keyButton, false);
        if (!result.ok) return toast(errorMessage(result));
        const holder = qs('#sync-public-key');
        const pre = document.createElement('pre');
        pre.className = 'source';
        pre.id = 'sync-public-key';
        pre.textContent = result.data.publicKey;
        holder.replaceWith(pre);
        toast(messages.sync_key_ready);
      });
    }
    const disconnect = qs('[data-action="sync-disconnect"]');
    if (disconnect) {
      disconnect.addEventListener('click', () => {
        confirmDialog(messages.sync_disconnect_title, messages.sync_disconnect_body, messages.sync_disconnect_action, async () => {
          const result = await api('DELETE', base + '/source');
          $('#dialog').close();
          if (!result.ok) return toast(errorMessage(result));
          location.reload();
        });
      });
    }
    qsa('[data-action="sync-resolve"]').forEach(button => {
      button.addEventListener('click', () => {
        const choice = button.dataset.resolve;
        const run = async () => {
          busy(button, true);
          const result = await api('POST', base + '/sync/resolve', {action: choice});
          if ($('#dialog').open) $('#dialog').close();
          busy(button, false);
          if (!result.ok) return toast(syncError(result));
          if (choice === 'branch' && result.data.pushedBranch) flash(fill(messages.sync_branch_pushed, {branch: result.data.pushedBranch}));
          location.reload();
        };
        if (choice === 'cancel') return run();
        const title = choice === 'branch' ? messages.sync_resolve_branch_title : messages.sync_resolve_remote_title;
        const body = choice === 'branch' ? messages.sync_resolve_branch_body : messages.sync_resolve_remote_body;
        confirmDialog(title, body, messages.sync_resolve_action, run);
      });
    });
    const push = qs('[data-action="sync-push"]');
    if (push) {
      push.addEventListener('click', async () => {
        busy(push, true);
        const preview = await api('GET', base + '/sync/preview');
        busy(push, false);
        if (!preview.ok) return toast(errorMessage(preview));
        const data = preview.data;
        const blocked = data.blockers.length > 0;
        modal(messages.sync_push_title, qs('#sync-push-form').innerHTML, blocked ? undefined : {
          label: messages.sync_push_action,
          run: async () => {
            const dialog = qs('#dialog-content');
            const action = $('#dialog-action');
            action.disabled = true;
            const result = await api('POST', base + '/sync/push', {message: qs('[name="message"]', dialog).value.trim() || null});
            action.disabled = false;
            if (!result.ok) {
              if (result.status === 409) {
                $('#dialog').close();
                flash(syncError(result));
                location.reload();
                return;
              }
              qs('.form-error', dialog).textContent = syncError(result);
              return;
            }
            $('#dialog').close();
            flash(messages.sync_pushed);
            location.reload();
          },
        });
        const dialog = qs('#dialog-content');
        fillList(qs('[data-push-blockers]', dialog), data.blockers);
        fillList(qs('[data-push-warnings]', dialog), data.warnings);
        const changes = qs('[data-push-changes]', dialog);
        qs('[data-summary]', changes).textContent = fill(messages.sync_changes, {count: data.changes.length});
        fillList(changes, data.changes.map(change => (messages['sync_' + change.action] || change.action) + ' ' + change.path));
        qs('[data-push-empty]', dialog).hidden = data.changes.length > 0;
        qs('[name="message"]', dialog).value = data.message;
      });
    }
  }

  // ---------------------------------------------------------------- 編輯版本

  function watchEditor(form) {
    const signature = () => JSON.stringify(qsa('textarea, input', form).map(field => [field.name, field.value]));
    let saved = signature();
    window.addEventListener('beforeunload', event => {
      if (signature() !== saved) { event.preventDefault(); event.returnValue = ''; }
    });
    return () => { saved = signature(); };
  }

  function savedRevision(form, number) {
    form.dataset.base = number;
    let notice = qs('#editor-saved');
    if (!notice) { notice = document.createElement('div'); notice.id = 'editor-saved'; notice.className = 'notice contract-next'; notice.setAttribute('role', 'status'); form.prepend(notice); }
    notice.innerHTML = '<span>' + esc(fill(messages.contract_saved_next, {number})) + '</span><a class="button" href="/scenes/' + path(form.dataset.scene) + '/run?purpose=validation&revision=' + number + '">' + esc(messages.validate_next) + '</a>';
    const description = qs('#description');
    if (description) description.textContent = fill(messages.editor_revision, {number});
    const revision = qs('.section-tabs > .muted');
    if (revision) revision.textContent = 'v' + number;
    const url = new URL(location.href); url.searchParams.delete('revision'); history.replaceState(null, '', url);
    toast(messages.saved + ' v' + number);
  }

  function bindEditor() {
    const form = qs('#revision-form');
    if (!form) return;
    const markSaved = watchEditor(form);
    const tabList = qs('#file-tabs', form);
    const select = name => {
      qsa('[data-file-tab]', form).forEach(other => {
        const active = other.dataset.fileTab === name;
        other.classList.toggle('active', active);
        other.setAttribute('aria-selected', String(active));
      });
      qsa('[data-file]', form).forEach(section => { section.hidden = section.dataset.file !== name; });
    };
    tabList?.addEventListener('click', event => {
      const tab = event.target.closest('[data-file-tab]');
      if (tab) select(tab.dataset.fileTab);
    });
    // Python 節點（ADR 0020）：新增 script.files 列的檔案、移除不用的檔案；存檔時一起校驗
    const newName = form.elements.namedItem('new-file');
    qs('[data-action="add-file"]', form)?.addEventListener('click', () => {
      const name = newName.value.trim();
      if (!/^[A-Za-z0-9_][A-Za-z0-9_.-]*(\/[A-Za-z0-9_][A-Za-z0-9_.-]*)*$/.test(name) || name.startsWith('files/')) {
        return toast(messages.file_name_invalid);
      }
      if (!qs('[data-file="' + CSS.escape(name) + '"]', form)) {
        const section = qs('#file-template').content.firstElementChild.cloneNode(true);
        section.dataset.file = name;
        qs('h2', section).textContent = name;
        const area = qs('textarea', section);
        area.name = name;
        area.setAttribute('aria-label', name);
        qs('#file-template').before(section);
        const tab = document.createElement('button');
        tab.type = 'button'; tab.setAttribute('role', 'tab'); tab.dataset.fileTab = name; tab.textContent = name;
        tabList.append(tab);
      }
      newName.value = '';
      select(name);
      form.dispatchEvent(new Event('input', {bubbles: true}));
    });
    form.addEventListener('click', event => {
      const button = event.target.closest('[data-action="remove-file"]');
      if (!button) return;
      const section = button.closest('[data-file]');
      const name = section.dataset.file;
      section.remove();
      qs('[data-file-tab="' + CSS.escape(name) + '"]', form)?.remove();
      select('scenario.yaml');
      form.dispatchEvent(new Event('input', {bubbles: true}));
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
    // 從運行回看的「在場景中開啟（第 N 行）」進來：選取那一行（M12）
    const line = Number(form.dataset.line);
    if (line && area) {
      selectLine(area, line);
      area.closest('section').scrollIntoView({block: 'start'});
    }
    const save = qs('[data-action="save-revision"]');
    form.addEventListener('submit', event => event.preventDefault());
    save.addEventListener('click', async () => {
      const files = {};
      qsa('textarea.code-editor', form).forEach(area => { files[area.name] = area.value; });
      const note = form.elements.namedItem('note').value.trim() || null;
      save.disabled = true; form.inert = true;
      const result = await api('POST', '/api/scenes/' + path(form.dataset.scene) + '/revisions', {
        baseRevision: Number(form.dataset.base), files, note,
      });
      save.disabled = false; form.inert = false;
      if (result.ok) {
        qs('#issues').hidden = true;
        markSaved(); savedRevision(form, result.data.number);
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

  // 場景網址指向本機（127.0.0.1、localhost、::1；測試網站的 8765 除外）：
  // 遠端 worker 上那指的是 worker 自己，交給它執行很可能連不到
  const TESTSITE_PORT = '8765';
  function pointsToThisComputer(value) {
    let url;
    try {
      url = new URL(value);
    } catch {
      return false;
    }
    const host = url.hostname.replace(/^\[|\]$/g, '');
    const local = host === 'localhost' || host === '::1' || /^127\./.test(host);
    return local && url.port !== TESTSITE_PORT;
  }

  // 換執行位置時，有頭模式能不能選跟著那個位置（本機看這台電腦，遠端看 worker）
  function bindTargetChoice(root) {
    const choice = qs('[data-target-choice]', root);
    if (!choice) return;
    const display = JSON.parse(choice.dataset.display || '{}');
    const baseUrl = qs('[name="baseUrl"]', root);
    const warning = qs('[data-local-url-warning]', root);
    const update = () => {
      const target = chosenTarget(root);
      if (warning) warning.hidden = !(baseUrl && target && target !== 'local' && pointsToThisComputer(baseUrl.value));
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
    if (baseUrl) baseUrl.addEventListener('input', update);
    update();
  }

  // ---------------------------------------------------------------- 檔案入參（M7c）

  // 傳一個檔案到伺服器（POST /api/files?name=檔名，本體就是檔案內容）；用 XHR 才看得到上傳進度
  function uploadFile(file, progress) {
    return new Promise(resolve => {
      const xhr = new XMLHttpRequest();
      xhr.open('POST', '/api/files?name=' + path(file.name));
      xhr.setRequestHeader('Accept', 'application/json');
      xhr.setRequestHeader('Content-Type', file.type || 'application/octet-stream');
      xhr.upload.addEventListener('progress', event => {
        if (event.lengthComputable && event.total) progress(event.loaded / event.total);
      });
      xhr.addEventListener('load', () => {
        let data = null;
        try { data = JSON.parse(xhr.responseText); } catch { data = null; }
        resolve({ok: xhr.status >= 200 && xhr.status < 300, status: xhr.status, data});
      });
      xhr.addEventListener('error', () => resolve({ok: false, status: 0, data: null}));
      xhr.send(file);
    });
  }

  const formatSize = size => {
    for (const [unit, base] of [['GB', 1024 ** 3], ['MB', 1024 ** 2], ['KB', 1024]]) {
      if (size >= base) return (size / base).toFixed(1).replace(/\.0$/, '') + ' ' + unit;
    }
    return size + ' B';
  };

  // 執行、驗證、調試表單的檔案入參：選檔上傳或選場景附件，值寫進入參 JSON。
  // 入參 JSON 仍是送出時唯一的來源；手改 JSON 時，這裡顯示的目前值跟著更新。
  // 回傳 pending()：還有檔案在上傳時，送出前要先擋下。
  function bindFileInputs(form) {
    const panel = qs('[data-file-inputs]', form);
    const textarea = form.elements.namedItem('inputs');
    if (!panel || !textarea) return {pending: () => false};
    const limit = Number(panel.dataset.limit) || 0;
    let uploading = 0;
    const read = () => {
      try {
        const value = JSON.parse(textarea.value.trim() || '{}');
        return value && typeof value === 'object' && !Array.isArray(value) ? value : null;
      } catch {
        return null;
      }
    };
    const write = inputs => {
      textarea.value = JSON.stringify(inputs, null, 2);
      render();
    };
    const listOf = value => (value === undefined || value === null || value === '' ? [] : Array.isArray(value) ? value : [value]);
    // 改一個入參的值；JSON 寫錯時不動，提示先修正
    const change = (box, update) => {
      const inputs = read();
      if (inputs === null) return toast(messages.json_invalid);
      const name = box.dataset.fileInput;
      const next = update(listOf(inputs[name]), name in inputs);
      if (next === undefined) delete inputs[name];
      else inputs[name] = box.dataset.multiple ? next : (next.length ? next[next.length - 1] : '');
      write(inputs);
    };
    const attachmentSize = (box, value) => {
      const option = qsa('[data-file-attachment] option', box).find(item => item.value === value);
      return option && option.dataset.size ? Number(option.dataset.size) : null;
    };
    const describe = (box, item) => {
      if (typeof item === 'string') {
        return {kind: messages.file_attachment, label: item.replace(/^files\//, ''), size: attachmentSize(box, item)};
      }
      if (item && typeof item === 'object') {
        if (typeof item.file === 'string') {
          return {kind: messages.file_uploaded, label: item.name || item.file, size: item.size, href: '/api/files/' + path(item.file) + '/content'};
        }
        if (typeof item.attachment === 'string') {
          const label = item.name ? item.name + ' ← ' + item.attachment.replace(/^files\//, '') : item.attachment.replace(/^files\//, '');
          return {kind: messages.file_attachment, label, size: attachmentSize(box, item.attachment)};
        }
        if (typeof item.path === 'string') return {kind: messages.file_path, label: item.name ? item.name + ' ← ' + item.path : item.path};
      }
      return {kind: messages.file_unknown, label: JSON.stringify(item)};
    };
    const render = () => {
      const inputs = read();
      qsa('[data-file-input]', panel).forEach(box => {
        const list = qs('[data-file-value]', box);
        list.textContent = '';
        const note = text => {
          const item = document.createElement('li');
          item.className = 'muted';
          item.textContent = text;
          list.append(item);
        };
        if (inputs === null) return note(messages.json_invalid);
        const name = box.dataset.fileInput;
        const values = listOf(inputs[name]);
        if (!values.length) return note(name in inputs ? messages.file_none : messages.file_default);
        values.forEach((value, index) => {
          const info = describe(box, value);
          const item = document.createElement('li');
          item.className = 'file-chip';
          const kind = document.createElement('span');
          kind.className = 'tag';
          kind.textContent = info.kind;
          const label = document.createElement(info.href ? 'a' : 'span');
          label.textContent = info.label;
          if (info.href) {
            label.href = info.href;
            label.target = '_blank';
            label.rel = 'noopener';
          }
          item.append(kind, label);
          if (typeof info.size === 'number') {
            const size = document.createElement('span');
            size.className = 'muted';
            size.textContent = formatSize(info.size);
            item.append(size);
          }
          const remove = document.createElement('button');
          remove.type = 'button';
          remove.className = 'icon-btn';
          remove.title = messages.file_remove;
          remove.setAttribute('aria-label', messages.file_remove + ' ' + info.label);
          remove.textContent = '✕';
          remove.addEventListener('click', () => change(box, items => items.filter((_, at) => at !== index)));
          item.append(remove);
          list.append(item);
        });
      });
    };
    qsa('[data-file-input]', panel).forEach(box => {
      const picker = qs('[data-file-pick]', box);
      const progress = qs('.file-progress', box);
      const max = Number(box.dataset.max) || 0;
      picker.addEventListener('change', async () => {
        const files = [...picker.files];
        picker.value = '';
        if (!files.length) return;
        const tooLarge = files.find(file => (limit && file.size > limit) || (max && file.size > max));
        if (tooLarge) {
          const cap = max && (!limit || max < limit) ? max : limit;
          return toast(fill(messages.file_too_large, {name: tooLarge.name, size: formatSize(tooLarge.size), limit: formatSize(cap)}));
        }
        uploading += 1;
        progress.hidden = false;
        progress.value = 0;
        const total = files.reduce((sum, file) => sum + file.size, 0) || 1;
        let done = 0;
        const added = [];
        try {
          for (const file of files) {
            const result = await uploadFile(file, part => { progress.value = (done + part * file.size) / total; });
            if (!result.ok) {
              toast(fill(messages.file_upload_failed, {name: file.name, error: errorMessage(result)}));
              break;
            }
            done += file.size;
            const {file: id, name, size, sha256} = result.data;
            added.push({file: id, name, size, sha256});
          }
        } finally {
          uploading -= 1;
          progress.hidden = true;
        }
        if (added.length) change(box, items => (box.dataset.multiple ? [...items, ...added] : added));
      });
      const attachment = qs('[data-file-attachment]', box);
      if (attachment) {
        attachment.addEventListener('change', () => {
          const value = attachment.value;
          attachment.value = '';
          if (value) change(box, items => (box.dataset.multiple ? [...items, value] : [value]));
        });
      }
      const reset = qs('[data-file-clear]', box);
      // 有預設值的入參：拿掉這個鍵就用預設值；沒有預設值的：清成空的，送出時提示要選
      reset.addEventListener('click', () => change(box, () => (box.dataset.default ? undefined : [])));
    });
    textarea.addEventListener('input', render);
    render();
    return {pending: () => uploading > 0};
  }

  // 場景詳情頁的附件區（M7c）：加上、換掉、刪除附件都存成新版本，完成後重新載入（有沒存的編輯時瀏覽器會先問）。
  // 附件區會被 refreshSceneSummary 換掉（基準版本跟著更新），所以事件掛在 document 上。
  const ATTACHMENT_NAME = /^[A-Za-z0-9_][A-Za-z0-9_.-]{0,99}$/;

  function suggestAttachmentName(name) {
    const dot = name.lastIndexOf('.');
    const extension = dot > 0 && /^\.[A-Za-z0-9]{1,10}$/.test(name.slice(dot)) ? name.slice(dot).toLowerCase() : '';
    const stem = (dot > 0 ? name.slice(0, dot) : name).normalize('NFKD').replace(/[^A-Za-z0-9_.-]+/g, '-').replace(/^[-.]+|[-.]+$/g, '').slice(0, 80);
    return (stem || 'file') + extension;
  }

  function bindAttachments() {
    if (!qs('#attachments')) return;
    const saveAttachment = async (file, name) => {
      const panel = qs('#attachments');
      const url = '/api/scenes/' + path(panel.dataset.scene) + '/attachments/' + path(name) + '?base=' + path(panel.dataset.base);
      let response;
      try {
        response = await fetch(url, {method: 'PUT', headers: {Accept: 'application/json', 'Content-Type': 'application/octet-stream'}, body: file});
      } catch {
        return toast(messages.network_error);
      }
      let data = null;
      try { data = await response.json(); } catch { data = null; }
      const result = {ok: response.ok, status: response.status, data};
      if (!result.ok) return toast(errorMessage(result));
      flash(fill(messages.attachment_saved, {name, number: data.number}));
      location.reload();
    };
    document.addEventListener('change', event => {
      const picker = event.target.closest('[data-attachment-pick]');
      if (!picker) return;
      const file = picker.files[0];
      picker.value = '';
      if (!file) return;
      const limit = Number(qs('#attachments').dataset.limit) || 0;
      if (limit && file.size > limit) {
        return toast(fill(messages.attachment_too_large, {name: file.name, size: formatSize(file.size), limit: formatSize(limit)}));
      }
      if (ATTACHMENT_NAME.test(file.name)) return saveAttachment(file, file.name);
      // 附件的檔名只能用英文（跨平台、放進 Git 都不會出問題）；網頁要看到原本的檔名時，在入參的預設值寫 name
      modal(messages.attachment_rename_title,
        '<p class="hint">' + esc(fill(messages.attachment_rename_body, {name: file.name})) + '</p>'
        + '<label class="field">' + esc(messages.attachment_rename_label)
        + '<input id="attachment-name" class="mono" maxlength="100" value="' + esc(suggestAttachmentName(file.name)) + '"></label>',
        {label: messages.attachment_save, run: () => {
          const name = qs('#attachment-name').value.trim();
          if (!ATTACHMENT_NAME.test(name)) return toast(messages.attachment_name_invalid);
          $('#dialog').close();
          saveAttachment(file, name);
        }});
    });
    document.addEventListener('click', event => {
      const button = event.target.closest('[data-action="delete-attachment"]');
      if (!button) return;
      const name = button.dataset.name;
      confirmDialog(messages.attachment_delete_title, fill(messages.attachment_delete_body, {name}), messages.attachment_delete_action, async () => {
        const panel = qs('#attachments');
        const result = await api('DELETE', '/api/scenes/' + path(panel.dataset.scene) + '/attachments/' + path(name) + '?base=' + path(panel.dataset.base));
        $('#dialog').close();
        if (!result.ok) return toast(errorMessage(result));
        flash(fill(messages.attachment_deleted, {name, number: result.data.number}));
        location.reload();
      });
    });
  }

  function bindRunForm() {
    const form = qs('#run-form');
    if (!form) return;
    bindTargetChoice(form);
    const files = bindFileInputs(form);
    const key = newKey();
    const button = qs('[data-action="submit-run"]', form);
    form.addEventListener('submit', async event => {
      event.preventDefault();
      if (files.pending()) return toast(messages.file_uploading);
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
      domainId: value('domainId'),
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
      const files = bindFileInputs(start);
      start.addEventListener('submit', async event => {
        event.preventDefault();
        if (files.pending()) return toast(messages.file_uploading);
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
        const number = saved.data.number;
        const reloaded = await api('POST', base + '/reload', {revision: number});
        if (reloaded.ok) {
          flash(messages.saved + ' v' + number);
          return location.reload();
        }
        // 新版本已經存好，只是這個調試沒有換過去：留下說明，讓使用者選擇用新版本重新開始或留在原本的版本
        busy(button, false);
        yaml.dataset.base = String(number);
        const failed = qs('#debug-reload-failed', yaml);
        const current = {number: yaml.dataset.revision};
        qs('[data-message]', failed).textContent = fill(messages.debug_reload_failed, {number, reason: errorMessage(reloaded)});
        const restart = qs('[data-action="debug-restart"]', failed);
        const stay = qs('[data-action="debug-stay"]', failed);
        restart.textContent = fill(messages.debug_restart, {number});
        stay.textContent = fill(messages.debug_stay, current);
        restart.onclick = async () => {
          busy(restart, true);
          stay.disabled = true;
          const restarted = await api('POST', base + '/restart', {revision: number});
          if (!restarted.ok) {
            busy(restart, false);
            stay.disabled = false;
            return toast(errorMessage(restarted));
          }
          location.href = '/scenes/' + path(scene) + '/debug';
        };
        stay.onclick = () => location.reload();
        failed.hidden = false;
        failed.scrollIntoView({block: 'nearest'});
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
    area.dispatchEvent(new Event('input', {bubbles: true}));
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

  // 場景詳情頁的「腳本」區（2026-10-25）：自動化腳本（steps）與斷言腳本（verify）切換編輯；
  // 兩段有改的一起存成一個新版本（PUT /api/scenes/{id}/sections）。不換頁：錄製端的視窗沒有上一頁。
  function bindScripts() {
    const panel = qs('#script');
    if (!panel) return null;
    const form = qs('#script-form');
    const tabs = qsa('[data-script-tab]', panel);
    const show = part => {
      // Python 節點的分頁是檔案：卡片的「自動化腳本」「斷言腳本」連結對到那支腳本的分頁
      const roles = {steps: 'automation', verify: 'assertion'};
      const byRole = tabs.find(tab => tab.dataset.scriptRole && tab.dataset.scriptRole === roles[part]);
      if (byRole) part = byRole.dataset.scriptTab;
      if (!tabs.some(tab => tab.dataset.scriptTab === part)) return;
      tabs.forEach(tab => {
        const active = tab.dataset.scriptTab === part;
        tab.classList.toggle('active', active);
        tab.setAttribute('aria-selected', String(active));
      });
      qsa('[data-script-part]', panel).forEach(element => { element.hidden = element.dataset.scriptPart !== part; });
      if (form) form.dataset.key = part;
    };
    tabs.forEach(tab => tab.addEventListener('click', () => show(tab.dataset.scriptTab)));
    if (!form) return show;
    const scene = form.dataset.scene;
    const archived = panel.dataset.archived === '1';
    const areas = {steps: form.elements.namedItem('steps'), verify: form.elements.namedItem('verify')};
    const saved = {steps: areas.steps.value, verify: areas.verify.value};
    const state = qs('#script-state');
    const save = qs('[data-action="save-scripts"]', form);
    const list = qs('#script-issues');
    const label = part => messages['script_' + part];
    const changed = () => Object.keys(areas).filter(part => areas[part].value !== saved[part]);
    const refresh = () => {
      const parts = changed();
      save.disabled = archived || parts.length === 0;
      state.textContent = parts.length
        ? fill(messages.scripts_unsaved, {parts: parts.map(label).join(messages.list_separator)})
        : fill(messages.scripts_state, {number: form.dataset.base});
    };
    form.addEventListener('input', refresh);
    window.addEventListener('beforeunload', event => {
      if (changed().length) { event.preventDefault(); event.returnValue = ''; }
    });
    // 入參、出參存成新版本時，接著用那個版本當基準（只換掉這兩段，不會蓋掉入參、出參）
    document.addEventListener('scene-revision', event => {
      if (event.detail.source === 'scripts') return;
      form.dataset.base = event.detail.number;
      refresh();
    });
    qsa('[data-insert]', form).forEach(chip => chip.addEventListener('click', () => insertAt(areas[form.dataset.key], chip.dataset.insert)));
    // 斷言範本：接在最後，縮排跟著現有的項目
    const rules = {notEmpty: 'notEmpty: true', equals: 'equals: ""', contains: 'contains: ""', matches: 'matches: "^$"'};
    qsa('[data-insert-check]', form).forEach(button => button.addEventListener('click', () => {
      const area = areas.verify;
      const found = /^( *)- /m.exec(area.value.replace(/^verify:.*$/m, ''));
      const indent = found ? found[1] : '  ';
      let text = area.value.replace(/\s+$/, '');
      if (!/^verify\s*:/m.test(text)) text = (text ? text + '\n' : '') + 'verify:';
      const item = [indent + '- name: ', indent + '  value: "{{ facts. }}"', indent + '  ' + rules[button.dataset.insertCheck]];
      area.value = text + '\n' + item.join('\n') + '\n';
      const position = area.value.lastIndexOf('- name: ') + '- name: '.length;
      area.focus();
      area.setSelectionRange(position, position);
      refresh();
    }));
    // 校驗問題：標出在哪一段的第幾行，點一下切到那一段、選到那一行
    const showIssues = result => {
      const error = result.data && result.data.error;
      const issues = error && Array.isArray(error.issues) ? error.issues : [];
      list.innerHTML = '<li>' + esc(errorMessage(result)) + '</li>' + issues.map((issue, index) => {
        const where = issue.section && issue.sectionLine ? label(issue.section) + ' ' + fill(messages.section_line, {line: issue.sectionLine}) + '  ' : '';
        return '<li><button type="button" class="text-btn" data-issue="' + index + '">' + esc(where + (issue.message || issue.text || '')) + '</button></li>';
      }).join('');
      list.hidden = false;
      qsa('[data-issue]', list).forEach(button => {
        const issue = issues[Number(button.dataset.issue)];
        button.disabled = !issue.section || !issue.sectionLine || !areas[issue.section];
        button.addEventListener('click', () => { show(issue.section); selectLine(areas[issue.section], issue.sectionLine); });
      });
      list.scrollIntoView({block: 'nearest'});
    };
    const submit = async () => {
      const parts = changed();
      if (!parts.length || archived) return;
      list.hidden = true;
      busy(save, true); form.inert = true;
      const result = await api('PUT', '/api/scenes/' + path(scene) + '/sections', {
        baseRevision: Number(form.dataset.base),
        sections: Object.fromEntries(parts.map(part => [part, areas[part].value])),
        note: form.elements.namedItem('note').value.trim() || null,
      });
      busy(save, false); form.inert = false;
      if (!result.ok) {
        if (result.status === 409 && result.data && result.data.error && result.data.error.code === 'stale_base') return toast(messages.stale_base);
        return showIssues(result);
      }
      const number = result.data.number;
      parts.forEach(part => { saved[part] = areas[part].value; });
      form.elements.namedItem('note').value = '';
      form.dataset.base = number;
      refresh();
      let notice = qs('#script-saved');
      if (!notice) { notice = document.createElement('div'); notice.id = 'script-saved'; notice.className = 'notice contract-next'; notice.setAttribute('role', 'status'); form.prepend(notice); }
      notice.innerHTML = '<span>' + esc(fill(messages.contract_saved_next, {number})) + '</span><a class="button" href="/scenes/' + path(scene) + '/run?purpose=validation&revision=' + number + '">' + esc(messages.validate_next) + '</a>';
      toast(messages.saved + ' v' + number);
      document.dispatchEvent(new CustomEvent('scene-revision', {detail: {number, source: 'scripts'}}));
      await refreshSceneSummary(scene);
    };
    form.addEventListener('submit', event => { event.preventDefault(); submit(); });
    refresh();
    return show;
  }

  // 場景詳情頁的區域連結（卡片與頁面上方的 #steps、#verify、#inputs、#outputs、#runs…）：
  // 切到對應的分頁並捲到那一區；同一頁內點連結也一樣（不留下上一頁的紀錄）。
  // 捲動只在這裡做：入參與出參、預覽等內容載入後版面會變，跳過去後的幾秒內、使用者還沒自己
  // 捲動或操作之前，版面一變就重新對齊。目標區塊閃一下外框：入參與出參左右並排時看得出是哪一個。
  function bindSceneAnchors(showScript) {
    const pageArea = qs('.scene-page');
    if (!pageArea) return;
    const targets = {versions: 'scene-versions', inputs: 'contract-inputs', outputs: 'contract-outputs', steps: 'script', verify: 'script'};
    let current = null;
    let holdUntil = 0;
    const align = smooth => current?.scrollIntoView({block: 'start', behavior: smooth ? 'smooth' : 'auto'});
    const go = (hash, smooth) => {
      const name = hash.replace(/^#/, '');
      if (!name) return;
      if ((name === 'steps' || name === 'verify') && showScript) showScript(name);
      const target = document.getElementById(targets[name] || name);
      if (!target) return;
      current = target;
      holdUntil = performance.now() + 4000;
      align(smooth);
      qsa('.scene-jump a').forEach(link => link.classList.toggle('active', link.getAttribute('href') === '#' + name));
      target.classList.remove('anchor-hit');
      void target.offsetWidth;  // 重新開始動畫
      target.classList.add('anchor-hit');
    };
    const release = () => { holdUntil = 0; };
    ['wheel', 'touchstart', 'keydown', 'mousedown'].forEach(type => window.addEventListener(type, release, {capture: true, passive: true}));
    const settle = () => { if (current && performance.now() < holdUntil) align(false); };
    // 區域連結列在窄視窗會換行：留給它的高度跟著實際高度（CSS 的 --scene-jump-height）
    const jump = qs('.scene-jump', pageArea);
    const measure = () => { if (jump) pageArea.style.setProperty('--scene-jump-height', jump.offsetHeight + 'px'); };
    measure();
    if ('ResizeObserver' in window) {
      new ResizeObserver(settle).observe(pageArea);
      if (jump) new ResizeObserver(() => { measure(); settle(); }).observe(jump);
    }
    document.addEventListener('scene-layout', settle);
    pageArea.addEventListener('animationend', event => event.target.classList.remove('anchor-hit'));
    document.addEventListener('click', event => {
      const link = event.target.closest('a[href^="#"]');
      if (!link || link.closest('#sidenav, #topnav') || link.classList.contains('skip')) return;
      event.preventDefault();
      history.replaceState(null, '', link.getAttribute('href'));
      go(link.getAttribute('href'), true);
    });
    window.addEventListener('hashchange', () => go(location.hash, true));
    // 等版面排好再捲動，位置才準
    requestAnimationFrame(() => go(location.hash, false));
  }

  // ---------------------------------------------------------------- 入參與出參的表單

  // 表單上的文字 → 型別正確的值；轉不了就保留原文，讓伺服器的校驗說明哪裡不對
  function typed(text, type) {
    const value = text.trim();
    if (value === '') return null;
    if (type === 'integer' && /^[-+]?\d+$/.test(value)) return Number(value);
    if (type === 'number' && !Number.isNaN(Number(value))) return Number(value);
    if (type === 'boolean' && (value === 'true' || value === 'false')) return value === 'true';
    if (type === 'array' || type === 'object') {
      // array、object 入參（ADR 0020）：預設值寫 JSON
      try { return JSON.parse(value); } catch { /* 交給伺服器說明哪裡不對 */ }
    }
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

  const RULE_KEYS = ['minLength', 'maxLength', 'pattern', 'minimum', 'maximum', 'enum', 'accept', 'maxSize', 'multiple'];

  // 一列的限制摘要（DSL 的寫法，各語言相同）；沒有限制時顯示 —
  function ruleSummary(row) {
    const parts = RULE_KEYS.filter(key => {
      const field = qs('[name="' + key + '"]', row.nextElementSibling);
      if (!field || field.closest('label').hidden) return false;
      return field.type === 'checkbox' ? field.checked : field.value.trim() !== '';
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
      fallback.placeholder = type === 'boolean' ? 'true / false'
        : type === 'array' ? '["甲", "乙"]'
        : type === 'object' ? '{"key": "value"}'
        : fallback.dataset.placeholder;
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
      if (!field || value === undefined || value === null) return;
      if (field.type === 'checkbox') field.checked = value === true;
      else field.value = typeof value === 'string' ? value : JSON.stringify(value);
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
    RULE_KEYS.forEach(key => set(rules, key, (key === 'enum' || key === 'accept') && Array.isArray(spec[key]) ? spec[key].join(', ') : spec[key]));
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
      // 檔案入參（M7c）：accept 是清單，multiple 沒勾就不寫
      accept: get(rules, 'accept').split(/[,，\s]+/).map(item => item.trim()).filter(Boolean),
      maxSize: get(rules, 'maxSize').trim() || null,
      multiple: type === 'file' && qs('[name="multiple"]', rules).checked ? true : null,
    };
    if (!item.accept.length) item.accept = null;
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
    const host = qs('#contract-workspace');
    if (!host) return;
    const data = JSON.parse(qs('#contract-data').textContent || '{}');
    const scene = host.dataset.scene;
    let base = Number(host.dataset.base), dirty = false, loaded = false, working = false;
    let previewSeq = 0, previewTimer, sample = null, pendingRenames = {};
    const state = qs('#contract-state'), saveButton = qs('[data-action="save-contract"]');
    const archived = host.dataset.archived === '1';
    const markDirty = () => {
      dirty = true;
      schedulePreviews();
      state.textContent = messages.contract_unsaved;
      saveButton.disabled = !loaded || archived || working;
      qs('#contract-next').hidden = true;
    };
    host.addEventListener('input', markDirty);
    host.addEventListener('change', markDirty);
    // 同一頁的腳本區存了新版本：接著用那個版本當基準（腳本區只換掉步驟、斷言，入參與出參不變）
    document.addEventListener('scene-revision', event => {
      if (event.detail.source === 'contract') return;
      base = event.detail.number;
      host.dataset.base = base;
      if (!dirty) state.textContent = fill(messages.contract_based_on, {number: base});
      schedulePreviews();
    });
    window.addEventListener('beforeunload', event => {
      if (dirty) { event.preventDefault(); event.returnValue = ''; }
    });
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
    const mergedRenames = rows => {
      const next = {...pendingRenames};
      rows.forEach(item => {
        if (!item.previous || item.previous === item.name) return;
        const origins = Object.entries(pendingRenames).filter(([, target]) => target === item.previous).map(([origin]) => origin);
        (origins.length ? origins : [item.previous]).forEach(origin => { next[origin] = item.name; });
      });
      return Object.fromEntries(Object.entries(next).filter(([origin, target]) => origin !== target));
    };
    const showView = async (editor, next) => {
      if (!loaded || working || editor.inert || view(editor) === next) return;
      editor.inert = true;
      const kind = editor.dataset.kind;
      const area = qs('[name="yaml"]', editor);
      qs('.form-issues', editor).hidden = true;
      // 表格 → YAML：由伺服器產生和存檔一樣的寫法；YAML → 表格：先校驗，再用結果重建表格
      const result = next === 'yaml'
        ? await api('POST', '/api/contract/render', {key: kind, items: items(editor)})
        : await api('POST', '/api/scenes/' + path(scene) + '/contract-yaml/preview', await payload());
      editor.inert = false;
      if (!result.ok) return issues(editor, result);
      if (next === 'yaml') {
        if (kind === 'inputs') pendingRenames = mergedRenames(items(editor));
        area.value = result.data.text;
      }
      else fillRows(editor, result.data[kind]);
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
        if (!button || working || archived) return;
        const row = button.closest('tr.edit-row');
        const action = button.dataset.action;
        if (['remove-row', 'move-up', 'move-down', 'add-row'].includes(action)) markDirty();
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
        }
      });
    });
    const payload = async (silent = false) => {
      const value = {baseRevision: base, note: qs('[name="contract-note"]').value.trim() || null, renames: {...pendingRenames}};
      for (const editor of qsa('.contract-editor', host)) {
        const kind = editor.dataset.kind;
        if (view(editor) === 'yaml') value[kind] = qs('[name="yaml"]', editor).value;
        else {
          const rows = items(editor);
          const rendered = await api('POST', '/api/contract/render', {key: kind, items: rows});
          if (!rendered.ok) { if (!silent) issues(editor, rendered); return null; }
          value[kind] = rendered.data.text;
          if (kind === 'inputs') value.renames = mergedRenames(rows);
        }
      }
      return value;
    };
    const showErrors = result => {
      const list = qs('#contract-issues');
      const found = result.data?.error?.issues || [];
      list.innerHTML = '<li>' + esc(errorMessage(result)) + '</li>' + found.map((item, index) =>
        '<li><button type="button" class="text-btn" data-contract-issue="' + index + '">' + esc((item.section || '') + (item.sectionLine ? ':' + item.sectionLine : '') + ' ' + (item.message || item.text || '')) + '</button></li>').join('');
      list.hidden = false;
      qsa('[data-contract-issue]', list).forEach(button => {
        const item = found[Number(button.dataset.contractIssue)];
        button.disabled = !item.section || !item.sectionLine;
        button.addEventListener('click', async () => {
          const editor = qs('#contract-' + item.section);
          await showView(editor, 'yaml');
          selectLine(qs('[name="yaml"]', editor), item.sectionLine);
        });
      });
    };
    const loadWorkspace = async () => {
      const result = await api('GET', '/api/scenes/' + path(scene) + '/contract-workspace?revision=' + base);
      if (!result.ok) { showErrors(result); return false; }
      qsa('.contract-editor', host).forEach(editor => {
        qs('[name="yaml"]', editor).value = result.data.yaml[editor.dataset.kind];
        qsa('input, textarea, select, button', editor).forEach(field => { field.disabled = archived; });
      });
      sample = result.data.sample;
      loaded = true;
      return true;
    };
    const setPreview = (name, value, source, error = false) => {
      const tile = qs('#contract-preview-' + name);
      tile.setAttribute('aria-busy', 'false');
      tile.dataset.error = String(error);
      qs('[data-preview-source]', tile).textContent = source;
      qs('[data-preview-value]', tile).textContent = value === null ? '' : JSON.stringify(value, null, 2);
    };
    const showSample = () => {
      let source = sample
        ? fill(messages.contract_sample_source, {number: base, run: sample.runId})
        : fill(messages.contract_sample_empty, {number: base});
      if (dirty) source += ' ' + messages.contract_sample_draft;
      setPreview('sample', sample?.values || {}, source);
    };
    const refreshPreviews = async seq => {
      if (!loaded || working || seq !== previewSeq) return;
      // 唯讀預覽不彈出儲存錯誤；無效草稿清掉舊結果，避免誤認為目前內容。
      const value = await payload(true);
      if (seq !== previewSeq) return;
      const result = value && await api('POST', '/api/scenes/' + path(scene) + '/contract-yaml/preview', value);
      if (seq !== previewSeq) return;
      if (!result?.ok) {
        ['defaults', 'mapping'].forEach(name => setPreview(name, null, messages.contract_preview_invalid, true));
        return;
      }
      let source = messages.contract_preview_draft;
      const required = result.data.inputs.filter(([, spec]) => spec.default === undefined || spec.default === null).map(([name]) => name);
      if (required.length) source += ' ' + fill(messages.contract_required, {names: required.join(', ')});
      setPreview('defaults', Object.fromEntries(result.data.inputs.filter(([, spec]) => spec.default !== undefined && spec.default !== null).map(([name, spec]) => [name, spec.default])), source);
      setPreview('mapping', Object.fromEntries(result.data.outputs.map(([name, spec]) => [name, spec.from || messages.contract_script_output])), messages.contract_preview_draft);
    };
    const schedulePreviews = () => {
      const seq = ++previewSeq;
      clearTimeout(previewTimer);
      if (!loaded || working) return;
      showSample();
      ['defaults', 'mapping'].forEach(name => {
        const tile = qs('#contract-preview-' + name);
        tile.setAttribute('aria-busy', 'true');
        tile.dataset.error = 'false';
        qs('[data-preview-source]', tile).textContent = messages.working;
      });
      previewTimer = setTimeout(() => refreshPreviews(seq), 300);
    };
    saveButton.addEventListener('click', async () => {
      if (!loaded || !dirty || archived || working) return;
      working = true;
      host.inert = true;
      previewSeq += 1;
      busy(saveButton, true);
      qs('#contract-issues').hidden = true;
      try {
        const value = await payload();
        if (!value) return;
        const result = await api('PUT', '/api/scenes/' + path(scene) + '/contract-yaml', value);
        if (!result.ok) return showErrors(result);
        base = result.data.number;
        host.dataset.base = base;
        pendingRenames = {};
        dirty = false;
        // 儲存後原地更新原文與版本，不跳走、不保留舊表格覆寫新版本。
        await loadWorkspace();
        for (const editor of qsa('.contract-editor', host)) {
          qsa('[data-view]', editor).forEach(tab => {
            const active = tab.dataset.view === 'yaml';
            tab.classList.toggle('active', active); tab.setAttribute('aria-selected', String(active));
          });
          qsa('[data-view-panel]', editor).forEach(panel => { panel.hidden = panel.dataset.viewPanel !== 'yaml'; });
        }
        state.textContent = messages.contract_saved + ' · v' + base;
        qs('#contract-next span').textContent = fill(messages.contract_saved_next, {number: base});
        qs('[data-validate-contract]').href = '/scenes/' + path(scene) + '/run?purpose=validation&revision=' + base;
        qs('#contract-next').hidden = false;
        document.dispatchEvent(new CustomEvent('scene-revision', {detail: {number: base, source: 'contract'}}));
        await refreshSceneSummary(scene);
      } finally {
        working = false; host.inert = false; busy(saveButton, false);
        saveButton.disabled = !dirty || archived;
        schedulePreviews();
      }
    });
    loadWorkspace().then(ok => {
      if (!ok) {
        ['defaults', 'sample', 'mapping'].forEach(name => setPreview(name, null, messages.contract_preview_invalid, true));
        return;
      }
      schedulePreviews();
      // 捲動交給 bindSceneAnchors（這裡再捲會把編輯區移到畫面中間）：只把游標放進原文，
      // 再請它依載入後的版面重新對齊
      const kind = location.hash.slice(1).replace('contract-', '');
      if (['inputs', 'outputs'].includes(kind)) qs('#contract-' + kind + ' [name="yaml"]').focus({preventScroll: true});
      document.dispatchEvent(new Event('scene-layout'));
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

  function workflowIssues(problems, definition, workflowId, locate = false) {
    const text = pageText();
    return problems.map((item, index) => {
      const node = definition.nodes.find(node => node.id === item.node);
      const context = item.node ? fill(text.problem_context, {node: item.node, scene: node?.sceneId || '—'}) + (item.input ? ' · ' + item.input : '') : '';
      const href = '/playground/' + path(workflowId) + (item.node ? '?node=' + path(item.node) + (item.input ? '&input=' + path(item.input) : '') : '#workflow-problems');
      const action = locate
        ? (node ? '<button class="text-btn" data-locate-problem="' + index + '">' + esc(text.locate_problem) + '</button>' : '')
        : '<a class="text-btn" href="' + esc(href) + '">' + esc(text.open_problem) + '</a>';
      return '<li>' + (context ? '<strong>' + esc(context) + '</strong>' : '') + '<span>' + esc(item.message) + '</span> ' + action + '</li>';
    }).join('');
  }

  function bindIssueLocations(container, problems, locate) {
    if (!locate) return;
    qsa('[data-locate-problem]', container).forEach(button => button.addEventListener('click', () => {
      if (container.closest('#dialog')) $('#dialog').close();
      locate(problems[Number(button.dataset.locateProblem)]);
    }));
  }

  function showWorkflowIssues(workflow, locate) {
    modal(pageText().fix_problems, '<ul class="workflow-issue-list">' + workflowIssues(workflow.problems, workflow.definition, workflow.id, !!locate) + '</ul>', null);
    bindIssueLocations(qs('#dialog-content'), workflow.problems, locate);
  }

  // 卡片與畫布共用同一份執行設定及 API；伺服器仍負責最後檢查。
  function openWorkflowRun(workflow, locate, onProblems, onStarted) {
    const text = pageText(), key = newKey();
    modal(fill(text.run_named, {name: workflow.name}), qs('#workflow-run-form').innerHTML, {label: text.run_action, run: async () => {
      const dialog = qs('#dialog-content');
      const engine = qs('[name="engine"]', dialog).value || null;
      const headless = (qs('[name="headless"]:checked', dialog) || {value: '1'}).value === '1';
      const target = chosenTarget(dialog);
      // 驗證最新版本，或執行發布的版本（M11 PR 2）
      const purpose = (qs('[name="purpose"]:checked', dialog) || {value: 'validation'}).value;
      busy($('#dialog-action'), true);
      const result = await api('POST', '/api/workflows/' + path(workflow.id) + '/runs', {engine, headless, target, purpose, idempotencyKey: key});
      busy($('#dialog-action'), false);
      if (!result.ok) {
        qs('.form-error', dialog).textContent = errorMessage(result);
        const problems = result.data?.error?.problems || [];
        const list = qs('.form-issues', dialog);
        list.classList.add('workflow-issue-list');
        list.innerHTML = workflowIssues(problems, workflow.definition, workflow.id, !!locate);
        list.hidden = problems.length === 0;
        bindIssueLocations(dialog, problems, locate);
        if (problems.length && onProblems) onProblems(problems);
        return;
      }
      if (onStarted) { $('#dialog').close(); onStarted(result.data); }
      else location.href = '/playground/runs/' + path(result.data.id);
    }});
    const dialog = qs('#dialog-content');
    bindTargetChoice(dialog);
    const execution = qs('[name="purpose"][value="execution"]', dialog);
    if (execution) {
      if (workflow.publishedRevision) execution.checked = true;
      else {
        execution.disabled = true;
        const hint = qs('[data-purpose-hint]', dialog);
        hint.textContent = hint.dataset.unpublished;
      }
    }
  }

  // 發布組合場景的版本（M11 PR 2）：和場景相同的確認對話框，發布後重新載入頁面
  function bindCompositePublish() {
    qsa('[data-action="publish-composite"]').forEach(button => {
      button.addEventListener('click', () => {
        const number = button.dataset.revision;
        confirmDialog(messages.publish_title + ' v' + number, messages.publish_body, messages.publish_action, async () => {
          const url = '/api/workflows/' + path(button.dataset.workflow) + '/revisions/' + path(number) + '/publish';
          const result = await api('POST', url);
          $('#dialog').close();
          if (!result.ok) return toast([errorMessage(result), ...problemLines(result)].join('\n'));
          flash(messages.published);
          location.reload();
        });
      });
    });
  }

  // 組合場景的代號、領域、封存，以及驗證指定的版本（M11 收尾）
  function bindCompositeSettings() {
    const form = qs('form[data-action="composite-settings"]');
    if (form) {
      form.addEventListener('submit', async event => {
        event.preventDefault();
        const body = {
          code: form.elements.namedItem('code').value.trim(),
          domainId: form.elements.namedItem('domainId').value,
          archived: form.elements.namedItem('archived').checked,
          projectId: form.elements.namedItem('projectId').value,
        };
        const result = await api('PATCH', '/api/workflows/' + path(form.dataset.workflow), body);
        if (!result.ok) {
          qs('.form-error', form).textContent = errorMessage(result);
          return;
        }
        flash(messages.saved);
        location.reload();
      });
    }
    qsa('[data-action="validate-composite"]').forEach(button => {
      button.addEventListener('click', () => {
        const number = button.dataset.revision;
        confirmDialog(fill(messages.composite_validate_title, {number}), messages.composite_validate_body, messages.composite_validate_action, async () => {
          const url = '/api/workflows/' + path(button.dataset.workflow) + '/runs';
          const result = await api('POST', url, {purpose: 'validation', revision: Number(number), idempotencyKey: newKey()});
          $('#dialog').close();
          if (!result.ok) return toast([errorMessage(result), ...problemLines(result)].join('\n'));
          location.href = '/playground/runs/' + path(result.data.id);
        });
      });
    });
  }

  function bindPlayground() {
    if (!qs('#playground')) return;
    const text = pageText();
    qs('[data-action="create-workflow"]').addEventListener('click', () => {
      const dialog = workflowDialog(text.create_title, null, text.create_action, async () => {
        const value = name => qs('[name="' + name + '"]', dialog).value.trim();
        const result = await api('POST', '/api/workflows', {name: value('name'), description: value('description') || null, code: value('code') || null, domainId: value('domainId') || null, projectId: value('projectId') || null});
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
          projectId: qs('[name="projectId"]', dialog).value || null,
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
    qsa('[data-action="run-composite"]').forEach(button => {
      button.addEventListener('click', async () => {
        busy(button, true);
        const result = await api('GET', '/api/workflows/' + path(button.dataset.workflow));
        busy(button, false);
        if (!result.ok) return toast(errorMessage(result));
        if (result.data.problems.length) return showWorkflowIssues(result.data);
        openWorkflowRun(result.data);
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

  // DAG 畫布：座標只影響顯示，連線與資料來源決定執行依賴。
  function bindWorkflowEditor() {
    const root = qs('#workflow');
    if (!root) return;
    const text = pageText();
    const data = JSON.parse(qs('#workflow-data').textContent);
    const library = new Map(data.library.map(scene => [scene.id, scene]));
    const definition = JSON.parse(JSON.stringify(data.definition));
    const legacy = definition.mode === 'serial';
    if (legacy) {
      definition.edges = definition.nodes.slice(1).map((node, i) => ({source: definition.nodes[i].id, target: node.id}));
      definition.version = 2;
      definition.mode = 'dag';
    }
    definition.edges ||= [];
    definition.nodes.forEach((node, i) => { node.position ||= {x: 40 + (i % 3) * 280, y: 40 + Math.floor(i / 3) * 160}; });
    let zoom = 1, picked = null, dragging = false, editVersion = 0, saving = false;
    let selectedSource = null, parameterPicked = null;
    const wirePending = new Set();
    let version = data.version;
    let selected = definition.nodes.length ? 0 : -1;
    let problems = data.problems;
    let dirty = false;
    let checkTimer = null;
    let checkSeq = 0;
    let heldPointer = null, libraryDragging = false, deferredCheck = null;
    const saveButton = qs('[data-action="workflow-save"]');
    const json = value => JSON.stringify(value);
    const hasDefault = spec => spec.default !== undefined && spec.default !== null;
    const compatible = (output, input) => output === input || (output === 'integer' && input === 'number');

    const sceneOf = node => node ? library.get(node.sceneId) || null : null;
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

    function allEdges() {
      const edges = new Map(definition.edges.map(edge => [edge.source + ':' + edge.target, edge]));
      definition.nodes.forEach(node => Object.values(node.inputs).forEach(binding => {
        if (binding.node) edges.set(binding.node + ':' + node.id, {source: binding.node, target: node.id});
      }));
      return [...edges.values()];
    }

    function canConnect(source, target) {
      if (source === target) return false;
      const edges = allEdges();
      const seen = new Set();
      const reaches = id => {
        if (id === source) return true;
        if (seen.has(id)) return false;
        seen.add(id);
        return edges.filter(edge => edge.source === id).some(edge => reaches(edge.target));
      };
      return !reaches(target);
    }

    function connect(source, target) {
      if (!source || !target || !canConnect(source, target)) { toast(text.cycle); return false; }
      if (!definition.edges.some(edge => edge.source === source && edge.target === target)) definition.edges.push({source, target});
      selected = definition.nodes.findIndex(node => node.id === target);
      selectedSource = source;
      picked = null;
      qs('#canvas-hint').textContent = text.canvas_hint;
      changed();
      return true;
    }

    function resetInputs(node) {
      node.inputs = Object.fromEntries((revisionOf(node)?.inputs || []).map(([name]) => [name, {auto: true}]));
    }

    function autoSource(node, name, spec) {
      return definition.nodes.filter(upstream => allEdges().some(edge => edge.source === upstream.id && edge.target === node.id))
        .filter(upstream => (revisionOf(upstream)?.outputs || []).some(([key, out]) => key === name && compatible(out.type, spec.type)));
    }

    // 檔案值給人看的寫法：網頁看到的檔名，或附件、路徑
    function fileText(value) {
      const items = Array.isArray(value) ? value : [value];
      return items.map(item => {
        if (typeof item === 'string') return item;
        if (item && typeof item === 'object') return item.name || item.attachment || item.path || item.file || json(item);
        return json(item);
      }).join(messages.list_separator);
    }

    function bindingText(node, name, spec) {
      const binding = node.inputs[name];
      if (binding?.auto) {
        const sources = autoSource(node, name, spec);
        if (sources.length > 1) return fill(text.auto_ambiguous, {name});
        if (sources.length === 1) return fill(text.binding_output, {name, node: sources[0].id, output: name});
        return fill(hasDefault(spec) ? text.binding_default : text.binding_missing, {name, value: json(spec.default)});
      }
      if (binding && 'value' in binding) return fill(text.binding_value, {name, value: spec.type === 'file' ? fileText(binding.value) : json(binding.value)});
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
        '<button type="button" class="library-item" draggable="true" title="' + esc(text.library_hint) + '" data-add="' + esc(scene.id) + '"><strong>' + esc(scene.id) + '</strong>' +
        '<span>' + esc(scene.name) + '</span><small>' + esc(fill(text.add, {number: scene.publishedRevision || scene.revisions[0].number})) + '</small></button>').join('')).join('');
    }

    function scale() {
      const stage = qs('#flow-stage');
      const width = Math.max(800, ...definition.nodes.map(node => node.position.x + 260));
      const height = Math.max(400, ...definition.nodes.map(node => node.position.y + 160));
      stage.style.width = width + 'px'; stage.style.height = height + 'px';
      stage.style.transform = 'scale(' + zoom + ')';
      qs('#canvas-spacer').style.width = width * zoom + 'px';
      qs('#canvas-spacer').style.height = height * zoom + 'px';
      qs('#canvas-scale').textContent = Math.round(zoom * 100) + '%';
    }

    function drawEdges() {
      const stage = qs('#flow-stage');
      const nodes = new Map(definition.nodes.map(node => [node.id, node]));
      qsa('[data-edge-line]', stage).forEach(line => {
        const a = nodes.get(line.dataset.source), b = nodes.get(line.dataset.target);
        if (!a || !b) return;
        const x = a.position.x + 200, y = a.position.y + 48, xx = b.position.x, yy = b.position.y + 48;
        const bend = Math.max(50, Math.abs(xx - x) / 2);
        line.setAttribute('d', `M ${x} ${y} C ${x + bend} ${y}, ${xx - bend} ${yy}, ${xx} ${yy}`);
      });
    }

    function renderBoard() {
      if (dragging) return;
      const stage = qs('#flow-stage');
      const edges = allEdges().map(edge => {
        const attrs = ' data-edge-line data-source="' + esc(edge.source) + '" data-target="' + esc(edge.target) + '"';
        return '<path class="dag-edge' + (edge.source === selectedSource && edge.target === definition.nodes[selected]?.id ? ' is-selected' : '') + '"' + attrs + ' marker-end="url(#dag-arrow)"/>' +
          '<path class="dag-edge-hit"' + attrs + ' data-edge tabindex="0" role="button" aria-label="' + esc(fill(text.edge_label, edge)) + '"/>';
      }).join('');
      stage.innerHTML = '<svg class="dag-links"><defs><marker id="dag-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M 0 0 L 10 5 L 0 10 z" fill="currentColor"/></marker></defs>' + edges + '</svg>' +
        (!definition.nodes.length ? '<div class="empty">' + esc(text.board_empty) + '</div>' : '') +
        definition.nodes.map((node, index) => {
          const revision = revisionOf(node), scene = sceneOf(node);
          const title = revision ? revision.name : (scene ? scene.name : node.sceneId);
          const count = problems.filter(item => item.node === node.id).length;
          return '<div class="flow-node' + (index === selected ? ' selected' : '') + (count ? ' has-problems' : '') + '" data-index="' + index + '" data-node="' + esc(node.id) + '" role="button" tabindex="0" aria-pressed="' + (index === selected) + '" style="left:' + node.position.x + 'px;top:' + node.position.y + 'px">' +
            '<span class="flow-node-head"><span class="tag mono">' + esc(node.sceneId) + '</span> <span class="muted">v' + node.revision + '</span></span>' +
            '<strong title="' + esc(title) + '">' + esc(title) + '</strong><small>' + esc(node.id) + (count ? ' · ' + esc(fill(text.problem_count, {count})) : '') + '</small>' +
            '<button class="dag-port in" data-in="' + esc(node.id) + '" aria-label="' + esc(fill(text.connect_to, {node: node.id})) + '"></button>' +
            '<button class="dag-port out" data-out="' + esc(node.id) + '" aria-label="' + esc(fill(text.connect_from, {node: node.id})) + '"></button></div>';
        }).join('');
      scale(); drawEdges();
    }

    function sourceOf(node, name, spec) {
      const binding = node.inputs[name];
      if (!binding) return hasDefault(spec) ? 'default' : '';
      return binding.auto ? 'auto' : 'value' in binding ? 'value' : 'out:' + binding.node + ':' + binding.output;
    }

    function valueField(name, spec, binding) {
      const current = binding && 'value' in binding ? binding.value : '';
      const attrs = ' data-value="' + esc(name) + '" aria-label="' + esc(fill(text.value_label, {name})) + '"';
      if (spec.type === 'file') {
        // 檔案入參（M7c）的固定值：選檔上傳到伺服器，或寫這個場景版本的附件 files/檔名
        const accept = Array.isArray(spec.accept) ? ' accept="' + esc(spec.accept.join(',')) + '"' : '';
        return '<label class="button">' + esc(spec.multiple ? text.file_choose_multiple : text.file_choose) +
          '<input class="visually-hidden" type="file" data-node-file="' + esc(name) + '"' + (spec.multiple ? ' multiple' : '') + accept + '></label>' +
          '<input type="text"' + attrs + ' placeholder="files/…" value="' + esc(typeof current === 'string' ? current : '') + '">';
      }
      if (spec.type === 'boolean') {
        const values = [true, false];
        return '<select' + attrs + '>' + values.map((value, index) =>
          '<option value="' + index + '"' + (json(value) === json(current) ? ' selected' : '') + '>' + esc(json(value)) + '</option>').join('') + '</select>';
      }
      if (spec.type === 'array' || spec.type === 'object') {
        const shown = current === '' ? '' : typeof current === 'string' ? current : JSON.stringify(current);
        return '<input type="text" class="mono"' + attrs + ' placeholder="' + (spec.type === 'array' ? '[…]' : '{…}') +
          '" value="' + esc(shown) + '">';
      }
      // 數字與枚舉也能填動態值；普通數字在 input 事件中按契約轉型。
      const listId = 'fixed-options-' + name;
      const options = Array.isArray(spec.enum) ? '<datalist id="' + esc(listId) + '">' +
        spec.enum.map(value => '<option value="' + esc(String(value)) + '"></option>').join('') + '</datalist>' : '';
      return '<input type="text"' + attrs + (options ? ' list="' + esc(listId) + '"' : '') +
        ' value="' + esc(current === '' ? '' : String(current)) + '">' + options;
    }

    function inputRow(node, name, spec) {
      const binding = node.inputs[name], current = sourceOf(node, name, spec);
      const mode = current.startsWith('out:') ? 'wire' : current || 'default';
      const choosingWire = mode === 'wire' || wirePending.has(node.id + ':' + name);
      const option = (value, label, disabled = false) => '<option value="' + esc(value) + '"' + (value === current ? ' selected' : '') + (disabled ? ' disabled' : '') + '>' + esc(label) + '</option>';
      let options = '<option value="">' + esc(text.pick_output) + '</option>', found = !current.startsWith('out:');
      definition.nodes.filter(upstream => canConnect(upstream.id, node.id)).forEach(upstream => {
        (revisionOf(upstream)?.outputs || []).forEach(([output, outSpec]) => {
          const value = 'out:' + upstream.id + ':' + output;
          found ||= value === current;
          options += option(value, fill(text.source_output, {node: upstream.id, scene: upstream.sceneId, output, type: outSpec.type}), !compatible(outSpec.type, spec.type));
        });
      });
      if (!found) options += option(current, fill(text.source_broken, {node: binding.node, output: binding.output}));
      const required = hasDefault(spec) ? '' : ' <span class="required-mark" title="' + esc(text.required) + '">*</span>';
      return '<div class="input-source" data-input="' + esc(name) + '">' +
        '<div class="input-name"><button type="button" class="parameter-port in" data-input-port="' + esc(name) + '" aria-label="' + esc(fill(text.bind_input, {name})) + '"></button><code>' + esc(name) + '</code>' + required + '<span class="cell-sub">' + esc(spec.type) + (spec.description ? ' · ' + esc(spec.description) : '') + '</span></div>' +
        '<div class="binding-method"><div class="binding-modes" role="group" aria-label="' + esc(fill(text.field_source, {name})) + '">' +
        ['auto', 'default', 'value', 'wire'].map(key => '<button type="button" data-mode="' + key + '" data-name="' + esc(name) + '" aria-pressed="' + (mode === key) + '"' + (mode === key ? ' class="active"' : '') + '>' + esc(text['mode_' + key]) + '</button>').join('') + '</div>' +
        (choosingWire ? '<select data-source="' + esc(name) + '" aria-label="' + esc(fill(text.field_source, {name})) + '">' + options + '</select>' : '') + '</div>' +
        '<div class="binding-value">' + (current === 'value' ? valueField(name, spec, binding) : '') + '<span class="binding-summary">' + esc(bindingText(node, name, spec)) + '</span>' + (binding?.node && binding.node !== selectedSource ? '<button class="text-btn" data-view-source="' + esc(binding.node) + '">' + esc(text.show_source) + '</button>' : '') + '</div></div>';
    }

    function renderParameters(node) {
      parameterPicked = null;
      qs('#parameter-hint').textContent = text.parameter_hint;
      const sources = node ? definition.nodes.filter(upstream => allEdges().some(edge => edge.source === upstream.id && edge.target === node.id)) : [];
      if (!sources.some(upstream => upstream.id === selectedSource)) selectedSource = sources[0]?.id || null;
      const upstream = sources.find(item => item.id === selectedSource);
      qs('#parameter-node').textContent = node ? (upstream ? upstream.id + ' · ' + upstream.sceneId + ' → ' : '') + node.id + ' · ' + node.sceneId : '';
      const contractButton = (item, kind) => '<button type="button" class="text-btn" data-inspect-contract="' + kind + '" data-inspect-node="' + esc(item.id) + '">' + esc(text['inspect_' + kind]) + ' v' + item.revision + '</button>';
      qs('#parameter-source').innerHTML = upstream ? '<label class="source-picker">' + esc(text.outputs) + '<select data-parameter-source aria-label="' + esc(text.parameter_source) + '">' + sources.map(item => '<option value="' + esc(item.id) + '"' + (item.id === selectedSource ? ' selected' : '') + '>' + esc(item.id + ' · ' + item.sceneId) + '</option>').join('') + '</select></label>' + contractButton(upstream, 'outputs') : esc(text.outputs);
      qs('#parameter-target').innerHTML = node ? esc(node.id + ' · ' + text.inputs) + ' ' + contractButton(node, 'inputs') : esc(text.inputs);
      const outputs = upstream ? revisionOf(upstream)?.outputs || [] : [];
      qs('#node-outputs').innerHTML = outputs.length ? outputs.map(([name, spec]) => '<div class="parameter-output"><div><code>' + esc(name) + '</code><button type="button" class="parameter-port out" data-output-port="' + esc(name) + '" aria-label="' + esc(fill(text.bind_output, {name})) + '"></button></div><span class="cell-sub">' + esc(spec.type) + (spec.description ? ' · ' + esc(spec.description) : '') + '</span></div>').join('') : '<p class="muted parameter-empty">' + esc(upstream ? text.no_outputs : text.no_upstream) + '</p>';
      requestAnimationFrame(drawParameterWires);
    }

    function drawParameterWires(pointer) {
      const grid = qs('#parameter-grid'), svg = qs('#parameter-wires'), node = definition.nodes[selected];
      if (!node) { svg.innerHTML = ''; return; }
      const bounds = grid.getBoundingClientRect();
      const point = el => { const rect = el.getBoundingClientRect(); return {x: rect.left + rect.width / 2 - bounds.left, y: rect.top + rect.height / 2 - bounds.top}; };
      const curve = (a, b, extra = '') => '<path ' + extra + ' d="M ' + a.x + ' ' + a.y + ' C ' + (a.x + 32) + ' ' + a.y + ', ' + (b.x - 32) + ' ' + b.y + ', ' + b.x + ' ' + b.y + '"/>';
      const outputPort = name => qsa('[data-output-port]').find(el => el.dataset.outputPort === name);
      let html = '';
      (revisionOf(node)?.inputs || []).forEach(([name, spec]) => {
        const binding = node.inputs[name];
        const sources = binding?.auto ? autoSource(node, name, spec) : [];
        const from = binding?.node || (sources.length === 1 ? sources[0].id : null);
        if (from !== selectedSource) return;
        const out = outputPort(binding?.output || name), input = qsa('[data-input-port]').find(el => el.dataset.inputPort === name);
        if (out && input) html += curve(point(out), point(input), 'data-parameter-wire="' + esc(name) + '"');
      });
      if (parameterPicked && pointer) {
        const out = outputPort(parameterPicked);
        if (out) html += curve(point(out), {x: pointer.x - bounds.left, y: pointer.y - bounds.top}, 'class="is-pending"');
      }
      svg.setAttribute('width', grid.scrollWidth); svg.setAttribute('height', grid.clientHeight); svg.innerHTML = html;
    }

    function bindParameter(output, input) {
      const node = definition.nodes[selected], upstream = definition.nodes.find(item => item.id === selectedSource);
      const outSpec = new Map(revisionOf(upstream)?.outputs || []).get(output);
      const inSpec = new Map(revisionOf(node)?.inputs || []).get(input);
      if (!outSpec || !inSpec || !compatible(outSpec.type, inSpec.type)) { toast(text.incompatible); return; }
      if (!canConnect(upstream.id, node.id)) { toast(text.cycle); return; }
      if (!definition.edges.some(edge => edge.source === upstream.id && edge.target === node.id)) definition.edges.push({source: upstream.id, target: node.id});
      node.inputs[input] = {node: upstream.id, output};
      wirePending.delete(node.id + ':' + input);
      changed();
    }

    function renderSettings() {
      const box = qs('#node-settings'), inputsBox = qs('#node-inputs');
      const node = definition.nodes[selected];
      renderParameters(node);
      if (!node) {
        box.innerHTML = '<p class="muted">' + esc(text.settings_empty) + '</p>';
        inputsBox.innerHTML = box.innerHTML;
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
      inputsBox.innerHTML = !revision ? '<p class="muted">' + esc(text.no_contract) + '</p>'
        : !revision.inputs.length ? '<p class="muted">' + esc(text.no_inputs) + '</p>'
        : revision.inputs.map(([name, spec]) => inputRow(node, name, spec)).join('');
      if (revision) {
        html += '<h3 class="section-title">' + esc(text.outputs) + '</h3>';
        html += revision.outputs.length
          ? '<ul class="io-list">' + revision.outputs.map(([name, spec]) => '<li><code>' + esc(name) + '</code> <span class="muted">' + esc(spec.type) + '</span></li>').join('') + '</ul>'
          : '<p class="muted">' + esc(text.no_outputs) + '</p>';
      }
      const candidates = definition.nodes.filter(upstream => canConnect(upstream.id, node.id) && !allEdges().some(edge => edge.source === upstream.id && edge.target === node.id));
      html += '<h3 class="section-title">' + esc(text.dependencies) + '</h3><label class="field">' + esc(text.connect_source) + '<select data-connect-source>' + candidates.map(upstream => '<option value="' + esc(upstream.id) + '">' + esc(upstream.id + ' · ' + upstream.sceneId) + '</option>').join('') + '</select></label>' +
        '<button class="button" data-connect' + (!candidates.length ? ' disabled' : '') + '>' + esc(text.connect) + '</button>';
      html += allEdges().filter(edge => edge.target === node.id).map(edge => '<div class="edge-row"><code>' + esc(edge.source) + ' → ' + esc(edge.target) + '</code><button class="text-btn" data-unlink="' + esc(edge.source) + '">' + esc(text.unlink) + '</button></div>').join('');
      html += '<p class="cell-sub">' + esc(text.unlink_hint) + '</p><button type="button" class="button danger" data-remove>' + esc(text.remove) + '</button>';
      box.innerHTML = html + '</div>';
      renderFieldProblems();
    }

    function renderFieldProblems() {
      const node = definition.nodes[selected];
      qsa('#node-inputs [data-input]').forEach((row, index) => {
        const items = problems.filter(item => item.node === node?.id && item.input === row.dataset.input);
        row.classList.toggle('has-problems', items.length > 0);
        qs('.input-problems', row)?.remove();
        qsa('input, select, [data-mode]', row).forEach(field => {
          field.setAttribute('aria-invalid', String(items.length > 0));
          field.removeAttribute('aria-describedby');
          if (items.length) field.setAttribute('aria-describedby', 'input-problems-' + index);
        });
        if (items.length) {
          const hint = document.createElement('div');
          hint.id = 'input-problems-' + index;
          hint.className = 'input-problems';
          hint.textContent = items.map(item => item.message).join(messages.list_separator);
          row.appendChild(hint);
        }
      });
    }

    function focusProblem(item) {
      selected = definition.nodes.findIndex(node => node.id === item.node);
      if (selected < 0) return;
      render();
      const card = qsa('[data-node]', qs('#flow-stage')).find(el => el.dataset.node === item.node);
      card?.scrollIntoView({block: 'nearest', inline: 'nearest'});
      const row = qsa('#node-inputs [data-input]').find(el => el.dataset.input === item.input);
      const field = row && qs('[data-mode].active', row);
      (row || card)?.scrollIntoView({block: 'nearest', inline: 'nearest'});
      (field || card)?.focus({preventScroll: true});
    }

    function renderProblems() {
      const panel = qs('#workflow-problems');
      qs('.count', panel).textContent = problems.length;
      qs('ul', panel).innerHTML = workflowIssues(problems, definition, data.id, true);
      bindIssueLocations(panel, problems, focusProblem);
      renderFieldProblems();
      panel.hidden = problems.length === 0;
    }

    function render({settings = true} = {}) {
      if (settings) renderSettings();
      else {
        const node = definition.nodes[selected];
        if (node) qsa('#node-inputs [data-input]').forEach(row => {
          const name = row.dataset.input, spec = new Map(revisionOf(node)?.inputs || []).get(name);
          if (spec) qs('.binding-summary', row).textContent = bindingText(node, name, spec);
        });
      }
      renderBoard();
      renderProblems();
      requestAnimationFrame(drawParameterWires);
      rememberCanvas();
      saveButton.disabled = !dirty || saving;
      saveButton.title = dirty ? text.unsaved : '';
      qs('#workflow-save-state').textContent = saving ? text.saving : dirty ? text.unsaved : text.saved;
      qs('#parameter-save-state').textContent = qs('#workflow-save-state').textContent;
    }

    // 校驗回覆不能在拖曳途中收起問題列、移動畫布或替換節點。
    function applyCheck(sequence, result) {
      if (sequence !== checkSeq) return;
      if (heldPointer !== null || libraryDragging) { deferredCheck = {sequence, result}; return; }
      if (!result.ok) {
        qs('#workflow-save-state').textContent = fill(text.check_failed, {reason: errorMessage(result)});
        return;
      }
      problems = result.data.problems;
      render({settings: false});
    }
    function finishGesture() {
      // 等 pointerup／drop 的既有處理完成；若有新修改，checkSeq 會淘汰舊回覆。
      setTimeout(() => {
        if (heldPointer !== null || libraryDragging || !deferredCheck) return;
        const {sequence, result} = deferredCheck;
        deferredCheck = null;
        applyCheck(sequence, result);
      }, 0);
    }
    document.addEventListener('pointerdown', event => {
      if (event.button === 0 && event.target.closest('#library-list, #flow-stage, .flow-parameters')) heldPointer = event.pointerId;
    }, true);
    ['pointerup', 'pointercancel'].forEach(name => document.addEventListener(name, event => {
      if (heldPointer !== event.pointerId) return;
      heldPointer = null;
      finishGesture();
    }));
    window.addEventListener('blur', () => {
      heldPointer = null;
      libraryDragging = false;
      finishGesture();
    });
    qs('#library-list').addEventListener('dragstart', () => { libraryDragging = true; });
    qs('#library-list').addEventListener('dragend', () => {
      libraryDragging = false;
      heldPointer = null;
      finishGesture();
    });

    // 每次修改後（稍等一下）請伺服器檢查，問題列在上方與節點上
    function scheduleCheck() {
      clearTimeout(checkTimer);
      checkSeq += 1;
      deferredCheck = null;
      checkTimer = setTimeout(async () => {
        const sequence = ++checkSeq;
        const result = await api('POST', '/api/workflows/check', {definition});
        applyCheck(sequence, result);
      }, 300);
    }

    function changed(options) {
      dirty = true;
      editVersion += 1;
      render(options);
      scheduleCheck();
    }

    async function save() {
      if (saving) return false;
      saving = true;
      const savedEdit = editVersion;
      clearTimeout(checkTimer); checkSeq += 1;
      busy(saveButton, true);
      qs('#workflow-save-state').textContent = text.saving;
      const result = await api('PUT', '/api/workflows/' + path(data.id), {baseVersion: version, definition});
      busy(saveButton, false);
      saving = false;
      if (!result.ok) {
        saveButton.disabled = false;
        qs('#workflow-save-state').textContent = text.unsaved;
        if (result.status === 409) toast(text.stale);
        else toast(errorMessage(result));
        return false;
      }
      version = result.data.version;
      dirty = savedEdit !== editVersion;
      if (!dirty) problems = result.data.problems;
      else scheduleCheck();
      render({settings: false});
      toast(text.saved);
      return true;
    }

    function addNode(sceneId, position) {
      const scene = library.get(sceneId);
      if (!scene || scene.archived || !scene.revisions.length) return;
      const node = {id: newNodeId(), sceneId: scene.id, revision: scene.publishedRevision || scene.revisions[0].number, inputs: {}};
      resetInputs(node);
      node.position = position || {x: 40 + (definition.nodes.length % 3) * 280, y: 40 + Math.floor(definition.nodes.length / 3) * 160};
      definition.nodes.push(node);
      selected = definition.nodes.length - 1;
      changed();
    }
    qs('#library-search').addEventListener('input', renderLibrary);
    qs('#library-list').addEventListener('click', event => {
      const button = event.target.closest('[data-add]');
      if (button) addNode(button.dataset.add);
    });
    qs('#library-list').addEventListener('dragstart', event => {
      const button = event.target.closest('[data-add]');
      if (!button) return;
      event.dataTransfer.setData('application/x-rpa-scene', button.dataset.add);
      event.dataTransfer.effectAllowed = 'copy';
    });
    const stage = qs('#flow-stage'), viewport = qs('#canvas-viewport');
    viewport.addEventListener('dragover', event => {
      if (!event.dataTransfer.types.includes('application/x-rpa-scene')) return;
      event.preventDefault();
      event.dataTransfer.dropEffect = 'copy';
      viewport.classList.add('is-drop-target');
    });
    viewport.addEventListener('dragleave', event => {
      if (!viewport.contains(event.relatedTarget)) viewport.classList.remove('is-drop-target');
    });
    viewport.addEventListener('drop', event => {
      const sceneId = event.dataTransfer.getData('application/x-rpa-scene');
      if (!sceneId) return;
      event.preventDefault();
      viewport.classList.remove('is-drop-target');
      const bounds = stage.getBoundingClientRect();
      addNode(sceneId, {x: Math.max(0, Math.min(100000, (event.clientX - bounds.left) / zoom - 100)), y: Math.max(0, Math.min(100000, (event.clientY - bounds.top) / zoom - 48))});
    });
    qs('#library-list').addEventListener('dragend', () => viewport.classList.remove('is-drop-target'));
    function pick(target) {
      const edge = target.closest('[data-edge]');
      const card = target.closest('[data-index]');
      if (edge) { selected = definition.nodes.findIndex(node => node.id === edge.dataset.target); selectedSource = edge.dataset.source; }
      else if (card) selected = Number(card.dataset.index);
      else return;
      render();
    }
    stage.addEventListener('click', event => {
      const out = event.target.closest('[data-out]'), input = event.target.closest('[data-in]');
      if (out) { picked = out.dataset.out; qs('#canvas-hint').textContent = fill(text.pick_target, {node: picked}); }
      else if (input && picked) connect(picked, input.dataset.in);
      else pick(event.target);
    });
    stage.addEventListener('keydown', event => {
      if (event.key === 'Escape') { picked = null; qs('#canvas-hint').textContent = text.canvas_hint; }
      const card = event.target.closest('[data-index]');
      const delta = {ArrowLeft: [-10, 0], ArrowRight: [10, 0], ArrowUp: [0, -10], ArrowDown: [0, 10]}[event.key];
      if (card && delta && event.target === card) {
        event.preventDefault(); const node = definition.nodes[Number(card.dataset.index)];
        node.position.x = Math.max(0, Math.min(100000, node.position.x + delta[0]));
        node.position.y = Math.max(0, Math.min(100000, node.position.y + delta[1]));
        changed(); qs('[data-node="' + node.id + '"]', stage).focus();
      } else if ((event.key === 'Enter' || event.key === ' ') && !event.target.closest('button')) {
        event.preventDefault(); pick(event.target);
      }
    });
    stage.addEventListener('pointerdown', event => {
      if (event.button !== 0) return;
      const card = event.target.closest('[data-index]');
      if (!card || event.target.closest('button')) return;
      selected = Number(card.dataset.index); renderSettings();
      qsa('[data-index]', stage).forEach(el => { el.classList.toggle('selected', el === card); el.setAttribute('aria-pressed', String(el === card)); });
      const node = definition.nodes[selected], origin = {...node.position}, x = event.clientX, y = event.clientY;
      dragging = true; card.setPointerCapture(event.pointerId);
      let moved = false;
      card.onpointermove = ev => {
        if (Math.abs(ev.clientX - x) + Math.abs(ev.clientY - y) < 3 && !moved) return;
        moved = true;
        node.position.x = Math.max(0, Math.min(100000, origin.x + (ev.clientX - x) / zoom));
        node.position.y = Math.max(0, Math.min(100000, origin.y + (ev.clientY - y) / zoom));
        card.style.left = node.position.x + 'px'; card.style.top = node.position.y + 'px';
        drawEdges();
      };
      const end = () => { card.onpointermove = card.onpointerup = card.onpointercancel = null; dragging = false; if (moved) changed({settings: false}); };
      card.onpointerup = end; card.onpointercancel = end;
    });
    qsa('[data-zoom]').forEach(button => button.addEventListener('click', () => { zoom = Math.max(.2, Math.min(2, zoom + Number(button.dataset.zoom) * .1)); scale(); }));
    qs('[data-fit]').addEventListener('click', () => {
      const viewport = qs('#canvas-viewport');
      zoom = Math.max(.001, Math.min(1, viewport.clientWidth / parseFloat(stage.style.width), viewport.clientHeight / parseFloat(stage.style.height)));
      viewport.scrollTo(0, 0); scale();
    });
    qs('[data-reset-inputs]').addEventListener('click', () => { const node = definition.nodes[selected]; if (node) { resetInputs(node); changed(); } });

    // 節點固定值的檔案：一個一個傳到伺服器，全部成功才寫進定義（組合場景存檔後，這些檔案不會被清掉）
    async function uploadNodeFiles(node, name, spec, files) {
      const added = [];
      toast(messages.working);
      for (const file of files) {
        const result = await uploadFile(file, () => {});
        if (!result.ok) return toast(fill(messages.file_upload_failed, {name: file.name, error: errorMessage(result)}));
        const {file: id, name: shown, size, sha256} = result.data;
        added.push({file: id, name: shown, size, sha256});
      }
      node.inputs[name] = {value: spec.multiple ? added : added[0]};
      toast(fill(text.file_uploaded, {count: added.length}));
      changed();
    }

    function setBinding(node, name, value) {
      const spec = new Map((revisionOf(node) || {inputs: []}).inputs).get(name) || {};
      wirePending.delete(node.id + ':' + name);
      if (value === 'auto') {
        node.inputs[name] = {auto: true};
      } else if (value === 'default' || value === '') {
        delete node.inputs[name];
      } else if (value === 'value') {
        const initial = hasDefault(spec) ? spec.default
          : spec.type === 'boolean' ? false
          : spec.type === 'array' ? []
          : spec.type === 'object' ? {}
          : Array.isArray(spec.enum) ? spec.enum[0]
          : spec.type === 'integer' || spec.type === 'number' ? 0 : '';
        node.inputs[name] = {value: initial};
      } else {
        const [, upstream, output] = value.split(':');
        selectedSource = upstream;
        if (!canConnect(upstream, node.id)) return toast(text.cycle);
        if (!definition.edges.some(edge => edge.source === upstream && edge.target === node.id)) definition.edges.push({source: upstream, target: node.id});
        node.inputs[name] = {node: upstream, output};
      }
      changed();
    }

    const settings = root;
    settings.addEventListener('change', event => {
      const node = definition.nodes[selected];
      if (!node) return;
      const target = event.target;
      if (target.dataset.nodeFile !== undefined) {
        const name = target.dataset.nodeFile;
        const spec = new Map((revisionOf(node) || {inputs: []}).inputs).get(name) || {};
        const files = [...target.files];
        target.value = '';
        if (files.length) uploadNodeFiles(node, name, spec, files);
        return;
      }
      if (target.hasAttribute('data-parameter-source')) { selectedSource = target.value; render(); }
      else if (target.dataset.field === 'revision') {
        node.revision = Number(target.value);
        const revision = revisionOf(node);
        if (revision) {
          const names = new Set(revision.inputs.map(([name]) => name));
          Object.keys(node.inputs).forEach(name => { if (!names.has(name)) delete node.inputs[name]; });
        }
        changed();
      } else if (target.dataset.source !== undefined) {
        setBinding(node, target.dataset.source, target.value);
      } else if (target.dataset.value !== undefined && target.tagName === 'SELECT') {
        const name = target.dataset.value;
        const spec = new Map(revisionOf(node).inputs).get(name);
        const values = spec.type === 'boolean' ? [true, false] : spec.enum;
        node.inputs[name] = {value: values[Number(target.value)]};
        changed({settings: false});
      }
    });
    // 打字時只更新定義與檢查，不重畫設定（游標才不會跳走）
    settings.addEventListener('input', event => {
      const target = event.target;
      const node = definition.nodes[selected];
      if (!node || target.dataset.value === undefined || target.tagName !== 'INPUT') return;
      const name = target.dataset.value;
      const spec = new Map(revisionOf(node).inputs).get(name);
      let value = target.value;
      if (spec.type === 'integer' && /^-?\d+$/.test(value.trim())) value = parseInt(value, 10);
      else if (spec.type === 'number' && value.trim() !== '' && !Number.isNaN(Number(value))) value = Number(value);
      else if (spec.type === 'array' || spec.type === 'object') {
        // array、object 入參（ADR 0020）的固定值寫 JSON；還沒寫完時保留文字，檢查會說明
        try { value = JSON.parse(value); } catch { /* 保留文字 */ }
      }
      node.inputs[name] = {value};
      changed({settings: false});
    });
    // 參數可拖曳，也可依次點選出參與入參；鍵盤 Enter／Space 使用相同按鈕。
    const parameters = qs('.flow-parameters');
    new ResizeObserver(() => requestAnimationFrame(drawParameterWires)).observe(qs('#parameter-grid'));
    parameters.addEventListener('click', event => {
      const mode = event.target.closest('[data-mode]');
      const output = event.target.closest('[data-output-port]');
      const input = event.target.closest('[data-input-port]');
      const node = definition.nodes[selected];
      const viewSource = event.target.closest('[data-view-source]');
      if (viewSource) { selectedSource = viewSource.dataset.viewSource; render(); }
      else if (mode && node) {
        const name = mode.dataset.name, key = mode.dataset.mode;
        if (key === 'wire') { wirePending.add(node.id + ':' + name); renderSettings(); }
        else {
          setBinding(node, name, key);
        }
      } else if (output) {
        parameterPicked = output.dataset.outputPort;
        qsa('[data-output-port]').forEach(port => port.classList.toggle('is-picked', port === output));
        qs('#parameter-hint').textContent = fill(text.pick_input, {name: parameterPicked});
      } else if (input && parameterPicked) bindParameter(parameterPicked, input.dataset.inputPort);
    });
    parameters.addEventListener('keydown', event => {
      if (event.key === 'Escape') { parameterPicked = null; renderSettings(); }
    });
    parameters.addEventListener('pointerdown', event => {
      const output = event.target.closest('[data-output-port]');
      if (!output || event.button !== 0) return;
      parameterPicked = output.dataset.outputPort;
      const origin = {x: event.clientX, y: event.clientY};
      let moved = false;
      const move = ev => {
        moved ||= Math.abs(ev.clientX - origin.x) + Math.abs(ev.clientY - origin.y) > 4;
        if (moved) { ev.preventDefault(); drawParameterWires({x: ev.clientX, y: ev.clientY}); }
      };
      const end = ev => {
        document.removeEventListener('pointermove', move); document.removeEventListener('pointerup', end); document.removeEventListener('pointercancel', cancel);
        if (moved) {
          const input = document.elementFromPoint(ev.clientX, ev.clientY)?.closest('[data-input-port]');
          if (input && ev.type !== 'pointercancel') bindParameter(output.dataset.outputPort, input.dataset.inputPort);
          else { parameterPicked = null; drawParameterWires(); }
        }
      };
      const cancel = ev => { parameterPicked = null; end(ev); drawParameterWires(); };
      document.addEventListener('pointermove', move, {passive: false}); document.addEventListener('pointerup', end); document.addEventListener('pointercancel', cancel);
    });
    parameters.addEventListener('click', async event => {
      const button = event.target.closest('[data-inspect-contract]');
      if (!button) return;
      const node = definition.nodes.find(item => item.id === button.dataset.inspectNode);
      const kind = button.dataset.inspectContract;
      const result = await api('GET', '/api/scenes/' + path(node.sceneId) + '/sections/' + kind + '?revision=' + node.revision);
      if (!result.ok) return toast(errorMessage(result));
      modal(node.id + ' · ' + node.sceneId + ' · v' + node.revision, '<p class="hint">' + esc(text.pinned_contract) + '</p><pre class="contract-preview-code">' + esc(result.data.text) + '</pre><a class="button" href="/scenes/' + path(node.sceneId) + '#contract-' + kind + '" target="_blank" rel="noopener">' + esc(text.edit_contract_tab) + '</a>', null);
    });

    settings.addEventListener('click', event => {
      const remove = event.target.closest('[data-remove]'), unlink = event.target.closest('[data-unlink]');
      const node = definition.nodes[selected];
      if (!node) return;
      if (event.target.closest('[data-connect]')) connect(qs('[data-connect-source]').value, node.id);
      else if (unlink) {
        const source = unlink.dataset.unlink;
        definition.edges = definition.edges.filter(edge => edge.source !== source || edge.target !== node.id);
        Object.entries(node.inputs).forEach(([name, binding]) => { if (binding.node === source) node.inputs[name] = {auto: true}; });
        changed();
      } else if (remove) {
        definition.edges = definition.edges.filter(edge => edge.source !== node.id && edge.target !== node.id);
        definition.nodes.forEach(other => Object.entries(other.inputs).forEach(([name, binding]) => { if (binding.node === node.id) other.inputs[name] = {auto: true}; }));
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
        qs('#title').title = data.name;
        qs('#description').textContent = data.description || text.description;
        $('#dialog').close();
        toast(text.saved);
      });
    });

    qs('[data-action="workflow-export"]').addEventListener('click', () => {
      const exported = {name: data.name, description: data.description || undefined, ...definition};
      download('workflow-' + data.id + '.json', JSON.stringify(exported, null, 2) + '\n');
    });

    qs('[data-action="workflow-check"]').addEventListener('click', async event => {
      clearTimeout(checkTimer);
      const sequence = ++checkSeq, button = event.currentTarget;
      busy(button, true);
      const result = await api('POST', '/api/workflows/check', {definition});
      busy(button, false);
      if (sequence !== checkSeq) return;
      if (!result.ok) return toast(fill(text.check_failed, {reason: errorMessage(result)}));
      problems = result.data.problems;
      render({settings: false});
      if (problems.length) showWorkflowIssues({id: data.id, definition, problems}, focusProblem);
      else toast(text.check_passed);
    });

    qs('[data-action="workflow-run"]').addEventListener('click', async () => {
      if ((dirty || legacy) && !(await save())) return;
      if (dirty) return toast(text.unsaved);
      const workflow = {id: data.id, name: data.name, definition, problems, publishedRevision: data.publishedRevision};
      if (problems.length) return showWorkflowIssues(workflow, focusProblem);
      openWorkflowRun(workflow, focusProblem, items => { problems = items; render({settings: false}); }, showLiveRun);
    });

    window.addEventListener('beforeunload', event => {
      if (!dirty) return;
      event.preventDefault();
      event.returnValue = '';
    });

    let liveRun = null, liveTimer = null, liveGeneration = 0;
    const livePanel = qs('#workflow-live'), runButton = qs('[data-action="workflow-run"]');
    function liveDetails(id) {
      const node = liveRun?.nodes.find(item => item.id === id);
      if (!node) return;
      qs('#live-detail').hidden = false;
      qs('#live-detail-title').textContent = node.id + ' · ' + node.sceneId + ' · v' + node.revision;
      qs('#live-inputs').textContent = JSON.stringify(node.run?.input || node.sources, null, 2);
      qs('#live-outputs').textContent = node.run?.output ? JSON.stringify(node.run.output, null, 2) : node.error || node.run?.error || text.live_waiting;
      const link = qs('#live-node-report');
      link.hidden = !node.run;
      if (node.run) link.href = '/runs/' + path(node.run.id);
    }
    function showLiveRun(run) {
      clearTimeout(liveTimer);
      liveGeneration += 1;
      const generation = liveGeneration;
      liveRun = run;
      livePanel.hidden = false;
      livePanel.dataset.run = run.id;
      livePanel.dataset.status = run.status;
      qs('#live-status').textContent = fill(text.live_summary, {version: run.workflowVersion, passed: run.nodes.filter(node => ['passed', 'reused'].includes(node.status)).length, total: run.nodes.length, status: text['status_' + run.status] || run.status});
      qs('#live-status').className = 'badge ' + (run.status === 'passed' ? 'green' : run.finished ? 'amber' : 'blue');
      qs('#live-report').href = '/playground/runs/' + path(run.id);
      qs('#live-error').textContent = run.error || '';
      qs('#live-error').hidden = !run.error;
      qs('#live-cancel').hidden = run.finished;
      qs('#live-cancel').disabled = run.cancelRequested;
      runButton.disabled = !run.finished;
      qs('#live-nodes').innerHTML = run.nodes.map(node => '<button type="button" class="chip-btn" data-live-node="' + esc(node.id) + '" data-status="' + esc(node.status) + '">' + esc(node.id + ' · ' + (text['status_' + node.status] || node.status)) + '</button>').join('');
      qsa('[data-live-node]').forEach(button => button.addEventListener('click', () => {
        livePanel.dataset.selectedNode = button.dataset.liveNode;
        liveDetails(button.dataset.liveNode);
      }));
      if (livePanel.dataset.selectedNode) liveDetails(livePanel.dataset.selectedNode);
      try { sessionStorage.setItem('rpa-live-' + data.id, run.id); } catch { /* 不依賴瀏覽器儲存 */ }
      if (!run.finished) liveTimer = setTimeout(() => pollLive(run.id, generation), 1000);
    }
    async function pollLive(id, generation) {
      const result = await api('GET', '/api/workflow-runs/' + path(id));
      if (generation !== liveGeneration) return;
      if (result.ok) showLiveRun(result.data);
      else {
        qs('#live-error').hidden = false;
        qs('#live-error').textContent = fill(text.live_poll_error, {reason: errorMessage(result)});
        liveTimer = setTimeout(() => pollLive(id, generation), 3000);
      }
    }
    qs('#live-cancel').addEventListener('click', () => {
      if (!liveRun || liveRun.finished) return;
      confirmDialog(text.cancel_title, text.cancel_body, text.cancel_action, async () => {
        const result = await api('POST', '/api/workflow-runs/' + path(liveRun.id) + '/cancel');
        $('#dialog').close();
        if (!result.ok) return toast(errorMessage(result));
        pollLive(liveRun.id, liveGeneration);
      });
    });
    qs('#live-collapse').addEventListener('click', () => { qs('#live-detail').hidden = true; delete livePanel.dataset.selectedNode; });
    try {
      const previous = sessionStorage.getItem('rpa-live-' + data.id);
      if (previous) api('GET', '/api/workflow-runs/' + path(previous)).then(result => { if (result.ok && !liveRun && result.data.workflowId === data.id) showLiveRun(result.data); });
    } catch { /* 沒有檢視歷史時照常編輯 */ }
    window.addEventListener('pagehide', () => { clearTimeout(liveTimer); liveGeneration += 1; });

    function rememberCanvas() {
      try { sessionStorage.setItem('rpa-canvas-' + data.id, JSON.stringify({node: definition.nodes[selected]?.id, source: selectedSource, zoom, left: viewport.scrollLeft, top: viewport.scrollTop})); } catch { /* 私密模式無儲存空間時仍可操作 */ }
    }
    try {
      const saved = JSON.parse(sessionStorage.getItem('rpa-canvas-' + data.id) || 'null');
      if (saved) {
        const index = definition.nodes.findIndex(node => node.id === saved.node);
        if (index >= 0) selected = index;
        selectedSource = saved.source;
        if (Number.isFinite(saved.zoom)) zoom = Math.max(.001, Math.min(2, saved.zoom));
        requestAnimationFrame(() => viewport.scrollTo(saved.left || 0, saved.top || 0));
      }
    } catch { /* 舊版或無效檢視狀態不影響定義 */ }
    viewport.addEventListener('scroll', rememberCanvas, {passive: true});
    window.addEventListener('pagehide', rememberCanvas);
    renderLibrary();
    render();
    const query = new URLSearchParams(location.search);
    if (query.has('node')) focusProblem({node: query.get('node'), input: query.get('input')});
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
    bindCompositeReport(root, run);
    if (root.hasAttribute('data-poll')) {
      pollUntilChanged('/api/workflow-runs/' + path(run), root.dataset.signature,
        data => data.status + '|' + data.nodes.map(node => node.status).join(','));
    }
  }

  // 組合運行的匯總報告（2026-10-27）：節點明細的展開與收起、從結論或時間軸跳到節點。
  // 執行中每次狀態改變會重新載入頁面：展開了哪些節點記在 sessionStorage，載入後照樣展開。
  function bindCompositeReport(root, run) {
    const nodes = qsa('details.creport-node', root);
    if (!nodes.length) return;
    const key = 'creport-open:' + run;
    const remember = () => {
      try { sessionStorage.setItem(key, JSON.stringify(nodes.filter(node => node.open).map(node => node.dataset.node))); } catch (error) { /* 瀏覽器不給存就算了 */ }
    };
    let saved = null;
    try { saved = JSON.parse(sessionStorage.getItem(key) || 'null'); } catch (error) { saved = null; }
    if (Array.isArray(saved)) nodes.forEach(node => { node.open = saved.includes(node.dataset.node); });
    const reveal = id => {
      const node = qs('#node-' + CSS.escape(id));
      if (!node) return;
      node.open = true;
      node.scrollIntoView({block: 'start', behavior: 'smooth'});
      node.classList.remove('anchor-hit');
      void node.offsetWidth;
      node.classList.add('anchor-hit');
      remember();
    };
    nodes.forEach(node => node.addEventListener('toggle', remember));
    qsa('[data-open-node]', root).forEach(link => link.addEventListener('click', event => {
      event.preventDefault();
      history.replaceState(null, '', '#node-' + link.dataset.openNode);
      reveal(link.dataset.openNode);
    }));
    qsa('[data-action="toggle-nodes"]', root).forEach(button => button.addEventListener('click', () => {
      nodes.forEach(node => { node.open = button.dataset.open === '1'; });
      remember();
    }));
    if (location.hash.startsWith('#node-')) reveal(decodeURIComponent(location.hash.slice(6)));
  }

  localizeTimes();
  // ---------------------------------------------------------------- 裝置（M9a 遠端 worker；M10.1 邀請）

  // 裝置的種類：worker 或錄製端（M10.2），各自一組 API
  const deviceApi = kind => kind === 'recorder' ? '/api/recorders' : '/api/workers';

  // 邀請只在這時候拿得到：一行邀請、分開的伺服器與代碼、命令列的用法
  function showInvite(worker, invite, kind) {
    modal(fill(messages.worker_invite_title, {name: worker.name}), qs('#worker-invite').innerHTML, null);
    const dialog = qs('#dialog-content');
    qsa('[data-app]', dialog).forEach(item => { item.hidden = item.dataset.app !== (kind || 'worker'); });
    qs('[name="invite"]', dialog).value = invite.line;
    qs('[name="server"]', dialog).value = invite.server;
    qs('[name="code"]', dialog).value = invite.code;
    const expires = qs('time[data-expires]', dialog);
    expires.setAttribute('datetime', invite.expiresAt);
    expires.textContent = invite.expiresAt;
    localizeTimes();
    const command = kind === 'recorder' ? 'uv run rpa recorder --invite "' : 'uv run rpa worker --invite "';
    qs('[data-command="cli"]', dialog).textContent = command + invite.line + '"';
    const field = qs('[name="invite"]', dialog);
    field.focus();
    field.select();
    if (navigator.clipboard) {
      navigator.clipboard.writeText(invite.line).then(() => toast(messages.worker_copied), () => {});
    }
    $('#dialog').addEventListener('close', () => location.reload(), {once: true});
  }

  async function inviteWorker(workerId, kind) {
    return api('POST', deviceApi(kind) + '/' + path(workerId) + '/invite');
  }

  // ---------------------------------------------------------------- 運行回看的錄影設定（M12）

  function bindVideoSettings() {
    const form = qs('[data-video-settings]');
    if (!form) return;
    const toggle = qs('[data-action="toggle-video-settings"]');
    const panel = qs('#video-settings');
    if (toggle && panel) {
      toggle.addEventListener('click', () => {
        panel.hidden = !panel.hidden;
        toggle.setAttribute('aria-expanded', String(!panel.hidden));
        if (!panel.hidden) panel.scrollIntoView({block: 'nearest'});
      });
    }
    form.addEventListener('submit', async event => {
      event.preventDefault();
      const error = qs('.form-error', form);
      error.textContent = '';
      const body = {
        enabled: form.elements.enabled.checked,
        keepPassedDays: Number(form.elements.keepPassedDays.value),
        keepOtherDays: Number(form.elements.keepOtherDays.value),
        maxTotalGb: Number(form.elements.maxTotalGb.value),
      };
      const result = await api('PUT', '/api/settings/video', body);
      if (!result.ok) {
        error.textContent = errorMessage(result);
        return;
      }
      flash(messages.saved);
      location.reload();
    });
  }

  function bindWorkers() {
    const root = qs('#workers');
    if (!root) return;
    qs('[data-action="new-worker"]').addEventListener('click', () => {
      modal(messages.worker_create_title, qs('#worker-form').innerHTML, {label: messages.worker_create_action, run: async () => {
        const dialog = qs('#dialog-content');
        const value = name => qs('[name="' + name + '"]', dialog).value.trim();
        const kind = value('kind') || 'worker';
        const result = await api('POST', deviceApi(kind), {id: value('id'), name: value('name') || null});
        if (!result.ok) return dialogError(dialog, result);
        const invited = await inviteWorker((result.data.worker || result.data.recorder).id, kind);
        if (!invited.ok) {
          $('#dialog').close();
          toast(errorMessage(invited));
          return location.reload();
        }
        showInvite(invited.data.worker || invited.data.recorder, invited.data.invite, kind);
      }});
      qs('[name="id"]', qs('#dialog-content')).focus();
    });
    const patch = async (button, disabled) => {
      busy(button, true);
      const result = await api('PATCH', deviceApi(button.dataset.kind) + '/' + path(button.dataset.worker), {disabled});
      if (!result.ok) {
        busy(button, false);
        return toast(errorMessage(result));
      }
      flash(disabled ? messages.worker_disabled : messages.worker_enabled);
      location.reload();
    };
    qsa('[data-action="disable-worker"]').forEach(button => button.addEventListener('click', () => patch(button, true)));
    qsa('[data-action="enable-worker"]').forEach(button => button.addEventListener('click', () => patch(button, false)));
    qsa('[data-action="invite-worker"]').forEach(button => {
      button.addEventListener('click', () => {
        confirmDialog(fill(messages.worker_invite_again_title, {name: button.dataset.name}), messages.worker_invite_again_body, messages.worker_invite_again_action, async () => {
          const result = await inviteWorker(button.dataset.worker, button.dataset.kind);
          if (!result.ok) {
            $('#dialog').close();
            return toast(errorMessage(result));
          }
          showInvite(result.data.worker || result.data.recorder, result.data.invite, button.dataset.kind);
        });
      });
    });
    qsa('[data-action="delete-worker"]').forEach(button => {
      button.addEventListener('click', () => {
        confirmDialog(fill(messages.worker_delete_title, {name: button.dataset.name}), messages.worker_delete_body, messages.worker_delete_action, async () => {
          const result = await api('DELETE', deviceApi(button.dataset.kind) + '/' + path(button.dataset.worker));
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
    // 自動更新裝置（ADR 0018）：勾選立刻儲存
    qsa('[name="device-updates-auto"]').forEach(input => {
      input.addEventListener('change', async () => {
        const result = await api('PUT', '/api/settings/device-updates', {auto: input.checked});
        toast(result.ok ? messages.saved : errorMessage(result));
      });
    });
    // 透過錄製端時另外顯示的選單（三段分工；預設不顯示叢集管理與管理後台）：勾選立刻儲存
    qsa('[data-recorder-menus]').forEach(group => {
      group.addEventListener('change', async () => {
        const menus = qsa('input[name="recorder-menu"]:checked', group).map(input => input.value);
        const result = await api('PATCH', '/api/recorders/' + path(group.dataset.recorderMenus), {menus});
        toast(result.ok ? messages.saved : errorMessage(result));
      });
    });
    // 允不允許 Agent 在這台調試、是否只允許無頭（M14）：勾選立刻儲存
    qsa('[data-recorder-agent]').forEach(group => {
      group.addEventListener('change', async event => {
        const input = event.target;
        const result = await api('PATCH', '/api/recorders/' + path(group.dataset.recorderAgent), {[input.name]: input.checked});
        if (!result.ok) input.checked = !input.checked;
        toast(result.ok ? messages.saved : errorMessage(result));
      });
    });
    // 狀態（上線、忙碌、離線）改變時重新載入；對話框開著時不打擾
    if (root.hasAttribute('data-poll')) {
      const states = () => qsa('tr[data-state]').map(row => row.dataset.state).join('|');
      const current = states();
      const timer = setInterval(async () => {
        if ($('#dialog').open) return;
        const [workers, recorders] = await Promise.all([api('GET', '/api/workers'), api('GET', '/api/recorders')]);
        if (!workers.ok || !recorders.ok) return;
        const next = workers.data.workers.map(worker => 'worker:' + worker.id + ':' + worker.status + ':' + (worker.currentRun || ''))
          .concat(recorders.data.recorders.map(item => 'recorder:' + item.id + ':' + item.status + ':' + item.active)).join('|');
        if (next !== current) {
          clearInterval(timer);
          location.reload();
        }
      }, 5000);
    }
  }

  // ---------------------------------------------------------------- API 用戶端（M14）

  function bindAgents() {
    const root = qs('#agents');
    if (!root) return;
    const base = (root.dataset.apiUrl || location.origin) + '/agent-api/v1';
    const checked = (dialog, name) => qsa('[name="' + name + '"]:checked', dialog).map(input => input.value);
    const lines = text => text.split(/[\s,，]+/).map(item => item.trim()).filter(Boolean);

    function showKey(agent, key) {
      modal(fill(messages.agent_key_title, {name: agent.name}), qs('#agent-key').innerHTML, null);
      const dialog = qs('#dialog-content');
      qs('[name="key"]', dialog).value = key;
      qs('[name="base"]', dialog).value = base;
      qs('[data-command="curl"]', dialog).textContent = 'curl -H "Authorization: Bearer ' + key + '" ' + base + '/meta';
      const field = qs('[name="key"]', dialog);
      field.focus();
      field.select();
      if (navigator.clipboard) {
        navigator.clipboard.writeText(key).then(() => toast(messages.agent_copied), () => {});
      }
      $('#dialog').addEventListener('close', () => location.reload(), {once: true});
    }

    function fillForm(dialog, agent) {
      const set = (name, value) => { qs('[name="' + name + '"]', dialog).value = value; };
      const tick = (name, values) => qsa('[name="' + name + '"]', dialog).forEach(input => { input.checked = values.includes(input.value); });
      set('id', agent ? agent.id : '');
      set('name', agent ? agent.name : '');
      set('description', agent ? agent.description || '' : '');
      tick('scope', agent ? agent.scopes : ['scenes:read', 'runs:read', 'projects:read']);
      qs('[name="all-domains"]', dialog).checked = !agent || agent.domains === null;
      tick('domain', agent && agent.domains ? agent.domains : []);
      qs('[name="all-projects"]', dialog).checked = !agent || agent.projects === null;
      tick('project', agent && agent.projects ? agent.projects : []);
      tick('recorder', agent ? agent.recorders : []);
      set('target', agent && agent.target ? agent.target : '');
      qs('[name="all-workers"]', dialog).checked = !agent || agent.workers === null;
      tick('worker', agent && agent.workers ? agent.workers : []);
      set('max-debug', agent ? agent.limits.debugSessions : 2);
      set('max-queued', agent ? agent.limits.queuedRuns : 20);
      qs('[name="page-content"]', dialog).checked = Boolean(agent && agent.pageContent);
      set('allowed-ips', agent && agent.allowedIps ? agent.allowedIps.join(', ') : '');
      set('expires', agent && agent.expiresAt ? agent.expiresAt.slice(0, 10) : '');
      if (agent) qs('[name="id"]', dialog).readOnly = true;
      // 「不限」和個別勾選互斥
      [['all-domains', 'domain'], ['all-projects', 'project'], ['all-workers', 'worker']].forEach(([all, item]) => {
        const everything = qs('[name="' + all + '"]', dialog);
        const sync = () => qsa('[name="' + item + '"]', dialog).forEach(input => { input.disabled = everything.checked; });
        everything.addEventListener('change', sync);
        sync();
      });
    }

    function readPolicy(dialog) {
      const value = name => qs('[name="' + name + '"]', dialog).value.trim();
      const expires = value('expires');
      const ips = lines(value('allowed-ips'));
      return {
        scopes: checked(dialog, 'scope'),
        domains: qs('[name="all-domains"]', dialog).checked ? null : checked(dialog, 'domain'),
        projects: qs('[name="all-projects"]', dialog).checked ? null : checked(dialog, 'project'),
        recorders: checked(dialog, 'recorder'),
        target: value('target') || null,
        workers: qs('[name="all-workers"]', dialog).checked ? null : checked(dialog, 'worker'),
        maxDebugSessions: Number(value('max-debug') || 0),
        maxQueuedRuns: Number(value('max-queued') || 0),
        pageContent: qs('[name="page-content"]', dialog).checked,
        allowedIps: ips.length ? ips : null,
        expiresAt: expires ? new Date(expires + 'T23:59:59').toISOString() : null,
      };
    }

    function agentDialog(agent) {
      const title = agent ? fill(messages.agent_edit_title, {name: agent.name}) : messages.agent_create_title;
      modal(title, qs('#agent-form').innerHTML, {label: agent ? messages.save : messages.agent_create_action, run: async () => {
        const dialog = qs('#dialog-content');
        const value = name => qs('[name="' + name + '"]', dialog).value.trim();
        const fields = {name: value('name') || null, description: value('description'), policy: readPolicy(dialog)};
        if (agent) {
          const result = await api('PATCH', '/api/agents/' + path(agent.id), fields);
          if (!result.ok) return dialogError(dialog, result);
          flash(messages.saved);
          return location.reload();
        }
        const result = await api('POST', '/api/agents', {id: value('id'), ...fields});
        if (!result.ok) return dialogError(dialog, result);
        showKey(result.data.agent, result.data.key);
      }});
      const dialog = qs('#dialog-content');
      fillForm(dialog, agent);
      qs(agent ? '[name="name"]' : '[name="id"]', dialog).focus();
    }

    const agentOf = button => JSON.parse(button.closest('tr[data-agent]').dataset.agent);
    qs('[data-action="new-agent"]').addEventListener('click', () => agentDialog(null));
    qsa('[data-action="edit-agent"]').forEach(button => button.addEventListener('click', () => agentDialog(agentOf(button))));
    const toggle = async (button, disabled) => {
      busy(button, true);
      const result = await api('PATCH', '/api/agents/' + path(agentOf(button).id), {disabled});
      if (!result.ok) {
        busy(button, false);
        return toast(errorMessage(result));
      }
      flash(disabled ? messages.agent_disabled : messages.agent_enabled);
      location.reload();
    };
    qsa('[data-action="disable-agent"]').forEach(button => button.addEventListener('click', () => toggle(button, true)));
    qsa('[data-action="enable-agent"]').forEach(button => button.addEventListener('click', () => toggle(button, false)));
    qsa('[data-action="rotate-agent"]').forEach(button => {
      button.addEventListener('click', () => {
        const agent = agentOf(button);
        confirmDialog(fill(messages.agent_rotate_title, {name: agent.name}), messages.agent_rotate_body, messages.agent_rotate_action, async () => {
          const result = await api('POST', '/api/agents/' + path(agent.id) + '/key');
          if (!result.ok) {
            $('#dialog').close();
            return toast(errorMessage(result));
          }
          showKey(result.data.agent, result.data.key);
        });
      });
    });
    qsa('[data-action="delete-agent"]').forEach(button => {
      button.addEventListener('click', () => {
        const agent = agentOf(button);
        confirmDialog(fill(messages.agent_delete_title, {name: agent.name}), messages.agent_delete_body, messages.agent_delete_action, async () => {
          const result = await api('DELETE', '/api/agents/' + path(agent.id));
          $('#dialog').close();
          if (!result.ok) return toast(errorMessage(result));
          location.reload();
        });
      });
    });
  }

  // 錄製端（macOS 的 WKWebView）會依系統的「自動將字首大寫」把輸入框的第一個字母改成大寫
  // （demo-001 變成 Demo-001）。代號、網址、定位器、入參都不該被改：所有文字輸入框關掉自動大寫、
  // 自動校正與拼字檢查；對話框之類之後才加進來的輸入框也一樣。
  const TEXT_FIELDS = 'input:not([type]), input[type="text"], input[type="url"], input[type="search"], input[type="email"], input[type="tel"], textarea';
  function plainTyping(field) {
    if (!field.matches || !field.matches(TEXT_FIELDS)) return;
    if (!field.hasAttribute('autocapitalize')) field.setAttribute('autocapitalize', 'off');
    if (!field.hasAttribute('autocorrect')) field.setAttribute('autocorrect', 'off');
    if (!field.hasAttribute('spellcheck')) field.spellcheck = false;
  }
  function bindPlainTyping() {
    qsa(TEXT_FIELDS).forEach(plainTyping);
    new MutationObserver(records => records.forEach(record => record.addedNodes.forEach(node => {
      if (node.nodeType !== Node.ELEMENT_NODE) return;
      plainTyping(node);
      qsa(TEXT_FIELDS, node).forEach(plainTyping);
    }))).observe(document.body, {childList: true, subtree: true});
    document.addEventListener('focusin', event => plainTyping(event.target));
  }

  bindPlainTyping();
  bindLanguage();
  bindFilters();
  bindPublish();
  bindScenes();
  bindCompositePublish();
  bindCompositeSettings();
  bindDomains();
  bindProjects();
  bindSync();
  bindSceneSettings();
  bindEditor();
  bindSceneAnchors(bindScripts());
  bindRunForm();
  bindAttachments();
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
  bindAgents();
  bindVideoSettings();
  showFlash();
})();
