/* FIX cotizador: panel "Cargos de esta cotización".
 * Agrupa las líneas en Recibo de Caja (IVA 0%) y Factura (IVA n%), con casillas para marcar o desmarcar cada
 * recargo, subtotales, IVA y total general (los calcula el backend en cada cambio). Los recargos fuera del
 * Incoterm y las alternativas (D-F3-7) llegan desmarcados. Costo y margen solo se dibujan si vienen en el JSON
 * (el gating lo hace el service). "¿Por qué no aparece?" lista los recargos que quedaron fuera y su motivo.
 */
"use strict";

const Cargos = (() => {
  const { crear } = XPS;
  const BLOQUES = {
    RECOGIDA_ORIGEN: "Recogida en origen", DESPACHO_EXPORT: "Despacho de exportación", GASTOS_ORIGEN: "Gastos en origen",
    FLETE_PRINCIPAL: "Flete principal", SEGURO: "Seguro", GASTOS_DESTINO: "Gastos en destino",
    DESPACHO_IMPORT: "Despacho de importación", ENTREGA_FINAL: "Entrega final",
  };
  const UNIDADES = { PCT_VALOR: "% del valor", PCT_RECIBO: "% sobre recibo", WM: "W/M", CONTENEDOR: "contenedor", ENVIO: "envío" };

  function etiquetas(linea) {
    const salida = [crear("span", { clase: "texto-suave", texto: BLOQUES[linea.bloque_incoterm] || linea.bloque_incoterm })];
    if (linea.vinculado) {
      salida.push(crear("span", { clase: "badge badge-estado badge-activo", texto: "Vinculado" }));
    }
    if (linea.seleccion === "FUERA_INCOTERM") {
      salida.push(crear("span", { clase: "badge badge-estado badge-alerta", texto: "Fuera del Incoterm" }));
    }
    if (linea.seleccion === "ALTERNATIVA") {
      salida.push(crear("span", { clase: "badge badge-estado badge-inactivo", texto: "Alternativa" }));
      if (linea.motivo_alternativa) salida.push(crear("div", { clase: "ayuda", texto: linea.motivo_alternativa }));  // D-A2
    }
    if (linea.proveedor_propio) {
      salida.push(crear("span", { clase: "badge badge-estado badge-info", texto: "Propio XPRESS" }));
    }
    return salida;
  }

  function casilla(linea, editable, alCambiar) {
    const marcable = editable && (linea.opcional || linea.recargo_id !== null);
    const entrada = crear("input", { atributos: { type: "checkbox", "aria-label": `Cobrar ${linea.concepto}` } });
    entrada.checked = linea.incluida;
    entrada.disabled = !marcable;
    if (marcable) {
      entrada.addEventListener("change", () => {
        entrada.disabled = true;
        alCambiar(linea, entrada.checked);
      });
    }
    return entrada;
  }

  function tabla(lineas, conCosto, conMargen, editable, alCambiar) {
    // D-R1: el proveedor es interno; solo llega en el JSON con costo.ver (admin, pricing, gerencia).
    const conProveedor = lineas.some((linea) => "proveedor" in linea);
    const titulos = ["Cobrar", "Concepto"];
    if (conProveedor) titulos.push("Proveedor");
    titulos.push("Cantidad", "Unidad", "Precio USD", "Venta USD");
    if (conCosto) titulos.push("Costo USD");
    if (conMargen) titulos.push("Margen USD");
    const filas = lineas.map((linea) => {
      const celdas = [
        UI.celda("Cobrar", [casilla(linea, editable, alCambiar)]),
        UI.celda("Concepto", [crear("div", { texto: linea.concepto }), ...etiquetas(linea)]),
        ...(conProveedor ? [UI.celda("Proveedor", [UI.texto(linea.proveedor, "texto-suave")])] : []),
        UI.celda("Cantidad", [UI.monto(linea.cantidad)]),
        UI.celda("Unidad", [UI.texto(linea.rate_unit === "KG" ? (linea.unidad_peso || "KG") : (UNIDADES[linea.rate_unit] || linea.rate_unit))]),
        UI.celda("Precio USD", [UI.monto(linea.precio_venta_unit_usd)]),
        UI.celda("Venta USD", [linea.incluida ? UI.monto(linea.subtotal_venta_usd) : UI.texto(`(${linea.subtotal_venta_usd})`, "texto-suave")]),
      ];
      if (conCosto) celdas.push(UI.celda("Costo USD", [UI.monto(linea.costo_usd)]));
      if (conMargen) celdas.push(UI.celda("Margen USD", [UI.monto(linea.margen_usd)]));
      const clase = linea.incluida ? "" : (linea.seleccion === "ALTERNATIVA" ? "fila-alternativa" : "fila-apagada");
      return crear("tr", { clase }, celdas);
    });
    return crear("div", { clase: "tabla-scroll" }, [crear("table", { clase: "tabla tabla-cargos" }, [
      crear("thead", {}, [crear("tr", {}, titulos.map((t) => crear("th", { texto: t })))]),
      crear("tbody", {}, filas.length ? filas : [UI.filaVacia(titulos.length, "Sin cargos en este bloque")]),
    ])]);
  }

  function dato(etiqueta, valor, destacado = false) {
    return crear("div", { clase: destacado ? "total-fila total-destacado" : "total-fila" }, [
      crear("span", { texto: etiqueta }), crear("span", { clase: "cifra", texto: valor ?? "—" }),
    ]);
  }

  /**
   * @param {HTMLElement} contenedor
   * @param {object} cotizacion respuesta de /cotizaciones/{id}
   * @param {{editable: boolean, alCambiar: Function, verDescartados?: Function|null, enlaceRecargos?: boolean}} opciones
   */
  function pintar(contenedor, cotizacion, { editable, alCambiar, verDescartados = null, enlaceRecargos = false }) {
    const t = cotizacion.totales || {};
    const conCosto = cotizacion.lineas.some((linea) => "costo_usd" in linea);
    const conMargen = cotizacion.lineas.some((linea) => "margen_usd" in linea);
    const partes = [];
    if (cotizacion.carga_especial) {
      partes.push(crear("p", { clase: "texto-suave", texto: cotizacion.carga_especial }));  // D-T6
    }
    if (cotizacion.sin_recargos) {
      const aviso = [crear("span", { texto: "Esta tarifa no tiene recargos cargados para este puerto y servicio. " })];
      if (enlaceRecargos) aviso.push(crear("a", { texto: "Ir a Recargos", atributos: { href: "recargos.html" } }));
      partes.push(crear("div", { clase: "alerta alerta-aviso", atributos: { role: "status" } }, aviso));
    }
    const iva = Number(t.iva_tasa_aplicada ?? 0);
    for (const [fiscal, titulo, subtotal] of [
      ["RECIBO_CAJA", "Recibo de Caja (IVA 0%)", t.subtotal_recibo_caja],
      ["FACTURA", `Factura (IVA ${iva}%)`, t.subtotal_factura],
    ]) {
      const lineas = cotizacion.lineas.filter((linea) => linea.bloque_fiscal === fiscal);
      partes.push(crear("section", { clase: "bloque-cargos" }, [
        crear("h4", { texto: titulo }),
        tabla(lineas, conCosto, conMargen, editable, alCambiar),
        dato(`Subtotal ${fiscal === "FACTURA" ? "Factura" : "Recibo de Caja"}`, subtotal),
      ]));
    }
    const totales = [dato(`IVA ${iva}%`, t.iva), dato("TOTAL GENERAL USD", t.total_general, true)];
    if ("costo_total" in t) {
      const venta = (Number(t.subtotal_recibo_caja || 0) + Number(t.subtotal_factura || 0)).toFixed(2);
      totales.push(dato("Costo total", t.costo_total), dato("Venta sin IVA", venta));
    }
    if ("margen_total" in t) totales.push(dato("Margen total", `${t.margen_total} (${t.margen_pct}%)`, true));
    partes.push(crear("div", { clase: "totales-cargos" }, totales));
    if (verDescartados) {
      const zona = crear("div", { clase: "zona-descartados" });
      const boton = UI.boton("¿Por qué no aparece?", async () => {
        boton.disabled = true;
        try {
          zona.replaceChildren(...descartados(await verDescartados()));
        } finally {
          boton.disabled = false;
        }
      });
      partes.push(crear("div", { clase: "config-acciones" }, [boton]), zona);
    }
    contenedor.replaceChildren(...partes);
  }

  function descartados(datos) {
    const extra = (datos.tarifas || []).map((t) => crear("p", { clase: "texto-suave",
      texto: `Tarifa #${t.tarifa_id} (${t.proveedor}): ${t.motivos.join(" · ")}` }));  // D-T4
    if (!datos.recargos.length) {
      return [...extra, crear("p", { clase: "texto-suave", texto: "No hay recargos del proveedor ni propios fuera de esta cotización." })];
    }
    const filas = datos.recargos.map((r) => crear("tr", {}, [
      UI.celda("Recargo", [crear("div", { texto: r.concepto }), crear("span", { clase: "texto-suave", texto: `${r.proveedor} · ${r.puerto} · ${r.lado} · ${BLOQUES[r.bloque_incoterm] || r.bloque_incoterm}` })]),
      UI.celda("Por qué no aparece", [crear("ul", { clase: "lista-motivos" }, r.motivos.map((m) => crear("li", { texto: m })))]),
    ]));
    return [...extra, crear("div", { clase: "tabla-scroll" }, [crear("table", { clase: "tabla" }, [
      crear("thead", {}, [crear("tr", {}, [crear("th", { texto: "Recargo" }), crear("th", { texto: "Por qué no aparece" })])]),
      crear("tbody", {}, filas),
    ])])];
  }

  return { pintar };
})();
