'use strict';
// 運行回看（M12，ADR 0016）：播放錄影、縮圖時間軸、步驟清單跟著影片走。
// 資料在 #replay-data（rpa_server.replay.build_replay），文字在 #replay-messages（replayjs.*）。
// 影片的第 t 秒＝錄影開始時間＋t；步驟的 startMs、endMs 已經換算成影片裡的毫秒。
// 縮圖在這個瀏覽器裡產生：另一個看不見的 video 跳到各時間點、畫到 canvas（伺服器沒有 ffmpeg）。
// 共用的 toast()、esc() 來自設計系統的 shell.js。
// 組合運行的合併回看（2026-10-27，rpa_server.composite_replay）：data.composite 有值時，步驟依節點
// 分組、時間軸多一條節點色帶、沒有影片的時間顯示卡片（#replay-card-<段> 樣板），N／P 跳到下一個／
// 上一個節點；步驟的 label 是「n2·3」，id 是「n2:search」（網址的 ?step= 用它）。
// 依步驟的章節軸（2026-10-29，任務 20261029-replay-chapters）：時間軸預設一格一步，沒有動作的空檔
// 折疊成窄格（播放時 4× 快轉），卡片固定寬；縮圖是執行端每一步做完拍的截圖（步驟的 shot），沒有時
// 退回錄影裡那一步做完的畫面。「依時間」是原本的等比例時間軸。兩種排法都用 axis（時間 ↔ 位置）畫。
// Python 節點（ADR 0020）：單一運行沒有播放器，是章節列與步驟詳情；合併回看裡是一段 kind 為 python
// 的「卡片」（ReplayMedia 的時鐘照走），一步一格，畫面顯示目前那一步的腳本、檔案變化、資料預覽與到那
// 一步為止的主控台（步驟的 console）。
(() => {
  const root = document.getElementById('replay');
  if (!root) return;
  const data = JSON.parse(document.getElementById('replay-data').textContent);
  const messages = JSON.parse(document.getElementById('replay-messages').textContent);
  const $ = id => document.getElementById(id);
  const fill = (template, values) =>
    template.replace(/\{(\w+)\}/g, (whole, key) => (key in values ? String(values[key]) : whole));
  const FPS = 25;
  const PREROLL = 0.4;
  // 章節軸的尺寸（px）與規則
  const FOLD = 0.5; // 同一段錄影裡超過這麼久沒有動作就折疊（秒）
  const TAIL = 0.25; // 折疊前留給那一步的結果多久（秒）
  const STEP_MIN = 44; // 一步至少多寬；放不下時進入「太擠」：格子變窄、縮圖只畫重點步驟、可以放大一章
  const GAP_W = 20;
  const CARD_W = 40;
  const THUMB_MIN = 24; // 比這窄的格子不畫縮圖
  const TILE_W = 96; // 一張縮圖多寬（54 px 高的 16:9）
  const KEY_ACTIONS = new Set(['goto', 'click', 'upload', 'screenshot']);
  const store = {
    get: key => { try { return localStorage.getItem(key); } catch { return null; } },
    set: (key, value) => { try { localStorage.setItem(key, value); } catch { /* 不能存就只在這一頁有效 */ } },
  };
  const runId = root.dataset.run;
  const composite = data.composite || null;
  const element = $('replay-video');
  const playable = Boolean(element && data.video && data.video.playable);
  const video = playable ? new ReplayMedia(element, data.video, data.steps, $('replay-gap')) : null;
  const numberOf = step => step.label || String(step.index).padStart(2, '0');
  // 合併回看：每個節點一個顏色，用在清單的節點標題與左側色條、時間軸的節點色帶、畫面上的步驟編號，
  // 一眼看出這一段是哪個場景在跑（2026-10-28 驗收）。和結果的顏色（綠、紅）分開。
  const NODE_COLORS = ['#2f6fdb', '#7c4dcc', '#0e8a8f', '#c26a10', '#b8407a', '#546479'];
  const nodeColor = id => {
    const index = composite ? composite.nodes.findIndex(node => node.id === id) : -1;
    return index < 0 ? '' : NODE_COLORS[index % NODE_COLORS.length];
  };

  const steps = data.steps.map(step => ({
    ...step,
    start: step.startMs == null ? null : Math.max(0, step.startMs / 1000),
    end: step.endMs == null ? null : Math.max(0, step.endMs / 1000),
    shotTime: step.shotMs == null ? null : Math.max(0, step.shotMs / 1000),
  }));
  const timed = steps.filter(step => step.start != null);
  const sameRun = (one, other) => Boolean(one && other) && (!composite || one.node === other.node);
  // 點一步跳到哪裡：「開始前 PREROLL 秒」與「同一段裡上一步結束」較晚的那一刻。步驟常常只有幾十毫秒，
  // 固定往前 0.4 秒時，前幾步都跳回開頭，時間軸與畫面看起來沒動（2026-10-28 驗收）
  const leadIn = step => {
    const before = timed[timed.indexOf(step) - 1];
    if (!sameRun(before, step)) return step.start - PREROLL;
    const end = before.end != null ? before.end : before.start;
    return Math.max(step.start - PREROLL, Math.min(end, step.start));
  };
  // 錄影裡「這一步做完」的那一刻：拍截圖的時間；沒有截圖時是結束後 3 格（讓結果畫出來），不超過下一步
  const frameTime = step => {
    if (step.shotTime != null) return step.shotTime;
    const end = step.end != null ? step.end : step.start;
    const after = timed[timed.indexOf(step) + 1];
    const limit = sameRun(after, step) ? after.start - 0.001 : Infinity;
    return Math.max(step.start, Math.min(end + 3 / FPS, limit));
  };
  const failedStep = steps.find(step => step.status === 'failed') || null;
  let duration = 0;
  let selected = failedStep ? failedStep.index : null;

  const fmt = seconds => {
    const value = Math.max(0, seconds || 0);
    const minutes = Math.floor(value / 60);
    const rest = value - minutes * 60;
    return String(minutes).padStart(2, '0') + ':' + rest.toFixed(2).padStart(5, '0');
  };
  const title = step => step.name || fill(messages['action_' + step.action] || '{id}', {id: step.rawId || step.id});
  const clamp = seconds => Math.min(Math.max(0, seconds), Math.max(0, duration - 0.04));
  const cardTitle = card => {
    const segment = composite && composite.segments[card.index];
    return fill(messages['card_' + card.kind] || '', {
      node: card.node || '', prev: (segment && segment.prev) || '', nodes: ((segment && segment.nodes) || []).join(', '),
    });
  };

  // 這一刻是哪一步：最後一個已經開始的步驟
  // 合併回看只看目前這個節點的步驟：節點那一段開頭、第一步之前不是上一個節點的最後一步
  const stepAt = seconds => {
    const where = composite ? nodeAt(seconds) : null;
    let found = null;
    for (const step of timed) {
      if (where && step.node !== where.id) continue;
      if (step.start <= seconds + 0.001) found = step;
    }
    return found;
  };
  // 畫面上標成目前的步驟：點一步會跳到它開始前 PREROLL 秒，這段時間標成點的那一步，不是前一步
  const shownAt = seconds => {
    const chosen = selected ? steps[selected - 1] : null;
    if (chosen && chosen.start != null && seconds < chosen.start && seconds >= chosen.start - PREROLL - 0.05) {
      return chosen;
    }
    return stepAt(seconds);
  };
  const stateOf = (step, seconds) => {
    if (step.start == null) return step.status;
    if (seconds < step.start) return 'upcoming';
    if (seconds <= step.end && step.end < duration - 0.05) return step.status === 'failed' ? 'failed' : 'running';
    return step.status;
  };

  // ---------------------------------------------------------------- 步驟清單

  const list = $('replay-steps');
  const thumbObserver = 'IntersectionObserver' in window ? new IntersectionObserver(entries => {
    for (const entry of entries) {
      if (!entry.isIntersecting || !duration) continue;
      thumbObserver.unobserve(entry.target);
      const step = steps[Number(entry.target.dataset.thumb) - 1];
      if (step && step.start != null) grab(clamp(frameTime(step)), step.pageId).then(frame => draw(entry.target, frame));
    }
  }) : null;

  // 步驟的縮圖：執行端拍的截圖（錄影刪了也還在）；沒有時，有錄影就從錄影取那一步做完的畫面；
  // 都沒有（略過的步驟）留一個空位，欄位才對齊
  const withThumbs = playable || steps.some(step => step.shot);
  function thumbnail(step) {
    if (step.shot) return '<img class="replay-thumb" src="' + esc(step.shot) + '" alt="" loading="lazy" decoding="async">';
    if (playable && step.start != null) return '<canvas class="replay-thumb" width="128" height="72" data-thumb="' + step.index + '" aria-hidden="true"></canvas>';
    return withThumbs ? '<span class="replay-thumb" aria-hidden="true"></span>' : '';
  }

  function row(step) {
    const item = document.createElement('li');
    const seekable = playable && step.start != null;
    const current = shown && shown.index === step.index;
    item.innerHTML =
      '<div class="replay-row' + (current ? ' selected' : '') + '" data-index="' + step.index + '" tabindex="0" role="button"' +
      (current ? ' aria-current="true"' : '') + '>' +
      '<span class="replay-n" data-n>' + esc(step.nodeIndex || step.index) + '</span>' + thumbnail(step) +
      '<span class="replay-title"><strong></strong><small></small></span>' +
      '<span class="replay-when">' + (seekable ? '<b>' + fmt(step.start) + '</b>' : '') +
      (step.status === 'skipped' ? esc(messages.status_skipped)
        : step.durationMs != null ? (step.durationMs / 1000).toFixed(2) + ' s' : '') + '</span></div>';
    item.querySelector('strong').textContent = title(step);
    item.querySelector('small').textContent = [step.action, step.target].filter(Boolean).join(' · ');
    item.querySelector('[data-n]').className = 'replay-n ' + (step.status || '');
    if (composite && step.node) {
      item.className = 'in-node';
      item.style.setProperty('--node', nodeColor(step.node));
    }
    const canvas = item.querySelector('canvas');
    if (canvas && thumbObserver) thumbObserver.observe(canvas);
    return item;
  }

  function detail(step) {
    const box = document.createElement('div');
    box.className = 'replay-detail';
    const rows = [];
    const add = (label, value, mono) => {
      if (value == null || value === '') return;
      rows.push('<dt>' + esc(label) + '</dt><dd' + (mono ? ' class="mono"' : '') + '>' + esc(value) + '</dd>');
    };
    add(messages.result, (messages['status_' + step.status] || step.status) +
      (step.durationMs != null ? ' · ' + fill(messages.took, {seconds: (step.durationMs / 1000).toFixed(2)}) : ''));
    add(messages.target, step.target, true);
    add(messages.detail, step.detail, true);
    if (step.files && step.files.length) add(messages.files, step.files.join(messages.list_separator));
    if (step.occurrence) add(messages.occurrence, fill(messages.occurrence_value, {n: step.occurrence}));
    if (step.changes) {
      for (const kind of ['added', 'changed', 'removed']) {
        const items = step.changes[kind] || [];
        if (items.length) add(messages['change_' + kind], items.join(messages.list_separator), true);
      }
    }
    if (step.hasFact) add(messages.fact, JSON.stringify(step.fact), true);
    add(messages.url_after, step.url, true);
    // Python 節點（ADR 0020）：腳本的那幾行，標出這一步的那一行
    const label = step.action === 'python' ? messages.source_script : messages.source;
    const source = step.source
      ? '<pre class="replay-source" aria-label="' + esc(fill(label, {line: step.line, file: step.target || ''})) + '">' +
        step.source.split('\n').map((text, offset) =>
          '<span' + (step.focusLine === step.line + offset ? ' class="focus"' : '') + '><i>' + (step.line + offset) + '</i>' + esc(text) + '</span>').join('') + '</pre>'
      : '';
    const previews = (step.previews || []).map(preview => {
      const head = '<div class="replay-preview-name">' + esc(fill(messages.preview, {name: preview.name || ''})) +
        (preview.rowCount != null ? ' <span class="muted">' + esc(fill(messages.preview_rows, {shown: (preview.rows || []).length, total: preview.rowCount})) + '</span>' : '') + '</div>';
      if (preview.kind === 'table' && Array.isArray(preview.columns) && Array.isArray(preview.rows)) {
        return '<div class="replay-preview">' + head + '<div class="table-scroll"><table class="wrap"><thead><tr>' +
          preview.columns.map(column => '<th>' + esc(column) + '</th>').join('') + '</tr></thead><tbody>' +
          preview.rows.map(row => '<tr>' + (Array.isArray(row) ? row : []).map(cell => '<td>' + esc(cell == null ? '' : cell) + '</td>').join('') + '</tr>').join('') +
          '</tbody></table></div></div>';
      }
      return '<div class="replay-preview">' + head + '<pre class="source">' + esc(preview.text || '') + '</pre></div>';
    }).join('');
    // Python 節點：到這一步為止的主控台，這一步自己寫的那幾行標出來
    const output = step.console;
    const outputBox = output && output.text
      ? '<div class="replay-preview"><div class="replay-preview-name">' + esc(messages.console_upto) + '</div>' +
        '<pre class="replay-source replay-console">' + output.text.split('\n').map((text, offset) => {
          const number = output.line + offset;
          const own = output.own && number >= output.own[0] && number <= output.own[1];
          return '<span' + (own ? ' class="focus"' : '') + '><i>' + number + '</i>' + esc(text) + '</span>';
        }).join('') + '</pre></div>'
      : '';
    const actions = [];
    if (playable && step.start != null) {
      actions.push('<button class="button primary" type="button" data-act="play">' + esc(messages.play_from) + '</button>');
      actions.push('<button class="button" type="button" data-act="link">' + esc(messages.copy_link) + '</button>');
    }
    if (step.line && (step.editUrl || data.editUrl)) {
      actions.push('<a class="button" href="' + esc((step.editUrl || data.editUrl) + '&line=' + step.line) + '">' +
        esc(fill(messages.open_in_scene, {line: step.line})) + '</a>');
    }
    const notes = (step.notes || []).map(text => '<div class="notice warn replay-note">' + esc(text) + '</div>').join('');
    // 這一步做完的截圖：點了看原圖
    const shot = step.shot
      ? '<a class="replay-shot" href="' + esc(step.shot) + '" target="_blank" rel="noopener" title="' + esc(messages.shot_open) + '">' +
        '<img src="' + esc(step.shot) + '" alt="' + esc(messages.shot_alt) + '" loading="lazy"></a>'
      : '';
    box.innerHTML = (step.error ? '<div class="replay-error">' + esc(step.error) + '</div>' : '') + notes + shot +
      '<dl class="replay-kv">' + rows.join('') + '</dl>' + source + previews + outputBox +
      (actions.length ? '<div class="actions">' + actions.join('') + '</div>' : '');
    return box;
  }

  // 合併回看：每個節點一列標題（狀態、名稱、這段從哪裡開始），下面是它的步驟
  function nodeHead(node) {
    const item = document.createElement('li');
    item.className = 'replay-node-head';
    item.dataset.node = node.id;
    item.style.setProperty('--node', nodeColor(node.id));
    const special = {reused: messages.node_reused, skipped: messages.node_skipped}[node.status];
    const note = special || (node.segment == null ? messages.node_waiting
      : !steps.some(step => step.node === node.id && step.start != null) ? messages.node_no_video
      : node.durationSeconds != null ? node.durationSeconds.toFixed(1) + ' s' : '');
    const status = special ? '' : messages['status_' + node.status] || node.status;
    item.innerHTML = '<button type="button" class="replay-node-button"' + (node.startMs == null ? ' disabled' : '') + '>' +
      '<span class="replay-n ' + esc(node.status) + '">' + esc(node.id) + '</span><strong></strong></button>' +
      '<small class="' + esc(node.status) + '">' + esc([status, note].filter(Boolean).join(' · ')) + '</small>';
    item.querySelector('strong').textContent = node.sceneName;
    return item;
  }

  function renderSteps() {
    list.textContent = '';
    if (!steps.length && !composite) {
      list.innerHTML = '<li class="empty">' + esc(messages.no_steps) + '</li>';
      return;
    }
    if (composite) {
      for (const node of composite.nodes) {
        list.appendChild(nodeHead(node));
        for (const step of steps) if (step.node === node.id) list.appendChild(row(step));
      }
    } else {
      for (const step of steps) list.appendChild(row(step));
    }
    if (playable) sync(true);
  }

  // 跳到某個節點那一段的開頭（N／P 與節點標題列）
  const seekNode = id => {
    const node = composite && composite.nodes.find(each => each.id === id);
    if (!node || node.startMs == null || !playable) return;
    selected = null;
    closeDetail({focus: false});
    seek(node.startMs / 1000);
    renderSteps();
  };
  const nodeAt = seconds => {
    if (!composite) return null;
    let found = null;
    for (const node of composite.nodes) if (node.startMs != null && node.startMs / 1000 <= seconds + 0.001) found = node;
    return found;
  };
  if (composite) {
    list.addEventListener('click', event => {
      const head = event.target.closest('.replay-node-head');
      if (head && event.target.closest('button')) seekNode(head.dataset.node);
    });
  }

  function choose(index, {seekTo = true, focus = true} = {}) {
    selected = index;
    const step = steps[index - 1];
    if (seekTo && playable && step.start != null) seek(leadIn(step), step);
    shown = step;
    renderSteps();
    openDetail(step, {focus});
  }

  // ---------------------------------------------------------------- 步驟詳情（從清單上方滑出，不蓋住清單）
  // 2026-10-28 驗收時改成從右側滑出、蓋住清單；2026-10-29 使用者改成在清單上方往下滑出：清單變短
  // 但一直看得到，可以直接點別的步驟換內容（選取的那一步在清單裡標出來）。上一步／下一步直接換內容，
  // 「收起」或 Esc 收回；換到「斷言」「運行資訊」也收回。
  const side = list.closest('.replay-side');
  const tabs = side ? side.querySelector('.replay-tabs') : null;
  const icon = path => '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="' + path + '"/></svg>';
  const drawer = document.createElement('section');
  drawer.className = 'replay-drawer';
  drawer.id = 'replay-drawer';
  drawer.setAttribute('aria-label', messages.step_detail || '');
  drawer.inert = true;
  drawer.innerHTML =
    '<div class="replay-drawer-inner"><div class="replay-drawer-head">' +
    '<div class="replay-drawer-title"></div>' +
    '<button type="button" class="replay-icon" data-drawer="prev" aria-label="' + esc(messages.prev_step || '') + '" title="' + esc(messages.prev_step || '') + '">' + icon('M6 15l6-6 6 6') + '</button>' +
    '<button type="button" class="replay-icon" data-drawer="next" aria-label="' + esc(messages.next_step || '') + '" title="' + esc(messages.next_step || '') + '">' + icon('M6 9l6 6-6 6') + '</button>' +
    '<button type="button" class="replay-icon" data-drawer="close" aria-label="' + esc(messages.close_detail || '') + '" title="' + esc(messages.close_detail || '') + '">' + icon('M6 6l12 12M18 6L6 18') + '</button>' +
    '</div><div class="replay-drawer-body"></div></div>';
  if (tabs) tabs.after(drawer);
  let shown = null;
  const drawerOpen = () => drawer.classList.contains('open');
  // 詳情展開後清單變短：選取的那一步留在看得到的地方
  const reveal = step => {
    const box = list.closest('.replay-tabpanel');
    const target = step && list.querySelector('.replay-row[data-index="' + step.index + '"]');
    if (!box || !target || box.hidden) return;
    const top = target.offsetTop - box.offsetTop - 6;
    const bottom = top + target.offsetHeight + 12;
    if (top < box.scrollTop) box.scrollTop = top;
    else if (bottom > box.scrollTop + box.clientHeight) box.scrollTop = bottom - box.clientHeight;
  };
  drawer.addEventListener('transitionend', () => reveal(shown));

  function openDetail(step, {focus = true} = {}) {
    if (!side || !step) return;
    shown = step;
    const head = drawer.querySelector('.replay-drawer-title');
    head.innerHTML = '<span class="replay-n ' + esc(step.status || '') + '">' + esc(numberOf(step)) + '</span>' +
      '<span class="replay-title"><strong></strong><small></small></span>';
    head.querySelector('strong').textContent = title(step);
    const node = composite && composite.nodes.find(each => each.id === step.node);
    head.querySelector('small').textContent = node
      ? node.id + ' · ' + node.sceneName
      : [step.action, step.target].filter(Boolean).join(' · ');
    head.classList.toggle('node', Boolean(node));
    head.style.setProperty('--node', node ? nodeColor(node.id) : '');
    const body = drawer.querySelector('.replay-drawer-body');
    body.textContent = '';
    body.appendChild(detail(step));
    body.scrollTop = 0;
    drawer.querySelector('[data-drawer="prev"]').disabled = step.index <= 1;
    drawer.querySelector('[data-drawer="next"]').disabled = step.index >= steps.length;
    for (const item of list.querySelectorAll('.replay-row')) {
      const mine = Number(item.dataset.index) === step.index;
      item.classList.toggle('selected', mine);
      if (mine) item.setAttribute('aria-current', 'true');
      else item.removeAttribute('aria-current');
    }
    const opening = !drawerOpen();
    drawer.classList.add('open');
    side.classList.add('detail-open');
    drawer.inert = false;
    if (!opening) reveal(step);
    if (opening && focus) drawer.querySelector('[data-drawer="close"]').focus({preventScroll: true});
  }
  function closeDetail({focus = true} = {}) {
    if (!drawerOpen()) return;
    drawer.classList.remove('open');
    if (side) side.classList.remove('detail-open');
    drawer.inert = true;
    const target = shown && list.querySelector('.replay-row[data-index="' + shown.index + '"]');
    for (const item of list.querySelectorAll('.replay-row.selected')) {
      item.classList.remove('selected');
      item.removeAttribute('aria-current');
    }
    shown = null;
    if (target && focus) target.focus({preventScroll: true});
  }

  drawer.addEventListener('click', async event => {
    const control = event.target.closest('[data-drawer]');
    if (control) {
      if (control.dataset.drawer === 'close') closeDetail();
      else if (shown) {
        const next = steps[shown.index - 1 + (control.dataset.drawer === 'next' ? 1 : -1)];
        if (next) choose(next.index, {focus: false});
      }
      return;
    }
    const action = event.target.closest('[data-act]');
    if (!action || !shown) return;
    const step = shown;
    if (action.dataset.act === 'play') {
      seek(leadIn(step), step);
      video.play();
    } else if (action.dataset.act === 'link') {
      const url = new URL(location.href);
      url.search = '';
      url.hash = '';
      url.searchParams.set('t', video.currentTime.toFixed(2));
      url.searchParams.set('step', step.id);
      try {
        await navigator.clipboard.writeText(url.href);
        toast(messages.copied);
      } catch {
        toast(fill(messages.copy_failed, {link: url.href}));
      }
    }
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && drawerOpen() && !document.fullscreenElement) {
      event.preventDefault();
      closeDetail();
    }
  });

  list.addEventListener('click', event => {
    const target = event.target.closest('.replay-row');
    if (target && !event.target.closest('a')) choose(Number(target.dataset.index));
  });
  list.addEventListener('keydown', event => {
    const target = event.target.closest('.replay-row');
    if (target && (event.key === 'Enter' || event.key === ' ')) {
      event.preventDefault();
      event.stopPropagation();
      choose(Number(target.dataset.index), {focus: false});
    }
  });

  // ---------------------------------------------------------------- 分頁、釘選

  document.querySelectorAll('[data-replay-tab]').forEach(tab => {
    tab.addEventListener('click', () => {
      closeDetail({focus: false});
      document.querySelectorAll('[data-replay-tab]').forEach(other => {
        const active = other === tab;
        other.setAttribute('aria-selected', String(active));
        $(other.getAttribute('aria-controls')).hidden = !active;
      });
    });
  });

  const pin = $('replay-pin');
  if (pin) {
    pin.addEventListener('click', async () => {
      const pinned = pin.getAttribute('aria-pressed') !== 'true';
      pin.disabled = true;
      let ok = false;
      try {
        const response = await fetch(pin.dataset.url || '/api/runs/' + encodeURIComponent(runId) + '/video', {
          method: 'PUT',
          headers: {'Content-Type': 'application/json', Accept: 'application/json'},
          body: JSON.stringify({pinned}),
        });
        ok = response.ok;
      } catch { ok = false; }
      pin.disabled = false;
      if (!ok) {
        toast(messages.pin_failed);
        return;
      }
      pin.setAttribute('aria-pressed', String(pinned));
      pin.textContent = pinned ? messages.pinned : messages.pin;
      const keep = $('replay-keep');
      if (keep) keep.hidden = pinned;
    });
  }

  // 運行還沒結束：結束後重新整理，錄影整理好就能回看
  const polling = document.querySelector('[data-poll-replay]');
  if (polling) {
    const poll = async () => {
      try {
        const response = await fetch(polling.dataset.url || '/api/runs/' + encodeURIComponent(runId), {headers: {Accept: 'application/json'}});
        if (response.ok && (await response.json()).finished) {
          location.reload();
          return;
        }
      } catch { /* 下次再試 */ }
      setTimeout(poll, 2000);
    };
    setTimeout(poll, 2000);
  }

  if (!playable) {
    // Python 節點的步驟時間軸（ADR 0020）：點章節看那一步；失敗的運行打開就停在失敗的那一步
    const chapters = document.querySelectorAll('[data-python-step]');
    const markChapter = index => chapters.forEach(button => button.classList.toggle('selected', Number(button.dataset.pythonStep) === index));
    chapters.forEach(button => button.addEventListener('click', () => {
      choose(Number(button.dataset.pythonStep), {focus: false});
      markChapter(Number(button.dataset.pythonStep));
    }));
    list.addEventListener('click', () => markChapter(selected));
    const first = failedStep || (chapters.length ? steps[Number(chapters[0].dataset.pythonStep) - 1] : null);
    if (first) shown = first;
    renderSteps();
    if (first && (failedStep || chapters.length)) {
      openDetail(first, {focus: false});
      markChapter(first.index);
    }
    return;
  }

  // ---------------------------------------------------------------- 縮圖

  const grabber = document.createElement('video');
  grabber.muted = true;
  grabber.preload = 'auto';
  const frames = new Map();
  let queue = Promise.resolve();
  const waitMedia = (target, event, action) => new Promise((resolve, reject) => {
    const cleanup = () => { clearTimeout(timer); target.removeEventListener(event, done); target.removeEventListener('error', fail); };
    const done = () => { cleanup(); resolve(); };
    const fail = () => { cleanup(); reject(new Error('media')); };
    const timer = setTimeout(fail, 5000);
    target.addEventListener(event, done, {once: true});
    target.addEventListener('error', fail, {once: true});
    try { action(); } catch { fail(); }
  });
  // 卡片那段時間沒有影片：縮圖與預覽畫成淺色的卡片（「n1 → n2」），不是黑的，免得看起來像黑屏
  // （2026-10-28 驗收）
  // Python 節點的步驟時間軸：每一步一張，寫上步驟編號與名稱
  function cardFrame(card, step = null) {
    const canvas = document.createElement('canvas');
    canvas.width = 384;
    canvas.height = 216;
    const context = canvas.getContext('2d');
    const segment = composite ? composite.segments[card.index] : null;
    const label = card.kind === 'transition'
      ? [segment && segment.prev, card.node].filter(Boolean).join(' → ')
      : step ? numberOf(step) : card.node || ((segment && segment.nodes) || []).join(', ');
    context.fillStyle = '#f4f7fb';
    context.fillRect(0, 0, canvas.width, canvas.height);
    context.fillStyle = nodeColor(card.node) || '#546479';
    context.fillRect(0, 0, 10, canvas.height);
    context.font = '600 52px ui-monospace, SFMono-Regular, Consolas, monospace';
    context.textAlign = 'center';
    context.textBaseline = 'middle';
    context.fillText(label, canvas.width / 2 + 5, canvas.height / 2 - (step ? 22 : 0));
    if (step) {
      const name = title(step);
      context.font = '500 28px system-ui, sans-serif';
      context.fillStyle = step.status === 'failed' ? '#c0362c' : '#334155';
      context.fillText(name.length > 20 ? name.slice(0, 19) + '…' : name, canvas.width / 2 + 5, canvas.height / 2 + 36);
    }
    return canvas;
  }
  // 錄影裡某一刻的畫面。快取依影片的格（每秒 25 格），不是 0.1 秒取整：相鄰的兩步不會共用同一張
  function grab(seconds, pageId) {
    const found = video.cardAt ? video.cardAt(seconds) : null;
    const card = found && (!pageId || found.kind === 'python') ? found : null;
    if (card) {
      // 那一格裡的步驟：不用 stepAt 的容差，一步的最後一刻（frameTime）不能算成下一步
      const step = card.kind === 'python'
        ? timed.filter(each => each.node === card.node && each.start <= seconds).pop() || null : null;
      const key = 'card:' + card.index + (step ? ':' + step.index : '');
      if (!frames.has(key)) frames.set(key, cardFrame(card, step));
      return Promise.resolve(frames.get(key));
    }
    const clip = video.clipAt(seconds, pageId);
    const local = clip ? Math.max(0, seconds - clip.start) : 0;
    const key = (clip ? clip.pageId : 'gap') + ':' + Math.round(local * FPS);
    if (frames.has(key)) return Promise.resolve(frames.get(key));
    queue = queue.then(async () => {
      if (frames.has(key)) return frames.get(key);
      const canvas = document.createElement('canvas');
      canvas.width = 384;
      canvas.height = Math.round(384 * ((clip && clip.height) || 9) / ((clip && clip.width) || 16));
      if (clip) {
        try {
          if (grabber.getAttribute('src') !== clip.url) {
            await waitMedia(grabber, 'loadeddata', () => { grabber.src = clip.url; });
          }
          const position = Math.min(Math.round(local * FPS) / FPS, Math.max(0, grabber.duration - 0.04));
          if (Math.abs(grabber.currentTime - position) > 0.001) {
            await waitMedia(grabber, 'seeked', () => { grabber.currentTime = position; });
          }
          canvas.getContext('2d').drawImage(grabber, 0, 0, canvas.width, canvas.height);
        } catch { /* 缺片或讀取失敗留空白，不借用其他分頁的縮圖 */ }
      }
      frames.set(key, canvas);
      return canvas;
    });
    return queue;
  }
  const draw = (canvas, frame) => {
    if (canvas.isConnected) canvas.getContext('2d').drawImage(frame, 0, 0, canvas.width, canvas.height);
  };
  const nearest = seconds => {
    const clip = video.clipAt(seconds);
    if (!clip) return null;
    let best = null;
    let distance = Infinity;
    for (const [key, canvas] of frames) {
      const [pageId, tick] = key.split(':');
      if (pageId !== clip.pageId) continue;
      const gap = Math.abs(Number(tick) / FPS - (seconds - clip.start));
      if (gap < distance) { distance = gap; best = canvas; }
    }
    return best;
  };
  // 執行端拍的截圖（滑過預覽要畫到 canvas 上）
  const images = new Map();
  const shotImage = url => {
    if (!images.has(url)) {
      images.set(url, new Promise(resolve => {
        const image = new Image();
        image.onload = () => resolve(image);
        image.onerror = () => resolve(null);
        image.src = url;
      }));
    }
    return images.get(url);
  };

  // ---------------------------------------------------------------- 卡片（合併回看）

  const cardBox = $('replay-card');
  let cardStep = null;
  const showCard = card => {
    if (!cardBox) return;
    const source = card && document.getElementById('replay-card-' + card.index);
    cardBox.hidden = !source;
    cardBox.textContent = '';
    cardStep = null;
    if (source) cardBox.appendChild(source.content.cloneNode(true));
  };
  // Python 節點的那一段：卡片內容換成目前那一步（sync 呼叫，步驟沒換時不重畫）
  const fillPythonCard = step => {
    const body = cardBox && cardBox.querySelector('[data-python-card]');
    if (!body || step === cardStep) return;
    cardStep = step;
    body.textContent = '';
    if (!step) return;
    const head = document.createElement('div');
    head.className = 'creplay-python-step';
    head.innerHTML = '<span class="replay-n ' + esc(step.status || '') + '">' + esc(numberOf(step)) + '</span><strong></strong>';
    head.querySelector('strong').textContent = title(step);
    body.appendChild(head);
    const box = detail(step);
    const actions = box.querySelector('.actions');
    if (actions) actions.remove();
    body.appendChild(box);
  };
  video.addEventListener('card', event => { showCard(event.detail); sync(); });
  showCard(video.card);

  // ---------------------------------------------------------------- 時間軸的排法（axis）
  // pieces：依時間排好、首尾相接的一段一段，各自對應時間軸上的 [x0, x1)。依時間只有一段；依步驟是
  // 「步驟」（一步一格）、「空檔」（折疊）與「卡片」。時間 ↔ 位置都用它換算。

  const film = $('replay-film');
  const past = $('replay-past');
  let axisMode = store.get('rpa.replay.axis') === 'time' ? 'time' : 'steps';
  let zooms = []; // 放大的章（可以再往下放大一層），最後一個是目前看的範圍
  let axis = null;

  // 時間軸上的一段一段：組合回看是各節點的錄影與卡片，單一運行是整段錄影
  const ranges = () => composite
    ? composite.segments.map(segment => ({
      kind: segment.kind, node: segment.node || null, segment,
      start: segment.startMs / 1000, end: (segment.startMs + segment.durationMs) / 1000,
    }))
    : [{kind: 'video', node: null, segment: null, start: 0, end: duration}];

  function buildPieces(from, to) {
    const pieces = [];
    const push = piece => { if (piece.t1 - piece.t0 > 0.0005) pieces.push(piece); };
    for (const range of ranges()) {
      const start = Math.max(range.start, from);
      const end = Math.min(range.end, to);
      if (end - start <= 0.0005) continue;
      if (range.kind !== 'video' && range.kind !== 'python') {
        push({kind: 'card', t0: start, t1: end, range});
        continue;
      }
      const inside = timed.filter(step =>
        (!composite || step.node === range.node) && step.start >= start - 0.0005 && step.start < end);
      if (!inside.length) {
        push({kind: 'gap', t0: start, t1: end, range});
        continue;
      }
      let cursor = start;
      if (inside[0].start - start >= FOLD) {
        push({kind: 'gap', t0: start, t1: inside[0].start, range});
        cursor = inside[0].start;
      }
      inside.forEach((step, index) => {
        const next = index + 1 < inside.length ? inside[index + 1].start : end;
        const done = Math.max(step.start, step.end != null ? step.end : step.start, step.shotTime != null ? step.shotTime : 0);
        if (next - done >= FOLD) {
          const until = Math.min(next, done + TAIL);
          push({kind: 'step', t0: cursor, t1: until, step, range});
          push({kind: 'gap', t0: until, t1: next, range});
        } else {
          push({kind: 'step', t0: cursor, t1: next, step, range});
        }
        cursor = next;
      });
    }
    return pieces;
  }

  function arrange(pieces, width) {
    const count = kind => pieces.filter(piece => piece.kind === kind).length;
    const stepCount = count('step');
    let gapWidth = GAP_W;
    let cardWidth = CARD_W;
    let fixed = count('gap') * gapWidth + count('card') * cardWidth;
    // 空檔與卡片太多（例如很多沒有錄影的節點）：一起縮小，至少留一半給步驟
    const limit = stepCount ? width / 2 : width;
    if (fixed > limit) {
      gapWidth *= limit / fixed;
      cardWidth *= limit / fixed;
      fixed = limit;
    }
    const room = Math.max(0, width - fixed);
    const dense = stepCount > 0 && room / stepCount < STEP_MIN;
    // 寬度依步驟的時長（開根號，長的不會佔掉全部），每步至少 STEP_MIN
    const weights = pieces.map(piece => (piece.kind === 'step' ? Math.sqrt(Math.max(0.05, piece.t1 - piece.t0)) : 0));
    const total = weights.reduce((sum, value) => sum + value, 0) || 1;
    const extra = dense ? 0 : room - stepCount * STEP_MIN;
    let x = 0;
    pieces.forEach((piece, index) => {
      const size = piece.kind === 'gap' ? gapWidth : piece.kind === 'card' ? cardWidth
        : dense ? room / stepCount : STEP_MIN + extra * weights[index] / total;
      piece.x0 = x;
      piece.x1 = x + size;
      x += size;
    });
    if (!stepCount && x > 0) {
      for (const piece of pieces) { piece.x0 *= width / x; piece.x1 *= width / x; }
    }
    return {mode: 'steps', pieces, width, dense};
  }

  const view = () => (zooms.length ? zooms[zooms.length - 1] : {t0: 0, t1: duration});
  const pieceAt = seconds => {
    const pieces = axis ? axis.pieces : [];
    for (const piece of pieces) if (seconds < piece.t1) return piece;
    return pieces[pieces.length - 1] || null;
  };
  const xAt = seconds => {
    const piece = pieceAt(seconds);
    if (!piece) return 0;
    const ratio = Math.min(1, Math.max(0, (seconds - piece.t0) / ((piece.t1 - piece.t0) || 1)));
    return piece.x0 + ratio * (piece.x1 - piece.x0);
  };
  const tAt = x => {
    const pieces = axis ? axis.pieces : [];
    const piece = pieces.find(each => x < each.x1) || pieces[pieces.length - 1];
    if (!piece) return 0;
    const ratio = Math.min(1, Math.max(0, (x - piece.x0) / ((piece.x1 - piece.x0) || 1)));
    return piece.t0 + ratio * (piece.t1 - piece.t0);
  };
  const inView = seconds => {
    const range = view();
    return seconds >= range.t0 - 0.001 && seconds <= range.t1 + 0.001;
  };

  // 太擠時可以放大的章：組合回看是節點的錄影；單一運行（或已經放大的一章）每幾步一組
  function chapters() {
    if (axis.mode !== 'steps' || !axis.dense) return [];
    if (composite && !zooms.length) {
      return ranges().filter(range => range.kind === 'video' || range.kind === 'python').map(range => {
        const node = composite.nodes.find(each => each.id === range.node);
        return {t0: range.start, t1: range.end, label: range.node + (node ? ' ' + node.sceneName : '')};
      });
    }
    const pieces = axis.pieces.filter(piece => piece.kind === 'step');
    const size = Math.max(5, Math.floor(axis.width / STEP_MIN) - 2);
    const groups = [];
    for (let index = 0; index < pieces.length; index += size) {
      const group = pieces.slice(index, index + size);
      const following = pieces[index + size];
      const from = group[0].step;
      const to = group[group.length - 1].step;
      groups.push({
        t0: index ? group[0].t0 : axis.pieces[0].t0,
        t1: following ? following.t0 : axis.pieces[axis.pieces.length - 1].t1,
        text: (from.nodeIndex || from.index) + '–' + (to.nodeIndex || to.index),
        label: fill(messages.group || '{from}–{to}', {from: numberOf(from), to: numberOf(to)}),
        group: true,
      });
    }
    return groups.length > 1 ? groups : [];
  }
  function zoomInto(chapter) {
    zooms.push({t0: chapter.t0, t1: chapter.t1, label: chapter.label});
    // 先跳進這一章再重畫：sync 看到播放位置在放大的範圍外會回到整次
    if (!inView(video.currentTime)) video.seek(clamp(chapter.t0));
    layout();
  }

  // 播放經過折疊的空檔時 4× 快轉（只在依步驟時；可以在控制列關掉）。空檔的最後 PREROLL 秒照原速，
  // 點步驟跳到它開始前時看得到動作前的畫面。
  const skimToggle = $('replay-skim-toggle');
  if (skimToggle) {
    skimToggle.checked = store.get('rpa.replay.skim') !== 'off';
    skimToggle.addEventListener('change', () => {
      store.set('rpa.replay.skim', skimToggle.checked ? 'on' : 'off');
      updateSkim();
    });
  }
  function updateSkim() {
    const on = Boolean(axis) && axis.mode === 'steps' && (!skimToggle || skimToggle.checked);
    const folds = on ? buildPieces(0, duration).filter(piece => piece.kind === 'gap')
      .map(piece => [piece.t0, piece.t1 - PREROLL]).filter(([start, end]) => end - start > 0.2) : [];
    video.setSkim(folds);
  }
  video.addEventListener('skim', event => {
    const badge = $('replay-skim');
    if (badge) badge.hidden = !event.detail;
  });

  const axisButtons = document.querySelectorAll('[data-axis]');
  const showMode = () => axisButtons.forEach(button =>
    button.setAttribute('aria-pressed', String(button.dataset.axis === axisMode)));
  axisButtons.forEach(button => button.addEventListener('click', () => {
    if (button.dataset.axis === axisMode) return;
    axisMode = button.dataset.axis === 'time' ? 'time' : 'steps';
    store.set('rpa.replay.axis', axisMode);
    zooms = [];
    showMode();
    layout();
  }));
  showMode();
  const unzoom = $('replay-unzoom');
  if (unzoom) {
    unzoom.addEventListener('click', () => {
      zooms = [];
      layout();
    });
  }

  // ---------------------------------------------------------------- 時間軸

  const timeline = $('replay-timeline');
  const track = $('replay-track');
  const ticks = $('replay-ticks');
  const playhead = $('replay-playhead');
  const hoverline = $('replay-hoverline');
  const preview = $('replay-preview');
  const previewCanvas = $('replay-preview-canvas');
  const timeAt = clientX => {
    const rect = film.getBoundingClientRect();
    return Math.min(duration, Math.max(0, tAt(clientX - rect.left)));
  };

  // 一格縮圖：步驟（截圖或錄影裡那一步做完的畫面）、錄影某一刻、空檔、卡片
  function tile(x0, x1, kind, {step = null, seconds = null, piece = null} = {}) {
    const box = document.createElement('div');
    box.className = 'replay-tile ' + kind + (step && step.status === 'failed' ? ' failed' : '');
    box.style.left = x0 + 'px';
    box.style.width = Math.max(1, x1 - x0 - 1) + 'px';
    if (step) box.dataset.index = step.index;
    film.insertBefore(box, past);
    if (kind === 'gap') {
      box.textContent = '⋯';
      box.title = fill(messages.gap || '', {seconds: (piece.t1 - piece.t0).toFixed(1)});
      box.classList.add('ready');
      return box;
    }
    if (kind === 'card') {
      const card = piece.range.segment;
      box.style.setProperty('--node', nodeColor(piece.range.node) || '#546479');
      box.textContent = card.kind === 'transition' ? '→' : piece.range.node || '…';
      box.title = cardTitle({index: card.index, kind: card.kind, node: card.node});
      box.classList.add('ready');
      return box;
    }
    if (step && x1 - x0 >= 30) {
      const label = document.createElement('b');
      label.textContent = composite ? step.label : String(step.index);
      box.appendChild(label);
    }
    if (step && step.shot) {
      const image = new Image();
      image.alt = '';
      image.decoding = 'async';
      image.onload = () => box.classList.add('ready');
      image.onerror = () => { image.remove(); frameInto(box, frameTime(step), step.pageId); };
      image.src = step.shot;
      box.prepend(image);
      return box;
    }
    frameInto(box, step ? frameTime(step) : seconds, step ? step.pageId : undefined);
    return box;
  }
  function frameInto(box, seconds, pageId) {
    const canvas = document.createElement('canvas');
    canvas.width = 192;
    canvas.height = 108;
    box.prepend(canvas);
    grab(clamp(seconds), pageId).then(frame => {
      if (!box.isConnected) return;
      draw(canvas, frame);
      box.classList.add('ready');
    });
  }

  function stepTiles(groups) {
    const starts = new Set(groups.map(group => group.t0));
    // 太擠（一步不到 THUMB_MIN 寬）：連續的步驟每幾步合成一格縮圖（至少 48 px，不跨過空檔、卡片
    // 與分組），畫裡面最重要的一步：失敗、選取的、開網址與點擊等，其次是最前面那一步
    const rank = step => (step.status === 'failed' ? 0 : step.index === selected ? 1 : KEY_ACTIONS.has(step.action) ? 2 : 3);
    let bunch = [];
    const flush = () => {
      if (!bunch.length) return;
      const best = bunch.reduce((one, other) => (rank(other.step) < rank(one.step) ? other : one));
      tile(bunch[0].x0, bunch[bunch.length - 1].x1, 'step key', {step: best.step, piece: best});
      bunch = [];
    };
    for (const piece of axis.pieces) {
      if (piece.kind !== 'step') {
        flush();
        tile(piece.x0, piece.x1, piece.kind, {piece});
        continue;
      }
      const width = piece.x1 - piece.x0;
      if (width >= THUMB_MIN) {
        // 很寬的一格（長的步驟、步驟很少）：第一張是這一步做完的畫面，後面用錄影補幾張那時候的畫面
        const count = Math.max(1, Math.round(width / TILE_W));
        const size = width / count;
        tile(piece.x0, piece.x0 + size, 'step', {step: piece.step, piece});
        for (let n = 1; n < count; n += 1) {
          const x = piece.x0 + n * size;
          tile(x, x + size, 'frame', {seconds: tAt(x + size / 2), piece});
        }
        continue;
      }
      if (starts.has(piece.t0)) flush();
      bunch.push(piece);
      if (piece.x1 - bunch[0].x0 >= 48) flush();
    }
    flush();
  }

  function timeTiles() {
    const width = axis.width;
    const count = Math.max(4, Math.round(width / (width < 480 ? 64 : TILE_W)));
    for (let index = 0; index < count; index += 1) {
      tile(index / count * width, (index + 1) / count * width + 1, 'frame', {seconds: (index + 0.5) / count * duration});
    }
  }

  function drawTrack() {
    track.textContent = '';
    if (axis.mode === 'steps') {
      for (const piece of axis.pieces) {
        if (piece.kind === 'card') continue;
        const segment = document.createElement('div');
        const step = piece.step;
        segment.className = 'replay-seg' + (piece.kind === 'gap' ? ' gap'
          : step.status === 'failed' ? ' failed' : step.status === 'skipped' ? ' skipped' : '');
        segment.style.left = piece.x0 + 'px';
        segment.style.width = Math.max(2, piece.x1 - piece.x0 - 1) + 'px';
        if (step) {
          segment.dataset.index = step.index;
          segment.title = numberOf(step) + ' · ' + title(step);
        } else {
          segment.title = fill(messages.gap || '', {seconds: (piece.t1 - piece.t0).toFixed(1)});
        }
        track.appendChild(segment);
      }
      return;
    }
    for (const step of timed) {
      const segment = document.createElement('div');
      const start = Math.min(step.start, duration);
      const end = Math.min(step.end != null ? step.end : step.start, duration);
      segment.className = 'replay-seg' + (step.status === 'failed' ? ' failed' : step.status === 'skipped' ? ' skipped' : '');
      segment.dataset.index = step.index;
      segment.style.left = xAt(start) + 'px';
      segment.style.width = Math.max(3, xAt(end) - xAt(start)) + 'px';
      segment.title = numberOf(step) + ' · ' + title(step);
      track.appendChild(segment);
    }
  }

  function drawBands(groups) {
    const bands = $('replay-bands');
    if (!bands) return;
    bands.textContent = '';
    const range = view();
    const add = (t0, t1, className, text, hint, onClick) => {
      const band = document.createElement('button');
      band.type = 'button';
      band.className = 'replay-band ' + className;
      const x0 = xAt(Math.max(t0, range.t0));
      band.style.left = x0 + 'px';
      band.style.width = Math.max(3, xAt(Math.min(t1, range.t1) - 0.0001) - x0) + 'px';
      band.textContent = text;
      band.title = hint;
      band.tabIndex = -1;
      band.addEventListener('pointerdown', event => event.stopPropagation());
      band.addEventListener('click', onClick);
      bands.appendChild(band);
      return band;
    };
    if (composite) {
      for (const segment of composite.segments) {
        const t0 = segment.startMs / 1000;
        const t1 = (segment.startMs + segment.durationMs) / 1000;
        if (t1 <= range.t0 + 0.0005 || t0 >= range.t1 - 0.0005) continue;
        const chapter = segment.kind === 'video' || segment.kind === 'python'
          ? groups.find(each => !each.group && Math.abs(each.t0 - t0) < 0.001) : null;
        const text = ['video', 'python', 'reused', 'no_video'].includes(segment.kind) ? segment.node : '';
        const hint = (segment.kind === 'video' ? segment.node
          : fill(messages['card_' + segment.kind] || '', {node: segment.node || '', prev: segment.prev || '', nodes: (segment.nodes || []).join(', ')}))
          + (chapter ? ' · ' + (messages.zoom_hint || '') : '');
        const band = add(t0, t1, segment.kind + (segment.status ? ' ' + segment.status : '') + (chapter ? ' zoomable' : ''), text, hint, () => {
          selected = null;
          closeDetail({focus: false});
          if (chapter) zoomInto(chapter);
          seek(t0);
          renderSteps();
        });
        if (segment.node && segment.kind !== 'transition') band.style.setProperty('--node', nodeColor(segment.node));
      }
    }
    for (const group of groups.filter(each => each.group)) {
      add(group.t0, group.t1, 'group zoomable', group.text, group.label + ' · ' + (messages.zoom_hint || ''), () => {
        zoomInto(group);
        seek(group.t0);
      });
    }
    bands.hidden = !bands.childElementCount;
  }

  function drawTicks() {
    ticks.textContent = '';
    const label = (x, seconds) => {
      const item = document.createElement('span');
      item.style.left = x + 'px';
      item.textContent = axis.mode === 'steps' ? fmt(seconds) : fmt(seconds).slice(0, 5);
      ticks.appendChild(item);
    };
    if (axis.mode === 'steps') {
      // 不是等比例：標在每一章與步驟開始的地方（實際時間），擠的時候跳過（第一個靠左，其餘置中）
      let last = null;
      for (const piece of axis.pieces) {
        if (piece.kind === 'gap') continue;
        const seconds = piece.kind === 'step' ? piece.step.start : piece.t0;
        if ((last === null || piece.x0 - last >= (last === 0 ? 84 : 72)) && piece.x0 < axis.width - 36) {
          label(piece.x0, seconds);
          last = piece.x0;
        }
      }
      return;
    }
    const every = duration > 600 ? 120 : duration > 120 ? 30 : duration > 40 ? 10 : duration > 15 ? 5 : 2;
    for (let seconds = 0; seconds <= duration - every * 0.4; seconds += every) label(xAt(seconds), seconds);
  }

  function drawZoomBar() {
    const bar = $('replay-zoom');
    if (!bar) return;
    bar.hidden = !zooms.length;
    $('replay-zoom-label').textContent = zooms.map(each => each.label).join(' › ');
  }

  function layout() {
    if (!duration) return;
    const width = film.clientWidth;
    const range = view();
    // 沒有任何有時間的步驟（例如步驟紀錄不完整）時，依步驟排不出東西：照時間排
    axis = axisMode === 'steps' && timed.length ? arrange(buildPieces(range.t0, range.t1), width) : null;
    if (!axis || !axis.pieces.length) {
      axis = {mode: 'time', pieces: [{kind: 'time', t0: 0, t1: duration, x0: 0, x1: width}], width, dense: false};
    }
    film.querySelectorAll('.replay-tile').forEach(each => each.remove());
    film.classList.toggle('by-steps', axis.mode === 'steps');
    const groups = chapters();
    if (axis.mode === 'steps') stepTiles(groups);
    else timeTiles();
    drawTrack();
    drawBands(groups);
    drawTicks();
    drawZoomBar();
    updateSkim();
    timeline.setAttribute('aria-valuemax', duration.toFixed(2));
    sync(true);
  }

  let scrubbing = false;
  let resume = false;
  let hoverTimer = 0;
  timeline.addEventListener('pointerdown', event => {
    scrubbing = true;
    resume = !video.paused;
    video.pause();
    timeline.setPointerCapture(event.pointerId);
    seek(timeAt(event.clientX));
    showPreview(event.clientX);
  });
  timeline.addEventListener('pointermove', event => {
    if (scrubbing) seek(timeAt(event.clientX));
    showPreview(event.clientX);
  });
  const endScrub = () => {
    if (!scrubbing) return;
    scrubbing = false;
    if (resume) video.play();
  };
  timeline.addEventListener('pointerup', endScrub);
  timeline.addEventListener('pointercancel', endScrub);
  timeline.addEventListener('pointerleave', () => {
    if (!scrubbing) {
      preview.hidden = true;
      hoverline.hidden = true;
    }
  });
  timeline.addEventListener('keydown', event => {
    const keys = {ArrowLeft: -1, ArrowRight: 1, PageDown: -10, PageUp: 10};
    if (event.key in keys) {
      event.preventDefault();
      event.stopPropagation();
      seek(video.currentTime + keys[event.key] * (event.shiftKey ? 5 : 1));
    }
  });

  // 滑過時間軸：這一刻的畫面與步驟。依步驟時，滑到一步的縮圖上是那一步做完的截圖
  function showPreview(clientX) {
    if (!duration || !axis) return;
    const seconds = timeAt(clientX);
    const rect = timeline.getBoundingClientRect();
    const filmLeft = film.getBoundingClientRect().left;
    const x = clientX - rect.left;
    hoverline.hidden = false;
    hoverline.style.left = x + 'px';
    preview.hidden = false;
    preview.style.left = Math.min(rect.width - preview.offsetWidth - 6, Math.max(6, x - preview.offsetWidth / 2)) + 'px';
    $('replay-preview-time').textContent = fmt(seconds);
    const piece = pieceAt(seconds);
    const found = video.cardAt ? video.cardAt(seconds) : null;
    const card = found && found.kind !== 'python' ? found : null;
    const step = piece && piece.kind === 'step' ? piece.step : piece && piece.kind === 'gap' ? null : stepAt(seconds);
    const first = piece && piece.kind === 'step' ? (piece.x1 - piece.x0) / Math.max(1, Math.round((piece.x1 - piece.x0) / TILE_W)) : 0;
    const onShot = Boolean(piece && piece.kind === 'step' && step.shot && clientX - filmLeft < piece.x0 + first);
    const label = card ? cardTitle(card)
      : piece && piece.kind === 'gap' ? fill(messages.gap || '', {seconds: (piece.t1 - piece.t0).toFixed(1)})
      : step ? numberOf(step) + ' · ' + title(step) + (onShot ? ' · ' + (messages.shot_source || '') : '')
      : messages.open_browser;
    $('replay-preview-step').textContent = label;
    const context = previewCanvas.getContext('2d');
    clearTimeout(hoverTimer);
    if (onShot) {
      shotImage(step.shot).then(image => {
        if (image && !preview.hidden && Math.abs(timeAt(clientX) - seconds) < 0.01) {
          context.drawImage(image, 0, 0, previewCanvas.width, previewCanvas.height);
        }
      });
      return;
    }
    const near = card ? null : nearest(seconds);
    if (near) context.drawImage(near, 0, 0, previewCanvas.width, previewCanvas.height);
    hoverTimer = setTimeout(() => grab(seconds).then(frame => {
      if (!preview.hidden && Math.abs(timeAt(clientX) - seconds) < 0.01) {
        context.drawImage(frame, 0, 0, previewCanvas.width, previewCanvas.height);
      }
    }), 120);
  }

  // ---------------------------------------------------------------- 播放與同步

  function seek(seconds, step = null) {
    const clip = step && video.clips.find(item => item.pageId === step.pageId);
    const start = clip ? Math.max(seconds, clip.start) : seconds;
    video.seek(clamp(start), step ? {pageId: step.pageId, until: step.start} : null);
    sync();
  }

  let lastStep = -1;
  function sync(force) {
    const seconds = video.currentTime;
    // 放大一章時播到外面（或跳到別的地方）：回到整次
    if (axis && zooms.length && !inView(seconds) && !scrubbing) {
      zooms = [];
      layout();
      return;
    }
    $('replay-now').textContent = fmt(seconds);
    const x = axis ? xAt(seconds) : 0;
    playhead.hidden = !axis;
    playhead.style.left = (film.offsetLeft + x) + 'px';
    past.style.width = x + 'px';
    // Python 節點的那一段也是卡片，但有步驟：照步驟顯示，卡片內容換成目前那一步
    const python = video.card && video.card.kind === 'python' ? video.card : null;
    const card = python ? null : video.card;
    const step = card ? null : shownAt(seconds);
    if (python) fillPythonCard(step && step.node === python.node ? step : null);
    const state = step ? stateOf(step, seconds) : 'upcoming';
    $('replay-chip-n').textContent = step ? numberOf(step) : '—';
    $('replay-chip-n').style.background = composite && step ? nodeColor(step.node) : '';
    $('replay-chip-state').className = 'replay-chip-state ' + (step ? state : '');
    $('replay-chip-text').textContent = card ? cardTitle(card) : step
      ? [title(step), [step.action, step.target].filter(Boolean).join(' ')].join(' · ')
      : messages.open_browser;
    $('replay-step-of').textContent = step
      ? fill(messages.step_of, {n: step.index, total: steps.length})
      : card ? '' : messages.open_browser;
    let url = 'about:blank';
    if (step && step.action === 'python') {
      url = step.target || '—';
    } else if (step) {
      const before = timed[timed.indexOf(step) - 1];
      const same = before && before.node === step.node ? before : null;
      url = seconds < (step.end != null ? step.end : step.start) ? (same ? same.url : 'about:blank') : step.url;
    }
    const where = composite ? nodeAt(seconds) : null;
    $('replay-url').textContent = card ? '—' : (where ? where.id + ' · ' : '') + (url || 'about:blank');
    if (composite) {
      for (const head of list.querySelectorAll('.replay-node-head')) {
        head.classList.toggle('current', Boolean(where) && !card && head.dataset.node === where.id);
      }
    }
    timeline.setAttribute('aria-valuenow', seconds.toFixed(2));
    timeline.setAttribute('aria-valuetext', fmt(seconds) + (step ? ' · ' + step.index + ' ' + title(step) : ''));
    const index = step ? step.index : 0;
    if (index !== lastStep || force) {
      track.querySelectorAll('.replay-seg[data-index]').forEach(segment => {
        segment.classList.toggle('current', Number(segment.dataset.index) === index);
      });
      film.querySelectorAll('.replay-tile[data-index]').forEach(each => {
        each.classList.toggle('current', Number(each.dataset.index) === index);
      });
    }
    for (const item of list.querySelectorAll('.replay-row')) {
      const each = steps[Number(item.dataset.index) - 1];
      item.classList.toggle('current', Boolean(step) && each.index === step.index);
      item.querySelector('[data-n]').className = 'replay-n ' + stateOf(each, seconds);
    }
    if ((index !== lastStep || force) && index && $('replay-follow').checked) {
      const target = list.querySelector('.replay-row[data-index="' + index + '"]');
      const box = list.closest('.replay-tabpanel');
      if (target && box && !box.hidden) {
        const top = target.offsetTop - box.offsetTop - 6;
        const bottom = top + target.offsetHeight + 12;
        if (top < box.scrollTop) box.scrollTop = top;
        else if (bottom > box.scrollTop + box.clientHeight) box.scrollTop = bottom - box.clientHeight;
      }
    }
    lastStep = index;
    const end = $('replay-end');
    if (end) end.hidden = !(duration && seconds >= duration - 0.06 && video.paused && failedStep);
  }

  function setPlaying() {
    const playing = !video.paused;
    $('replay-play-icon').innerHTML = playing
      ? '<path d="M7 5h4v14H7zm6 0h4v14h-4z"/>'
      : '<path d="M8 5.5v13l10.5-6.5z"/>';
    $('replay-play').setAttribute('aria-label', playing ? messages.pause : messages.play);
    $('replay-bigplay').hidden = playing;
  }
  const toggle = () => {
    if (video.paused) {
      if (video.currentTime >= duration - 0.06) seek(0);
      video.play();
    } else {
      video.pause();
    }
  };
  let frame = 0;
  const loop = () => {
    sync();
    frame = video.paused ? 0 : requestAnimationFrame(loop);
  };
  video.addEventListener('play', () => {
    setPlaying();
    if (!frame) frame = requestAnimationFrame(loop);
  });
  video.addEventListener('pause', () => { setPlaying(); sync(); });
  video.addEventListener('seeked', () => sync());
  video.addEventListener('ended', () => { setPlaying(); sync(); });
  video.addEventListener('click', toggle);
  $('replay-play').addEventListener('click', toggle);
  $('replay-bigplay').addEventListener('click', toggle);

  // 上一步／下一步：依步驟的順序，不依時間找（步驟常常比 PREROLL 還短）。
  // 上一步時，已經播到這一步 1 秒以後就先回到這一步的開頭。
  const jump = direction => {
    const now = video.currentTime;
    const current = shownAt(now);
    const position = current ? timed.indexOf(current) : -1;
    let target;
    if (direction > 0) target = timed[position + 1];
    else if (current && now > current.start + 1) target = current;
    else target = position > 0 ? timed[position - 1] : null;
    if (target) {
      selected = target.index;
      seek(leadIn(target), target);
      if (drawerOpen()) shown = target;
      renderSteps();
      if (drawerOpen()) openDetail(target, {focus: false});
    } else if (direction < 0) {
      seek(0);
    }
  };
  // 下一個／上一個節點（合併回看）：上一個時，已經播到這個節點 1 秒以後就先回到它的開頭
  const jumpNode = direction => {
    if (!composite) return;
    const starts = composite.nodes.filter(node => node.startMs != null);
    const now = video.currentTime;
    const current = nodeAt(now);
    const position = current ? starts.indexOf(current) : -1;
    let target;
    if (direction > 0) target = starts[position + 1];
    else if (current && now > current.startMs / 1000 + 1) target = current;
    else target = position > 0 ? starts[position - 1] : null;
    if (target) seekNode(target.id);
  };
  $('replay-prev').addEventListener('click', () => jump(-1));
  $('replay-next').addEventListener('click', () => jump(1));
  const step = direction => {
    video.pause();
    seek(video.currentTime + direction / FPS);
  };
  $('replay-frame-back').addEventListener('click', () => step(-1));
  $('replay-frame-forward').addEventListener('click', () => step(1));
  const rates = [0.25, 0.5, 1, 2];
  const setRate = rate => {
    video.playbackRate = rate;
    $('replay-speed').querySelectorAll('button').forEach(button =>
      button.setAttribute('aria-pressed', String(Number(button.dataset.rate) === rate)));
  };
  $('replay-speed').addEventListener('click', event => {
    const button = event.target.closest('button');
    if (button) setRate(Number(button.dataset.rate));
  });
  $('replay-fullscreen').addEventListener('click', () => {
    const stage = $('replay-stage');
    const request = document.fullscreenElement ? document.exitFullscreen() : stage.requestFullscreen && stage.requestFullscreen();
    if (request && request.catch) request.catch(() => {});
  });
  $('replay-help-button').addEventListener('click', () => {
    const help = $('replay-help');
    help.hidden = !help.hidden;
    $('replay-help-button').setAttribute('aria-expanded', String(!help.hidden));
  });
  const endCard = $('replay-end');
  if (endCard) {
    endCard.addEventListener('click', event => {
      const button = event.target.closest('[data-go]');
      if (!button) return;
      if (button.dataset.go === 'failed') choose(failedStep.index);
      else { seek(0); video.play(); }
    });
  }

  document.addEventListener('keydown', event => {
    if (event.target.closest('input, textarea, select, [contenteditable]') || event.metaKey || event.ctrlKey || event.altKey) return;
    if (event.key === ' ' && event.target.closest('button, a, .replay-row')) return;
    const keys = {
      ' ': toggle, k: toggle, K: toggle,
      ArrowLeft: () => seek(video.currentTime - (event.shiftKey ? 5 : 1)),
      ArrowRight: () => seek(video.currentTime + (event.shiftKey ? 5 : 1)),
      ',': () => step(-1), '.': () => step(1),
      j: () => jump(-1), J: () => jump(-1), l: () => jump(1), L: () => jump(1),
      e: () => failedStep && choose(failedStep.index), E: () => failedStep && choose(failedStep.index),
      n: () => jumpNode(1), N: () => jumpNode(1), p: () => jumpNode(-1), P: () => jumpNode(-1),
      '[': () => setRate(rates[Math.max(0, rates.indexOf(video.playbackRate) - 1)]),
      ']': () => setRate(rates[Math.min(rates.length - 1, rates.indexOf(video.playbackRate) + 1)]),
      f: () => $('replay-fullscreen').click(), F: () => $('replay-fullscreen').click(),
      '?': () => $('replay-help-button').click(),
      Home: () => seek(0), End: () => seek(duration),
    };
    if (keys[event.key]) {
      event.preventDefault();
      keys[event.key]();
    }
  });

  // ---------------------------------------------------------------- 開始

  video.addEventListener('error', () => {
    $('replay-cannot-play').hidden = false;
  });
  // 知道影片長度之後：畫時間軸、依網址或失敗的步驟決定從哪裡開始
  const begin = () => {
    duration = Number.isFinite(video.duration) ? video.duration : (data.video.durationMs || 0) / 1000;
    $('replay-duration').textContent = fmt(duration);
    const last = timed.length ? Math.max(...timed.map(each => each.end != null ? each.end : each.start)) : 0;
    if (data.video.missingPages || last > duration + 0.5) {
      const note = $('replay-beyond');
      note.textContent = data.video.missingPages ? messages.missing_pages : fill(messages.beyond_video, {time: fmt(duration)});
      note.hidden = false;
    }
    renderSteps();
    layout();
    const params = new URLSearchParams(location.search);
    const asked = steps.find(each => each.id === params.get('step'));
    if (composite && params.has('node') && !params.has('t') && !asked) {
      seekNode(params.get('node'));
    } else if (params.has('t')) {
      if (asked) selected = asked.index;
      seek(Number(params.get('t')) || 0, asked);
      renderSteps();
    } else if (asked && asked.start != null) {
      choose(asked.index, {focus: false});
    } else if (failedStep && failedStep.start != null) {
      seek(failedStep.start - 1, failedStep);
      shown = failedStep;
      renderSteps();
      openDetail(failedStep, {focus: false});
      const located = $('replay-located');
      located.textContent = fill(messages.located_failed, {n: failedStep.label || failedStep.index});
      located.hidden = false;
      setTimeout(() => { located.hidden = true; }, 4000);
    }
    setPlaying();
  };
  video.addEventListener('durationchange', () => {
    duration = video.duration;
    $('replay-duration').textContent = fmt(duration);
    renderSteps();
    layout();
  });
  let resizeTimer = 0;
  if ('ResizeObserver' in window) {
    // 寬度真的變了才重排（一開始觀察時也會通知一次）
    new ResizeObserver(() => {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(() => { if (!axis || film.clientWidth !== axis.width) layout(); }, 150);
    }).observe(film);
  }
  renderSteps();
  if (video.readyState >= 1) begin();
  else video.addEventListener('loadedmetadata', begin, {once: true});
})();
