'use strict';
// 運行回看（M12，ADR 0016）：播放錄影、縮圖時間軸、步驟清單跟著影片走。
// 資料在 #replay-data（rpa_server.replay.build_replay），文字在 #replay-messages（replayjs.*）。
// 影片的第 t 秒＝錄影開始時間＋t；步驟的 startMs、endMs 已經換算成影片裡的毫秒。
// 縮圖在這個瀏覽器裡產生：另一個看不見的 video 跳到各時間點、畫到 canvas（伺服器沒有 ffmpeg）。
// 共用的 toast()、esc() 來自設計系統的 shell.js。
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
  const video = $('replay-video');
  const playable = Boolean(video && data.video && data.video.playable);

  const steps = data.steps.map(step => ({
    ...step,
    start: step.startMs == null ? null : Math.max(0, step.startMs / 1000),
    end: step.endMs == null ? null : Math.max(0, step.endMs / 1000),
  }));
  const timed = steps.filter(step => step.start != null);
  const failedStep = steps.find(step => step.status === 'failed') || null;
  let duration = 0;
  let selected = failedStep ? failedStep.index : null;

  const fmt = seconds => {
    const value = Math.max(0, seconds || 0);
    const minutes = Math.floor(value / 60);
    const rest = value - minutes * 60;
    return String(minutes).padStart(2, '0') + ':' + rest.toFixed(2).padStart(5, '0');
  };
  const title = step => step.name || fill(messages['action_' + step.action] || '{id}', {id: step.id});
  const clamp = seconds => Math.min(Math.max(0, seconds), Math.max(0, duration - 0.04));

  // 這一刻是哪一步：最後一個已經開始的步驟
  const stepAt = seconds => {
    let found = null;
    for (const step of timed) if (step.start <= seconds + 0.001) found = step;
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
      if (step && step.end != null) grab(clamp(step.end + 0.15)).then(frame => draw(entry.target, frame));
    }
  }) : null;

  function row(step) {
    const item = document.createElement('li');
    const seekable = playable && step.start != null;
    item.innerHTML =
      '<div class="replay-row" data-index="' + step.index + '" tabindex="0" role="button">' +
      '<span class="replay-n" data-n>' + step.index + '</span>' +
      (playable ? '<canvas class="replay-thumb" width="128" height="72" data-thumb="' + step.index + '" aria-hidden="true"></canvas>' : '') +
      '<span class="replay-title"><strong></strong><small></small></span>' +
      '<span class="replay-when">' + (seekable ? '<b>' + fmt(step.start) + '</b>' : '') +
      (step.status === 'skipped' ? esc(messages.status_skipped)
        : step.durationMs != null ? (step.durationMs / 1000).toFixed(2) + ' s' : '') + '</span></div>';
    item.querySelector('strong').textContent = title(step);
    item.querySelector('small').textContent = [step.action, step.target].filter(Boolean).join(' · ');
    item.querySelector('[data-n]').className = 'replay-n ' + (step.status || '');
    if (step.index === selected) item.appendChild(detail(step));
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
    if (step.line) {
      actions.push('<a class="button" href="' + esc(data.editUrl + '&line=' + step.line) + '">' +
        esc(fill(messages.open_in_scene, {line: step.line})) + '</a>');
    }
    box.innerHTML = (step.error ? '<div class="replay-error">' + esc(step.error) + '</div>' : '') +
      '<dl class="replay-kv">' + rows.join('') + '</dl>' + source +
      (actions.length ? '<div class="actions">' + actions.join('') + '</div>' : '');
    return box;
  }

  function renderSteps() {
    list.textContent = '';
    if (!steps.length) {
      list.innerHTML = '<li class="empty">' + esc(messages.no_steps) + '</li>';
      return;
    }
    for (const step of steps) list.appendChild(row(step));
    if (playable) sync(true);
  }

  function choose(index, {seekTo = true} = {}) {
    selected = index;
    const step = steps[index - 1];
    if (seekTo && playable && step.start != null) seek(step.start - PREROLL);
    renderSteps();
    const target = list.querySelector('.replay-row[data-index="' + index + '"]');
    if (target) target.focus({preventScroll: true});
  }

  list.addEventListener('click', async event => {
    const action = event.target.closest('[data-act]');
    if (action) {
      const step = steps[selected - 1];
      if (action.dataset.act === 'play') {
        seek(step.start - PREROLL);
        video.play();
      } else if (action.dataset.act === 'link') {
        const url = new URL(location.href);
        url.search = '';
        url.searchParams.set('t', video.currentTime.toFixed(2));
        url.searchParams.set('step', step.id);
        try {
          await navigator.clipboard.writeText(url.href);
          toast(messages.copied);
        } catch {
          toast(fill(messages.copy_failed, {link: url.href}));
        }
      }
      return;
    }
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
        const response = await fetch('/api/runs/' + encodeURIComponent(runId) + '/video', {
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
  if (document.querySelector('[data-poll-replay]')) {
    const poll = async () => {
      try {
        const response = await fetch('/api/runs/' + encodeURIComponent(runId), {headers: {Accept: 'application/json'}});
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
    return;
  }

  // ---------------------------------------------------------------- 縮圖

  const grabber = document.createElement('video');
  grabber.muted = true;
  grabber.preload = 'auto';
  grabber.src = video.currentSrc || video.src;
  const frames = new Map();
  let queue = Promise.resolve();
  const seekVideo = (target, seconds) => new Promise(resolve => {
    const done = () => { clearTimeout(timer); resolve(); };
    const timer = setTimeout(done, 3000);
    target.addEventListener('seeked', done, {once: true});
    target.currentTime = seconds;
  });
  function grab(seconds) {
    const key = Math.round(seconds * 10) / 10;
    if (frames.has(key)) return Promise.resolve(frames.get(key));
    queue = queue.then(async () => {
      if (frames.has(key)) return frames.get(key);
      if (grabber.readyState < 2) {
        await new Promise(resolve => {
          grabber.addEventListener('loadeddata', resolve, {once: true});
          grabber.addEventListener('error', resolve, {once: true});
        });
      }
      const canvas = document.createElement('canvas');
      canvas.width = 384;
      canvas.height = Math.round(384 * (video.videoHeight || 9) / (video.videoWidth || 16));
      try {
        await seekVideo(grabber, Math.min(key, Math.max(0, (grabber.duration || duration) - 0.04)));
        canvas.getContext('2d').drawImage(grabber, 0, 0, canvas.width, canvas.height);
      } catch { /* 畫不出來就留空白 */ }
      frames.set(key, canvas);
      return canvas;
    });
    return queue;
  }
  const draw = (canvas, frame) => {
    if (canvas.isConnected) canvas.getContext('2d').drawImage(frame, 0, 0, canvas.width, canvas.height);
  };
  const nearest = seconds => {
    let best = null;
    let distance = Infinity;
    for (const [key, canvas] of frames) {
      const gap = Math.abs(key - seconds);
      if (gap < distance) { distance = gap; best = canvas; }
    }
    return best;
  };

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
    $('replay-preview-step').textContent = step ? step.index + ' · ' + title(step) : messages.open_browser;
    const context = previewCanvas.getContext('2d');
    const near = nearest(seconds);
    if (near) context.drawImage(near, 0, 0, previewCanvas.width, previewCanvas.height);
    clearTimeout(hoverTimer);
    hoverTimer = setTimeout(() => grab(seconds).then(frame => {
      if (!preview.hidden && Math.abs(timeAt(clientX) - seconds) < 0.01) {
        context.drawImage(frame, 0, 0, previewCanvas.width, previewCanvas.height);
      }
    }), 120);
  }

  // ---------------------------------------------------------------- 播放與同步

  function seek(seconds) {
    video.currentTime = clamp(seconds);
    sync();
  }

  let lastStep = -1;
  function sync(force) {
    const seconds = video.currentTime;
    $('replay-now').textContent = fmt(seconds);
    playhead.style.left = (film.offsetLeft + (duration ? seconds / duration * film.clientWidth : 0)) + 'px';
    $('replay-past').style.width = (duration ? seconds / duration * 100 : 0) + '%';
    const step = shownAt(seconds);
    const state = step ? stateOf(step, seconds) : 'upcoming';
    $('replay-chip-n').textContent = step ? String(step.index).padStart(2, '0') : '—';
    $('replay-chip-state').className = 'replay-chip-state ' + (step ? state : '');
    $('replay-chip-text').textContent = step
      ? [title(step), [step.action, step.target].filter(Boolean).join(' ')].join(' · ')
      : messages.open_browser;
    $('replay-step-of').textContent = step
      ? fill(messages.step_of, {n: step.index, total: steps.length})
      : messages.open_browser;
    let url = 'about:blank';
    if (step) {
      const before = timed[timed.indexOf(step) - 1];
      url = seconds < (step.end != null ? step.end : step.start) ? (before ? before.url : 'about:blank') : step.url;
    }
    $('replay-url').textContent = url || 'about:blank';
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
      seek(target.start - PREROLL);
      renderSteps();
    } else if (direction < 0) {
      seek(0);
    }
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
    if (last > duration + 0.5) {
      const note = $('replay-beyond');
      note.textContent = fill(messages.beyond_video, {time: fmt(duration)});
      note.hidden = false;
    }
    renderSteps();
    layout();
    const params = new URLSearchParams(location.search);
    const asked = steps.find(each => each.id === params.get('step'));
    if (params.has('t')) {
      if (asked) selected = asked.index;
      seek(Number(params.get('t')) || 0);
      renderSteps();
    } else if (asked && asked.start != null) {
      choose(asked.index);
    } else if (failedStep && failedStep.start != null) {
      seek(failedStep.start - 1);
      const located = $('replay-located');
      located.textContent = fill(messages.located_failed, {n: failedStep.index});
      located.hidden = false;
      setTimeout(() => { located.hidden = true; }, 4000);
    }
    setPlaying();
  };
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
