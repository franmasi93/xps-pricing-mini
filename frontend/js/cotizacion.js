/* P11 Detalle de cotización: líneas por bloque, ajuste con motivo, seguro, emitir, estados, duplicar y PDF.
 * Los montos y totales los calcula el backend; las columnas de costo y margen solo se dibujan si la
 * clave viene en el JSON (gating en el service, no en la pantalla).
 */
"use strict";

(() => {
  const { crear } = XPS;
  const alertas = document.getElementById("alertas");
  const id = Number(new URLSearchParams(window.location.search).get("id"));
  const NOMBRES_BLOQUE = {
    RECOGIDA_ORIGEN: "Recogida en origen",
    DESPACHO_EXPORT: "Despacho de exportación",
    GASTOS_ORIGEN: "Gastos en origen",
    FLETE_PRINCIPAL: "Flete principal",
    SEGURO: "Seguro",
    GASTOS_DESTINO: "Gastos en destino",
    DESPACHO_IMPORT: "Despacho de importación",
    ENTREGA_FINAL: "Entrega final",
  };
  const FISCAL = { RECIBO_CAJA: "Recibo de caja", FACTURA: "Factura" };
  let yo = null;
  let cotizacion = null;
  let lineaEnAjuste = null;

  const puede = (permiso) => UI.tieneAlguno(yo, [permiso]);

  // ---------- Datos ----------

  function dato(etiqueta, valor) {
    return crear("div", {}, [crear("dt", { texto: etiqueta }), crear("dd", { texto: valor ?? "—" })]);
  }

  function pintarFicha() {
    const c = cotizacion;
    const carga = c.carga;
    const partesCarga = [`${carga.peso_kg} kg`];
    if (carga.cbm) partesCarga.push(`${carga.cbm} m³`);
    if (carga.bultos) partesCarga.push(`${carga.bultos} bultos`);
    for (const contenedor of carga.contenedores) partesCarga.push(`${contenedor.cantidad} × ${contenedor.codigo}`);
    const elementos = [
      dato("Cliente", c.cliente.razon_social),
      dato("Contacto", c.contacto ? `${c.contacto.nombre}${c.contacto.email ? ` · ${c.contacto.email}` : ""}` : "Sin contacto"),
      dato("Ruta", `${c.origen.codigo} ${c.origen.nombre} → ${c.destino.codigo} ${c.destino.nombre}`),
      dato("Modo · Incoterm · Sentido", `${c.modo} · ${c.incoterm.codigo} · ${c.sentido === "IMPORTACION" ? "Importación" : "Exportación"}`),
      dato("Carga", partesCarga.join(" · ")),
      dato("Comercial", c.comercial.nombre),
    ];
    if (carga.peso_cobrable_kg) elementos.push(dato("Peso cobrable", `${carga.peso_cobrable_kg} kg (volumétrico ${carga.peso_volumetrico_kg} kg)`));
    if (carga.peso_medida) elementos.push(dato("Peso/medida (W/M)", carga.peso_medida));
    if (carga.valor_mercancia_usd) elementos.push(dato("Valor de la mercancía", `USD ${carga.valor_mercancia_usd}`));
    elementos.push(dato("Emisión", c.fecha_emision));
    elementos.push(dato("Válida hasta", c.valida_hasta || (c.valida_hasta_calculada ? `${c.valida_hasta_calculada} (calculada)` : null)));
    if (c.motivo_rechazo) elementos.push(dato("Motivo de rechazo", `${c.motivo_rechazo}${c.detalle_rechazo ? ` · ${c.detalle_rechazo}` : ""}`));
    if (c.notas_cliente) elementos.push(dato("Notas para el cliente", c.notas_cliente));
    if (c.notas_internas) elementos.push(dato("Notas internas", c.notas_internas));
    document.getElementById("ficha").replaceChildren(...elementos);
    document.getElementById("datos").hidden = false;
  }

  function pintarAvisos() {
    const contenedor = document.getElementById("avisos");
    contenedor.replaceChildren(...cotizacion.avisos.map((aviso) => crear("div", { clase: "alerta alerta-aviso", texto: aviso, atributos: { role: "status" } })));
    if (cotizacion.requiere_proponer) {
      contenedor.append(crear("div", { clase: "alerta alerta-info", texto: "Este borrador no tiene líneas: elija la tarifa y proponga las líneas." }));
    }
  }

  // ---------- Líneas ----------

  function avisosLinea(linea) {
    const avisos = [];
    if (linea.bajo_minimo_venta) {
      avisos.push(crear("span", { clase: "badge badge-estado badge-alerta", texto: `Bajo el mínimo de venta (${linea.minimo_venta_usd})` }));
    }
    if (linea.bajo_costo) {
      avisos.push(crear("span", { clase: "badge badge-estado badge-critico", texto: "Bajo el costo" }));
    }
    return avisos;
  }

  function celdaIncluida(linea, editable) {
    if (!linea.opcional) {
      return UI.texto("Sí");
    }
    if (!editable) {
      return UI.texto(linea.incluida ? "Sí" : "No");
    }
    const interruptor = crear("input", { atributos: { type: "checkbox", "aria-label": `Incluir ${linea.concepto}` } });
    interruptor.checked = linea.incluida;
    interruptor.addEventListener("change", () => modificarLinea(linea, { incluida: interruptor.checked }));
    return interruptor;
  }

  function filaLinea(linea, editable, conCosto) {
    const concepto = [crear("div", { texto: linea.concepto }), ...avisosLinea(linea)];
    if (linea.ajuste_manual) {
      concepto.push(crear("span", { clase: "badge badge-estado badge-info", texto: `Ajuste: ${linea.motivo_ajuste}` }));
    }
    const celdas = [
      UI.celda("Concepto", concepto),
      UI.celda("Cantidad", [UI.monto(linea.cantidad)]),
      UI.celda("Unidad", [UI.texto(linea.rate_unit)]),
      UI.celda("Precio USD", [UI.monto(linea.precio_venta_unit_usd)]),
      // Una línea opcional apagada no se cobra: no entra en los totales ni en el PDF.
      UI.celda("Subtotal USD", linea.incluida ? [UI.monto(linea.subtotal_venta_usd)] : [UI.texto("No incluida", "texto-suave")]),
      UI.celda("Fiscal", [UI.texto(`${FISCAL[linea.bloque_fiscal]}${linea.aplica_iva && linea.bloque_fiscal === "FACTURA" ? " + IVA" : ""}`)]),
    ];
    if (conCosto) {
      celdas.push(UI.celda("Costo USD", [UI.monto(linea.costo_usd)]));
    }
    celdas.push(UI.celda("Incluida", [celdaIncluida(linea, editable)]));
    if (editable) {
      const acciones = [UI.boton("Ajustar", () => abrirAjuste(linea))];
      if (linea.ajuste_manual) {
        acciones.push(UI.boton("Quitar ajuste", () => modificarLinea(linea, { quitar_ajuste: true })));
      }
      celdas.push(UI.celda("Acciones", acciones));
    }
    return crear("tr", {}, celdas);
  }

  function pintarLineas() {
    const editable = cotizacion.estado === "BORRADOR" && cotizacion.activo && puede("cotizacion.crear");
    const conCosto = cotizacion.lineas.some((linea) => "costo_usd" in linea);
    const titulos = ["Concepto", "Cantidad", "Unidad", "Precio USD", "Subtotal USD", "Fiscal"];
    if (conCosto) titulos.push("Costo USD");
    titulos.push("Incluida");
    if (editable) titulos.push("Acciones");
    document.getElementById("cabecera-lineas").replaceChildren(crear("tr", {}, titulos.map((t) => crear("th", { texto: t }))));
    const cuerpo = document.getElementById("tabla-lineas");
    if (!cotizacion.lineas.length) {
      cuerpo.replaceChildren(UI.filaVacia(titulos.length, "Sin líneas"));
    } else {
      // Las líneas llegan ordenadas por bloque: una fila de título por cada bloque del Incoterm.
      const filas = [];
      let bloqueActual = null;
      for (const linea of cotizacion.lineas) {
        if (linea.bloque_incoterm !== bloqueActual) {
          bloqueActual = linea.bloque_incoterm;
          filas.push(crear("tr", { clase: "fila-grupo" }, [crear("td", { texto: NOMBRES_BLOQUE[bloqueActual], atributos: { colspan: titulos.length } })]));
        }
        filas.push(filaLinea(linea, editable, conCosto));
      }
      cuerpo.replaceChildren(...filas);
    }
    document.getElementById("bloque-lineas").hidden = false;
  }

  function pintarTotales() {
    const t = cotizacion.totales;
    if (!t || !t.total_general) {
      document.getElementById("bloque-totales").hidden = true;
      return;
    }
    const elementos = [
      dato("Recibo de caja (IVA 0%)", t.subtotal_recibo_caja),
      dato("Factura", t.subtotal_factura),
      dato(`IVA ${Number(t.iva_tasa_aplicada)}%`, t.iva),
      dato("Total USD", t.total_general),
    ];
    if ("costo_total" in t) elementos.push(dato("Costo total", t.costo_total));
    if ("margen_total" in t) elementos.push(dato("Margen", `${t.margen_total} (${t.margen_pct}%)`));
    document.getElementById("totales").replaceChildren(...elementos);
    document.getElementById("bloque-totales").hidden = false;
  }

  // ---------- Acciones ----------

  async function ejecutar(accion) {
    XPS.limpiarAlerta(alertas);
    try {
      await accion();
    } catch (error) {
      XPS.mostrarError(alertas, error);
    }
  }

  async function verPdf(descargar) {
    const { blob, nombre } = await XPS.archivo(`/cotizaciones/${id}/pdf`);
    const url = URL.createObjectURL(blob);
    if (descargar) {
      const enlace = crear("a", { atributos: { href: url, download: nombre } });
      document.body.append(enlace);
      enlace.click();
      enlace.remove();
    } else {
      window.open(url, "_blank", "noopener");
    }
    window.setTimeout(() => URL.revokeObjectURL(url), 60000);
  }

  function pintarBotones() {
    const c = cotizacion;
    const botones = [];
    const borrador = c.estado === "BORRADOR" && c.activo;
    botones.push(UI.boton(borrador ? "Vista previa PDF" : "Ver PDF", () => ejecutar(() => verPdf(false)), "btn btn-secundario"));
    if (!borrador) {
      botones.push(UI.boton("Descargar PDF", () => ejecutar(() => verPdf(true)), "btn btn-secundario"));
    }
    if (borrador && puede("cotizacion.crear")) {
      const editar = crear("a", { clase: "btn btn-secundario", texto: c.lineas.length ? "Editar datos o tarifa" : "Elegir tarifa y proponer", atributos: { href: `cotizador.html?id=${c.id}` } });
      botones.push(editar);
    }
    if (borrador && puede("cotizacion.emitir")) {
      botones.push(UI.boton("Emitir", abrirEmitir, "btn btn-primario"));
      botones.push(UI.boton("Descartar borrador", () => ejecutar(descartar), "btn btn-secundario"));
    }
    if (["EMITIDA", "ENVIADA"].includes(c.estado) && puede("cotizacion.emitir")) {
      botones.push(UI.boton("Marcar aceptada", () => ejecutar(() => cambiarEstado({ estado: "ACEPTADA" })), "btn btn-primario"));
      botones.push(UI.boton("Marcar rechazada", () => document.getElementById("dialogo-rechazo").showModal(), "btn btn-secundario"));
    }
    if (c.estado !== "BORRADOR" && puede("cotizacion.enviar")) {
      const correo = crear("button", { clase: "btn btn-secundario", texto: "Enviar por correo · Disponible en F4", atributos: { type: "button", disabled: "disabled" } });
      botones.push(correo);
    }
    if (puede("cotizacion.crear")) {
      botones.push(UI.boton("Duplicar", () => ejecutar(duplicar), "btn btn-secundario"));
    }
    document.getElementById("botones").replaceChildren(...botones);
    document.getElementById("acciones").hidden = false;
  }

  async function modificarLinea(linea, cambios) {
    await ejecutar(async () => {
      cotizacion = await XPS.api(`/cotizaciones/${id}/lineas/${linea.id}`, { metodo: "PATCH", cuerpo: cambios });
      pintar();
    });
  }

  function abrirAjuste(linea) {
    lineaEnAjuste = linea;
    XPS.limpiarAlerta(document.getElementById("alertas-ajuste"));
    document.getElementById("ajuste-linea").textContent = `${linea.concepto} · precio calculado ${linea.precio_calculado_unit_usd ?? linea.precio_venta_unit_usd} USD`;
    document.getElementById("ajuste-precio").value = linea.precio_venta_unit_usd;
    document.getElementById("ajuste-motivo").value = linea.motivo_ajuste || "";
    document.getElementById("dialogo-ajuste").showModal();
  }

  async function guardarAjuste(evento) {
    evento.preventDefault();
    const alertasAjuste = document.getElementById("alertas-ajuste");
    try {
      cotizacion = await XPS.api(`/cotizaciones/${id}/lineas/${lineaEnAjuste.id}`, {
        metodo: "PATCH",
        cuerpo: {
          precio_venta_unit_usd: document.getElementById("ajuste-precio").value.trim(),
          motivo: document.getElementById("ajuste-motivo").value,
        },
      });
      document.getElementById("dialogo-ajuste").close();
      pintar();
    } catch (error) {
      XPS.mostrarError(alertasAjuste, error);
    }
  }

  function abrirEmitir() {
    const validez = document.getElementById("emitir-validez");
    validez.value = cotizacion.valida_hasta_calculada || "";
    if (cotizacion.valida_hasta_calculada) {
      validez.setAttribute("max", cotizacion.valida_hasta_calculada);
    }
    XPS.limpiarAlerta(document.getElementById("alertas-emitir"));
    document.getElementById("dialogo-emitir").showModal();
  }

  async function emitir(evento) {
    evento.preventDefault();
    const validez = document.getElementById("emitir-validez").value;
    try {
      cotizacion = await XPS.api(`/cotizaciones/${id}/emitir`, { metodo: "POST", cuerpo: validez ? { valida_hasta: validez } : {} });
      document.getElementById("dialogo-emitir").close();
      pintar();
    } catch (error) {
      XPS.mostrarError(document.getElementById("alertas-emitir"), error);
    }
  }

  async function cambiarEstado(cuerpo) {
    cotizacion = await XPS.api(`/cotizaciones/${id}/estado`, { metodo: "PATCH", cuerpo });
    pintar();
  }

  async function rechazar(evento) {
    evento.preventDefault();
    const motivo = document.getElementById("rechazo-motivo").value;
    const detalle = document.getElementById("rechazo-detalle").value.trim();
    try {
      await cambiarEstado({ estado: "RECHAZADA", motivo_rechazo: motivo || null, detalle_rechazo: detalle || null });
      document.getElementById("dialogo-rechazo").close();
    } catch (error) {
      XPS.mostrarError(document.getElementById("alertas-rechazo"), error);
    }
  }

  async function descartar() {
    if (!window.confirm("¿Descartar este borrador? No se puede deshacer.")) {
      return;
    }
    await XPS.api(`/cotizaciones/${id}/descartar`, { metodo: "POST" });
    XPS.irA("cotizaciones.html");
  }

  async function duplicar() {
    const copia = await XPS.api(`/cotizaciones/${id}/duplicar`, { metodo: "POST" });
    XPS.irA(`cotizacion.html?id=${copia.id}`);
  }

  function pintar() {
    document.getElementById("titulo").textContent = cotizacion.etiqueta;
    document.title = `${cotizacion.etiqueta} · XPS Pricing`;
    const estado = document.getElementById("estado");
    estado.replaceChildren(...UI.badgesCotizacion(cotizacion.estado, cotizacion.vencida));
    if (!cotizacion.activo) {
      estado.append(crear("span", { clase: "badge badge-estado badge-inactivo", texto: "Descartada" }));
    }
    pintarAvisos();
    pintarBotones();
    pintarFicha();
    pintarLineas();
    pintarTotales();
  }

  async function iniciar() {
    yo = await iniciarLayout("cotizaciones.html");
    if (!yo || !UI.exigirAlguno(yo, ["cotizacion.crear", "cotizacion.ver_todas"], alertas)) {
      return;
    }
    for (const dialogo of document.querySelectorAll("dialog")) {
      UI.prepararDialogo(dialogo);
    }
    document.getElementById("form-ajuste").addEventListener("submit", guardarAjuste);
    document.getElementById("form-emitir").addEventListener("submit", emitir);
    document.getElementById("form-rechazo").addEventListener("submit", rechazar);
    await ejecutar(async () => {
      cotizacion = await XPS.api(`/cotizaciones/${id}`);
      pintar();
    });
  }

  iniciar();
})();
