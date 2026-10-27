// Light or dark, chosen per device in Ajustes (Oscuro, Claro or Como el sistema). A classic script
// in <head>, so data-theme is set before the first paint and the page never flashes the other theme.
(function () {
  var pref = 'oscuro';
  try { pref = localStorage.getItem('agenda:tema') || 'oscuro'; } catch (e) { /* private mode */ }
  var sistema = window.matchMedia('(prefers-color-scheme: light)');

  function aplicar() {
    var tema = pref === 'sistema' ? (sistema.matches ? 'claro' : 'oscuro') : pref;
    document.documentElement.setAttribute('data-theme', tema);
    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute('content', tema === 'claro' ? '#eef1e8' : '#0e110c');
  }

  aplicar();
  sistema.addEventListener('change', function () { if (pref === 'sistema') aplicar(); });
  window.agendaTema = {
    preferencia: function () { return pref; },
    poner: function (nueva) {
      pref = nueva;
      try { localStorage.setItem('agenda:tema', nueva); } catch (e) { /* private mode */ }
      aplicar();
    },
  };
}());
