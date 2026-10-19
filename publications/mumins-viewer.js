// All panel images are loaded before a slice is displayed, keeping comparisons aligned.
(function () {
  'use strict';
  const assets = '../figs/mumins/viewer/';
  const data = window.MUMINS_VIEWER_DATA;
  if (!data) {
    document.querySelectorAll('.mumins-load-status').forEach(el => {
      el.textContent = 'Interactive controls unavailable. Static axial views are shown.';
    });
    return;
  }
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  const clamp = (value, lo, hi) => Math.min(hi, Math.max(lo, value));

  class VolumeViewer {
    constructor(root, metadata) {
      this.root = root;
      this.meta = metadata;
      this.plane = 'axial';
      this.frame = metadata.planes.axial.default_frame;
      this.target = this.frame;
      this.token = 0;
      this.playToken = 0;
      this.playing = false;
      this.visible = false;
      this.wantsPlay = false;
      this.scale = 1;
      this.cache = new Map();
      this.slider = root.querySelector('.mumins-slice-slider');
      this.selector = root.querySelector('.mumins-plane');
      this.counter = root.querySelector('.mumins-frame-count');
      this.playButton = root.querySelector('[data-action="play"]');
      this.retry = root.querySelector('[data-action="retry"]');
      this.status = root.querySelector('.mumins-load-status');
      this.panels = Array.from(root.querySelectorAll('[data-series]'));
      this.bindControls();
      this.render(this.frame).then(ok => {
        if (!ok) return;
        root.dataset.ready = 'true';
        root.querySelectorAll('button, select, input').forEach(el => { el.disabled = false; });
        this.observe();
      });
    }

    path(series, frame, plane) {
      const template = this.meta.series[series];
      return assets + this.meta.id + '/' + template.replace('{plane}', plane)
        .replace('{frame:03d}', String(frame).padStart(3, '0'));
    }

    load(url) {
      if (this.cache.has(url)) {
        const cached = this.cache.get(url);
        this.cache.delete(url);
        this.cache.set(url, cached);
        return cached;
      }
      const pending = new Promise((resolve, reject) => {
        const image = new Image();
        image.onload = async () => {
          try { await image.decode(); } catch { /* A completed image can still be displayed. */ }
          resolve(image);
        };
        image.onerror = () => reject(new Error('Slice image unavailable'));
        image.src = url;
      });
      this.cache.set(url, pending);
      pending.catch(() => { if (this.cache.get(url) === pending) this.cache.delete(url); });
      // Bound decoded-image memory instead of retaining the entire volume.
      while (this.cache.size > 90) this.cache.delete(this.cache.keys().next().value);
      return pending;
    }

    async render(index) {
      const token = ++this.token;
      const plane = this.plane;
      const info = this.meta.planes[plane];
      index = clamp(index, 0, info.frames - 1);
      this.target = index;
      this.root.setAttribute('aria-busy', 'true');
      try {
        const urls = this.panels.map(panel => this.path(panel.dataset.series, index, plane));
        await Promise.all(urls.map(url => this.load(url)));
        if (token !== this.token) return false;
        // Commit only a complete set, with the corresponding plane labels and count.
        this.panels.forEach((panel, i) => {
          const image = panel.querySelector('.mumins-view-image img');
          image.src = urls[i];
          image.alt = `${this.meta.modality} ${panel.querySelector('figcaption').textContent}, ${plane} slice ${index + 1}`;
          image.width = info.width;
          image.height = info.height;
          panel.querySelector('.mumins-image-area').style.setProperty('--physical-aspect', info.physical_aspect_ratio);
        });
        this.frame = index;
        this.slider.max = info.frames - 1;
        this.slider.value = index;
        this.slider.setAttribute('aria-valuetext', `Slice ${index + 1} of ${info.frames}`);
        this.counter.textContent = `${index + 1} / ${info.frames}`;
        this.root.dataset.frame = index;
        this.root.dataset.plane = plane;
        this.root.setAttribute('aria-busy', 'false');
        this.status.textContent = '';
        this.retry.hidden = true;
        // A small look-ahead keeps playback smooth without downloading every slice.
        if (this.visible) {
          for (const offset of [1, 2]) {
            const ahead = (index + offset) % info.frames;
            this.panels.forEach(panel => { this.load(this.path(panel.dataset.series, ahead, plane)).catch(() => {}); });
          }
        }
        return true;
      } catch {
        if (token !== this.token) return false;
        this.pause(true);
        this.root.setAttribute('aria-busy', 'false');
        this.status.textContent = 'Could not load this slice. The last complete slice is still shown.';
        this.retry.hidden = false;
        this.retry.disabled = false;
        return false;
      }
    }

    play() {
      if (this.playing || document.hidden || !this.visible) return;
      this.playing = true;
      const token = ++this.playToken;
      this.updatePlayButton();
      const tick = async () => {
        if (!this.playing || token !== this.playToken) return;
        const next = (this.frame + 1) % this.meta.planes[this.plane].frames;
        const ok = await this.render(next);
        if (ok && this.playing && token === this.playToken) this.timer = window.setTimeout(tick, 130);
      };
      this.timer = window.setTimeout(tick, 130);
    }

    pause(user = false) {
      this.playing = false;
      ++this.playToken;
      window.clearTimeout(this.timer);
      if (user) this.wantsPlay = false;
      this.updatePlayButton();
    }

    updatePlayButton() {
      this.root.dataset.playing = String(this.playing);
      this.playButton.textContent = this.playing ? '❚❚ Pause' : '▶ Play';
      this.playButton.setAttribute('aria-pressed', String(this.playing));
      this.playButton.setAttribute('aria-label', `${this.playing ? 'Pause' : 'Play'} ${this.meta.modality} slices`);
    }

    observe() {
      if ('IntersectionObserver' in window) {
        new IntersectionObserver(entries => {
          this.visible = entries[0].isIntersecting && entries[0].intersectionRatio >= 0.2;
          if (this.visible && this.wantsPlay) this.play();
          else if (!this.visible) this.pause();
        }, {threshold: [0, 0.2]}).observe(this.root);
      } else {
        this.visible = true;
        if (this.wantsPlay) this.play();
      }
      document.addEventListener('visibilitychange', () => {
        if (document.hidden) this.pause();
        else if (this.visible && this.wantsPlay) this.play();
      });
      reducedMotion.addEventListener('change', event => { if (event.matches) this.pause(true); });
    }

    applyZoom() {
      this.panels.forEach(panel => {
        panel.querySelector('.mumins-view-image').style.transform =
          `scale(${this.scale})`;
      });
      this.root.dataset.zoom = String(this.scale);
    }

    zoom(factor) {
      this.scale = clamp(this.scale * factor, 1, 3);
      this.applyZoom();
    }

    reset() {
      this.scale = 1;
      this.applyZoom();
    }

    bindControls() {
      this.playButton.addEventListener('click', () => {
        if (this.playing) this.pause(true);
        else { this.wantsPlay = true; this.play(); }
      });
      const seek = () => {
        this.pause(true);
        window.clearTimeout(this.seekTimer);
        this.render(Number(this.slider.value));
      };
      this.slider.addEventListener('input', () => {
        this.pause(true);
        window.clearTimeout(this.seekTimer);
        this.seekTimer = window.setTimeout(seek, 45);
      });
      this.slider.addEventListener('change', seek);
      this.selector.addEventListener('change', () => {
        this.pause(true);
        window.clearTimeout(this.seekTimer);
        this.plane = this.selector.value;
        this.reset();
        this.render(this.meta.planes[this.plane].default_frame);
      });
      this.root.querySelector('[data-action="zoom-in"]').addEventListener('click', () => this.zoom(1.3));
      this.root.querySelector('[data-action="zoom-out"]').addEventListener('click', () => this.zoom(1 / 1.3));
      this.root.querySelector('[data-action="reset"]').addEventListener('click', () => this.reset());
      this.retry.addEventListener('click', async () => {
        const ok = await this.render(this.target);
        if (ok && this.root.dataset.ready !== 'true') {
          this.root.dataset.ready = 'true';
          this.root.querySelectorAll('button, select, input').forEach(el => { el.disabled = false; });
          this.observe();
        }
      });
    }
  }

  document.querySelectorAll('.mumins-live-viewer').forEach(root => {
    const metadata = data.cases.find(item => item.id === root.dataset.case);
    if (metadata) new VolumeViewer(root, metadata);
  });
})();
