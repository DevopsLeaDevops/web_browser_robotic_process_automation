'use strict';
// 多分頁共用運行時間軸；載入新片段時暫停時鐘，缺片時顯示空缺，不沿用上一頁的畫面。
class ReplayMedia extends EventTarget {
  constructor(element, info, steps, gap) {
    super();
    this.element = element;
    this.clips = (info.clips || [{...info, pageId: 'page-1', startMs: 0}]).map(clip => ({
      ...clip, start: (clip.startMs || 0) / 1000, length: Number.isFinite(clip.durationMs) ? clip.durationMs / 1000 : Infinity,
    }));
    this.steps = steps.filter(step => step.startMs != null);
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
  pageAt(seconds) {
    let id = this.clips[0]?.pageId || 'page-1';
    for (const step of this.steps) {
      if (step.startMs / 1000 <= seconds + 0.001) id = step.pageId || 'page-1';
    }
    return id;
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
    const clip = this.clipAt(this.position, forced);
    const revision = ++this.revision;
    clearTimeout(this.loadTimer);
    this.pending = false;
    this.element.pause();
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
      if (this.clipAt(this.position, forced) !== this.active) this.load();
    }
    this.lastTick = time;
    this.tick = requestAnimationFrame(next => this.advance(next));
  }
}
