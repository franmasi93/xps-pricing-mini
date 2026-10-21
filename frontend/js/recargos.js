/* P7 Recargos. Entra quien tenga tarifa.editar o costo.ver (el comercial recibe "No tiene permiso",
 * D-R2: vincular a tarifas (el puerto sale de la tarifa) y a servicios; aviso de coherencia antes de guardar.
 * D-R3: "Va en" Recibo de Caja o Factura (y, en Factura, si aplica IVA).
 * igual que Geografía en F1). tarifa.editar edita; gerencia lee. Las columnas de costo solo se
 * dibujan si el backend envió esas claves. E0: servicios, tipos de ubicación y tipos de equipo salen del catálogo.
 */
"use strict";

(async () => {
  const { crear } = XPS;
  const BLOQUES = {
    RECOGIDA_ORIGEN: "Recogida en origen",
    DESPACHO_EXPORT: "Despacho de exportación",
    GASTOS_ORIGEN: "Gastos en origen",
    SEGURO: "Seguro",
    GASTOS_DESTINO: "Gastos en destino",
    DESPACHO_IMPORT: "Despacho de importación",
    ENTREGA_FINAL: "Entrega final",
  };
  const BLOQUES_POR_LADO = {
    ORIGEN: ["RECOGIDA_ORIGEN", "DESPACHO_EXPORT", "GASTOS_ORIGEN", "SEGURO"],
    DESTINO: ["GASTOS_DESTINO", "DESPACHO_IMPORT", "ENTREGA_FINAL", "SEGURO"],
  };

  const alertas = document.getElementById("alertas");
  const herramientas = document.getElementById("herramientas");
  const botonNuevo = document.getElementById("btn-nuevo");
  const cabecera = document.getElementById("cabecera-recargos");
  const cuerpo = document.getElementById("tabla-recargos");
  const filtros = {
    puerto: document.getElementById("filtro-puerto"),
    lado: document.getElementById("filtro-lado"),
    bloque: document.getElementById("filtro-bloque"),
    proveedor: document.getElementById("filtro-proveedor"),
    modo: document.getElementById("filtro-modo"),
    vigente_en: document.getElementById("filtro-vigente"),
    por_vencer: document.getElementById("filtro-por-vencer"),
    activo: document.getElementById("filtro-activo"),
  };
  const dialogo = document.getElementById("dialogo-recargo");
  const form = document.getElementById("form-recargo");
  const alertasDialogo = document.getElementById("alertas-recargo");

  let puedeEditar = false;
  let diasAlerta = "7";
  let catalogos = { puertos: [], proveedores: [], monedas: [], tipos: [], servicios: [], ubicaciones: [], tarifas: [] };
  const FISCAL = { RECIBO_CAJA: "Recibo de Caja", FACTURA: "Factura" };
  let enEdicion = null;

  const servicioDe = (codigo) => catalogos.servicios.find((s) => s.codigo === codigo) || null;
  const nombreServicio = (codigo) => (servicioDe(codigo) || { nombre: codigo }).nombre;
  const nombreUbicacion = (codigo) => (catalogos.ubicaciones.find((u) => u.codigo === codigo) || { nombre: codigo }).nombre;

  function pintar(lista) {
    const conCosto = lista.some((r) => "costo" in r);
    const conMargen = lista.some((r) => "margen_pct" in r);
    const columnas = ["Puerto", "Lado y bloque", "Concepto", "Servicio", "Unidad", "Venta"];
    if (conCosto) columnas.push("Costo");
    if (conMargen) columnas.push("Margen");
    columnas.push("IVA / rol", "Vigencia", "Estado");
    if (puedeEditar) columnas.push("Acciones");
    cabecera.replaceChildren(crear("tr", {}, columnas.map((c) => crear("th", { texto: c }))));
    cuerpo.replaceChildren(...(lista.length ? [] : [UI.filaVacia(columnas.length, "No hay recargos con estos filtros.")]));
    for (const recargo of lista) {
      const servicio = recargo.modo ? nombreServicio(recargo.modo) : "Todos";
      const modo = recargo.tipo_equipo ? `${servicio} ${recargo.tipo_equipo.codigo}` : servicio;
      const celdas = [
        UI.celda("Puerto", [UI.texto(recargo.puerto ? recargo.puerto.codigo : "De la tarifa", "cifra"),
          ...(recargo.tarifas_vinculadas.length ? [crear("span", { clase: "badge badge-estado badge-info", texto: `Vinculado a ${recargo.tarifas_vinculadas.length} tarifa(s)` })] : []),
          ...(recargo.servicios_vinculados.length ? [crear("span", { clase: "badge badge-estado badge-info", texto: `Solo ${recargo.servicios_vinculados.join(", ")}` })] : [])]),
        UI.celda("Lado y bloque", [UI.texto(`${recargo.lado === "ORIGEN" ? "Origen" : "Destino"} · ${BLOQUES[recargo.bloque_incoterm]}`)]),
        UI.celda("Concepto", [UI.texto(recargo.proveedor ? `${recargo.concepto} (${recargo.proveedor.nombre})` : recargo.concepto)]),
        UI.celda("Servicio", [UI.texto(modo)]),
        UI.celda("Unidad", [UI.texto({ PCT_VALOR: "% del valor", PCT_RECIBO: "% sobre Recibo de Caja" }[recargo.rate_unit] || recargo.rate_unit)]),
        UI.celda("Venta", [UI.monto(recargo.precio_venta, recargo.moneda)]),
      ];
      if (conCosto) celdas.push(UI.celda("Costo", [UI.monto(recargo.costo, recargo.moneda)]));
      if (conMargen) celdas.push(UI.celda("Margen", [UI.texto(`${recargo.margen_pct} %`, "cifra")]));
      celdas.push(
        UI.celda("IVA / rol", [UI.texto(`${FISCAL[recargo.bloque_fiscal]}${recargo.bloque_fiscal === "FACTURA" ? (recargo.aplica_iva ? " con IVA" : " sin IVA") : ""} · ${recargo.rol_ingreso === "PRINCIPAL" ? "Principal" : "Agente"}`)]),
        UI.celda("Vigencia", [
          crear("div", {}, [
            UI.texto(`${recargo.valido_desde} a ${recargo.valido_hasta}`, "cifra"),
            crear("div", {}, [UI.badgeVigencia(recargo.estado_vigencia, diasAlerta)]),
          ]),
        ]),
        UI.celda("Estado", [UI.badgeEstado(recargo.activo)])
      );
      if (puedeEditar) {
        celdas.push(
          UI.celda("Acciones", [
            crear("div", { clase: "celda-acciones" }, [
              UI.boton("Editar", () => abrir(recargo)),
              UI.boton(recargo.activo ? "Desactivar" : "Activar", () => cambiarEstado(recargo)),
            ]),
          ])
        );
      }
      cuerpo.append(crear("tr", {}, celdas));
    }
  }

  // F5-A2: paginado en el servidor, con los mismos filtros.
  const POR_PAGINA = 25;
  let pagina = 0;
  const pintarPaginador = UI.paginador(document.getElementById("paginador-recargos"), POR_PAGINA, (nueva) => {
    pagina = Math.max(0, nueva);
    seguro(cargar);
  });

  async function cargar() {
    const parametros = { limit: POR_PAGINA, offset: pagina * POR_PAGINA };
    for (const [clave, control] of Object.entries(filtros)) {
      parametros[clave] = control.value;
    }
    const { datos, total } = await XPS.api(UI.consulta("/recargos", parametros), { conTotal: true });
    if (!datos.length && pagina > 0) {
      pagina -= 1;
      await cargar();
      return;
    }
    pintar(datos);
    pintarPaginador(total, pagina);
  }

  async function seguro(funcion) {
    try {
      await funcion();
    } catch (error) {
      XPS.mostrarError(alertas, error);
    }
  }

  // ---------- Formulario ----------

  function ajustar() {
    const lado = form.elements.lado.value;
    const actual = form.elements.bloque_incoterm.value;
    UI.opciones(form.elements.bloque_incoterm, BLOQUES_POR_LADO[lado].map((b) => ({ b })), { valor: (x) => x.b, texto: (x) => BLOQUES[x.b] });
    if (BLOQUES_POR_LADO[lado].includes(actual)) form.elements.bloque_incoterm.value = actual;
    const servicio = servicioDe(form.elements.modo.value);
    document.getElementById("campo-equipo").hidden = !(servicio && servicio.usa_tipo_equipo);
    const enUso = enEdicion && enEdicion.tipo_equipo ? enEdicion.tipo_equipo.id : null;
    const tipos = catalogos.tipos.filter((t) => servicio && t.servicio_id === servicio.id && (t.activo || t.id === enUso));
    UI.opciones(form.elements.tipo_equipo_id, tipos, { valor: (t) => t.id, texto: (t) => t.codigo, todos: "Cualquiera" });
    document.getElementById("campo-iva").hidden = form.elements.bloque_fiscal.value !== "FACTURA";
    pintarTarifas();
    const manual = form.elements.metodo_venta.value === "MANUAL";
    document.getElementById("campo-parametro").hidden = manual;
    document.getElementById("campo-precio-manual").hidden = !manual;
    document.getElementById("campo-minimo-manual").hidden = !manual;
  }

  // D-R2: tarifas para vincular, filtradas por proveedor, servicio y puerto (según el lado); las ya vinculadas siempre.
  function pintarTarifas() {
    const elegidas = new Set([...form.elements.tarifas_ids.selectedOptions].map((o) => Number(o.value)));
    if (enEdicion && !form.dataset.tarifasListas) {
      for (const t of enEdicion.tarifas_vinculadas) elegidas.add(t.id);
    }
    const proveedor = Number(form.elements.proveedor_id.value) || null;
    const modo = form.elements.modo.value || null;
    const puerto = Number(form.elements.puerto_id.value) || null;
    const lado = form.elements.lado.value;
    const visibles = catalogos.tarifas.filter((t) => elegidas.has(t.id) || (
      (!proveedor || t.proveedor.id === proveedor) && (!modo || t.modo === modo)
      && (!puerto || (lado === "ORIGEN" ? t.origen.id : t.destino.id) === puerto)));
    form.elements.tarifas_ids.replaceChildren(...visibles.map((t) => {
      const opcion = crear("option", { texto: `#${t.id} ${t.proveedor.nombre} · ${t.modo}${t.tipo_equipo ? ` ${t.tipo_equipo.codigo}` : ""} · ${t.origen.codigo} → ${t.destino.codigo} · hasta ${t.valido_hasta}`, atributos: { value: t.id } });
      opcion.selected = elegidas.has(t.id);
      return opcion;
    }));
    form.dataset.tarifasListas = "1";
  }

  function abrir(recargo = null) {
    enEdicion = recargo;
    form.reset();
    delete form.dataset.tarifasListas;
    XPS.limpiarAlerta(alertasDialogo);
    document.getElementById("titulo-recargo").textContent = recargo ? `Editar recargo #${recargo.id}` : "Nuevo recargo";
    UI.opciones(form.elements.puerto_id, catalogos.puertos.filter((p) => p.activo || (recargo && recargo.puerto && p.id === recargo.puerto.id)), {
      valor: (p) => p.id,
      texto: (p) => `${p.codigo} · ${p.nombre} (${nombreUbicacion(p.tipo).toLowerCase()})`,
      todos: "De la tarifa vinculada",
    });
    UI.opciones(form.elements.servicios, catalogos.servicios.filter((s) => s.activo || (recargo && recargo.servicios_vinculados.includes(s.codigo))), { valor: (s) => s.codigo, texto: (s) => s.nombre });
    // Solo servicios activos para recargos nuevos; al editar, también el del recargo aunque esté inactivo.
    const ofrecidos = catalogos.servicios.filter((s) => s.activo || (recargo && s.codigo === recargo.modo));
    UI.opciones(form.elements.modo, ofrecidos, { valor: (s) => s.codigo, texto: (s) => (s.activo ? s.nombre : `${s.nombre} (inactivo)`), todos: "Todos los compatibles" });
    UI.opciones(form.elements.proveedor_id, catalogos.proveedores.filter((p) => p.activo), { valor: (p) => p.id, texto: (p) => p.nombre, todos: "Cargo propio de XPRESS" });
    UI.opciones(form.elements.moneda_id, catalogos.monedas.filter((m) => m.activo), { valor: (m) => m.id, texto: (m) => m.codigo });
    if (recargo) {
      form.elements.lado.value = recargo.lado;
      form.elements.metodo_venta.value = recargo.metodo_venta;
      form.elements.modo.value = recargo.modo || "";
    }
    ajustar();
    if (recargo) {
      const moneda = catalogos.monedas.find((m) => m.codigo === recargo.moneda);
      const valores = {
        puerto_id: recargo.puerto ? recargo.puerto.id : "",
        bloque_fiscal: recargo.bloque_fiscal,
        proveedor_id: recargo.proveedor ? recargo.proveedor.id : "",
        bloque_incoterm: recargo.bloque_incoterm,
        concepto: recargo.concepto,
        tipo_equipo_id: recargo.tipo_equipo ? recargo.tipo_equipo.id : "",
        rate_unit: recargo.rate_unit,
        moneda_id: moneda ? moneda.id : "",
        costo: recargo.costo,
        minimo: recargo.minimo,
        parametro_venta: recargo.parametro_venta,
        precio_venta_manual: recargo.precio_venta_manual,
        minimo_venta_manual: recargo.minimo_venta_manual,
        aplica_iva: String(recargo.aplica_iva),
        rol_ingreso: recargo.rol_ingreso,
        valido_desde: recargo.valido_desde,
        valido_hasta: recargo.valido_hasta,
      };
      for (const [campo, valor] of Object.entries(valores)) {
        form.elements[campo].value = valor === null || valor === undefined ? "" : String(valor);
      }
      for (const opcion of form.elements.servicios.options) opcion.selected = recargo.servicios_vinculados.includes(opcion.value);
    }
    ajustar();
    dialogo.showModal();
  }

  function leer() {
    const datos = {};
    for (const elemento of form.elements) {
      if (!elemento.name || elemento.closest("[hidden]") || elemento.multiple) continue;
      const valor = elemento.value.trim().replace(/^(-?\d+),(\d+)$/, "$1.$2");
      datos[elemento.name] = valor === "" ? null : valor;
    }
    for (const campo of ["puerto_id", "proveedor_id", "moneda_id", "tipo_equipo_id"]) {
      if (datos[campo] !== null && datos[campo] !== undefined) datos[campo] = Number(datos[campo]);
    }
    const servicio = servicioDe(datos.modo);
    if (!(servicio && servicio.usa_tipo_equipo)) datos.tipo_equipo_id = null;
    datos.aplica_iva = datos.bloque_fiscal === "FACTURA" ? datos.aplica_iva === "true" : false;
    datos.tarifas_ids = [...form.elements.tarifas_ids.selectedOptions].map((o) => Number(o.value));
    datos.servicios = [...form.elements.servicios.selectedOptions].map((o) => o.value);
    if (datos.metodo_venta === "MANUAL") datos.parametro_venta = null;
    else {
      datos.precio_venta_manual = null;
      datos.minimo_venta_manual = null;
    }
    return datos;
  }

  function original(campo) {
    const r = enEdicion;
    if (campo === "puerto_id") return r.puerto ? r.puerto.id : null;
    if (campo === "tarifas_ids") return r.tarifas_vinculadas.map((t) => t.id);
    if (campo === "servicios") return r.servicios_vinculados;
    if (campo === "proveedor_id") return r.proveedor ? r.proveedor.id : null;
    if (campo === "tipo_equipo_id") return r.tipo_equipo ? r.tipo_equipo.id : null;
    if (campo === "moneda_id") return (catalogos.monedas.find((m) => m.codigo === r.moneda) || {}).id;
    return r[campo];
  }

  form.elements.lado.addEventListener("change", ajustar);
  for (const nombre of ["bloque_fiscal", "proveedor_id", "puerto_id"]) form.elements[nombre].addEventListener("change", ajustar);
  form.elements.modo.addEventListener("change", ajustar);
  form.elements.metodo_venta.addEventListener("change", ajustar);

  form.addEventListener("submit", async (evento) => {
    evento.preventDefault();
    XPS.limpiarAlerta(alertasDialogo);
    const datos = leer();
    if (datos.bloque_fiscal === null || datos.rol_ingreso === null) {
      XPS.mostrarAlerta(alertasDialogo, "error", "Indique si va en Recibo de Caja o Factura y el rol del ingreso.");
      return;
    }
    if (datos.puerto_id === null && !datos.tarifas_ids.length) {
      XPS.mostrarAlerta(alertasDialogo, "error", "Elija el puerto o vincule el recargo a una tarifa.");
      return;
    }
    try {
      // D-R2: advertencia de coherencia (no bloquea): por ejemplo, un gasto de destino en un puerto de China.
      const { advertencias } = await XPS.api("/recargos/validar", { metodo: "POST", cuerpo: datos });
      if (advertencias.length && !window.confirm(`${advertencias.join("\n\n")}\n\n¿Guardar de todos modos?`)) {
        return;
      }
      if (enEdicion) {
        const cambios = {};
        for (const [campo, valor] of Object.entries(datos)) {
          if (JSON.stringify(valor ?? "") !== JSON.stringify(original(campo) ?? "") && String(valor ?? "") !== String(original(campo) ?? "")) cambios[campo] = valor;
        }
        if (Object.keys(cambios).length) {
          await XPS.api(`/recargos/${enEdicion.id}`, { metodo: "PATCH", cuerpo: cambios });
        }
      } else {
        await XPS.api("/recargos", { metodo: "POST", cuerpo: datos });
      }
      dialogo.close();
      XPS.mostrarAlerta(alertas, "exito", "Recargo guardado.");
      await cargar();
    } catch (error) {
      XPS.mostrarError(alertasDialogo, error);
    }
  });

  async function cambiarEstado(recargo) {
    XPS.limpiarAlerta(alertas);
    try {
      await XPS.api(`/recargos/${recargo.id}`, { metodo: "PATCH", cuerpo: { activo: !recargo.activo } });
      XPS.mostrarAlerta(alertas, "exito", recargo.activo ? "Recargo desactivado." : "Recargo activado.");
      await cargar();
    } catch (error) {
      XPS.mostrarError(alertas, error);
    }
  }

  // ---------- Inicio ----------

  const yo = await iniciarLayout("recargos.html");
  if (!yo || !UI.exigirAlguno(yo, ["tarifa.editar", "costo.ver"], alertas)) {
    return;
  }
  puedeEditar = UI.tieneAlguno(yo, ["tarifa.editar"]);
  document.getElementById("nota-lectura").hidden = puedeEditar;
  UI.prepararDialogo(dialogo);
  botonNuevo.addEventListener("click", () => abrir());
  for (const control of Object.values(filtros)) {
    control.addEventListener("change", () => {
      pagina = 0;
      seguro(cargar);
    });
  }

  try {
    diasAlerta = await UI.diasAlerta();
    const [todos, puertos, proveedores, monedas, tipos, servicios, ubicaciones, tarifas] = await Promise.all([
      XPS.api("/recargos"),
      XPS.api("/puertos"),
      XPS.api("/proveedores"),
      XPS.api("/monedas"),
      XPS.api("/tipos-equipo"),
      XPS.api("/servicios"),
      XPS.api("/tipos-ubicacion"),
      XPS.api("/tarifas?activo=true"),
    ]);
    catalogos = { puertos, proveedores, monedas, tipos, servicios, ubicaciones, tarifas };
    UI.opciones(filtros.modo, servicios, { valor: (s) => s.codigo, texto: (s) => s.nombre, todos: "Todos" });
    const conRecargos = new Set(todos.filter((r) => r.puerto).map((r) => r.puerto.id));
    UI.opciones(filtros.puerto, puertos.filter((p) => conRecargos.has(p.id)), { valor: (p) => p.id, texto: (p) => `${p.codigo} · ${p.nombre}`, todos: "Todos" });
    UI.opciones(filtros.bloque, Object.keys(BLOQUES).map((b) => ({ b })), { valor: (x) => x.b, texto: (x) => BLOQUES[x.b], todos: "Todos" });
    UI.opciones(filtros.proveedor, proveedores, { valor: (p) => p.id, texto: (p) => p.nombre, todos: "Todos" });
    await cargar();
    herramientas.hidden = false;
    botonNuevo.hidden = !puedeEditar;
  } catch (error) {
    XPS.mostrarError(alertas, error);
  }
})();
