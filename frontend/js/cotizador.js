/* P9 Cotizador paso a paso. Todo cálculo (peso cobrable, W/M, precios, totales) lo hace el backend;
 * esta pantalla solo arma la cabecera, muestra las opciones de flete y pide proponer las líneas.
 * ?id=N edita un BORRADOR existente (cambiar ruta, modo, Incoterm o carga borra sus líneas: D-F3-10).
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

  // ---------- Paso 2: ruta según el modo ----------

  async function cargarPuertos() {
    const tipo = campo("modo").value === "AEREO" ? "AEREO" : "MARITIMO";
    const puertos = await XPS.api(UI.consulta("/puertos", { tipo, activo: true }));
    for (const id of ["origen", "destino"]) {
      UI.opciones(campo(id), puertos, {
        valor: (p) => p.id,
        texto: (p) => `${p.codigo} · ${p.nombre}${p.pais ? ` (${p.pais.nombre})` : ""}`,
        todos: "Elija un puerto…",
      });
    }
    const fcl = campo("modo").value === "FCL";
    campo("bloque-contenedores").hidden = !fcl;
    campo("bloque-dimensiones").hidden = fcl;
    if (fcl && !campo("tabla-contenedores").children.length) {
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
    UI.opciones(tipo, tiposEquipo, { valor: (t) => t.id, texto: (t) => `${t.codigo} · ${t.nombre}` });
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
    datos.dimensiones = modo === "FCL" || !dimensiones.length ? null : dimensiones.map((b) => ({
      cantidad: Number(b.cantidad),
      [`largo_${sufijo}`]: b.largo,
      [`ancho_${sufijo}`]: b.ancho,
      [`alto_${sufijo}`]: b.alto,
    }));
    datos.contenedores = modo === "FCL" ? filas("tabla-contenedores").map((c) => ({ tipo_equipo_id: Number(c.tipo_equipo_id), cantidad: Number(c.cantidad) })) : [];
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
    const detalle = [
      `${opcion.proveedor.nombre}`,
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
    campo("tarifas-bajada").textContent = "Ordenadas por precio de venta para esta carga. Elija una por grupo.";
    campo("paso-tarifas").hidden = false;
    campo("paso-tarifas").scrollIntoView({ behavior: "smooth" });
  }

  async function proponer() {
    XPS.limpiarAlerta(alertas);
    const tarifas = {};
    for (const elegido of campo("grupos-tarifas").querySelectorAll("input[type=radio]:checked")) {
      tarifas[elegido.name.replace("grupo-", "")] = Number(elegido.value);
    }
    const ruta = `/cotizaciones/${cotizacionId}/proponer-lineas`;
    try {
      try {
        await XPS.api(ruta, { metodo: "POST", cuerpo: { tarifas } });
      } catch (error) {
        if (!(error instanceof XPS.ErrorApi) || error.codigo !== "AJUSTES_SE_PIERDEN") {
          throw error;
        }
        if (!window.confirm(`${error.message}. ¿Continuar?`)) {
          return;
        }
        await XPS.api(ruta, { metodo: "POST", cuerpo: { tarifas, confirmar: true } });
      }
      XPS.irA(`cotizacion.html?id=${cotizacionId}`);
    } catch (error) {
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
    campo("modo").value = cotizacion.modo;
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
      agregarContenedor(contenedor);
    }
    await mostrarTarifas();
  }

  async function iniciar() {
    const yo = await iniciarLayout("cotizaciones.html");
    if (!yo || !UI.exigirAlguno(yo, ["cotizacion.crear"], alertas)) {
      return;
    }
    try {
      const [incoterms, tipos] = await Promise.all([XPS.api("/incoterms"), XPS.api("/tipos-equipo")]);
      tiposEquipo = tipos.filter((t) => t.activo);
      UI.opciones(campo("incoterm"), incoterms.filter((i) => i.activo), {
        valor: (i) => i.id,
        texto: (i) => `${i.codigo} · ${i.nombre}${i.solo_maritimo ? " (solo marítimo)" : ""}`,
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
      campo("btn-proponer").addEventListener("click", proponer);
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
