/* P9 Cotizador paso a paso. Todo cálculo (peso cobrable, W/M, precios, totales) lo hace el backend;
 * esta pantalla solo arma la cabecera, muestra las opciones de flete y pide proponer las líneas.
 * FIX cotizador: al elegir la tarifa las líneas se proponen solas y se muestran abajo (panel de cargos, cargos.js),
 * con Recibo de Caja y Factura, casillas por recargo y totales al instante.
 * ?id=N edita un BORRADOR existente (cambiar ruta, servicio, Incoterm o carga borra sus líneas: D-F3-10).
 * E0: los servicios activos (y sus tipos de ubicación y de equipo) salen del catálogo; no hay modos fijos.
 */
"use strict";

(() => {
  const { crear } = XPS;
  const alertas = document.getElementById("alertas");
  const form = document.getElementById("form-cotizacion");
  const campo = (id) => document.getElementById(id);
  const parametros = new URLSearchParams(window.location.search);
  let cotizacionId = parametros.get("id") ? Number(parametros.get("id")) : null;
  let tiposEquipo = [];
  let servicios = [];
  let yo = null;

  const servicioDe = (codigo) => servicios.find((s) => s.codigo === codigo) || null;
  const servicioActual = () => servicioDe(campo("modo").value);
  const tiposDelServicio = () => {
    const servicio = servicioActual();
    return tiposEquipo.filter((t) => servicio && t.servicio_id === servicio.id);
  };

  // ---------- Paso 1: cliente y contacto ----------

  function opcionesClientes(clientes) {
    UI.opciones(campo("cliente"), clientes, {
      valor: (c) => c.id,
      texto: (c) => `${c.razon_social} · ${c.ruc_o_id}`,
      todos: clientes.length ? "Elija un cliente…" : "Sin resultados",
    });
  }

  async function buscarClientes() {
    XPS.limpiarAlerta(alertas);
    try {
      opcionesClientes(await XPS.api(UI.consulta("/clientes/buscar", { q: campo("buscar-cliente").value.trim() })));
    } catch (error) {
      XPS.mostrarError(alertas, error);
    }
  }

  async function cargarContactos(contactoElegido = null) {
    const clienteId = campo("cliente").value;
    if (!clienteId) {
      UI.opciones(campo("contacto"), [], { valor: (c) => c.id, texto: (c) => c.nombre, todos: "—" });
      return;
    }
    const contactos = (await XPS.api(`/clientes/${clienteId}/contactos`)).filter((c) => c.activo);
    UI.opciones(campo("contacto"), contactos, {
      valor: (c) => c.id,
      texto: (c) => `${c.nombre}${c.principal ? " (principal)" : ""}${c.email ? ` · ${c.email}` : ""}`,
      todos: "Sin contacto (se exige al emitir)",
    });
    const principal = contactos.find((c) => c.principal);
    const elegido = contactoElegido || (principal && principal.id);
    if (elegido) {
      campo("contacto").value = String(elegido);
    }
  }

  // ---------- Paso 2: ruta según el servicio ----------

  async function cargarPuertos() {
    const servicio = servicioActual();
    const tipos = servicio ? [servicio.tipo_ubicacion_origen, servicio.tipo_ubicacion_destino] : [];
    const listas = {};
    for (const tipo of new Set(tipos)) {
      listas[tipo] = await XPS.api(UI.consulta("/puertos", { tipo, activo: true }));
    }
    for (const [indice, id] of ["origen", "destino"].entries()) {
      UI.opciones(campo(id), listas[tipos[indice]] || [], {
        valor: (p) => p.id,
        texto: (p) => `${p.codigo} · ${p.nombre}${p.pais ? ` (${p.pais.nombre})` : ""}`,
        todos: "Elija un puerto…",
      });
    }
    const porEquipo = Boolean(servicio && servicio.usa_tipo_equipo);
    campo("bloque-contenedores").hidden = !porEquipo;
    campo("bloque-dimensiones").hidden = porEquipo;
    // Al cambiar de servicio, las filas de equipo deben ser de los tipos del servicio nuevo.
    const validos = new Set(tiposDelServicio().map((t) => String(t.id)));
    for (const fila of [...campo("tabla-contenedores").children]) {
      const tipo = fila.querySelector('[data-campo="tipo_equipo_id"]');
      if (!validos.has(tipo.value)) fila.remove();
    }
    if (porEquipo && !campo("tabla-contenedores").children.length) {
      agregarContenedor();
    }
  }

  // ---------- Paso 3: carga ----------

  function entradaNumero(valor, atributos = {}) {
    return crear("input", { clase: "input cifra", atributos: { type: "text", inputmode: "decimal", value: valor ?? "", ...atributos } });
  }

  // D2: la carga se captura en kg y cm, o en lb y pulgadas; el backend convierte (constantes exactas, Decimal).
  const unidad = () => campo("unidad-peso").value;
  const sufijoMedida = () => (unidad() === "LB" ? "in" : "cm");

  function actualizarUnidad() {
    const lb = unidad() === "LB";
    campo("etiqueta-peso").textContent = lb ? "Peso real (lb)" : "Peso real (kg)";
    campo("ayuda-dimensiones").textContent = `Dimensiones por bulto (${lb ? "pulgadas" : "cm"}). El peso volumétrico y el cobrable los calcula el sistema.`;
    for (const control of campo("tabla-dimensiones").querySelectorAll("[data-medida]")) {
      control.setAttribute("aria-label", `${control.dataset.medida} en ${lb ? "pulgadas" : "cm"}`);
    }
  }

  function agregarDimension(bulto = {}) {
    const sufijo = sufijoMedida();
    const medida = (nombre, etiqueta) => entradaNumero(bulto[`${nombre}_${sufijo}`], {
      "data-campo": nombre, "data-medida": etiqueta, "aria-label": `${etiqueta} en ${sufijo === "in" ? "pulgadas" : "cm"}`,
    });
    const fila = crear("tr", {}, [
      UI.celda("Cantidad", [entradaNumero(bulto.cantidad ?? "1", { "data-campo": "cantidad", "aria-label": "Cantidad" })]),
      UI.celda("Largo", [medida("largo", "Largo")]),
      UI.celda("Ancho", [medida("ancho", "Ancho")]),
      UI.celda("Alto", [medida("alto", "Alto")]),
    ]);
    fila.append(UI.celda("", [UI.boton("Quitar", () => fila.remove())]));
    campo("tabla-dimensiones").append(fila);
  }

  function agregarContenedor(contenedor = {}) {
    const tipo = crear("select", { clase: "select", atributos: { "data-campo": "tipo_equipo_id", "aria-label": "Tipo de contenedor" } });
    UI.opciones(tipo, tiposDelServicio(), { valor: (t) => t.id, texto: (t) => `${t.codigo} · ${t.nombre}` });
    if (contenedor.tipo_equipo_id) {
      tipo.value = String(contenedor.tipo_equipo_id);
    }
    const fila = crear("tr", {}, [
      UI.celda("Tipo", [tipo]),
      UI.celda("Cantidad", [entradaNumero(contenedor.cantidad ?? "1", { "data-campo": "cantidad", "aria-label": "Cantidad" })]),
    ]);
    fila.append(UI.celda("", [UI.boton("Quitar", () => fila.remove())]));
    campo("tabla-contenedores").append(fila);
  }

  function filas(idCuerpo) {
    return [...campo(idCuerpo).children].map((fila) => {
      const datos = {};
      for (const control of fila.querySelectorAll("[data-campo]")) {
        datos[control.dataset.campo] = control.value.trim();
      }
      return datos;
    });
  }

  function textoONulo(id) {
    const valor = campo(id).value.trim();
    return valor === "" ? null : valor;
  }

  function cuerpo() {
    const modo = campo("modo").value;
    const porEquipo = Boolean(servicioActual() && servicioActual().usa_tipo_equipo);
    const datos = {
      cliente_id: Number(campo("cliente").value) || null,
      contacto_id: Number(campo("contacto").value) || null,
      sentido: campo("sentido").value,
      incoterm_id: Number(campo("incoterm").value) || null,
      modo,
      origen_puerto_id: Number(campo("origen").value) || null,
      destino_puerto_id: Number(campo("destino").value) || null,
      unidad_peso: unidad(),
      cbm: textoONulo("cbm"),
      bultos: textoONulo("bultos") === null ? null : Number(campo("bultos").value),
      valor_mercancia_usd: textoONulo("valor"),
      notas_cliente: textoONulo("notas-cliente"),
      notas_internas: textoONulo("notas-internas"),
      transportista: textoONulo("transportista"),
      descripcion_carga: textoONulo("descripcion-carga"),
    };
    datos[unidad() === "LB" ? "peso_lb" : "peso_kg"] = textoONulo("peso") || "0";
    const sufijo = sufijoMedida();
    const dimensiones = filas("tabla-dimensiones").filter((b) => b.largo || b.ancho || b.alto);
    datos.dimensiones = porEquipo || !dimensiones.length ? null : dimensiones.map((b) => ({
      cantidad: Number(b.cantidad),
      [`largo_${sufijo}`]: b.largo,
      [`ancho_${sufijo}`]: b.ancho,
      [`alto_${sufijo}`]: b.alto,
    }));
    datos.contenedores = porEquipo ? filas("tabla-contenedores").map((c) => ({ tipo_equipo_id: Number(c.tipo_equipo_id), cantidad: Number(c.cantidad) })) : [];
    return datos;
  }

  // ---------- Guardar el borrador (crear o editar) ----------

  async function guardar(evento) {
    evento.preventDefault();
    XPS.limpiarAlerta(alertas);
    const datos = cuerpo();
    try {
      if (cotizacionId === null) {
        const creada = await XPS.api("/cotizaciones", { metodo: "POST", cuerpo: datos });
        cotizacionId = creada.id;
        window.history.replaceState(null, "", `cotizador.html?id=${creada.id}`);
      } else {
        try {
          await XPS.api(`/cotizaciones/${cotizacionId}`, { metodo: "PATCH", cuerpo: datos });
        } catch (error) {
          if (!(error instanceof XPS.ErrorApi) || error.codigo !== "AJUSTES_SE_PIERDEN") {
            throw error;
          }
          if (!window.confirm(`${error.message}. ¿Continuar y borrar las líneas?`)) {
            return;
          }
          await XPS.api(`/cotizaciones/${cotizacionId}`, { metodo: "PATCH", cuerpo: { ...datos, confirmar: true } });
        }
      }
      campo("titulo").textContent = `Borrador #${cotizacionId}`;
      campo("btn-guardar").textContent = "Guardar cambios y ver tarifas";
      await mostrarTarifas();
    } catch (error) {
      XPS.mostrarError(alertas, error);
    }
  }

  // ---------- Paso 5: opciones de flete ----------

  function opcionTarifa(grupo, opcion, indice) {
    const id = `tarifa-${grupo.clave}-${opcion.tarifa_id}`;
    const radio = crear("input", { atributos: { type: "radio", name: `grupo-${grupo.clave}`, value: opcion.tarifa_id, id } });
    radio.checked = indice === 0 && opcion.subtotal_venta_usd !== null;
    radio.addEventListener("change", () => proponer());  // FIX cotizador: elegir la tarifa propone las líneas
    // D-R1: el proveedor solo llega con costo.ver; el comercial ve el transportista o la tarifa.
    const detalle = [
      opcion.proveedor ? opcion.proveedor.nombre : (opcion.transportista || `Tarifa #${opcion.tarifa_id}`),
      `transit time ${opcion.transit_time_dias ?? "—"} días`,
      `días libres ${opcion.dias_libres ?? "—"}`,
      `vigente hasta ${opcion.valido_hasta}`,
      opcion.subtotal_venta_usd !== null ? `venta USD ${opcion.subtotal_venta_usd}` : `sin precio (${opcion.aviso})`,
    ];
    if ("costo_usd" in opcion) {
      detalle.push(`costo USD ${opcion.costo_usd}`);
    }
    return crear("label", { clase: "campo-check", atributos: { for: id } }, [radio, crear("span", { texto: detalle.join(" · ") })]);
  }

  async function mostrarTarifas() {
    const opciones = await XPS.api(`/cotizaciones/${cotizacionId}/opciones-flete`);
    const contenedor = campo("grupos-tarifas");
    contenedor.replaceChildren();
    for (const grupo of opciones.grupos) {
      const titulo = grupo.tipo_equipo ? `Contenedor ${grupo.tipo_equipo.codigo}` : `Flete ${grupo.clave}`;
      const lista = grupo.opciones.length
        ? grupo.opciones.map((opcion, indice) => opcionTarifa(grupo, opcion, indice))
        : [crear("p", { clase: "texto-suave", texto: "No hay tarifas vigentes para esta ruta (si el Incoterm no incluye el flete, no hace falta)." })];
      contenedor.append(crear("div", { clase: "opciones-flete" }, [crear("h4", { texto: titulo }), ...lista]));
    }
    campo("tarifas-bajada").textContent = "Ordenadas por precio de venta para esta carga. Al elegir una, los cargos se proponen solos abajo.";
    campo("paso-tarifas").hidden = false;
    campo("paso-tarifas").scrollIntoView({ behavior: "smooth" });
    const actual = await XPS.api(`/cotizaciones/${cotizacionId}`);
    if (actual.requiere_proponer) {
      await proponer();
    } else {
      pintarCargos(actual);
    }
  }

  // ---------- Paso 6: cargos de esta cotización (FIX cotizador) ----------

  function pintarCargos(cotizacion) {
    const puedeRecargos = UI.tieneAlguno(yo, ["tarifa.editar"]);
    Cargos.pintar(campo("panel-cargos"), cotizacion, {
      editable: true,
      alCambiar: cambiarLinea,
      verDescartados: puedeRecargos ? () => XPS.api(`/cotizaciones/${cotizacionId}/recargos-descartados`) : null,
      enlaceRecargos: puedeRecargos,
    });
    campo("btn-ver-cotizacion").href = `cotizacion.html?id=${cotizacionId}`;
    campo("paso-cargos").hidden = false;
  }

  async function cambiarLinea(linea, incluida) {
    XPS.limpiarAlerta(alertas);
    try {
      pintarCargos(await XPS.api(`/cotizaciones/${cotizacionId}/lineas/${linea.id}`, { metodo: "PATCH", cuerpo: { incluida } }));
    } catch (error) {
      XPS.mostrarError(alertas, error);
      pintarCargos(await XPS.api(`/cotizaciones/${cotizacionId}`));
    }
  }

  async function proponer() {
    XPS.limpiarAlerta(alertas);
    const tarifas = {};
    for (const elegido of campo("grupos-tarifas").querySelectorAll("input[type=radio]:checked")) {
      tarifas[elegido.name.replace("grupo-", "")] = Number(elegido.value);
    }
    const ruta = `/cotizaciones/${cotizacionId}/proponer-lineas`;
    try {
      let respuesta;
      try {
        respuesta = await XPS.api(ruta, { metodo: "POST", cuerpo: { tarifas } });
      } catch (error) {
        if (!(error instanceof XPS.ErrorApi) || error.codigo !== "AJUSTES_SE_PIERDEN") {
          throw error;
        }
        // D-F3-10: si había ajustes manuales, se mantiene la confirmación.
        if (!window.confirm(`${error.message}. ¿Continuar?`)) {
          pintarCargos(await XPS.api(`/cotizaciones/${cotizacionId}`));
          return;
        }
        respuesta = await XPS.api(ruta, { metodo: "POST", cuerpo: { tarifas, confirmar: true } });
      }
      pintarCargos(respuesta);
      campo("paso-cargos").scrollIntoView({ behavior: "smooth" });
    } catch (error) {
      campo("paso-cargos").hidden = true;
      XPS.mostrarError(alertas, error);
    }
  }

  // ---------- Carga inicial ----------

  async function cargarBorrador() {
    const cotizacion = await XPS.api(`/cotizaciones/${cotizacionId}`);
    if (cotizacion.estado !== "BORRADOR") {
      XPS.irA(`cotizacion.html?id=${cotizacionId}`);
      return;
    }
    campo("titulo").textContent = cotizacion.etiqueta;
    campo("btn-guardar").textContent = "Guardar cambios y ver tarifas";
    opcionesClientes([{ id: cotizacion.cliente.id, razon_social: cotizacion.cliente.razon_social, ruc_o_id: "" }]);
    campo("cliente").value = String(cotizacion.cliente.id);
    await cargarContactos(cotizacion.contacto && cotizacion.contacto.id);
    campo("sentido").value = cotizacion.sentido;
    if (!servicioDe(cotizacion.modo) || ![...campo("modo").options].some((o) => o.value === cotizacion.modo)) {
      // Borrador de un servicio que ya no se ofrece: se muestra para poder seguir editándolo.
      campo("modo").append(crear("option", { texto: `${cotizacion.servicio.nombre} (inactivo)`, atributos: { value: cotizacion.modo } }));
    }
    campo("modo").value = cotizacion.modo;
    campo("tabla-contenedores").replaceChildren();
    await cargarPuertos();
    campo("origen").value = String(cotizacion.origen.id);
    campo("destino").value = String(cotizacion.destino.id);
    campo("incoterm").value = String(cotizacion.incoterm.id);
    campo("unidad-peso").value = cotizacion.carga.unidad_peso || "KG";
    actualizarUnidad();
    campo("peso").value = (cotizacion.carga.unidad_peso === "LB" ? cotizacion.carga.peso_lb : cotizacion.carga.peso_kg) ?? "";
    campo("transportista").value = cotizacion.transportista ?? "";
    campo("descripcion-carga").value = cotizacion.descripcion_carga ?? "";
    campo("cbm").value = cotizacion.carga.cbm ?? "";
    campo("bultos").value = cotizacion.carga.bultos ?? "";
    campo("valor").value = cotizacion.carga.valor_mercancia_usd ?? "";
    campo("notas-cliente").value = cotizacion.notas_cliente ?? "";
    campo("notas-internas").value = cotizacion.notas_internas ?? "";
    campo("tabla-dimensiones").replaceChildren();
    for (const bulto of cotizacion.carga.dimensiones || []) {
      agregarDimension(bulto);
    }
    campo("tabla-contenedores").replaceChildren();
    for (const contenedor of cotizacion.carga.contenedores) {
      if (!tiposEquipo.some((t) => t.id === contenedor.tipo_equipo_id)) {
        tiposEquipo.push({ id: contenedor.tipo_equipo_id, codigo: contenedor.codigo, nombre: "(inactivo)", servicio_id: servicioActual().id });
      }
      agregarContenedor(contenedor);
    }
    await mostrarTarifas();
  }

  async function iniciar() {
    yo = await iniciarLayout("cotizaciones.html");
    if (!yo || !UI.exigirAlguno(yo, ["cotizacion.crear"], alertas)) {
      return;
    }
    try {
      const [incoterms, tipos, todos] = await Promise.all([XPS.api("/incoterms"), XPS.api("/tipos-equipo"), XPS.api("/servicios")]);
      tiposEquipo = tipos.filter((t) => t.activo);
      servicios = todos;
      // La fuente única: solo los servicios activos, en su orden.
      UI.opciones(campo("modo"), servicios.filter((s) => s.activo), { valor: (s) => s.codigo, texto: (s) => s.nombre });
      const nombres = (i) => i.servicios.map((codigo) => (servicioDe(codigo) || { nombre: codigo }).nombre).join(", ");
      UI.opciones(campo("incoterm"), incoterms.filter((i) => i.activo), {
        valor: (i) => i.id,
        texto: (i) => `${i.codigo} · ${i.nombre} (${nombres(i) || "sin servicios"})`,
        todos: "Elija un Incoterm…",
      });
      opcionesClientes([]);
      await cargarPuertos();
      agregarDimension();
      campo("btn-buscar").addEventListener("click", buscarClientes);
      campo("buscar-cliente").addEventListener("keydown", (evento) => {
        if (evento.key === "Enter") {
          evento.preventDefault();
          buscarClientes();
        }
      });
      campo("cliente").addEventListener("change", () => cargarContactos().catch((error) => XPS.mostrarError(alertas, error)));
      campo("modo").addEventListener("change", () => cargarPuertos().catch((error) => XPS.mostrarError(alertas, error)));
      campo("btn-dimension").addEventListener("click", () => agregarDimension());
      campo("unidad-peso").addEventListener("change", actualizarUnidad);
      campo("btn-contenedor").addEventListener("click", () => agregarContenedor());
      form.addEventListener("submit", guardar);
      form.hidden = false;
      if (cotizacionId !== null) {
        await cargarBorrador();
      }
    } catch (error) {
      XPS.mostrarError(alertas, error);
    }
  }

  iniciar();
})();
