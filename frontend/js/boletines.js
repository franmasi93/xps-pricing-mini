/* E1 Campañas: listado con filtros (estado, servicio y fechas) y la vista de programadas.
 * boletines.ver lee; boletines.campanas.gestionar crea. Los servicios salen de la fuente única (/servicios).
 */
"use strict";

(async () => {
  const { crear } = XPS;
  const alertas = document.getElementById("alertas");
  const cuerpo = document.getElementById("tabla-campanas");
  const filtros = {
    estado: document.getElementById("filtro-estado"),
    servicio: document.getElementById("filtro-servicio"),
    desde: document.getElementById("filtro-desde"),
    hasta: document.getElementById("filtro-hasta"),
  };
  const ETIQUETAS = {
    BORRADOR: ["badge badge-estado badge-inactivo", "Borrador"],
    PROGRAMADA: ["badge badge-estado badge-info", "Programada"],
    ENVIANDO: ["badge badge-estado badge-alerta", "Enviando"],
    PAUSADA: ["badge badge-estado badge-alerta", "Pausada"],
    ENVIADA: ["badge badge-estado badge-activo", "Enviada"],
    CANCELADA: ["badge badge-estado badge-critico", "Cancelada"],
  };

  function badge(estado) {
    const [clase, texto] = ETIQUETAS[estado] || ["badge badge-estado", estado];
    return crear("span", { clase, texto });
  }

  const fecha = (valor) => (valor ? new Date(valor).toLocaleString("es-EC", { dateStyle: "short", timeStyle: "short" }) : "—");

  async function cargar() {
    const lista = await XPS.api(UI.consulta("/boletines/campanas", {
      estado: filtros.estado.value, servicio: filtros.servicio.value, desde: filtros.desde.value, hasta: filtros.hasta.value,
    }));
    cuerpo.replaceChildren(...(lista.length ? [] : [UI.filaVacia(7, "No hay campañas con estos filtros.")]));
    for (const campana of lista) {
      const cuando = campana.estado === "PROGRAMADA" ? `Programada: ${fecha(campana.programada_para)}` : fecha(campana.enviada_en || campana.creado_en);
      cuerpo.append(crear("tr", {}, [
        UI.celda("Campaña", [UI.texto(campana.nombre)]),
        UI.celda("Estado", [badge(campana.estado)]),
        UI.celda("Destinatarios", [UI.texto(String(campana.total_destinatarios), "cifra")]),
        UI.celda("Enviados", [UI.texto(String(campana.enviados), "cifra")]),
        UI.celda("Rebotes", [UI.texto(String(campana.rebotados), "cifra")]),
        UI.celda("Fecha", [UI.texto(cuando)]),
        UI.celda("Acciones", [UI.boton(campana.estado === "BORRADOR" ? "Continuar" : "Ver", () => XPS.irA(`campana.html?id=${campana.id}`))]),
      ]));
    }
  }

  async function seguro() {
    try {
      await cargar();
    } catch (error) {
      XPS.mostrarError(alertas, error);
    }
  }

  const yo = await iniciarLayout("boletines.html");
  if (!yo || !UI.exigirAlguno(yo, ["boletines.ver"], alertas)) {
    return;
  }
  const puedeCrear = UI.tieneAlguno(yo, ["boletines.campanas.gestionar"]);
  const botonNueva = document.getElementById("btn-nueva");
  botonNueva.addEventListener("click", () => XPS.irA("campana.html"));
  for (const control of Object.values(filtros)) {
    control.addEventListener("change", seguro);
  }
  for (const pestana of document.querySelectorAll("[data-vista]")) {
    pestana.addEventListener("click", () => {
      for (const otra of document.querySelectorAll("[data-vista]")) otra.classList.toggle("activa", otra === pestana);
      filtros.estado.value = pestana.dataset.vista === "todas" ? "" : pestana.dataset.vista;
      seguro();
    });
  }
  try {
    const servicios = await XPS.api("/servicios");
    UI.opciones(filtros.servicio, servicios, { valor: (s) => s.codigo, texto: (s) => s.nombre, todos: "Todos" });
    await cargar();
    document.getElementById("herramientas").hidden = false;
    botonNueva.hidden = !puedeCrear;
  } catch (error) {
    XPS.mostrarError(alertas, error);
  }
})();
