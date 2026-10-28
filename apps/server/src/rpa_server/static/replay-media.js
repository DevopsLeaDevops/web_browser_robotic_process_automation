'use strict';
// 多分頁共用運行時間軸；載入新片段時暫停時鐘，缺片時顯示空缺，不沿用上一頁的畫面。
// 組合運行的合併回看（2026-10-27）另有 segments（每個節點的錄影是一段，pageAt 只看那一段裡的步驟）
// 與 cards（轉場卡、說明卡：這段時間沒有影片，時鐘照走，發出 card 事件讓頁面顯示卡片）。
class ReplayMedia extends EventTarget {
  constructor(element, info, steps, gap) {
    super();
    this.element = element;
    this.clips = (info.clips || [{...info, pageId: 'page-1', startMs: 0}]).map(clip => ({
      ...clip, start: (clip.startMs || 0) / 1000, length: Number.isFinite(clip.durationMs) ? clip.durationMs / 1000 : Infinity,
    }));
    this.steps = steps.filter(step => step.startMs != null);
    this.segments = (info.segments || []).map(segment => ({
      start: segment.startMs / 1000, length: segment.durationMs / 1000, page: segment.page,
    }));
    this.cards = (info.cards || []).map(card => ({...card, start: card.startMs / 1000, length: card.durationMs / 1000}));
    this.card = null;
    this.duration = (info.durationMs || 0) / 1000;
    this.position = 0;
    this.playing = false;
    this.rate = 1;
    this.revision = 0;
    this.pending = false;
    this.active = null;
    this.failed = new Set();
    this.loadTimer = 0;
    this.gap = gap;
    this.hold = null;
    this.tick = 0;
    this.lastTick = performance.now();
    this.loaded = false;
    element.addEventListener('click', () => this.dispatchEvent(new Event('click')));
    element.addEventListener('error', () => this.fail());
    this.seek(0);
  }
  // 一段都還沒播出來就失敗，多半是這個瀏覽器播不了 WebM（例如 Safari、錄製端 App）：
  // 轉給頁面顯示「播不了、請下載」（ADR 0016），不顯示成缺片。
  fail() {
    this.unavailable();
    if (this.loaded) return;
    if (this.gap) this.gap.hidden = true;
    this.dispatchEvent(new Event('error'));
  }
  get readyState() { return 1; }
  get videoWidth() { return this.element.videoWidth; }
  get videoHeight() { return this.element.videoHeight; }
  get currentTime() { return this.position; }
  set currentTime(value) { this.seek(value); }
  get paused() { return !this.playing; }
  get playbackRate() { return this.rate; }
  set playbackRate(value) { this.rate = value; this.element.playbackRate = value; }
  // 兩段相接的那一刻算後面那一段：開頭與結尾都留 1 毫秒，浮點數相加（開始＋長度）略大於下一段的
  // 開始時，跳到下一段開頭（N、點節點色帶）不會還停在前面的卡片上（2026-10-28）
  segmentAt(seconds) {
    return this.segments.find(segment => seconds >= segment.start - 0.001 && seconds < segment.start + segment.length - 0.001) || null;
  }
  cardAt(seconds) {
    return this.cards.find(card => seconds >= card.start - 0.001 && seconds < card.start + card.length - 0.001) || null;
  }
  pageAt(seconds) {
    const segment = this.segmentAt(seconds);
    let id = segment ? segment.page : (this.clips[0]?.pageId || 'page-1');
    for (const step of this.steps) {
      const start = step.startMs / 1000;
      if (segment && (start < segment.start - 0.001 || start >= segment.start + segment.length)) continue;
      if (start <= seconds + 0.001) id = step.pageId || 'page-1';
    }
    return id;
  }
  showCard(card) {
    if (card === this.card) return;
    this.card = card;
    this.dispatchEvent(new CustomEvent('card', {detail: card}));
  }
  clipAt(seconds, pageId) {
    const id = pageId || this.pageAt(seconds);
    return this.clips.find(clip => clip.pageId === id && !this.failed.has(id) && clip.url && Number.isFinite(clip.startMs) &&
      seconds >= clip.start - 0.001 && seconds < clip.start + clip.length) || null;
  }
  unavailable() {
    clearTimeout(this.loadTimer);
    if (this.active) this.failed.add(this.active.pageId);
    this.pending = false;
    this.active = null;
    this.showGap(true);
  }
  showGap(missing) {
    this.element.style.visibility = missing ? 'hidden' : '';
    if (this.gap) this.gap.hidden = !missing;
  }
  seek(value, hold = null) {
    this.hold = hold;
    this.position = Math.max(0, Math.min(Number(value) || 0, Math.max(0, this.duration - 0.04)));
    this.lastTick = performance.now();
    this.load();
    this.dispatchEvent(new Event('seeked'));
  }
  load() {
    const forced = this.hold && this.position < this.hold.until ? this.hold.pageId : null;
    const card = this.cardAt(this.position);
    const clip = card ? null : this.clipAt(this.position, forced);
    const revision = ++this.revision;
    clearTimeout(this.loadTimer);
    this.pending = false;
    this.element.pause();
    this.showCard(card);
    if (card) {
      // 卡片的時間沒有影片：藏起影片與缺片提示，時鐘照走（advance 依實際時間前進）
      this.active = null;
      this.element.style.visibility = 'hidden';
      if (this.gap) this.gap.hidden = true;
      return;
    }
    // 首格可能晚於時間軸零點；即使目前是空白，也不能漏掉腳本載入前已發生的媒體錯誤。
    if (!this.loaded && this.element.error && (!clip || this.element.getAttribute('src') === clip.url)) {
      setTimeout(() => { if (revision === this.revision) { ++this.revision; this.fail(); } });
      return;
    }
    if (!clip) {
      this.active = null;
      this.element.dataset.pageId = forced || this.pageAt(this.position);
      this.showGap(true);
      return;
    }
    const changing = this.element.getAttribute('src') !== clip.url;
    this.active = clip;
    this.element.dataset.pageId = clip.pageId;
    this.pending = true;
    this.element.style.visibility = 'hidden';
    if (this.gap) this.gap.hidden = true;
    this.loadTimer = setTimeout(() => {
      if (revision === this.revision) { ++this.revision; this.unavailable(); }
    }, 10000);
    const ready = () => {
      if (revision !== this.revision) return;
      clearTimeout(this.loadTimer);
      if (Number.isFinite(this.element.duration)) {
        clip.length = this.element.duration;
        if (!Number.isFinite(clip.durationMs) && clip.start + clip.length > this.duration) {
          this.duration = clip.start + clip.length;
          this.dispatchEvent(new Event('durationchange'));
        }
      }
      const local = Math.max(0, Math.min(this.position - clip.start, this.element.duration - 0.04));
      this.element.currentTime = local;
      this.element.playbackRate = this.rate;
      this.pending = false;
      this.loaded = true;
      this.lastTick = performance.now();
      this.showGap(false);
      if (this.playing) this.element.play().catch(() => this.pause());
      this.dispatchEvent(new Event('seeked'));
    };
    if (!changing && this.element.error) {
      // 樣板的 src 在這個腳本執行前就已經載入失敗：error 事件不會再來，等頁面接好事件再轉出去
      setTimeout(() => { if (revision === this.revision) { ++this.revision; this.fail(); } });
    } else if (changing || this.element.readyState < 1) {
      this.element.addEventListener('loadedmetadata', ready, {once: true});
      if (changing) this.element.src = clip.url;
    } else ready();
  }
  play() {
    if (this.playing) return Promise.resolve();
    this.playing = true;
    this.lastTick = performance.now();
    if (this.active && !this.pending) this.element.play().catch(() => this.pause());
    this.dispatchEvent(new Event('play'));
    if (!this.tick) this.tick = requestAnimationFrame(time => this.advance(time));
    return Promise.resolve();
  }
  pause() {
    this.playing = false;
    this.element.pause();
    cancelAnimationFrame(this.tick);
    this.tick = 0;
    this.dispatchEvent(new Event('pause'));
  }
  advance(time) {
    this.tick = 0;
    if (!this.playing) return;
    if (!this.pending) {
      if (this.active && this.element.ended) this.active.length = this.element.currentTime;
      if (this.active && !this.element.ended) this.position = this.active.start + this.element.currentTime;
      else this.position += Math.min(0.25, (time - this.lastTick) / 1000) * this.rate;
      if (this.position >= this.duration - 0.02) {
        this.position = this.duration;
        this.pause();
        this.dispatchEvent(new Event('ended'));
        return;
      }
      const forced = this.hold && this.position < this.hold.until ? this.hold.pageId : null;
      if (this.cardAt(this.position) !== this.card || (!this.card && this.clipAt(this.position, forced) !== this.active)) this.load();
    }
    this.lastTick = time;
    this.tick = requestAnimationFrame(next => this.advance(next));
  }
}
