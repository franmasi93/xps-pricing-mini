/* E1 Bajas de correo: aplican a todas las campañas y a los avisos comerciales. boletines.ver lee;
 * boletines.listas.gestionar registra una baja a mano o la revierte (nunca se borra).
 */
"use strict";

(async () => {
  const { crear } = XPS;
  const alertas = document.getElementById("alertas");
  const cuerpo = document.getElementById("tabla-bajas");
  const dialogo = document.getElementById("dialogo-baja");
  const form = document.getElementById("form-baja");
  const MOTIVOS = { ENLACE: "Enlace del correo", MANUAL: "Registrada a mano", TENCENT: "Rebote o queja (Tencent)" };
  let puedeEditar = false;

  async function cargar() {
    const lista = await XPS.api(UI.consulta("/boletines/bajas", {
      q: document.getElementById("filtro-q").value.trim(), revertida: document.getElementById("filtro-revertida").value,
    }));
    cuerpo.replaceChildren(...(lista.length ? [] : [UI.filaVacia(5, "No hay bajas con estos filtros.")]));
    for (const baja of lista) {
      const celdas = [
        UI.celda("Email", [UI.texto(baja.email, "cifra")]),
        UI.celda("Motivo", [UI.texto(MOTIVOS[baja.motivo] || baja.motivo)]),
        UI.celda("Fecha", [UI.texto(new Date(baja.fecha).toLocaleString("es-EC", { dateStyle: "short", timeStyle: "short" }))]),
        UI.celda("Estado", [UI.texto(baja.revertida ? "Revertida" : "Vigente")]),
      ];
      if (puedeEditar) {
        celdas.push(UI.celda("Acciones", [baja.revertida ? UI.texto("—") : UI.boton("Revertir", () => seguro(async () => {
          if (!window.confirm(`¿Revertir la baja de ${baja.email}? Volverá a recibir boletines.`)) return;
          await XPS.api(`/boletines/bajas/${baja.id}/revertir`, { metodo: "POST" });
          await cargar();
        }))]));
      }
      cuerpo.append(crear("tr", {}, celdas));
    }
  }

  async function seguro(funcion, contenedor = alertas) {
    try {
      await funcion();
    } catch (error) {
      XPS.mostrarError(contenedor, error);
    }
  }

  form.addEventListener("submit", (evento) => {
    evento.preventDefault();
    seguro(async () => {
      await XPS.api("/boletines/bajas", { metodo: "POST", cuerpo: { email: form.elements.email.value.trim() } });
      dialogo.close();
      XPS.mostrarAlerta(alertas, "exito", "Baja registrada.");
      await cargar();
    }, document.getElementById("alertas-baja"));
  });

  const yo = await iniciarLayout("bajas.html");
  if (!yo || !UI.exigirAlguno(yo, ["boletines.ver"], alertas)) {
    return;
  }
  puedeEditar = UI.tieneAlguno(yo, ["boletines.listas.gestionar"]);
  document.getElementById("th-acciones").hidden = !puedeEditar;
  UI.prepararDialogo(dialogo);
  const botonNueva = document.getElementById("btn-nueva");
  botonNueva.addEventListener("click", () => { form.reset(); dialogo.showModal(); });
  document.getElementById("filtro-revertida").addEventListener("change", () => seguro(cargar));
  let espera = null;
  document.getElementById("filtro-q").addEventListener("input", () => {
    window.clearTimeout(espera);
    espera = window.setTimeout(() => seguro(cargar), 300);
  });
  await seguro(cargar);
  document.getElementById("herramientas").hidden = false;
  botonNueva.hidden = !puedeEditar;
})();
