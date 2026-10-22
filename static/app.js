// Keyboard nav (1-5 sections, j/k items, Enter opens) + active-section highlight. Page works without it.
(function () {
  var links = [].slice.call(document.querySelectorAll('nav.top a[data-key]'));
  var items = [].slice.call(document.querySelectorAll('main a.hl'));
  var cur = -1;
  function focusItem(i) {
    if (!items.length) return;
    cur = Math.max(0, Math.min(items.length - 1, i));
    var prev = document.querySelector('.kf');
    if (prev) prev.classList.remove('kf');
    items[cur].parentNode.classList.add('kf');
    items[cur].focus({ preventScroll: true });
    items[cur].parentNode.scrollIntoView({ block: 'nearest' });
  }
  document.addEventListener('keydown', function (e) {
    if (e.ctrlKey || e.metaKey || e.altKey || /input|textarea|select/i.test(e.target.tagName)) return;
    var k = e.key;
    if (k >= '1' && k <= '9' && links[k - 1]) {
      var sec = document.getElementById(links[k - 1].getAttribute('href').slice(1));
      var first = sec && sec.querySelector('a.hl');
      if (first) { focusItem(items.indexOf(first)); sec.scrollIntoView(); } else if (sec) sec.scrollIntoView();
      e.preventDefault();
    } else if (k === 'j' || k === 'k') {
      var i = items.indexOf(document.activeElement);
      if (i < 0) i = cur;
      focusItem(i < 0 ? 0 : i + (k === 'j' ? 1 : -1));
      e.preventDefault();
    } else if (k === 'Enter' && items.indexOf(document.activeElement) >= 0) {
      window.open(document.activeElement.href, '_blank', 'noopener');
      e.preventDefault();
    }
  });
  if (!('IntersectionObserver' in window)) return;
  var vis = {};
  var io = new IntersectionObserver(function (es) {
    es.forEach(function (en) { vis[en.target.id] = en.isIntersecting; });
    var on = null;
    links.forEach(function (l) { if (!on && vis[l.getAttribute('href').slice(1)]) on = l; });
    links.forEach(function (l) { if (l === on) l.setAttribute('aria-current', 'true'); else l.removeAttribute('aria-current'); });
  }, { rootMargin: '-15% 0px -60% 0px' });
  links.forEach(function (l) { var s = document.getElementById(l.getAttribute('href').slice(1)); if (s) io.observe(s); });
})();
