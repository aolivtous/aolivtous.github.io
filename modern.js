(() => {
  'use strict';
  const filters = document.querySelector('.event-filters');
  if (filters) {
    filters.hidden = false;
    const events = Array.from(document.querySelectorAll('.event-list [data-kind]'));
    filters.addEventListener('click', event => {
      const button = event.target.closest('[data-filter]');
      if (!button) return;
      filters.querySelectorAll('button').forEach(item => item.setAttribute('aria-pressed', String(item === button)));
      events.forEach(item => { item.hidden = button.dataset.filter !== 'all' && item.dataset.kind !== button.dataset.filter; });
      document.querySelector('.filter-status').textContent = `${events.filter(item => !item.hidden).length} entries shown.`;
    });
  }
  const portrait = document.querySelector('.portrait-toggle');
  if (portrait) portrait.addEventListener('click', () => {
    const showingResearch = portrait.getAttribute('aria-pressed') !== 'true';
    portrait.setAttribute('aria-pressed', String(showingResearch));
    portrait.setAttribute('aria-label', showingResearch ? 'Show portrait of Anna outdoors' : 'Show portrait of Anna presenting her research');
  });
  const prediction = document.getElementById('hero-prediction');
  if (!prediction) return;
  const uncertainty = document.getElementById('hero-uncertainty');
  const explorer = document.querySelector('.sample-explorer');
  const toggle = document.querySelector('.motion-toggle');
  const slider = document.getElementById('sample-slice');
  const counter = document.getElementById('sample-counter');
  const interval = document.getElementById('sample-interval');
  const baselineAge = document.getElementById('sample-age');
  const status = document.querySelector('.sample-status');
  const tabs = Array.from(document.querySelectorAll('.sample-tabs button'));
  const motion = window.matchMedia('(prefers-reduced-motion: reduce)');
  const samples = {
    mri: {folder:'mri_01_predicted', label:'Brain MRI', first:44, last:88, initial:64, total:128, size:128, interval:'1.7 years', ageYears:54},
    ct: {folder:'ct_01', label:'Lung CT', first:16, last:48, initial:32, total:64, size:64, interval:'2 months', ageYears:47},
  };
  let sample = 'mri', frame = 64, visible = true, paused = motion.matches;
  let timer, playbackVersion = 0, renderVersion = 0;
  document.querySelector('.sample-tabs').hidden = false;
  document.querySelector('.sample-playback').hidden = false;

  const updatePlayback = () => {
    toggle.textContent = paused ? '▷ Play' : 'Ⅱ Pause';
    toggle.setAttribute('aria-pressed', String(paused));
    toggle.setAttribute('aria-label', paused ? 'Play preview animation' : 'Pause preview animation');
    explorer.dataset.playing = String(!paused && visible && !document.hidden);
  };
  const stop = () => {
    ++playbackVersion;
    ++renderVersion;
    clearTimeout(timer);
    explorer.setAttribute('aria-busy', 'false');
  };
  const loadImage = src => new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = resolve;
    image.onerror = reject;
    image.src = src;
  });
  const render = async (key, index) => {
    const config = samples[key];
    index = Math.max(config.first, Math.min(config.last, index));
    const version = ++renderVersion;
    const paths = ['prediction_0', 'uncertainty_0'].map(series =>
      `figs/mumins/viewer/${config.folder}/axial/${series}/${String(index).padStart(3, '0')}.png`);
    explorer.setAttribute('aria-busy', 'true');
    try {
      await Promise.all(paths.map(loadImage));
      if (version !== renderVersion) return false;
      // Commit both panels and their metadata together, including rapid sample changes.
      prediction.src = paths[0];
      uncertainty.src = paths[1];
      prediction.alt = `MUMINS predicted ${config.label}, axial slice ${index + 1}`;
      uncertainty.alt = `Predicted uncertainty for ${config.label}, axial slice ${index + 1}`;
      [prediction, uncertainty].forEach(image => { image.width = config.size; image.height = config.size; });
      sample = key;
      frame = index;
      explorer.dataset.sample = key;
      explorer.dataset.frame = String(index);
      slider.min = config.first;
      slider.max = config.last;
      slider.value = index;
      slider.setAttribute('aria-valuetext', `Slice ${index + 1} of ${config.total}`);
      counter.textContent = `${index + 1} / ${config.total}`;
      interval.textContent = config.interval;
      baselineAge.textContent = Number.isFinite(config.ageYears) ? `${config.ageYears} years` : 'Not provided';
      tabs.forEach(button => button.setAttribute('aria-pressed', String(button.dataset.sample === key)));
      status.textContent = '';
      explorer.setAttribute('aria-busy', 'false');
      return true;
    } catch {
      if (version !== renderVersion) return false;
      paused = true;
      stop();
      slider.value = frame;
      updatePlayback();
      status.textContent = 'Could not load this slice. Try another slice or open the full explorer.';
      return false;
    }
  };
  const start = () => {
    stop();
    updatePlayback();
    if (paused || !visible || document.hidden) return;
    const version = playbackVersion;
    const tick = async () => {
      const config = samples[sample];
      const next = frame >= config.last ? config.first : frame + 1;
      const ok = await render(sample, next);
      if (ok && version === playbackVersion && !paused) timer = setTimeout(tick, 180);
    };
    timer = setTimeout(tick, 180);
  };
  toggle.addEventListener('click', () => { paused = !paused; start(); });
  slider.addEventListener('input', () => {
    paused = true;
    stop();
    updatePlayback();
    render(sample, Number(slider.value));
  });
  tabs.forEach(button => button.addEventListener('click', async () => {
    const key = button.dataset.sample;
    stop();
    const ok = await render(key, samples[key].initial);
    if (ok) start();
  }));
  document.addEventListener('visibilitychange', start);
  motion.addEventListener('change', () => { paused = motion.matches; start(); });
  if ('IntersectionObserver' in window) new IntersectionObserver(entries => {
    visible = entries[0].isIntersecting;
    start();
  }).observe(explorer);
  start();
})();
