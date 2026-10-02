/* Pantalla de inicio: bienvenida. Las tarjetas de cotizaciones y tarifas llegan en módulos posteriores. */
"use strict";

(async () => {
  const yo = await iniciarLayout("inicio.html");
  if (!yo) {
    return;
  }
  document.getElementById("saludo").textContent = `Bienvenido, ${yo.nombre}`;
  document.getElementById("detalle-rol").textContent = `Ingresó con el rol ${yo.rol.nombre}.`;
  document.getElementById("bienvenida").hidden = false;
})();
