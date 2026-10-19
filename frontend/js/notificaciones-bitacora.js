/* E3 Bitácora de notificaciones (notificaciones.bitacora.ver): filtros, contenido enviado o simulado y reenvío de fallidas. */
"use strict";

(async () => {
  const { crear } = XPS;
  const alertas = document.getElementById("alertas");
  const filtros = document.getElementById("filtros");
  const cuerpo = document.getElementById("tabla-bitacora");
  const dialogo = document.getElementById("dialogo-aviso");
  const ESTADOS = {
    PENDIENTE: "badge-alerta", ENVIADO: "badge-activo", SIMULADO: "badge-inactivo", OMITIDO: "badge-inactivo",
    FALLIDO: "badge-critico", CANCELADO: "badge-inactivo",
  };
  let nombres = {};
  let usuarios = {};

  const fecha = (valor) => (valor ? new Date(valor).toLocaleString("es-EC") : "—");
  const destinatario = (n) => (n.usuario_id && usuarios[n.usuario_id] ? usuarios[n.usuario_id] : n.email || "—");

  async function cargar() {
    const parametros = new URLSearchParams();
    for (const [clave, valor] of new FormData(filtros)) if (valor) parametros.set(clave, valor);
    const lista = await XPS.api(`/notificaciones/bitacora?${parametros}`);
    cuerpo.replaceChildren(...(lista.length ? [] : [UI.filaVacia(7, "No hay avisos con esos filtros.")]));
    for (const n of lista) {
      const estado = crear("div", {}, [crear("span", { clase: `badge badge-estado ${ESTADOS[n.estado] || ""}`, texto: n.estado })]);
      if (n.motivo_omision || n.ultimo_error) estado.append(crear("div", { clase: "ayuda", texto: n.motivo_omision || n.ultimo_error }));
      const acciones = [UI.boton("Ver", () => ver(n.id))];
      if (n.estado === "FALLIDO" && n.canal === "CORREO") acciones.push(UI.boton("Reenviar", () => reenviar(n.id)));
      cuerpo.append(crear("tr", {}, [
        UI.celda("Fecha", [UI.texto(fecha(n.creado_en))]),
        UI.celda("Evento", [UI.texto(nombres[n.evento] || n.evento)]),
        UI.celda("Destinatario", [UI.texto(destinatario(n))]),
        UI.celda("Canal", [UI.texto(n.canal === "INTERNO" ? "Campana" : "Correo")]),
        UI.celda("Estado", [estado]),
        UI.celda("Aviso", [UI.texto(n.titulo)]),
        UI.celda("Acciones", [crear("div", { clase: "celda-acciones" }, acciones)]),
      ]));
    }
  }

  async function ver(id) {
    try {
      const n = await XPS.api(`/notificaciones/bitacora/${id}`);
      document.getElementById("titulo-aviso").textContent = n.titulo;
      const datos = [
        ["Evento", nombres[n.evento] || n.evento], ["Destinatario", destinatario(n)], ["Estado", n.estado],
        ["Motivo", n.motivo_omision || n.ultimo_error || "—"], ["Asunto", n.asunto || "—"], ["Plantilla", n.plantilla || "—"],
        ["Programada para", fecha(n.programada_para)], ["Enviada", fecha(n.enviado_en)], ["Intentos", n.intentos],
      ];
      document.getElementById("datos-aviso").replaceChildren(...datos.map(([t, v]) => crear("div", {}, [crear("dt", { texto: t }), crear("dd", { texto: v })])));
      document.getElementById("contenido-aviso").textContent = n.contenido || "(sin contenido)";
      dialogo.showModal();
    } catch (error) {
      XPS.mostrarError(alertas, error);
    }
  }

  async function reenviar(id) {
    XPS.limpiarAlerta(alertas);
    try {
      await XPS.api(`/notificaciones/bitacora/${id}/reenviar`, { metodo: "POST" });
      XPS.mostrarAlerta(alertas, "exito", "Quedó pendiente: sale en el próximo lote.");
      await cargar();
    } catch (error) {
      XPS.mostrarError(alertas, error);
    }
  }

  const yo = await iniciarLayout("notificaciones-bitacora.html");
  if (!yo || !UI.exigirAlguno(yo, ["notificaciones.bitacora.ver"], alertas)) {
    return;
  }
  UI.prepararDialogo(dialogo);
  try {
    if (UI.tieneAlguno(yo, ["notificaciones.reglas.gestionar"])) {
      const eventos = await XPS.api("/notificaciones/eventos");
      nombres = Object.fromEntries(eventos.map((e) => [e.codigo, e.nombre]));
    }
    UI.opciones(document.getElementById("filtro-evento"), Object.entries(nombres), { valor: ([c]) => c, texto: ([, n]) => n, todos: "Todos" });
    if (UI.tieneAlguno(yo, ["usuario.admin"])) {
      const lista = await XPS.api("/usuarios");
      usuarios = Object.fromEntries(lista.map((u) => [u.id, u.nombre]));
      UI.opciones(document.getElementById("filtro-comercial"), lista, { valor: (u) => u.id, texto: (u) => u.nombre, todos: "Todos" });
    } else {
      document.getElementById("filtro-comercial").closest(".campo").hidden = true;
    }
    filtros.addEventListener("change", () => cargar().catch((error) => XPS.mostrarError(alertas, error)));
    await cargar();
    document.getElementById("herramientas").hidden = false;
  } catch (error) {
    XPS.mostrarError(alertas, error);
  }
})();
