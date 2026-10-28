'use strict';
// 運行回看（M12，ADR 0016）：播放錄影、縮圖時間軸、步驟清單跟著影片走。
// 資料在 #replay-data（rpa_server.replay.build_replay），文字在 #replay-messages（replayjs.*）。
// 影片的第 t 秒＝錄影開始時間＋t；步驟的 startMs、endMs 已經換算成影片裡的毫秒。
// 縮圖在這個瀏覽器裡產生：另一個看不見的 video 跳到各時間點、畫到 canvas（伺服器沒有 ffmpeg）。
// 共用的 toast()、esc() 來自設計系統的 shell.js。
// 組合運行的合併回看（2026-10-27，rpa_server.composite_replay）：data.composite 有值時，步驟依節點
// 分組、時間軸多一條節點色帶、沒有影片的時間顯示卡片（#replay-card-<段> 樣板），N／P 跳到下一個／
// 上一個節點；步驟的 label 是「n2·3」，id 是「n2:search」（網址的 ?step= 用它）。
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
  }));
  const timed = steps.filter(step => step.start != null);
  // 點一步跳到哪裡：「開始前 PREROLL 秒」與「同一段裡上一步結束」較晚的那一刻。步驟常常只有幾十毫秒，
  // 固定往前 0.4 秒時，前幾步都跳回開頭，時間軸與畫面看起來沒動（2026-10-28 驗收）
  const leadIn = step => {
    const before = timed[timed.indexOf(step) - 1];
    const same = before && (!composite || before.node === step.node) ? before : null;
    if (!same) return step.start - PREROLL;
    const end = same.end != null ? same.end : same.start;
    return Math.max(step.start - PREROLL, Math.min(end, step.start));
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
  const thumbs = new Map();
  const thumbObserver = 'IntersectionObserver' in window ? new IntersectionObserver(entries => {
    for (const entry of entries) {
      if (!entry.isIntersecting || !duration) continue;
      thumbObserver.unobserve(entry.target);
      const step = steps[Number(entry.target.dataset.thumb) - 1];
      if (step && step.end != null) grab(clamp(step.end), step.pageId).then(frame => draw(entry.target, frame));
    }
  }) : null;

  function row(step) {
    const item = document.createElement('li');
    const seekable = playable && step.start != null;
    item.innerHTML =
      '<div class="replay-row" data-index="' + step.index + '" tabindex="0" role="button">' +
      '<span class="replay-n" data-n>' + esc(step.nodeIndex || step.index) + '</span>' +
      (playable ? '<canvas class="replay-thumb" width="128" height="72" data-thumb="' + step.index + '" aria-hidden="true"></canvas>' : '') +
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
    if (canvas) {
      thumbs.set(step.index, canvas);
      if (thumbObserver) thumbObserver.observe(canvas);
    }
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
    if (step.hasFact) add(messages.fact, JSON.stringify(step.fact), true);
    add(messages.url_after, step.url, true);
    const source = step.source
      ? '<pre class="replay-source" aria-label="' + esc(fill(messages.source, {line: step.line})) + '">' +
        step.source.split('\n').map((text, offset) =>
          '<span><i>' + (step.line + offset) + '</i>' + esc(text) + '</span>').join('') + '</pre>'
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
    box.innerHTML = (step.error ? '<div class="replay-error">' + esc(step.error) + '</div>' : '') + notes +
      '<dl class="replay-kv">' + rows.join('') + '</dl>' + source +
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
    renderSteps();
    openDetail(step, {focus});
  }

  // ---------------------------------------------------------------- 步驟詳情（從右側滑出，蓋住清單）
  // 2026-10-28 驗收：詳情原本在那一步底下展開，把後面的步驟往下推；改成在右側欄裡滑出的一張卡，
  // 清單不動。上一步／下一步直接換內容，「← 步驟清單」或 Esc 收回；換到「斷言」「運行資訊」也收回。
  const side = list.closest('.replay-side');
  const tabs = side ? side.querySelector('.replay-tabs') : null;
  const arrow = path => '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="' + path + '"/></svg>';
  const drawer = document.createElement('section');
  drawer.className = 'replay-drawer';
  drawer.id = 'replay-drawer';
  drawer.setAttribute('aria-label', messages.step_detail || '');
  drawer.inert = true;
  drawer.innerHTML =
    '<div class="replay-drawer-head">' +
    '<button type="button" class="text-btn replay-drawer-back" data-drawer="back">' + arrow('M15 6l-6 6 6 6') + esc(messages.back_to_steps || '') + '</button>' +
    '<span class="replay-grow"></span>' +
    '<button type="button" class="replay-icon" data-drawer="prev" aria-label="' + esc(messages.prev_step || '') + '" title="' + esc(messages.prev_step || '') + '">' + arrow('M6 15l6-6 6 6') + '</button>' +
    '<button type="button" class="replay-icon" data-drawer="next" aria-label="' + esc(messages.next_step || '') + '" title="' + esc(messages.next_step || '') + '">' + arrow('M6 9l6 6 6-6') + '</button>' +
    '</div><div class="replay-drawer-title"></div><div class="replay-drawer-body"></div>';
  if (side) side.appendChild(drawer);
  let shown = null;
  const drawerOpen = () => drawer.classList.contains('open');

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
    drawer.style.top = (tabs ? tabs.offsetTop + tabs.offsetHeight : 0) + 'px';
    const opening = !drawerOpen();
    drawer.classList.add('open');
    side.classList.add('detail-open');
    drawer.inert = false;
    if (opening && focus) drawer.querySelector('[data-drawer="back"]').focus({preventScroll: true});
  }
  function closeDetail({focus = true} = {}) {
    if (!drawerOpen()) return;
    drawer.classList.remove('open');
    if (side) side.classList.remove('detail-open');
    drawer.inert = true;
    const row = shown && list.querySelector('.replay-row[data-index="' + shown.index + '"]');
    shown = null;
    if (row && focus) row.focus({preventScroll: true});
  }

  drawer.addEventListener('click', async event => {
    const control = event.target.closest('[data-drawer]');
    if (control) {
      if (control.dataset.drawer === 'back') closeDetail();
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
      closeDetail({focus: false});
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
      choose(Number(target.dataset.index));
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
    renderSteps();
    if (failedStep) openDetail(failedStep, {focus: false});
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
  function cardFrame(card) {
    const canvas = document.createElement('canvas');
    canvas.width = 384;
    canvas.height = 216;
    const context = canvas.getContext('2d');
    const segment = composite ? composite.segments[card.index] : null;
    const label = card.kind === 'transition'
      ? [segment && segment.prev, card.node].filter(Boolean).join(' → ')
      : card.node || ((segment && segment.nodes) || []).join(', ');
    context.fillStyle = '#f4f7fb';
    context.fillRect(0, 0, canvas.width, canvas.height);
    context.fillStyle = nodeColor(card.node) || '#546479';
    context.fillRect(0, 0, 10, canvas.height);
    context.font = '600 52px ui-monospace, SFMono-Regular, Consolas, monospace';
    context.textAlign = 'center';
    context.textBaseline = 'middle';
    context.fillText(label, canvas.width / 2 + 5, canvas.height / 2);
    return canvas;
  }
  function grab(seconds, pageId) {
    const card = !pageId && video.cardAt ? video.cardAt(seconds) : null;
    if (card) {
      const key = 'card:' + card.index;
      if (!frames.has(key)) frames.set(key, cardFrame(card));
      return Promise.resolve(frames.get(key));
    }
    const clip = video.clipAt(seconds, pageId);
    const local = clip ? Math.max(0, seconds - clip.start) : 0;
    const key = (clip ? clip.pageId : 'gap') + ':' + Math.round(local * 10);
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
          const position = Math.min(local, Math.max(0, grabber.duration - 0.04));
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
      const gap = Math.abs(Number(tick) / 10 - (seconds - clip.start));
      if (gap < distance) { distance = gap; best = canvas; }
    }
    return best;
  };

  // ---------------------------------------------------------------- 卡片（合併回看）

  const cardBox = $('replay-card');
  const showCard = card => {
    if (!cardBox) return;
    const source = card && document.getElementById('replay-card-' + card.index);
    cardBox.hidden = !source;
    cardBox.textContent = '';
    if (source) cardBox.appendChild(source.content.cloneNode(true));
  };
  video.addEventListener('card', event => { showCard(event.detail); sync(); });
  showCard(video.card);

  // ---------------------------------------------------------------- 時間軸

  const timeline = $('replay-timeline');
  const film = $('replay-film');
  const track = $('replay-track');
  const ticks = $('replay-ticks');
  const playhead = $('replay-playhead');
  const hoverline = $('replay-hoverline');
  const preview = $('replay-preview');
  const previewCanvas = $('replay-preview-canvas');
  let tiles = [];
  const timeAt = clientX => {
    const rect = film.getBoundingClientRect();
    return Math.min(duration, Math.max(0, (clientX - rect.left) / rect.width * duration));
  };

  function layout() {
    if (!duration) return;
    const width = film.clientWidth;
    const count = Math.max(4, Math.round(width / (width < 480 ? 64 : 96)));
    film.querySelectorAll('.replay-tile').forEach(tile => tile.remove());
    tiles = [];
    for (let index = 0; index < count; index += 1) {
      const tile = document.createElement('div');
      tile.className = 'replay-tile';
      tile.style.left = (index / count * 100) + '%';
      tile.style.width = (100 / count) + '%';
      const canvas = document.createElement('canvas');
      canvas.width = 192;
      canvas.height = 108;
      tile.appendChild(canvas);
      film.insertBefore(tile, $('replay-past'));
      tiles.push({tile, canvas, seconds: (index + 0.5) / count * duration});
    }
    track.textContent = '';
    for (const step of timed) {
      const segment = document.createElement('div');
      const start = Math.min(step.start, duration);
      const end = Math.min(step.end != null ? step.end : step.start, duration);
      segment.className = 'replay-seg' + (step.status === 'failed' ? ' failed' : step.status === 'skipped' ? ' skipped' : '');
      segment.dataset.index = step.index;
      segment.style.left = (start / duration * 100) + '%';
      segment.style.width = ((end - start) / duration * 100) + '%';
      segment.title = step.index + ' · ' + title(step);
      track.appendChild(segment);
    }
    const bands = $('replay-bands');
    if (bands && composite) {
      bands.textContent = '';
      for (const segment of composite.segments) {
        const band = document.createElement('button');
        band.type = 'button';
        band.className = 'replay-band ' + segment.kind + (segment.status ? ' ' + segment.status : '');
        band.style.left = (segment.startMs / 1000 / duration * 100) + '%';
        band.style.width = (segment.durationMs / 1000 / duration * 100) + '%';
        band.textContent = segment.kind === 'video' || segment.kind === 'reused' || segment.kind === 'no_video' ? segment.node : '';
        band.title = segment.kind === 'video' ? segment.node
          : fill(messages['card_' + segment.kind] || '', {node: segment.node || '', nodes: (segment.nodes || []).join(', ')});
        band.tabIndex = -1;
        band.addEventListener('pointerdown', event => event.stopPropagation());
        if (segment.node && segment.kind !== 'transition') band.style.setProperty('--node', nodeColor(segment.node));
        band.addEventListener('click', () => {
          selected = null;
          closeDetail({focus: false});
          seek(segment.startMs / 1000);
          renderSteps();
        });
        bands.appendChild(band);
      }
    }
    ticks.textContent = '';
    const every = duration > 600 ? 120 : duration > 120 ? 30 : duration > 40 ? 10 : duration > 15 ? 5 : 2;
    for (let seconds = 0; seconds <= duration - every * 0.4; seconds += every) {
      const label = document.createElement('span');
      label.style.left = (seconds / duration * 100) + '%';
      label.textContent = fmt(seconds).slice(0, 5);
      ticks.appendChild(label);
    }
    timeline.setAttribute('aria-valuemax', duration.toFixed(2));
    for (const item of tiles) {
      grab(item.seconds).then(frame => {
        if (!item.tile.isConnected) return;
        draw(item.canvas, frame);
        item.tile.classList.add('ready');
      });
    }
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

  function showPreview(clientX) {
    if (!duration) return;
    const seconds = timeAt(clientX);
    const rect = timeline.getBoundingClientRect();
    const x = clientX - rect.left;
    hoverline.hidden = false;
    hoverline.style.left = x + 'px';
    preview.hidden = false;
    preview.style.left = Math.min(rect.width - preview.offsetWidth - 6, Math.max(6, x - preview.offsetWidth / 2)) + 'px';
    $('replay-preview-time').textContent = fmt(seconds);
    const step = stepAt(seconds);
    const card = video.cardAt ? video.cardAt(seconds) : null;
    $('replay-preview-step').textContent = card ? cardTitle(card) : step ? numberOf(step) + ' · ' + title(step) : messages.open_browser;
    const context = previewCanvas.getContext('2d');
    const near = card ? null : nearest(seconds);
    if (near) context.drawImage(near, 0, 0, previewCanvas.width, previewCanvas.height);
    clearTimeout(hoverTimer);
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
    $('replay-now').textContent = fmt(seconds);
    playhead.style.left = (film.offsetLeft + (duration ? seconds / duration * film.clientWidth : 0)) + 'px';
    $('replay-past').style.width = (duration ? seconds / duration * 100 : 0) + '%';
    const card = video.card;
    const step = card ? null : shownAt(seconds);
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
    if (step) {
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
    track.querySelectorAll('.replay-seg').forEach(segment => {
      segment.classList.toggle('current', Boolean(step) && Number(segment.dataset.index) === step.index);
    });
    for (const item of list.querySelectorAll('.replay-row')) {
      const each = steps[Number(item.dataset.index) - 1];
      item.classList.toggle('current', Boolean(step) && each.index === step.index);
      item.querySelector('[data-n]').className = 'replay-n ' + stateOf(each, seconds);
    }
    const index = step ? step.index : 0;
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
    new ResizeObserver(() => {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(layout, 150);
    }).observe(film);
  }
  renderSteps();
  if (video.readyState >= 1) begin();
  else video.addEventListener('loadedmetadata', begin, {once: true});
})();
