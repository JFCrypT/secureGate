// JS mínimo del front. Todo lo demás lo resuelve el servidor (HTMX + Jinja).
(function () {
  "use strict";

  function csrfToken() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute("content") : "";
  }

  // Cada pedido de HTMX lleva el token CSRF de la sesión.
  document.addEventListener("htmx:configRequest", function (event) {
    event.detail.headers["X-CSRF-Token"] = csrfToken();
  });

  // Confirmación antes de acciones que cambian credenciales o estado.
  document.addEventListener("submit", function (event) {
    var message = event.target.getAttribute("data-confirm");
    if (message && !window.confirm(message)) {
      event.preventDefault();
    }
  });

  // Si el propio front deja de responder, se avisa en vez de mostrar datos viejos.
  function connectionLost(lost) {
    var banner = document.getElementById("sin-conexion");
    if (banner) { banner.hidden = !lost; }
  }
  document.addEventListener("htmx:sendError", function () { connectionLost(true); });
  document.addEventListener("htmx:timeout", function () { connectionLost(true); });
  document.addEventListener("htmx:afterOnLoad", function () { connectionLost(false); });

  // Resalta 3 s la tarjeta de "último acceso" cuando llega un evento nuevo.
  var lastEventId = null;
  var highlightUntil = 0;

  function refreshHighlight() {
    var card = document.querySelector("[data-event-id]");
    if (!card) { return; }
    var id = card.getAttribute("data-event-id");
    if (lastEventId !== null && id !== lastEventId) {
      highlightUntil = Date.now() + 3000;
    }
    lastEventId = id;
    card.classList.toggle("nuevo", Date.now() < highlightUntil);
  }

  document.addEventListener("DOMContentLoaded", refreshHighlight);
  document.addEventListener("htmx:afterSwap", refreshHighlight);
})();
