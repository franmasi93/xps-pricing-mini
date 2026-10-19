/* E1 Campaña: asistente de 4 pasos (contenido, tarifas, destinatarios, revisar) con borrador en cada paso, y detalle
 * con progreso, copia congelada de las tarifas y destinatarios. Las pestañas de tarifas salen de la fuente única de
 * servicios (cero lógica por servicio aquí). La vista previa se muestra en un iframe aislado (sandbox, sin scripts).
 */
"use strict";

(async () => {
  const { crear } = XPS;
  const alertas = document.getElementById("alertas");
  const parametros = new URLSearchParams(window.location.search);
  let campanaId = parametros.get("id") ? Number(parametros.get("id")) : null;
  let campana = null;
  let permisos = { gestionar: false, enviar: false };
  let grupos = [];
  let servicioActivo = null;
  let elegidas = new Set();
  let conteoActual = null;
  let accionPendiente = null;

  const formContenido = document.getElementById("form-contenido");
  const tablaTarifas = document.getElementById("tabla-tarifas");
  const filtroOrigen = document.getElementById("filtro-origen");
  const filtroDestino = document.getElementById("filtro-destino");
  const filtroEquipo = document.getElementById("filtro-equipo");
  const dialogo = document.getElementById("dialogo-confirmar");
  const fecha = (valor) => (valor ? new Date(valor).toLocaleString("es-EC", { dateStyle: "short", timeStyle: "short" }) : "—");
  const fechaCorta = (iso) => (iso ? iso.split("-").reverse().join("/") : "—");

  // ---------- Pasos ----------

  function irAPaso(numero) {
    for (const boton of document.querySelectorAll("[data-paso]")) boton.classList.toggle("activo", Number(boton.dataset.paso) === numero);
    for (const panel of document.querySelectorAll("[data-panel]")) panel.hidden = Number(panel.dataset.panel) !== numero;
    XPS.limpiarAlerta(alertas);
    if (numero === 2) pintarTarifas();
    if (numero === 3) seguro(pintarListas);
    if (numero === 4) seguro(pintarRevision);
  }

  async function guardar(cambios) {
    if (campanaId === null) {
      campana = await XPS.api("/boletines/campanas", { metodo: "POST", cuerpo: cambios });
      campanaId = campana.id;
      window.history.replaceState(null, "", `campana.html?id=${campanaId}`);
    } else {
      campana = await XPS.api(`/boletines/campanas/${campanaId}`, { metodo: "PATCH", cuerpo: cambios });
    }
    document.getElementById("titulo").textContent = campana.nombre;
  }

  async function seguro(funcion) {
    try {
      await funcion();
    } catch (error) {
      XPS.mostrarError(alertas, error);
    }
  }

  // ---------- Paso 1: contenido ----------

  async function prepararContenido() {
    const plantillas = (await XPS.api("/plantillas-correo?uso=BOLETIN&activo=true"));
    UI.opciones(formContenido.elements.plantilla_id, plantillas, {
      valor: (p) => p.id,
      texto: (p) => `${p.nombre}${p.estado_tencent === "APROBADA" ? "" : ` (${p.estado_tencent.replace("_", " ").toLowerCase()})`}`,
      todos: "Elija una plantilla…",
    });
    const ayuda = () => {
      const elegida = plantillas.find((p) => String(p.id) === formContenido.elements.plantilla_id.value);
      document.getElementById("ayuda-plantilla").textContent = elegida && elegida.estado_tencent !== "APROBADA"
        ? "Esta plantilla todavía no está aprobada en Tencent: puede preparar el borrador, pero no enviarlo."
        : "";
    };
    formContenido.elements.plantilla_id.addEventListener("change", ayuda);
    if (campana) {
      formContenido.elements.nombre.value = campana.nombre;
      formContenido.elements.asunto.value = campana.asunto || "";
      formContenido.elements.texto_intro.value = campana.texto_intro || "";
      formContenido.elements.plantilla_id.value = campana.plantilla_id ? String(campana.plantilla_id) : "";
      formContenido.elements.adjuntar_pdf.checked = campana.adjuntar_pdf;
    } else {
      const masivos = { adjuntar_pdf: true };
      formContenido.elements.adjuntar_pdf.checked = masivos.adjuntar_pdf;
    }
    ayuda();
  }

  formContenido.addEventListener("submit", (evento) => {
    evento.preventDefault();
    seguro(async () => {
      const datos = {
        nombre: formContenido.elements.nombre.value.trim(),
        asunto: formContenido.elements.asunto.value.trim(),
        texto_intro: formContenido.elements.texto_intro.value.trim(),
        plantilla_id: Number(formContenido.elements.plantilla_id.value) || null,
        adjuntar_pdf: formContenido.elements.adjuntar_pdf.checked,
      };
      if (!datos.nombre) {
        XPS.mostrarAlerta(alertas, "error", "El nombre interno es obligatorio.");
        return;
      }
      await guardar(datos);
      irAPaso(2);
    });
  });

  // ---------- Paso 2: tarifas (pestañas por servicio activo) ----------

  function tarifasDelServicio() {
    const grupo = grupos.find((g) => g.servicio === servicioActivo);
    return grupo ? grupo.tarifas : [];
  }

  function pintarPestanas() {
    const contenedor = document.getElementById("pestanas-servicios");
    contenedor.replaceChildren(...grupos.map((grupo) => {
      const boton = crear("button", {
        clase: `pestana${grupo.servicio === servicioActivo ? " activa" : ""}`,
        texto: `${grupo.nombre} (${grupo.tarifas.filter((t) => elegidas.has(t.tarifa_id)).length}/${grupo.tarifas.length})`,
        atributos: { type: "button", role: "tab" },
      });
      boton.addEventListener("click", () => {
        servicioActivo = grupo.servicio;
        filtroOrigen.value = "";
        filtroDestino.value = "";
        filtroEquipo.value = "";
        pintarTarifas();
      });
      return boton;
    }));
  }

  function pintarTarifas() {
    pintarPestanas();
    const grupo = grupos.find((g) => g.servicio === servicioActivo);
    const todas = tarifasDelServicio();
    const unicos = (clave, nombre) => [...new Map(todas.map((t) => [t[clave], { id: t[clave], nombre: t[nombre] }])).values()];
    UI.opciones(filtroOrigen, unicos("origen_id", "origen_nombre"), { valor: (p) => p.id, texto: (p) => p.nombre, todos: "Todos" });
    UI.opciones(filtroDestino, unicos("destino_id", "destino_nombre"), { valor: (p) => p.id, texto: (p) => p.nombre, todos: "Todos" });
    UI.opciones(filtroEquipo, unicos("tipo_equipo_id", "tipo_equipo").filter((t) => t.id), { valor: (t) => t.id, texto: (t) => t.nombre, todos: "Todos" });
    document.getElementById("campo-filtro-equipo").hidden = !(grupo && grupo.usa_tipo_equipo);
    const visibles = todas.filter((t) => (!filtroOrigen.value || String(t.origen_id) === filtroOrigen.value)
      && (!filtroDestino.value || String(t.destino_id) === filtroDestino.value)
      && (!filtroEquipo.value || String(t.tipo_equipo_id) === filtroEquipo.value));
    tablaTarifas.replaceChildren(...(visibles.length ? [] : [UI.filaVacia(6, "No hay tarifas vigentes de este servicio con estos filtros.")]));
    for (const tarifa of visibles) {
      const casilla = crear("input", { atributos: { type: "checkbox", "aria-label": `Incluir tarifa ${tarifa.origen} → ${tarifa.destino}` } });
      casilla.checked = elegidas.has(tarifa.tarifa_id);
      casilla.addEventListener("change", () => {
        if (casilla.checked) elegidas.add(tarifa.tarifa_id); else elegidas.delete(tarifa.tarifa_id);
        resumirTarifas();
        pintarPestanas();
      });
      const vigencia = crear("div", {}, [UI.texto(fechaCorta(tarifa.valido_hasta), "cifra")]);
      if (tarifa.por_vencer) vigencia.append(crear("span", { clase: "badge badge-estado badge-alerta", texto: "Vence pronto" }));
      tablaTarifas.append(crear("tr", {}, [
        UI.celda("", [casilla]),
        UI.celda("Ruta", [UI.texto(`${tarifa.origen_nombre} → ${tarifa.destino_nombre}`)]),
        UI.celda("Tarifa", [UI.texto(tarifa.texto_tarifa, "cifra")]),
        UI.celda("Detalle", [UI.texto(tarifa.detalle)]),
        UI.celda("Vigencia", [vigencia]),
        UI.celda("Transportista", [UI.texto(tarifa.transportista)]),
      ]));
    }
    resumirTarifas();
  }

  function resumirTarifas() {
    const proximas = grupos.flatMap((g) => g.tarifas).filter((t) => elegidas.has(t.tarifa_id) && t.por_vencer).length;
    document.getElementById("resumen-tarifas").textContent = `${elegidas.size} tarifas elegidas${proximas ? ` · ${proximas} vencen pronto` : ""}.`;
  }

  for (const filtro of [filtroOrigen, filtroDestino, filtroEquipo]) filtro.addEventListener("change", pintarTarifas);
  document.getElementById("btn-todas").addEventListener("click", () => {
    for (const tarifa of tarifasDelServicio()) elegidas.add(tarifa.tarifa_id);
    pintarTarifas();
  });
  document.getElementById("btn-guardar-tarifas").addEventListener("click", () => seguro(async () => {
    const todas = grupos.flatMap((g) => g.tarifas);
    const elegidasLista = todas.filter((t) => elegidas.has(t.tarifa_id));
    await guardar({
      tarifas_ids: [...elegidas],
      servicios: [...new Set(elegidasLista.map((t) => t.servicio))],
      tipos_equipo: [...new Set(elegidasLista.map((t) => t.tipo_equipo_id).filter(Boolean))],
    });
    irAPaso(3);
  }));

  // ---------- Paso 3: destinatarios ----------

  async function pintarListas() {
    const listas = (await XPS.api("/boletines/listas?activo=true"));
    const contenedor = document.getElementById("checks-listas");
    contenedor.replaceChildren(...(listas.length ? [] : [crear("p", { clase: "texto-suave", texto: "No hay listas activas. Créelas en Boletines → Listas." })]));
    for (const lista of listas) {
      const casilla = crear("input", { atributos: { type: "checkbox", value: String(lista.id), id: `lista-${lista.id}` } });
      casilla.checked = (campana.listas_ids || []).includes(lista.id);
      casilla.addEventListener("change", () => seguro(async () => {
        await guardar({ listas_ids: [...contenedor.querySelectorAll("input:checked")].map((c) => Number(c.value)) });
        await pintarConteo();
      }));
      contenedor.append(crear("label", { clase: "campo-check", atributos: { for: `lista-${lista.id}` } }, [casilla, `${lista.nombre} (${lista.miembros})`]));
    }
    await pintarConteo();
  }

  function contador(etiqueta, valor) {
    return crear("div", { clase: "contador" }, [crear("strong", { texto: String(valor) }), crear("span", { clase: "texto-suave", texto: etiqueta })]);
  }

  async function pintarConteo() {
    conteoActual = await XPS.api(`/boletines/campanas/${campanaId}/conteo`);
    document.getElementById("contadores").replaceChildren(
      contador("en las listas", conteoActual.total), contador("omitidos por baja", conteoActual.omitidos_baja),
      contador("omitidos por consentimiento", conteoActual.omitidos_consentimiento ?? 0),
      contador("duplicados", conteoActual.duplicados), contador("recibirán", conteoActual.recibiran));
  }

  document.getElementById("btn-guardar-listas").addEventListener("click", () => irAPaso(4));

  // ---------- Paso 4: revisar ----------

  async function pintarRevision() {
    const avisos = document.getElementById("avisos-revision");
    avisos.replaceChildren();
    await pintarConteo();
    const previa = await XPS.api(`/boletines/campanas/${campanaId}/vista-previa`);
    document.getElementById("vista-correo").srcdoc = previa.html;
    document.getElementById("resumen-previa").textContent =
      `Plantilla ${previa.plantilla.nombre} (Tencent ${previa.plantilla.tencent_id || "sin ID"}, ${previa.plantilla.estado_tencent.toLowerCase()}) · `
      + `${previa.filas_en_correo} de ${previa.tarifas} tarifas en el cuerpo del correo · ${previa.bytes} bytes de variables · `
      + `recibirán ${conteoActual.recibiran} destinatarios. `
      + `Vista como la recibirá ${previa.como?.nombre_contacto || "el destinatario"} (comercial: ${previa.como?.comercial || "—"}).`;
    if (previa.avisos.length) XPS.mostrarAlerta(avisos, "aviso", `Atención: ${previa.avisos.join(" · ")}.`);
    for (const id of ["btn-enviar", "btn-programar"]) document.getElementById(id).hidden = !permisos.enviar;
    document.getElementById("btn-prueba").hidden = !permisos.gestionar;
  }

  for (const boton of document.querySelectorAll("[data-vista-correo]")) {
    boton.addEventListener("click", () => {
      for (const otro of document.querySelectorAll("[data-vista-correo]")) {
        otro.classList.toggle("activo", otro === boton);
        otro.setAttribute("aria-pressed", String(otro === boton));
      }
      document.getElementById("vista-correo").classList.toggle("movil", boton.dataset.vistaCorreo === "movil");
    });
  }

  document.getElementById("btn-prueba").addEventListener("click", () => seguro(async () => {
    const resultado = await XPS.api(`/boletines/campanas/${campanaId}/prueba`, { metodo: "POST", cuerpo: {} });
    const como = resultado.como || {};
    XPS.mostrarAlerta(alertas, "exito", `Prueba enviada a ${resultado.destinatario}, como la verá ${como.nombre_contacto || "el destinatario"}`
      + ` (comercial: ${como.comercial || "—"}). Revísela también en el celular.`);
  }));

  function abrirConfirmacion(programar) {
    accionPendiente = programar;
    XPS.limpiarAlerta(document.getElementById("alertas-confirmar"));
    document.getElementById("confirmar-numero").value = "";
    document.getElementById("texto-confirmar").textContent = programar
      ? `La campaña se enviará el ${fecha(programar)} a ${conteoActual.recibiran} destinatarios.`
      : `La campaña empezará a enviarse ahora a ${conteoActual.recibiran} destinatarios, por lotes.`;
    dialogo.showModal();
  }

  document.getElementById("btn-enviar").addEventListener("click", () => abrirConfirmacion(null));
  document.getElementById("btn-programar").addEventListener("click", () => {
    const valor = document.getElementById("programar-para").value;
    if (!valor) {
      XPS.mostrarAlerta(alertas, "error", "Indique la fecha y la hora para programar.");
      return;
    }
    abrirConfirmacion(new Date(valor).toISOString());
  });
  document.getElementById("btn-confirmar").addEventListener("click", async () => {
    const alertasDialogo = document.getElementById("alertas-confirmar");
    const numero = Number(document.getElementById("confirmar-numero").value);
    if (numero !== conteoActual.recibiran) {
      XPS.mostrarAlerta(alertasDialogo, "error", `Escriba exactamente ${conteoActual.recibiran}.`);
      return;
    }
    try {
      const cuerpo = { destinatarios_confirmados: numero };
      if (accionPendiente) cuerpo.programada_para = accionPendiente;
      await XPS.api(`/boletines/campanas/${campanaId}/enviar`, { metodo: "POST", cuerpo });
      dialogo.close();
      await cargarCampana();
    } catch (error) {
      XPS.mostrarError(alertasDialogo, error);
    }
  });

  // ---------- Detalle ----------

  async function pintarDetalle() {
    document.getElementById("pasos").hidden = true;
    for (const panel of document.querySelectorAll("[data-panel]")) panel.hidden = true;
    document.getElementById("detalle").hidden = false;
    document.getElementById("subtitulo").textContent = `Campaña ${campana.estado.toLowerCase()}`;
    document.getElementById("contadores-detalle").replaceChildren(
      contador("destinatarios", campana.total_destinatarios), contador("enviados", campana.enviados),
      contador("entregados", campana.entregados ?? 0), contador("abiertos", campana.abiertos ?? 0),
      contador("clics", campana.clics ?? 0), contador("pendientes", campana.pendientes),
      contador("rebotados", campana.rebotados), contador("fallidos", campana.fallidos), contador("omitidos", campana.omitidos));
    const par = (etiqueta, valor) => crear("div", {}, [crear("dt", { texto: etiqueta }), crear("dd", {}, [UI.texto(valor)])]);
    document.getElementById("ficha-campana").replaceChildren(
      par("Asunto", campana.asunto), par("Estado", campana.estado),
      par("Plantilla", campana.plantilla ? `${campana.plantilla.nombre} · ID Tencent ${campana.plantilla.tencent_id}` : "—"),
      par("Programada para", fecha(campana.programada_para)), par("Envío iniciado", fecha(campana.enviada_en)),
      par("Terminada", fecha(campana.terminada_en)), par("PDF adjunto", campana.adjuntar_pdf ? "Sí" : "No"));
    const acciones = document.getElementById("acciones-detalle");
    acciones.replaceChildren();
    const disponibles = { ENVIANDO: ["pausar", "cancelar"], PAUSADA: ["reanudar", "cancelar"], PROGRAMADA: ["cancelar"] }[campana.estado] || [];
    if (permisos.enviar) {
      for (const accion of disponibles) {
        acciones.append(UI.boton(accion[0].toUpperCase() + accion.slice(1), () => seguro(async () => {
          if (accion === "cancelar" && !window.confirm("¿Cancelar la campaña? Los pendientes no se enviarán.")) return;
          await XPS.api(`/boletines/campanas/${campanaId}/${accion}`, { metodo: "POST" });
          await cargarCampana();
        }), "btn btn-secundario"));
      }
    }
    const snapshot = (campana.snapshot_tarifas || { tarifas: [] }).tarifas;
    document.getElementById("tabla-snapshot").replaceChildren(...snapshot.map((t) => crear("tr", {}, [
      UI.celda("Servicio", [UI.texto(t.servicio_nombre)]),
      UI.celda("Ruta", [UI.texto(`${t.origen_nombre} → ${t.destino_nombre}`)]),
      UI.celda("Tarifa", [UI.texto(t.texto_tarifa, "cifra")]),
      UI.celda("Vigencia", [UI.texto(fechaCorta(t.valido_hasta), "cifra")]),
      UI.celda("Transportista", [UI.texto(t.transportista)]),
    ])));
    await pintarDestinatarios();
  }

  async function pintarDestinatarios() {
    const estado = document.getElementById("filtro-destinatario").value;
    const lista = await XPS.api(UI.consulta(`/boletines/campanas/${campanaId}/destinatarios`, { estado }));
    const cuerpo = document.getElementById("tabla-destinatarios");
    cuerpo.replaceChildren(...(lista.length ? [] : [UI.filaVacia(6, "Sin destinatarios con este filtro.")]));
    for (const d of lista) {
      cuerpo.append(crear("tr", {}, [
        UI.celda("Email", [UI.texto(d.email, "cifra")]), UI.celda("Contacto", [UI.texto(`${d.nombre} · ${d.empresa}`)]),
        UI.celda("Estado", [UI.texto(d.estado)]), UI.celda("Intentos", [UI.texto(String(d.intentos), "cifra")]),
        UI.celda("Último error", [UI.texto(d.ultimo_error)]), UI.celda("Enviado", [UI.texto(fecha(d.enviado_en))]),
      ]));
    }
  }

  document.getElementById("filtro-destinatario").addEventListener("change", () => seguro(pintarDestinatarios));

  // ---------- Inicio ----------

  async function cargarCampana() {
    if (campanaId !== null) {
      campana = await XPS.api(`/boletines/campanas/${campanaId}`);
      document.getElementById("titulo").textContent = campana.nombre;
      elegidas = new Set(campana.tarifas_ids);
    }
    if (campana && campana.estado !== "BORRADOR") {
      await pintarDetalle();
      return;
    }
    if (!permisos.gestionar) {
      XPS.mostrarAlerta(alertas, "error", UI.SIN_PERMISO);
      return;
    }
    document.getElementById("pasos").hidden = false;
    await prepararContenido();
    grupos = await XPS.api("/boletines/tarifas");
    servicioActivo = grupos.length ? grupos[0].servicio : null;
    irAPaso(1);
  }

  const yo = await iniciarLayout("boletines.html");
  if (!yo || !UI.exigirAlguno(yo, ["boletines.ver"], alertas)) {
    return;
  }
  permisos = { gestionar: UI.tieneAlguno(yo, ["boletines.campanas.gestionar"]), enviar: UI.tieneAlguno(yo, ["boletines.campanas.enviar"]) };
  UI.prepararDialogo(dialogo);
  for (const boton of document.querySelectorAll("[data-paso]")) {
    boton.addEventListener("click", () => {
      if (campanaId === null && boton.dataset.paso !== "1") {
        XPS.mostrarAlerta(alertas, "error", "Guarde primero el contenido (paso 1).");
        return;
      }
      irAPaso(Number(boton.dataset.paso));
    });
  }
  await seguro(cargarCampana);
})();
