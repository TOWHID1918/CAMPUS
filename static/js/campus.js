/* campus.js — Global UI behaviours
   Theme application (reading localStorage) runs inline in <head> to
   prevent flash-of-unstyled-content. This file wires up interactive
   behaviour after the DOM is ready.
*/

document.addEventListener('DOMContentLoaded', function () {

  /* ── Dark mode toggle ───────────────────────────────────── */
  var btn = document.getElementById('theme-toggle');
  if (btn) {
    btn.addEventListener('click', function () {
      var current = document.documentElement.getAttribute('data-theme');
      var next    = current === 'dark' ? 'light' : 'dark';

      document.documentElement.setAttribute('data-theme', next);
      localStorage.setItem('campus-theme', next);

      btn.setAttribute(
        'aria-label',
        next === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'
      );
    });
  }

  /* ── Auto-dismiss flash messages after 3 s ─────────────── */
  document.querySelectorAll('.message').forEach(function (el) {
    setTimeout(function () {
      el.style.transition = 'opacity .4s';
      el.style.opacity = '0';
      setTimeout(function () { el.remove(); }, 400);
    }, 3000);
  });

  /* ── Hamburger menu ─────────────────────────────────────── */
  var hamburgerBtn = document.getElementById('hamburger-btn');
  var campusNav    = document.getElementById('campus-nav');

  var barsSVG  = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 640" width="15" height="15" fill="currentColor"><path d="M96 160C96 142.3 110.3 128 128 128L512 128C529.7 128 544 142.3 544 160C544 177.7 529.7 192 512 192L128 192C110.3 192 96 177.7 96 160zM96 320C96 302.3 110.3 288 128 288L512 288C529.7 288 544 302.3 544 320C544 337.7 529.7 352 512 352L128 352C110.3 352 96 337.7 96 320zM544 480C544 497.7 529.7 512 512 512L128 512C110.3 512 96 497.7 96 480C96 462.3 110.3 448 128 448L512 448C529.7 448 544 462.3 544 480z"/></svg>';
  var xmarkSVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 384 512" width="13" height="13" fill="currentColor"><path d="M342.6 150.6c12.5-12.5 12.5-32.8 0-45.3s-32.8-12.5-45.3 0L192 210.7 86.6 105.4c-12.5-12.5-32.8-12.5-45.3 0s-12.5 32.8 0 45.3L146.7 256 41.4 361.4c-12.5 12.5-12.5 32.8 0 45.3s32.8 12.5 45.3 0L192 301.3 297.4 406.6c12.5 12.5 32.8 12.5 45.3 0s12.5-32.8 0-45.3L237.3 256 342.6 150.6z"/></svg>';

  if (hamburgerBtn && campusNav) {

    function closeMenu() {
      campusNav.classList.remove('is-open');
      hamburgerBtn.classList.remove('is-open');
      hamburgerBtn.innerHTML = barsSVG;
    }

    hamburgerBtn.addEventListener('click', function (e) {
      e.stopPropagation();
      var isOpen = campusNav.classList.toggle('is-open');
      hamburgerBtn.classList.toggle('is-open', isOpen);
      hamburgerBtn.innerHTML = isOpen ? xmarkSVG : barsSVG;
    });

    campusNav.addEventListener('click', function (e) {
      e.stopPropagation();
    });

    campusNav.querySelectorAll('.campus-nav__links a').forEach(function (link) {
      link.addEventListener('click', function () {
        closeMenu();
      });
    });

    document.addEventListener('click', function () {
      closeMenu();
    });

  }

});