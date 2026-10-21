/* P6 Tarifas. tarifa.ver lee; tarifa.editar crea, edita, duplica, desactiva y edita tramos.
 * Gating (D-F2-5): el backend decide qué claves envía. Esta pantalla solo dibuja las columnas de
 * costo y margen si esas claves existen en el JSON; nunca las oculta con CSS ni calcula precios.
 * E0: los servicios, sus unidades, sus tipos de ubicación y sus tramos salen del catálogo (/servicios y
 * /formas-cobro); aquí no hay modos fijos.
 */
"use strict";

(async () => {
  const { crear } = XPS;
  const OPCIONALES = ["parametro_venta", "precio_venta_manual", "minimo_venta_manual", "transit_time_dias", "dias_libres", "notas", "tipo_equipo_id", "transportista"];

  const alertas = document.getElementById("alertas");
  const herramientas = document.getElementById("herramientas");
  const botonNueva = document.getElementById("btn-nueva");
  const cabecera = document.getElementById("cabecera-tarifas");
  const cuerpo = document.getElementById("tabla-tarifas");
  const filtros = {
    modo: document.getElementById("filtro-modo"),
    origen: document.getElementById("filtro-origen"),
    destino: document.getElementById("filtro-destino"),
    proveedor: document.getElementById("filtro-proveedor"),
    tipo_equipo: document.getElementById("filtro-equipo"),
    vigente_en: document.getElementById("filtro-vigente"),
    por_vencer: document.getElementById("filtro-por-vencer"),
    activo: document.getElementById("filtro-activo"),
  };

  const dialogoFicha = document.getElementById("dialogo-ficha");
  const dialogoTarifa = document.getElementById("dialogo-tarifa");
  const formTarifa = document.getElementById("form-tarifa");
  const alertasTarifa = document.getElementById("alertas-tarifa");
  const dialogoDuplicar = document.getElementById("dialogo-duplicar");
  const formDuplicar = document.getElementById("form-duplicar");
  const alertasDuplicar = document.getElementById("alertas-duplicar");
  const dialogoTramos = document.getElementById("dialogo-tramos");
  const formTramos = document.getElementById("form-tramos");
  const alertasTramos = document.getElementById("alertas-tramos");

  let puedeEditar = false;
  let diasAlerta = "7";
  let catalogos = { puertos: [], proveedores: [], monedas: [], tipos: [], servicios: [], formas: [], tiposCarga: [] };

  // D-T4: tipos de carga que acepta la tarifa y clases IMO excluidas (solo si acepta un tipo que pide datos IMO).
  function pintarCarga(tarifa) {
    const tipos = formTarifa.elements.tipos_carga;
    const elegidos = new Set(tarifa ? tarifa.tipos_carga : ["GENERAL"]);
    tipos.replaceChildren(...catalogos.tiposCarga.filter((t) => t.activo || elegidos.has(t.codigo)).map((t) => {
      const opcion = crear("option", { texto: t.nombre, atributos: { value: t.codigo } });
      opcion.selected = elegidos.has(t.codigo);
      return opcion;
    }));
    const excluidas = new Set(tarifa ? tarifa.clases_imo_excluidas : []);
    formTarifa.elements.clases_imo_excluidas.replaceChildren(...["1", "2", "3", "4", "5", "6", "7", "8", "9"].map((c) => {
      const opcion = crear("option", { texto: `Clase ${c}`, atributos: { value: c } });
      opcion.selected = excluidas.has(c);
      return opcion;
    }));
    ajustarCarga();
  }

  function ajustarCarga() {
    const imo = new Set(catalogos.tiposCarga.filter((t) => t.pide_imo).map((t) => t.codigo));
    document.getElementById("campo-clases-excluidas").hidden = ![...formTarifa.elements.tipos_carga.selectedOptions].some((o) => imo.has(o.value));
  }
  let enEdicion = null;
  let enFicha = null;

  const ruta = (t) => `${t.origen.codigo} → ${t.destino.codigo}`;

  // ---------- Servicios (E0) ----------

  const servicioDe = (codigo) => catalogos.servicios.find((s) => s.codigo === codigo) || null;
  const formaDe = (servicio) => (servicio && catalogos.formas.find((f) => f.codigo === servicio.forma_cobro)) || null;
  const nombreServicio = (codigo) => (servicioDe(codigo) || { nombre: codigo }).nombre;
  const etiquetaServicio = (t) => (t.tipo_equipo ? `${nombreServicio(t.modo)} ${t.tipo_equipo.codigo}` : nombreServicio(t.modo));

  /** H-F4-2 + E0: los "desde" activos del servicio en la unidad de peso de la tarifa. */
  function desdesDe(tarifa) {
    const servicio = servicioDe(tarifa.modo);
    const unidad = tarifa.unidad_peso === "LB" ? "LB" : "KG";
    return (servicio ? servicio.tramos : [])
      .filter((t) => t.activo && t.unidad_peso === unidad)
      .map((t) => t.desde)
      .sort((a, b) => a - b);
  }

  // ---------- Listado ----------

  function opcionesDeFiltro(tarifas) {
    const unicos = (lista, clave) => [...new Map(lista.filter(Boolean).map((x) => [x.id, x])).values()];
    UI.opciones(filtros.origen, unicos(tarifas.map((t) => t.origen)), { valor: (p) => p.id, texto: (p) => `${p.codigo} · ${p.nombre}`, todos: "Todos" });
    UI.opciones(filtros.destino, unicos(tarifas.map((t) => t.destino)), { valor: (p) => p.id, texto: (p) => `${p.codigo} · ${p.nombre}`, todos: "Todos" });
    UI.opciones(filtros.proveedor, unicos(tarifas.map((t) => t.proveedor)), { valor: (p) => p.id, texto: (p) => p.nombre, todos: "Todos" });
    UI.opciones(filtros.tipo_equipo, catalogos.tipos, { valor: (t) => t.id, texto: (t) => t.codigo, todos: "Todos" });
  }

  function pintar(lista) {
    // Las columnas de costo existen solo si el backend envió esas claves.
    const conCosto = lista.some((t) => "costo" in t);
    const conMargen = lista.some((t) => "margen_pct" in t);
    const columnas = ["Ruta", "Servicio", "Proveedor", "Unidad", "Venta", "Venta mínima"];
    if (conCosto) columnas.push("Costo");
    if (conMargen) columnas.push("Margen");
    columnas.push("Vigencia", "Estado", "Acciones");
    cabecera.replaceChildren(crear("tr", {}, columnas.map((c) => crear("th", { texto: c }))));

    cuerpo.replaceChildren(...(lista.length ? [] : [UI.filaVacia(columnas.length, "No hay tarifas con estos filtros.")]));
    for (const tarifa of lista) {
      const celdas = [
        UI.celda("Ruta", [UI.texto(ruta(tarifa), "cifra")]),
        UI.celda("Servicio", [UI.texto(etiquetaServicio(tarifa))]),
        UI.celda("Proveedor", [UI.texto(tarifa.proveedor.nombre)]),
        UI.celda("Unidad", [UI.texto(tarifa.tiene_tramos ? `${tarifa.rate_unit} (tramos)` : tarifa.rate_unit)]),
        UI.celda("Venta", [UI.monto(tarifa.precio_venta, tarifa.moneda)]),
        UI.celda("Venta mínima", [UI.monto(tarifa.precio_venta_minimo, tarifa.moneda)]),
      ];
      if (conCosto) celdas.push(UI.celda("Costo", [UI.monto(tarifa.costo, tarifa.moneda)]));
      if (conMargen) celdas.push(UI.celda("Margen", [UI.texto(`${tarifa.margen_pct} %`, "cifra")]));
      celdas.push(
        UI.celda("Vigencia", [
          crear("div", {}, [
            UI.texto(`${tarifa.valido_desde} a ${tarifa.valido_hasta}`, "cifra"),
            crear("div", {}, [UI.badgeVigencia(tarifa.estado_vigencia, diasAlerta)]),
          ]),
        ]),
        UI.celda("Estado", [UI.badgeEstado(tarifa.activo)])
      );
      const acciones = [UI.boton("Ver", () => abrirFicha(tarifa))];
      if (puedeEditar) {
        acciones.push(
          UI.boton("Editar", () => abrirEditor(tarifa)),
          UI.boton("Duplicar", () => abrirDuplicar(tarifa)),
          UI.boton(tarifa.activo ? "Desactivar" : "Activar", () => cambiarEstado(tarifa))
        );
      }
      celdas.push(UI.celda("Acciones", [crear("div", { clase: "celda-acciones" }, acciones)]));
      cuerpo.append(crear("tr", {}, celdas));
    }
  }

  // F5-A2: paginado en el servidor, con los mismos filtros.
  const POR_PAGINA = 25;
  let pagina = 0;
  const pintarPaginador = UI.paginador(document.getElementById("paginador-tarifas"), POR_PAGINA, (nueva) => {
    pagina = Math.max(0, nueva);
    seguro(cargar);
  });

  async function cargar() {
    const parametros = { limit: POR_PAGINA, offset: pagina * POR_PAGINA };
    for (const [clave, control] of Object.entries(filtros)) {
      parametros[clave] = control.value;
    }
    const { datos, total } = await XPS.api(UI.consulta("/tarifas", parametros), { conTotal: true });
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

  // ---------- Ficha y tramos ----------

  function par(etiqueta, valor) {
    return crear("div", {}, [crear("dt", { texto: etiqueta }), crear("dd", {}, [valor instanceof Node ? valor : UI.texto(valor)])]);
  }

  async function abrirFicha(tarifa) {
    enFicha = tarifa;
    document.getElementById("titulo-ficha").textContent = `Tarifa #${tarifa.id} · ${ruta(tarifa)}`;
    const datos = [
      par("Proveedor", tarifa.proveedor.nombre),
      par("Servicio", etiquetaServicio(tarifa)),
      par("Unidad", tarifa.rate_unit === "KG" ? `${tarifa.rate_unit} · por ${tarifa.unidad_peso === "LB" ? "libra" : "kilo"}` : tarifa.rate_unit),
      par("Transportista", tarifa.transportista),
      par("Acepta carga", `${(tarifa.tipos_carga || ["GENERAL"]).join(", ")}${(tarifa.clases_imo_excluidas || []).length ? ` (sin IMO clase ${tarifa.clases_imo_excluidas.join(", ")})` : ""}`),
      par("Moneda", tarifa.moneda),
      par("Venta", UI.monto(tarifa.precio_venta, tarifa.moneda)),
      par("Venta mínima", UI.monto(tarifa.precio_venta_minimo, tarifa.moneda)),
      par("Transit time (días)", tarifa.transit_time_dias),
      par("Días libres", tarifa.dias_libres),
      par("Vigencia", `${tarifa.valido_desde} a ${tarifa.valido_hasta}`),
      par("Estado", UI.badgeVigencia(tarifa.estado_vigencia, diasAlerta)),
    ];
    if ("costo" in tarifa) {
      datos.push(
        par("Costo", UI.monto(tarifa.costo, tarifa.moneda)),
        par("Mínimo de costo", UI.monto(tarifa.minimo, tarifa.moneda)),
        par("Método de venta", tarifa.metodo_venta),
        par("Parámetro", tarifa.parametro_venta),
        par("Notas", tarifa.notas)
      );
    }
    if ("margen_pct" in tarifa) {
      datos.push(par("Margen", `${tarifa.margen_unitario} ${tarifa.moneda} (${tarifa.margen_pct} %)`));
    }
    document.getElementById("ficha-datos").replaceChildren(...datos);

    const bloqueTramos = document.getElementById("bloque-tramos");
    bloqueTramos.hidden = !tarifa.tiene_tramos;
    const forma = formaDe(servicioDe(tarifa.modo));
    document.getElementById("btn-editar-tramos").hidden = !(puedeEditar && forma && forma.usa_tramos && tarifa.rate_unit === "KG");
    if (tarifa.tiene_tramos) {
      try {
        pintarTramos(await XPS.api(`/tarifas/${tarifa.id}/tramos`), tarifa.moneda, tarifa.unidad_peso, desdesDe(tarifa));
      } catch (error) {
        XPS.mostrarError(alertas, error);
      }
    }
    try {
      await pintarVinculos(tarifa);
    } catch (error) {
      XPS.mostrarError(alertas, error);
    }
    dialogoFicha.showModal();
  }

  // ---------- D-R2: recargos vinculados a la tarifa ----------

  const FISCAL = { RECIBO_CAJA: "Recibo de Caja", FACTURA: "Factura" };
  const BLOQUE = { RECOGIDA_ORIGEN: "Recogida en origen", DESPACHO_EXPORT: "Despacho de exportación", GASTOS_ORIGEN: "Gastos en origen",
    SEGURO: "Seguro", GASTOS_DESTINO: "Gastos en destino", DESPACHO_IMPORT: "Despacho de importación", ENTREGA_FINAL: "Entrega final" };

  async function pintarVinculos(tarifa) {
    const alertasVinculos = document.getElementById("alertas-vinculos");
    XPS.limpiarAlerta(alertasVinculos);
    const vinculados = await XPS.api(`/tarifas/${tarifa.id}/recargos`);
    const cuerpoVinculos = document.getElementById("tabla-vinculos");
    cuerpoVinculos.replaceChildren(...(vinculados.length ? [] : [UI.filaVacia(5, "Esta tarifa no tiene recargos vinculados.")]));
    for (const recargo of vinculados) {
      const acciones = puedeEditar ? [UI.boton("Desvincular", () => cambiarVinculo(tarifa, recargo.id, false))] : [];
      cuerpoVinculos.append(crear("tr", {}, [
        UI.celda("Concepto", [UI.texto(recargo.concepto)]),
        UI.celda("Lado y bloque", [UI.texto(`${recargo.lado === "ORIGEN" ? "Origen" : "Destino"} · ${BLOQUE[recargo.bloque_incoterm]}`)]),
        UI.celda("Va en", [UI.texto(`${FISCAL[recargo.bloque_fiscal]}${recargo.bloque_fiscal === "FACTURA" && recargo.aplica_iva ? " con IVA" : ""}`)]),
        UI.celda("Vigencia", [UI.texto(`${recargo.valido_desde} a ${recargo.valido_hasta}`, "cifra")]),
        UI.celda("Acciones", acciones),
      ]));
    }
    document.getElementById("vincular-nuevo").hidden = !puedeEditar;
    if (puedeEditar) {
      const ya = new Set(vinculados.map((r) => r.id));
      const candidatos = (await XPS.api("/recargos?activo=true")).filter((r) => !ya.has(r.id)
        && (!r.proveedor || r.proveedor.id === tarifa.proveedor.id) && (!r.modo || r.modo === tarifa.modo));
      UI.opciones(document.getElementById("vincular-recargo"), candidatos, {
        valor: (r) => r.id,
        texto: (r) => `#${r.id} ${r.concepto} · ${r.lado === "ORIGEN" ? "origen" : "destino"} · ${r.puerto ? r.puerto.codigo : "de la tarifa"} · ${r.proveedor ? r.proveedor.nombre : "XPRESS"}`,
        todos: "Elija un recargo…",
      });
    }
  }

  async function cambiarVinculo(tarifa, recargoId, vincular) {
    const alertasVinculos = document.getElementById("alertas-vinculos");
    try {
      await XPS.api(`/tarifas/${tarifa.id}/recargos/${recargoId}`, { metodo: vincular ? "POST" : "DELETE" });
      await pintarVinculos(tarifa);
      XPS.mostrarAlerta(alertasVinculos, "exito", vincular ? "Recargo vinculado." : "Recargo desvinculado.");
    } catch (error) {
      XPS.mostrarError(alertasVinculos, error);
    }
  }

  function pintarTramos(tramos, moneda, unidadPeso = "KG", permitidos = []) {
    const u = unidadPeso === "LB" ? "lb" : "kg";
    // El tramo 0 se lee "hasta el siguiente" (−45 en el aéreo): el siguiente "desde" del servicio o de la tarifa.
    const primero = permitidos[1] ?? (tramos[1] ? tramos[1].desde_kg : "");
    const conCosto = tramos.some((t) => "costo_kg" in t);
    const columnas = [`Desde (${u})`, `Venta por ${u}`];
    if (conCosto) columnas.push(`Costo por ${u}`);
    document.getElementById("cabecera-tramos").replaceChildren(crear("tr", {}, columnas.map((c) => crear("th", { texto: c }))));
    document.getElementById("tabla-tramos").replaceChildren(
      ...tramos.map((tramo) => {
        const celdas = [
          UI.celda(`Desde (${u})`, [UI.texto(tramo.desde_kg === 0 ? `−${primero}` : `+${tramo.desde_kg}`, "cifra")]),
          UI.celda(`Venta por ${u}`, [UI.monto(tramo.precio_venta_kg, moneda)]),
        ];
        if (conCosto) celdas.push(UI.celda(`Costo por ${u}`, [UI.monto(tramo.costo_kg, moneda)]));
        return crear("tr", {}, celdas);
      })
    );
  }

  async function abrirTramos() {
    const tarifa = enFicha;
    XPS.limpiarAlerta(alertasTramos);
    const actuales = tarifa.tiene_tramos ? await XPS.api(`/tarifas/${tarifa.id}/tramos`) : [];
    const porDesde = new Map(actuales.map((t) => [t.desde_kg, t]));
    const manual = tarifa.metodo_venta === "MANUAL";
    // Los activos del servicio y, para no perderlos de vista, los que la tarifa ya tiene (aunque estén inactivos).
    const lista = [...new Set([...desdesDe(tarifa), ...actuales.map((t) => t.desde_kg)])].sort((a, b) => a - b);
    if (!lista.length) {
      XPS.mostrarAlerta(alertas, "error", "El servicio no tiene tramos activos en esta unidad; cárguelos en Administración → Servicios.");
      return;
    }
    const u = tarifa.unidad_peso === "LB" ? "lb" : "kg";
    const filas = lista.map((desde) => {
      const actual = porDesde.get(desde);
      const costo = crear("input", { clase: "input cifra", atributos: { type: "text", inputmode: "decimal", "data-desde": desde, "data-campo": "costo_kg", "aria-label": `Costo por ${u} desde ${desde}` } });
      costo.value = actual && actual.costo_kg ? actual.costo_kg : "";
      const campos = [
        crear("div", { clase: "campo" }, [crear("span", { clase: "etiqueta", texto: desde === 0 && lista.length > 1 ? `Desde 0 ${u} (−${lista[1]})` : `Desde ${desde} ${u}` }), costo]),
      ];
      if (manual) {
        const venta = crear("input", { clase: "input cifra", atributos: { type: "text", inputmode: "decimal", "data-desde": desde, "data-campo": "precio_venta_kg", "aria-label": `Venta por ${u} desde ${desde}` } });
        venta.value = actual ? actual.precio_venta_kg : "";
        campos.push(crear("div", { clase: "campo" }, [crear("span", { clase: "etiqueta", texto: `Venta por ${u}` }), venta]));
      }
      return crear("div", { clase: "grupo-campos" }, campos);
    });
    document.getElementById("filas-tramos").replaceChildren(...filas);
    dialogoFicha.close();
    dialogoTramos.showModal();
  }

  formTramos.addEventListener("submit", async (evento) => {
    evento.preventDefault();
    XPS.limpiarAlerta(alertasTramos);
    const tramos = [];
    const desdes = [...formTramos.querySelectorAll('[data-campo="costo_kg"]')].map((campo) => campo.dataset.desde);
    for (const desde of desdes) {
      const costo = formTramos.querySelector(`[data-desde="${desde}"][data-campo="costo_kg"]`).value.trim().replace(",", ".");
      const ventaCampo = formTramos.querySelector(`[data-desde="${desde}"][data-campo="precio_venta_kg"]`);
      if (!costo) continue;
      const tramo = { desde_kg: Number(desde), costo_kg: costo };
      if (ventaCampo) tramo.precio_venta_kg = ventaCampo.value.trim().replace(",", ".") || null;
      tramos.push(tramo);
    }
    try {
      await XPS.api(`/tarifas/${enFicha.id}/tramos`, { metodo: "PUT", cuerpo: { tramos } });
      dialogoTramos.close();
      XPS.mostrarAlerta(alertas, "exito", "Tramos guardados.");
      await cargar();
    } catch (error) {
      XPS.mostrarError(alertasTramos, error);
    }
  });

  // ---------- Alta y edición ----------

  function ajustarFormulario() {
    const servicio = servicioDe(formTarifa.elements.modo.value);
    const forma = formaDe(servicio);
    const usados = enEdicion ? [enEdicion.origen.id, enEdicion.destino.id] : [];
    for (const [campo, tipo] of [["origen_puerto_id", servicio && servicio.tipo_ubicacion_origen], ["destino_puerto_id", servicio && servicio.tipo_ubicacion_destino]]) {
      const puertos = catalogos.puertos.filter((p) => p.tipo === tipo && (p.activo || usados.includes(p.id)));
      UI.opciones(formTarifa.elements[campo], puertos, { valor: (p) => p.id, texto: (p) => `${p.codigo} · ${p.nombre}` });
    }
    UI.opciones(formTarifa.elements.rate_unit, (forma ? forma.unidades_tarifa : []).map((u) => ({ u })), { valor: (x) => x.u, texto: (x) => x.u });
    document.getElementById("ayuda-servicio").textContent = forma ? `${forma.nombre}: ${forma.descripcion}` : "";
    document.getElementById("campo-equipo").hidden = !(servicio && servicio.usa_tipo_equipo);
    const enUso = enEdicion && enEdicion.tipo_equipo ? enEdicion.tipo_equipo.id : null;
    const tipos = catalogos.tipos.filter((t) => servicio && t.servicio_id === servicio.id && (t.activo || t.id === enUso));
    UI.opciones(formTarifa.elements.tipo_equipo_id, tipos, { valor: (t) => t.id, texto: (t) => `${t.codigo} · ${t.nombre}` });
    // D2 + E0: la unidad de peso (kg o lb) solo existe si el servicio admite libras y el precio es por peso.
    document.getElementById("campo-unidad-peso").hidden = !(servicio && servicio.permite_libras && formTarifa.elements.rate_unit.value === "KG");
    const manual = formTarifa.elements.metodo_venta.value === "MANUAL";
    document.getElementById("campo-parametro").hidden = manual;
    document.getElementById("campo-precio-manual").hidden = !manual;
    document.getElementById("campo-minimo-manual").hidden = !manual;
  }

  function abrirEditor(tarifa = null) {
    enEdicion = tarifa;
    formTarifa.reset();
    XPS.limpiarAlerta(alertasTarifa);
    document.getElementById("titulo-tarifa").textContent = tarifa ? `Editar tarifa #${tarifa.id}` : "Nueva tarifa";
    const proveedores = catalogos.proveedores.filter((p) => p.activo || (tarifa && p.id === tarifa.proveedor.id));
    UI.opciones(formTarifa.elements.proveedor_id, proveedores, { valor: (p) => p.id, texto: (p) => p.nombre });
    UI.opciones(formTarifa.elements.moneda_id, catalogos.monedas.filter((m) => m.activo), { valor: (m) => m.id, texto: (m) => m.codigo });
    // Solo servicios activos para tarifas nuevas; al editar, también el de la tarifa aunque esté inactivo.
    const ofrecidos = catalogos.servicios.filter((s) => s.activo || (tarifa && s.codigo === tarifa.modo));
    UI.opciones(formTarifa.elements.modo, ofrecidos, { valor: (s) => s.codigo, texto: (s) => (s.activo ? s.nombre : `${s.nombre} (inactivo)`) });
    if (tarifa) {
      formTarifa.elements.modo.value = tarifa.modo;
      formTarifa.elements.metodo_venta.value = tarifa.metodo_venta;
    }
    ajustarFormulario();
    if (tarifa) {
      const moneda = catalogos.monedas.find((m) => m.codigo === tarifa.moneda);
      const valores = {
        proveedor_id: tarifa.proveedor.id,
        origen_puerto_id: tarifa.origen.id,
        destino_puerto_id: tarifa.destino.id,
        tipo_equipo_id: tarifa.tipo_equipo ? tarifa.tipo_equipo.id : "",
        rate_unit: tarifa.rate_unit,
        moneda_id: moneda ? moneda.id : "",
        costo: tarifa.costo,
        minimo: tarifa.minimo,
        parametro_venta: tarifa.parametro_venta,
        precio_venta_manual: tarifa.precio_venta_manual,
        minimo_venta_manual: tarifa.minimo_venta_manual,
        transit_time_dias: tarifa.transit_time_dias,
        dias_libres: tarifa.dias_libres,
        valido_desde: tarifa.valido_desde,
        valido_hasta: tarifa.valido_hasta,
        notas: tarifa.notas,
        unidad_peso: tarifa.unidad_peso,
        transportista: tarifa.transportista,
      };
      for (const [campo, valor] of Object.entries(valores)) {
        formTarifa.elements[campo].value = valor === null || valor === undefined ? "" : String(valor);
      }
    }
    const conTramos = Boolean(tarifa && tarifa.tiene_tramos);
    document.getElementById("nota-tramos").hidden = !conTramos;
    ajustarFormulario();
    for (const campo of ["modo", "rate_unit", "metodo_venta", "costo", "unidad_peso"]) {
      formTarifa.elements[campo].disabled = conTramos;
    }
    formTarifa.elements.precio_venta_manual.disabled = conTramos;
    pintarCarga(tarifa);
    dialogoTarifa.showModal();
  }

  function leerFormulario() {
    const datos = {};
    for (const elemento of formTarifa.elements) {
      if (!elemento.name || elemento.disabled || elemento.closest("[hidden]") || elemento.multiple) continue;
      const valor = elemento.value.trim().replace(/^(-?\d+),(\d+)$/, "$1.$2");
      datos[elemento.name] = valor === "" ? null : valor;
    }
    for (const campo of ["proveedor_id", "origen_puerto_id", "destino_puerto_id", "moneda_id", "tipo_equipo_id", "transit_time_dias", "dias_libres"]) {
      if (datos[campo] !== null && datos[campo] !== undefined) datos[campo] = Number(datos[campo]);
    }
    if (document.getElementById("campo-unidad-peso").hidden) datos.unidad_peso = "KG";
    datos.tipos_carga = [...formTarifa.elements.tipos_carga.selectedOptions].map((o) => o.value).sort();
    if (!datos.tipos_carga.length) datos.tipos_carga = ["GENERAL"];
    datos.clases_imo_excluidas = document.getElementById("campo-clases-excluidas").hidden ? []
      : [...formTarifa.elements.clases_imo_excluidas.selectedOptions].map((o) => o.value).sort();
    const metodo = datos.metodo_venta || (enEdicion && enEdicion.metodo_venta);
    // Campos que no corresponden al servicio o al método van vacíos, como exige el backend.
    const servicio = servicioDe(datos.modo || (enEdicion && enEdicion.modo));
    if (!(servicio && servicio.usa_tipo_equipo)) datos.tipo_equipo_id = null;
    if (metodo === "MANUAL") datos.parametro_venta = null;
    else {
      datos.precio_venta_manual = null;
      datos.minimo_venta_manual = null;
    }
    return datos;
  }

  formTarifa.elements.modo.addEventListener("change", ajustarFormulario);
  formTarifa.elements.metodo_venta.addEventListener("change", ajustarFormulario);
  formTarifa.elements.rate_unit.addEventListener("change", ajustarFormulario);

  formTarifa.addEventListener("submit", async (evento) => {
    evento.preventDefault();
    XPS.limpiarAlerta(alertasTarifa);
    const datos = leerFormulario();
    try {
      if (enEdicion) {
        const cambios = {};
        for (const [campo, valor] of Object.entries(datos)) {
          const original = campo === "proveedor_id" ? enEdicion.proveedor.id
            : campo === "origen_puerto_id" ? enEdicion.origen.id
            : campo === "destino_puerto_id" ? enEdicion.destino.id
            : campo === "tipo_equipo_id" ? (enEdicion.tipo_equipo ? enEdicion.tipo_equipo.id : null)
            : campo === "moneda_id" ? (catalogos.monedas.find((m) => m.codigo === enEdicion.moneda) || {}).id
            : enEdicion[campo];
          if (String(valor ?? "") !== String(original ?? "")) cambios[campo] = valor;
        }
        if (Object.keys(cambios).length) {
          await XPS.api(`/tarifas/${enEdicion.id}`, { metodo: "PATCH", cuerpo: cambios });
        }
      } else {
        await XPS.api("/tarifas", { metodo: "POST", cuerpo: datos });
      }
      dialogoTarifa.close();
      XPS.mostrarAlerta(alertas, "exito", "Tarifa guardada.");
      await cargar();
    } catch (error) {
      XPS.mostrarError(alertasTarifa, error);
    }
  });

  // ---------- Duplicar y estado ----------

  function abrirDuplicar(tarifa) {
    enEdicion = tarifa;
    formDuplicar.reset();
    XPS.limpiarAlerta(alertasDuplicar);
    document.getElementById("duplicar-referencia").textContent = `#${tarifa.id} · ${ruta(tarifa)} · ${tarifa.valido_desde} a ${tarifa.valido_hasta}`;
    dialogoDuplicar.showModal();
  }

  formDuplicar.addEventListener("submit", async (evento) => {
    evento.preventDefault();
    XPS.limpiarAlerta(alertasDuplicar);
    const cuerpoDuplicar = { valido_desde: formDuplicar.elements.valido_desde.value, valido_hasta: formDuplicar.elements.valido_hasta.value,
      copiar_vinculos: formDuplicar.elements.copiar_vinculos.checked };
    if (!cuerpoDuplicar.valido_desde || !cuerpoDuplicar.valido_hasta) {
      XPS.mostrarAlerta(alertasDuplicar, "error", "Indique las dos fechas de la nueva vigencia.");
      return;
    }
    try {
      const copia = await XPS.api(`/tarifas/${enEdicion.id}/duplicar`, { metodo: "POST", cuerpo: cuerpoDuplicar });
      dialogoDuplicar.close();
      XPS.mostrarAlerta(alertas, "exito", `Tarifa duplicada como #${copia.id}.`);
      await cargar();
    } catch (error) {
      XPS.mostrarError(alertasDuplicar, error);
    }
  });

  async function cambiarEstado(tarifa) {
    XPS.limpiarAlerta(alertas);
    try {
      await XPS.api(`/tarifas/${tarifa.id}`, { metodo: "PATCH", cuerpo: { activo: !tarifa.activo } });
      XPS.mostrarAlerta(alertas, "exito", tarifa.activo ? "Tarifa desactivada." : "Tarifa activada.");
      await cargar();
    } catch (error) {
      XPS.mostrarError(alertas, error);
    }
  }

  // ---------- Inicio ----------

  document.getElementById("btn-vincular").addEventListener("click", () => {
    const elegido = Number(document.getElementById("vincular-recargo").value);
    if (enFicha && elegido) cambiarVinculo(enFicha, elegido, true);
  });

  const yo = await iniciarLayout("tarifas.html");
  if (!yo || !UI.exigirAlguno(yo, ["tarifa.ver"], alertas)) {
    return;
  }
  puedeEditar = UI.tieneAlguno(yo, ["tarifa.editar"]);
  document.getElementById("nota-lectura").hidden = puedeEditar;
  for (const dialogo of [dialogoFicha, dialogoTarifa, dialogoDuplicar, dialogoTramos]) {
    UI.prepararDialogo(dialogo);
  }
  document.getElementById("btn-editar-tramos").addEventListener("click", () => seguro(abrirTramos));
  botonNueva.addEventListener("click", () => abrirEditor());
  for (const control of Object.values(filtros)) {
    control.addEventListener("change", () => {
      pagina = 0;
      seguro(cargar);
    });
  }

  try {
    diasAlerta = await UI.diasAlerta();
    const [todas, tipos, servicios, formas] = await Promise.all([
      XPS.api("/tarifas"), XPS.api("/tipos-equipo"), XPS.api("/servicios"), XPS.api("/formas-cobro"),
    ]);
    catalogos = { ...catalogos, tipos, servicios, formas };
    UI.opciones(filtros.modo, servicios, { valor: (s) => s.codigo, texto: (s) => s.nombre, todos: "Todos" });
    opcionesDeFiltro(todas);
    if (puedeEditar) {
      const [puertos, proveedores, monedas, tiposCarga] = await Promise.all([XPS.api("/puertos"), XPS.api("/proveedores"),
        XPS.api("/monedas"), XPS.api("/tipos-carga")]);
      catalogos = { ...catalogos, puertos, proveedores, monedas, tiposCarga };
      formTarifa.elements.tipos_carga.addEventListener("change", ajustarCarga);
    }
    await cargar();
    herramientas.hidden = false;
    botonNueva.hidden = !puedeEditar;
  } catch (error) {
    XPS.mostrarError(alertas, error);
  }
})();
