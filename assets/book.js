
(function () {
  var root = document.documentElement;
  var light = window.matchMedia('(prefers-color-scheme: light)');

  /* ------------------------------------------------------------ theme */
  function resolved(preference) {
    return preference === 'auto' ? (light.matches ? 'light' : 'dark') : preference;
  }

  function apply(preference) {
    root.setAttribute('data-theme', resolved(preference));
    var button = document.querySelector('[data-theme-toggle]');
    if (button) {
      var order = preference === 'auto' ? 'light' : preference === 'light' ? 'dark' : 'auto';
      button.setAttribute('data-next', order);
      var label = button.querySelector('[data-theme-label]');
      if (label) label.textContent = order.charAt(0).toUpperCase() + order.slice(1);
      button.setAttribute('aria-label', 'Colour theme: ' + preference + '. Switch to ' + order + '.');
      button.setAttribute('aria-pressed', preference === 'dark' ? 'true' : 'false');
    }
  }

  function stored() {
    try { return localStorage.getItem('theme') || 'auto'; } catch (error) { return 'auto'; }
  }

  apply(stored());

  // follow the system only while the preference is automatic
  var onSystemChange = function () { if (stored() === 'auto') apply('auto'); };
  if (light.addEventListener) light.addEventListener('change', onSystemChange);
  else if (light.addListener) light.addListener(onSystemChange);

  var themeButton = document.querySelector('[data-theme-toggle]');
  if (themeButton) {
    themeButton.addEventListener('click', function () {
      var next = themeButton.getAttribute('data-next') || 'auto';
      try { localStorage.setItem('theme', next); } catch (error) { /* private mode */ }
      apply(next);
    });
  }

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

  /* --------------------------------------------------- page facsimiles */
  var toggle = document.querySelector('[data-toggle-pages]');
  if (toggle) {
    var show = false;
    try { show = localStorage.getItem('showFacsimiles') === '1'; } catch (error) { /* ignore */ }
    var applyPages = function (on) {
      document.body.classList.toggle('show-facsimiles', on);
      toggle.setAttribute('aria-pressed', on ? 'true' : 'false');
      toggle.textContent = on ? 'Hide original pages' : 'Show original pages';
      try { localStorage.setItem('showFacsimiles', on ? '1' : '0'); } catch (error) { /* ignore */ }
    };
    applyPages(show);
    toggle.addEventListener('click', function () {
      applyPages(!document.body.classList.contains('show-facsimiles'));
    });
  }
})();
