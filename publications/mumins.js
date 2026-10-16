// Keep the preprint citation selectable when clipboard access is unavailable.
(function () {
  const button = document.getElementById('copy-cite');
  const citation = document.getElementById('bibtex');
  const status = document.getElementById('citation-status');
  button.addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(citation.textContent);
      button.classList.add('copied');
      button.setAttribute('aria-label', 'Citation copied');
      status.textContent = 'Citation copied.';
      window.setTimeout(() => {
        button.classList.remove('copied');
        button.setAttribute('aria-label', 'Copy citation');
      }, 2500);
    } catch {
      const selection = window.getSelection();
      const range = document.createRange();
      range.selectNodeContents(citation);
      selection.removeAllRanges();
      selection.addRange(range);
      status.textContent = 'Citation selected. Press Ctrl+C or ⌘C to copy.';
    }
  });
})();
