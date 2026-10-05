
(function () {
  /* The colour theme is pure CSS: it follows the reader's system setting, so
     there is nothing to store and nothing to toggle here. */

  /* -------------------------------------------------------- mobile nav */
  var sidebar = document.querySelector('.sidebar');
  var navToggle = document.querySelector('[data-nav-toggle]');
  if (sidebar && navToggle) {
    var setNav = function (open) {
      sidebar.classList.toggle('nav-open', open);
      navToggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    };
    setNav(false);
    navToggle.addEventListener('click', function () {
      setNav(!sidebar.classList.contains('nav-open'));
    });
    sidebar.addEventListener('click', function (event) {
      if (event.target.closest('nav.toc a')) setNav(false);
    });
    document.addEventListener('keydown', function (event) {
      if (event.key === 'Escape') setNav(false);
    });
  }

  /* ---------------------------------------------------------- lightbox */
  var lightbox = document.querySelector('.lightbox');
  var lightboxImg = lightbox ? lightbox.querySelector('img') : null;
  document.addEventListener('click', function (event) {
    var img = event.target.closest('.figures img, .page-facsimile img');
    if (img && lightboxImg) {
      lightboxImg.src = img.dataset.full || img.src;
      lightbox.classList.add('open');
      event.preventDefault();
      return;
    }
    if (lightbox && lightbox.classList.contains('open')) {
      lightbox.classList.remove('open');
      lightboxImg.src = '';
    }
  });
  document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape' && lightbox) {
      lightbox.classList.remove('open');
      if (lightboxImg) lightboxImg.src = '';
    }
  });

  /* -------------------------------------------------------- back to top */
  var top = document.querySelector('.backtotop');
  if (top) {
    var onScroll = function () { top.classList.toggle('show', window.scrollY > 900); };
    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();
    top.addEventListener('click', function () {
      window.scrollTo({ top: 0, behavior: 'smooth' });
    });
  }

  /* ------------------------------------------------------------- filter */
  var search = document.querySelector('.search');
  if (search) {
    search.addEventListener('input', function () {
      var query = search.value.trim().toLowerCase();
      document.querySelectorAll('nav.toc a').forEach(function (link) {
        var match = !query || link.textContent.toLowerCase().indexOf(query) !== -1;
        link.style.display = match ? '' : 'none';
      });
    });
  }

  /* ------------------------------------------------ offline availability */
  var saveButton = document.querySelector('[data-save-offline]');
  if (saveButton) {
    saveButton.addEventListener('click', function () {
      var worker = navigator.serviceWorker && navigator.serviceWorker.controller;
      if (!worker) {
        saveButton.textContent = 'Open over http(s) to save';
        return;
      }
      saveButton.disabled = true;
      saveButton.textContent = 'Saving…';
      worker.postMessage('save-all');
    });
  }
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.addEventListener('message', function (event) {
      var data = event.data || {};
      if (!saveButton) return;
      if (data.type === 'save-progress') {
        saveButton.textContent = 'Saving ' + Math.round((data.done / data.total) * 100) + '%';
      } else if (data.type === 'save-done') {
        saveButton.disabled = false;
        saveButton.textContent = data.failed
          ? 'Saved ' + (data.total - data.failed) + ' of ' + data.total + ' — retry'
          : 'Saved for offline';
      }
    });
  }

  // A service worker has to come from a secure origin, so this quietly does
  // nothing when the page is opened straight from disk.
  if ('serviceWorker' in navigator && location.protocol.indexOf('http') === 0) {
    window.addEventListener('load', function () {
      navigator.serviceWorker.register('sw.js').catch(function () {
        /* offline reading is a bonus: failing to install is not an error */
      });
    });
  }

  /* --------------------------------------------------- page facsimiles */
  var toggle = document.querySelector('[data-toggle-pages]');
  if (toggle) {
    var show = false;
    try { show = localStorage.getItem('showFacsimiles') === '1'; } catch (error) { /* ignore */ }
    var facsimiles = document.querySelectorAll('details.page-facsimile');
    var applyPages = function (on) {
      facsimiles.forEach(function (details) { details.open = on; });
      toggle.setAttribute('aria-pressed', on ? 'true' : 'false');
      toggle.textContent = on ? 'Hide original pages' : 'Show original pages';
      try { localStorage.setItem('showFacsimiles', on ? '1' : '0'); } catch (error) { /* ignore */ }
    };
    // restore the remembered state; each summary still toggles on its own
    if (show) applyPages(true);
    toggle.addEventListener('click', function () {
      var currentlyOpen = document.querySelectorAll('details.page-facsimile[open]').length;
      applyPages(currentlyOpen < facsimiles.length);
    });
  }
})();
