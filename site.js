// Shared site chrome: scroll-progress bar, back-to-top button, active-section
// nav highlight + sliding indicator, reveal-on-scroll, and stat counters.
(function () {
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const finePointer = window.matchMedia('(pointer: fine)').matches;

  // ---------- scroll progress bar ----------
  const bar = document.createElement('div');
  bar.className = 'scroll-progress';
  document.body.prepend(bar);

  function updateProgress() {
    const doc = document.documentElement;
    const max = doc.scrollHeight - doc.clientHeight;
    bar.style.width = max > 0 ? `${(doc.scrollTop / max) * 100}%` : '0%';
  }

  // ---------- back to top ----------
  const toTop = document.createElement('button');
  toTop.type = 'button';
  toTop.className = 'to-top';
  toTop.setAttribute('aria-label', 'Back to top');
  toTop.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><line x1="12" y1="19" x2="12" y2="5"></line><polyline points="5 12 12 5 19 12"></polyline></svg>';
  toTop.addEventListener('click', () => window.scrollTo({ top: 0, behavior: 'smooth' }));
  document.body.appendChild(toTop);

  function updateToTop() {
    toTop.classList.toggle('visible', window.scrollY > 480);
  }

  // ---------- header scroll shadow ----------
  const header = document.querySelector('header');
  function updateHeader() {
    if (header) header.classList.toggle('is-scrolled', window.scrollY > 8);
  }

  updateProgress();
  updateToTop();
  updateHeader();
  window.addEventListener('scroll', () => { updateProgress(); updateToTop(); updateHeader(); }, { passive: true });
  window.addEventListener('resize', updateProgress);

  // ---------- active-section nav highlight + sliding indicator ----------
  const nav = document.querySelector('header nav');
  const navLinks = Array.from(document.querySelectorAll('header nav a[href^="#"]'));
  let indicator = null;
  if (nav && navLinks.length) {
    indicator = document.createElement('span');
    indicator.className = 'nav-indicator';
    indicator.setAttribute('aria-hidden', 'true');
    nav.appendChild(indicator);
  }

  function moveIndicator(link) {
    if (!indicator || !link) return;
    indicator.style.width = `${link.offsetWidth}px`;
    indicator.style.transform = `translateX(${link.offsetLeft}px)`;
    indicator.classList.add('is-visible');
  }

  if (navLinks.length && 'IntersectionObserver' in window) {
    const sectionToLink = new Map();
    navLinks.forEach(a => {
      const section = document.getElementById(a.getAttribute('href').slice(1));
      if (section) sectionToLink.set(section, a);
    });
    const io = new IntersectionObserver(entries => {
      entries.forEach(entry => {
        if (!entry.isIntersecting) return;
        const link = sectionToLink.get(entry.target);
        if (!link) return;
        navLinks.forEach(a => a.classList.remove('active'));
        link.classList.add('active');
        moveIndicator(link);
      });
    }, { rootMargin: '-45% 0px -50% 0px', threshold: 0 });
    sectionToLink.forEach((_, section) => io.observe(section));

    window.addEventListener('resize', () => {
      const active = navLinks.find(a => a.classList.contains('active'));
      if (active) moveIndicator(active);
    });
  }

  // ---------- reveal-on-scroll (fade + slide up) ----------
  const revealEls = document.querySelectorAll('.reveal-up');
  if (revealEls.length) {
    if ('IntersectionObserver' in window) {
      const revealIo = new IntersectionObserver((entries) => {
        entries.forEach(e => { if (e.isIntersecting) { e.target.classList.add('in'); revealIo.unobserve(e.target); } });
      }, { threshold: 0.12 });
      revealEls.forEach(el => revealIo.observe(el));
    } else {
      revealEls.forEach(el => el.classList.add('in'));
    }
  }

  // ---------- spotlight hover (pills + publication cards) ----------
  if (finePointer && !reduceMotion) {
    let raf = null, lastEvent = null;
    const spotlightSelector = '.pill, .pub';
    document.addEventListener('pointermove', (e) => {
      lastEvent = e;
      if (raf) return;
      raf = requestAnimationFrame(() => {
        raf = null;
        const el = lastEvent.target.closest && lastEvent.target.closest(spotlightSelector);
        if (!el) return;
        const r = el.getBoundingClientRect();
        el.style.setProperty('--mx', `${lastEvent.clientX - r.left}px`);
        el.style.setProperty('--my', `${lastEvent.clientY - r.top}px`);
      });
    }, { passive: true });
  }

  // ---------- table-of-contents rail (long publication pages only) ----------
  const tocTargets = Array.from(document.querySelectorAll('[data-toc]'));
  if (!document.body.hasAttribute('data-disable-toc-rail') && tocTargets.length >= 4) {
    const rail = document.createElement('nav');
    rail.className = 'toc-rail';
    rail.setAttribute('aria-label', 'Page sections');
    const tooltip = document.createElement('div');
    tooltip.className = 'toc-tooltip';
    const tocLinks = tocTargets.map((el) => {
      const a = document.createElement('a');
      a.href = `#${el.id}`;
      a.innerHTML = '<span class="toc-dot"></span>';
      rail.appendChild(a);
      return { el, a };
    });
    document.body.appendChild(rail);
    document.body.appendChild(tooltip);

    const showTooltip = (a, label) => {
      const r = a.getBoundingClientRect();
      tooltip.textContent = label;
      tooltip.style.top = `${r.top + r.height / 2}px`;
      tooltip.style.right = `${window.innerWidth - r.left + 12}px`;
      tooltip.classList.add('is-visible');
    };
    const hideTooltip = () => tooltip.classList.remove('is-visible');
    tocLinks.forEach(({ el, a }) => {
      a.addEventListener('mouseenter', () => showTooltip(a, el.dataset.toc));
      a.addEventListener('focus', () => showTooltip(a, el.dataset.toc));
      a.addEventListener('mouseleave', hideTooltip);
      a.addEventListener('blur', hideTooltip);
    });

    if ('IntersectionObserver' in window) {
      const tocIo = new IntersectionObserver((entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;
          const match = tocLinks.find((l) => l.el === entry.target);
          if (!match) return;
          tocLinks.forEach((l) => l.a.classList.remove('active'));
          match.a.classList.add('active');
        });
      }, { rootMargin: '-45% 0px -50% 0px', threshold: 0 });
      tocTargets.forEach((el) => tocIo.observe(el));
    }
  }

  // ---------- LAND thumbnail mask-overlay animation (homepage research card) ----------
  const landPreview = document.querySelector('.land-preview');
  if (landPreview) {
    const samples = Array.from(landPreview.querySelectorAll('.land-preview-sample')).map((sampleEl) => {
      const baseImg = sampleEl.querySelector('.land-preview-base');
      const maskImg = sampleEl.querySelector('.land-preview-mask');
      const basePrefix = baseImg && baseImg.dataset.prefix;
      const baseExt = baseImg && baseImg.dataset.ext;
      const maskPrefix = maskImg && maskImg.dataset.prefix;
      const maskExt = maskImg && maskImg.dataset.ext;
      if (!baseImg || !maskImg || !basePrefix || !baseExt || !maskPrefix || !maskExt) return null;
      return {
        baseImg,
        maskImg,
        basePrefix,
        baseExt,
        maskPrefix,
        maskExt,
        start: Number(baseImg.dataset.start || 80),
        end: Number(baseImg.dataset.end || 176),
        step: Number(baseImg.dataset.step || 2),
        frame: Number(baseImg.dataset.frame || 110),
      };
    }).filter(Boolean);

    if (samples.length) {
      let timer = null;
      const pad = (n) => String(n).padStart(3, '0');

      const setFrame = (sample, idx) => {
        const tag = pad(idx);
        sample.baseImg.src = `${sample.basePrefix}${tag}.${sample.baseExt}`;
        sample.maskImg.src = `${sample.maskPrefix}${tag}.${sample.maskExt}`;
      };

      const play = () => {
        if (timer || reduceMotion) return;
        timer = window.setInterval(() => {
          samples.forEach((sample) => {
            sample.frame = sample.frame + sample.step > sample.end ? sample.start : sample.frame + sample.step;
            setFrame(sample, sample.frame);
          });
        }, 120);
      };

      const stop = () => {
        if (!timer) return;
        window.clearInterval(timer);
        timer = null;
      };

      if ('IntersectionObserver' in window) {
        const previewIo = new IntersectionObserver((entries) => {
          entries.forEach((entry) => {
            if (entry.isIntersecting) play();
            else stop();
          });
        }, { threshold: 0.35 });
        previewIo.observe(landPreview);
      } else {
        play();
      }

      document.addEventListener('visibilitychange', () => {
        if (document.hidden) stop();
      });
    }
  }

})();
