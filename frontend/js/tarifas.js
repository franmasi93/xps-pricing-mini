/* P6 Tarifas. tarifa.ver lee; tarifa.editar crea, edita, duplica, desactiva y edita tramos.
 * Gating (D-F2-5): el backend decide qué claves envía. Esta pantalla solo dibuja las columnas de
 * costo y margen si esas claves existen en el JSON; nunca las oculta con CSS ni calcula precios.
 */
"use strict";

(async () => {
  const { crear } = XPS;
  const MODOS = { AEREO: "Aéreo", LCL: "LCL", FCL: "FCL" };
  const UNIDADES = { AEREO: ["KG", "ENVIO"], LCL: ["WM", "CBM", "ENVIO"], FCL: ["CONTENEDOR"] };
  const DESDE_KG = [0, 45, 100, 300, 500, 1000];
  const OPCIONALES = ["parametro_venta", "precio_venta_manual", "minimo_venta_manual", "transit_time_dias", "dias_libres", "notas", "tipo_equipo_id"];

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
  let catalogos = { puertos: [], proveedores: [], monedas: [], tipos: [] };
  let enEdicion = null;
  let enFicha = null;

  const ruta = (t) => `${t.origen.codigo} → ${t.destino.codigo}`;

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
    const columnas = ["Ruta", "Modo", "Proveedor", "Unidad", "Venta", "Venta mínima"];
    if (conCosto) columnas.push("Costo");
    if (conMargen) columnas.push("Margen");
    columnas.push("Vigencia", "Estado", "Acciones");
    cabecera.replaceChildren(crear("tr", {}, columnas.map((c) => crear("th", { texto: c }))));

    cuerpo.replaceChildren(...(lista.length ? [] : [UI.filaVacia(columnas.length, "No hay tarifas con estos filtros.")]));
    for (const tarifa of lista) {
      const modo = tarifa.tipo_equipo ? `${MODOS[tarifa.modo]} ${tarifa.tipo_equipo.codigo}` : MODOS[tarifa.modo];
      const celdas = [
        UI.celda("Ruta", [UI.texto(ruta(tarifa), "cifra")]),
        UI.celda("Modo", [UI.texto(modo)]),
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

  async function cargar() {
    const parametros = {};
    for (const [clave, control] of Object.entries(filtros)) {
      parametros[clave] = control.value;
    }
    pintar(await XPS.api(UI.consulta("/tarifas", parametros)));
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
      par("Modo", tarifa.tipo_equipo ? `${MODOS[tarifa.modo]} ${tarifa.tipo_equipo.codigo}` : MODOS[tarifa.modo]),
      par("Unidad", tarifa.rate_unit),
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
    document.getElementById("btn-editar-tramos").hidden = !(puedeEditar && tarifa.modo === "AEREO" && tarifa.rate_unit === "KG");
    if (tarifa.tiene_tramos) {
      try {
        pintarTramos(await XPS.api(`/tarifas/${tarifa.id}/tramos`), tarifa.moneda);
      } catch (error) {
        XPS.mostrarError(alertas, error);
      }
    }
    dialogoFicha.showModal();
  }

  function pintarTramos(tramos, moneda) {
    const conCosto = tramos.some((t) => "costo_kg" in t);
    const columnas = ["Desde kg", "Venta por kg"];
    if (conCosto) columnas.push("Costo por kg");
    document.getElementById("cabecera-tramos").replaceChildren(crear("tr", {}, columnas.map((c) => crear("th", { texto: c }))));
    document.getElementById("tabla-tramos").replaceChildren(
      ...tramos.map((tramo) => {
        const celdas = [
          UI.celda("Desde kg", [UI.texto(tramo.desde_kg === 0 ? "−45" : `+${tramo.desde_kg}`, "cifra")]),
          UI.celda("Venta por kg", [UI.monto(tramo.precio_venta_kg, moneda)]),
        ];
        if (conCosto) celdas.push(UI.celda("Costo por kg", [UI.monto(tramo.costo_kg, moneda)]));
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
    const filas = DESDE_KG.map((desde) => {
      const actual = porDesde.get(desde);
      const costo = crear("input", { clase: "input cifra", atributos: { type: "text", inputmode: "decimal", "data-desde": desde, "data-campo": "costo_kg", "aria-label": `Costo por kg desde ${desde}` } });
      costo.value = actual && actual.costo_kg ? actual.costo_kg : "";
      const campos = [
        crear("div", { clase: "campo" }, [crear("span", { clase: "etiqueta", texto: desde === 0 ? "Desde 0 kg (−45)" : `Desde ${desde} kg` }), costo]),
      ];
      if (manual) {
        const venta = crear("input", { clase: "input cifra", atributos: { type: "text", inputmode: "decimal", "data-desde": desde, "data-campo": "precio_venta_kg", "aria-label": `Venta por kg desde ${desde}` } });
        venta.value = actual ? actual.precio_venta_kg : "";
        campos.push(crear("div", { clase: "campo" }, [crear("span", { clase: "etiqueta", texto: "Venta por kg" }), venta]));
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
    for (const desde of DESDE_KG) {
      const costo = formTramos.querySelector(`[data-desde="${desde}"][data-campo="costo_kg"]`).value.trim().replace(",", ".");
      const ventaCampo = formTramos.querySelector(`[data-desde="${desde}"][data-campo="precio_venta_kg"]`);
      if (!costo) continue;
      const tramo = { desde_kg: desde, costo_kg: costo };
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
    const modo = formTarifa.elements.modo.value;
    const tipoPuerto = modo === "AEREO" ? "AEREO" : "MARITIMO";
    const puertos = catalogos.puertos.filter((p) => p.tipo === tipoPuerto && (p.activo || (enEdicion && [enEdicion.origen.id, enEdicion.destino.id].includes(p.id))));
    for (const campo of ["origen_puerto_id", "destino_puerto_id"]) {
      UI.opciones(formTarifa.elements[campo], puertos, { valor: (p) => p.id, texto: (p) => `${p.codigo} · ${p.nombre}` });
    }
    UI.opciones(formTarifa.elements.rate_unit, UNIDADES[modo].map((u) => ({ u })), { valor: (x) => x.u, texto: (x) => x.u });
    document.getElementById("campo-equipo").hidden = modo !== "FCL";
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
    UI.opciones(formTarifa.elements.tipo_equipo_id, catalogos.tipos.filter((t) => t.activo), { valor: (t) => t.id, texto: (t) => `${t.codigo} · ${t.nombre}` });
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
      };
      for (const [campo, valor] of Object.entries(valores)) {
        formTarifa.elements[campo].value = valor === null || valor === undefined ? "" : String(valor);
      }
    }
    const conTramos = Boolean(tarifa && tarifa.tiene_tramos);
    document.getElementById("nota-tramos").hidden = !conTramos;
    for (const campo of ["modo", "rate_unit", "metodo_venta", "costo"]) {
      formTarifa.elements[campo].disabled = conTramos;
    }
    formTarifa.elements.precio_venta_manual.disabled = conTramos;
    dialogoTarifa.showModal();
  }

  function leerFormulario() {
    const datos = {};
    for (const elemento of formTarifa.elements) {
      if (!elemento.name || elemento.disabled || elemento.closest("[hidden]")) continue;
      const valor = elemento.value.trim().replace(/^(-?\d+),(\d+)$/, "$1.$2");
      datos[elemento.name] = valor === "" ? null : valor;
    }
    for (const campo of ["proveedor_id", "origen_puerto_id", "destino_puerto_id", "moneda_id", "tipo_equipo_id", "transit_time_dias", "dias_libres"]) {
      if (datos[campo] !== null && datos[campo] !== undefined) datos[campo] = Number(datos[campo]);
    }
    const metodo = datos.metodo_venta || (enEdicion && enEdicion.metodo_venta);
    // Campos que no corresponden al modo o al método van vacíos, como exige el backend.
    if ((datos.modo || (enEdicion && enEdicion.modo)) !== "FCL") datos.tipo_equipo_id = null;
    if (metodo === "MANUAL") datos.parametro_venta = null;
    else {
      datos.precio_venta_manual = null;
      datos.minimo_venta_manual = null;
    }
    return datos;
  }

  formTarifa.elements.modo.addEventListener("change", ajustarFormulario);
  formTarifa.elements.metodo_venta.addEventListener("change", ajustarFormulario);

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
    const cuerpoDuplicar = { valido_desde: formDuplicar.elements.valido_desde.value, valido_hasta: formDuplicar.elements.valido_hasta.value };
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
    control.addEventListener("change", () => seguro(cargar));
  }

  try {
    diasAlerta = await UI.diasAlerta();
    const [todas, tipos] = await Promise.all([XPS.api("/tarifas"), XPS.api("/tipos-equipo")]);
    catalogos.tipos = tipos;
    opcionesDeFiltro(todas);
    if (puedeEditar) {
      const [puertos, proveedores, monedas] = await Promise.all([XPS.api("/puertos"), XPS.api("/proveedores"), XPS.api("/monedas")]);
      catalogos = { ...catalogos, puertos, proveedores, monedas };
    }
    await cargar();
    herramientas.hidden = false;
    botonNueva.hidden = !puedeEditar;
  } catch (error) {
    XPS.mostrarError(alertas, error);
  }
})();
