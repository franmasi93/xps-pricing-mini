/* E1 Página pública de baja (sin login): muestra el correo enmascarado, registra la baja y permite deshacerla.
 * Con la base apagada (fuera de horario) muestra un mensaje amable en lugar de un error.
 */
"use strict";

(async () => {
  const mensaje = document.getElementById("mensaje");
  const alertas = document.getElementById("alertas");
  const acciones = document.getElementById("acciones");
  const botonBaja = document.getElementById("btn-baja");
  const botonDeshacer = document.getElementById("btn-deshacer");
  const token = new URLSearchParams(window.location.search).get("t") || "";
  const FUERA_DE_HORARIO = "En este momento no podemos procesar su solicitud. Intente de nuevo en horario de atención (lunes a viernes, de 07:00 a 20:00) o responda el correo con la palabra BAJA.";

  function pintar(estado) {
    acciones.hidden = false;
    botonBaja.hidden = estado.de_baja;
    botonDeshacer.hidden = !estado.de_baja;
    mensaje.textContent = estado.de_baja
      ? `Listo: ${estado.email} ya no recibirá nuestros boletines de tarifas.`
      : `¿Desea dejar de recibir los boletines de tarifas en ${estado.email}?`;
  }

  function mostrarFalla(error) {
    acciones.hidden = true;
    mensaje.textContent = error.codigo === "SISTEMA_FUERA_DE_HORARIO" || error.status === 503 ? FUERA_DE_HORARIO : error.message;
  }

  async function llamar(ruta, metodo = "GET") {
    XPS.limpiarAlerta(alertas);
    try {
      pintar(await XPS.api(ruta, { metodo, manejar401: false }));
    } catch (error) {
      mostrarFalla(error);
    }
  }

  botonBaja.addEventListener("click", () => llamar(`/publico/baja/${encodeURIComponent(token)}`, "POST"));
  botonDeshacer.addEventListener("click", () => llamar(`/publico/baja/${encodeURIComponent(token)}/deshacer`, "POST"));
  if (!token) {
    mensaje.textContent = "El enlace no es válido. Si desea darse de baja, responda el correo con la palabra BAJA.";
    return;
  }
  await llamar(`/publico/baja/${encodeURIComponent(token)}`);
})();
