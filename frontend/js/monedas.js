/* Monedas y tasas: tasa.editar edita; costo.ver (gerencia) solo lee.
 * Si el backend pide confirmar un desvío >20 %, se muestra la tasa anterior y la nueva antes de reenviar.
 */
"use strict";

(async () => {
  const { crear } = XPS;
  const MONEDA_BASE = "USD";
  const alertas = document.getElementById("alertas");
  const herramientas = document.getElementById("herramientas");
  const botonNuevaTasa = document.getElementById("btn-nueva-tasa");
  const botonNuevaMoneda = document.getElementById("btn-nueva-moneda");

  const filtroMoneda = document.getElementById("filtro-moneda");
  const filtroDesde = document.getElementById("filtro-desde");
  const filtroHasta = document.getElementById("filtro-hasta");

  const dialogoMoneda = document.getElementById("dialogo-moneda");
  const formMoneda = document.getElementById("form-moneda");
  const alertasMoneda = document.getElementById("alertas-moneda");

  const dialogoTasa = document.getElementById("dialogo-tasa");
  const formTasa = document.getElementById("form-tasa");
  const alertasTasa = document.getElementById("alertas-tasa");
  const rotuloTasa = document.getElementById("tasa-rotulo");
  const tasaAnterior = document.getElementById("tasa-anterior");

  const dialogoCorregir = document.getElementById("dialogo-corregir");
  const formCorregir = document.getElementById("form-corregir");
  const alertasCorregir = document.getElementById("alertas-corregir");

  const dialogoDesvio = document.getElementById("dialogo-desvio");

  let puedeEditar = false;
  let monedas = [];
  let monedaEnEdicion = null;
  let tasaEnCorreccion = null;
  let pendiente = null; // envío que espera la confirmación del desvío

  function hoy() {
    const ahora = new Date();
    const local = new Date(ahora.getTime() - ahora.getTimezoneOffset() * 60000);
    return local.toISOString().slice(0, 10);
  }

  function rotulo(codigo) {
    return codigo ? `USD por 1 ${codigo}` : "USD por 1 unidad";
  }

  // ---------- Monedas ----------

  async function cargarMonedas() {
    monedas = await XPS.api("/monedas");
    const cuerpo = document.getElementById("tabla-monedas");
    cuerpo.replaceChildren();
    for (const moneda of monedas) {
      const celdas = [
        UI.celda("Código", [UI.texto(moneda.codigo, "cifra")]),
        UI.celda("Nombre", [UI.texto(moneda.nombre)]),
        UI.celda("Símbolo", [UI.texto(moneda.simbolo)]),
        UI.celda("Estado", [
          moneda.codigo === MONEDA_BASE
            ? crear("span", { clase: "badge badge-rol", texto: "Moneda base" })
            : UI.badgeEstado(moneda.activo),
        ]),
      ];
      if (puedeEditar) {
        const acciones = [UI.boton("Editar", () => abrirMoneda(moneda))];
        if (moneda.codigo !== MONEDA_BASE) {
          acciones.push(UI.boton(moneda.activo ? "Desactivar" : "Activar", () => cambiarEstadoMoneda(moneda)));
        }
        celdas.push(UI.celda("Acciones", [crear("div", { clase: "celda-acciones" }, acciones)]));
      }
      cuerpo.append(crear("tr", {}, celdas));
    }
    const conTasas = monedas.filter((m) => m.codigo !== MONEDA_BASE);
    UI.opciones(filtroMoneda, conTasas, { valor: (m) => m.codigo, texto: (m) => `${m.codigo} · ${m.nombre}`, todos: "Todas" });
  }

  function abrirMoneda(moneda = null) {
    monedaEnEdicion = moneda;
    formMoneda.reset();
    XPS.limpiarAlerta(alertasMoneda);
    document.getElementById("titulo-moneda").textContent = moneda ? "Editar moneda" : "Nueva moneda";
    formMoneda.elements.codigo.disabled = Boolean(moneda && moneda.codigo === MONEDA_BASE);
    if (moneda) {
      formMoneda.elements.codigo.value = moneda.codigo;
      formMoneda.elements.nombre.value = moneda.nombre;
      formMoneda.elements.simbolo.value = moneda.simbolo;
    }
    dialogoMoneda.showModal();
  }

  async function cambiarEstadoMoneda(moneda) {
    XPS.limpiarAlerta(alertas);
    try {
      await XPS.api(`/monedas/${moneda.id}`, { metodo: "PATCH", cuerpo: { activo: !moneda.activo } });
      XPS.mostrarAlerta(alertas, "exito", moneda.activo ? "Moneda desactivada." : "Moneda activada.");
      await cargarMonedas();
    } catch (error) {
      XPS.mostrarError(alertas, error);
    }
  }

  formMoneda.addEventListener("submit", async (evento) => {
    evento.preventDefault();
    XPS.limpiarAlerta(alertasMoneda);
    const datos = {
      codigo: formMoneda.elements.codigo.value.trim(),
      nombre: formMoneda.elements.nombre.value.trim(),
      simbolo: formMoneda.elements.simbolo.value.trim(),
    };
    if (!datos.codigo || !datos.nombre || !datos.simbolo) {
      XPS.mostrarAlerta(alertasMoneda, "error", "Complete todos los campos.");
      return;
    }
    try {
      if (monedaEnEdicion) {
        const cambios = {};
        if (monedaEnEdicion.codigo !== MONEDA_BASE && datos.codigo.toUpperCase() !== monedaEnEdicion.codigo) {
          cambios.codigo = datos.codigo;
        }
        for (const campo of ["nombre", "simbolo"]) {
          if (datos[campo] !== monedaEnEdicion[campo]) {
            cambios[campo] = datos[campo];
          }
        }
        if (Object.keys(cambios).length) {
          await XPS.api(`/monedas/${monedaEnEdicion.id}`, { metodo: "PATCH", cuerpo: cambios });
        }
      } else {
        await XPS.api("/monedas", { metodo: "POST", cuerpo: datos });
      }
      dialogoMoneda.close();
      XPS.mostrarAlerta(alertas, "exito", "Moneda guardada.");
      await cargarMonedas();
    } catch (error) {
      XPS.mostrarError(alertasMoneda, error);
    }
  });

  // ---------- Tasas ----------

  async function cargarTasas() {
    const lista = await XPS.api(
      UI.consulta("/tasas", { moneda: filtroMoneda.value, desde: filtroDesde.value, hasta: filtroHasta.value })
    );
    const cuerpo = document.getElementById("tabla-tasas");
    const columnas = puedeEditar ? 5 : 4;
    cuerpo.replaceChildren(...(lista.length ? [] : [UI.filaVacia(columnas, "No hay tasas con estos filtros.")]));
    for (const tasa of lista) {
      const celdas = [
        UI.celda("Moneda", [UI.texto(tasa.moneda, "cifra")]),
        UI.celda("Vigente desde", [UI.texto(tasa.fecha_vigencia, "cifra")]),
        UI.celda("USD por 1 unidad", [UI.texto(tasa.tasa_a_usd, "cifra")]),
        UI.celda("Registrada", [UI.texto(XPS.formatearFecha(tasa.creado_en), "cifra")]),
      ];
      if (puedeEditar) {
        celdas.push(UI.celda("Acciones", [UI.boton("Corregir", () => abrirCorreccion(tasa))]));
      }
      cuerpo.append(crear("tr", {}, celdas));
    }
  }

  /** Muestra la tasa anterior a la fecha elegida (consulta al backend; aquí no se calcula nada). */
  async function mostrarTasaAnterior() {
    const moneda = formTasa.elements.moneda.value;
    const fecha = formTasa.elements.fecha.value;
    rotuloTasa.textContent = rotulo(moneda);
    tasaAnterior.textContent = "";
    if (!moneda || !fecha) {
      return;
    }
    try {
      const previas = await XPS.api(UI.consulta("/tasas", { moneda, hasta: fecha }));
      const anterior = previas.find((t) => t.fecha_vigencia < fecha);
      tasaAnterior.textContent = anterior
        ? `Tasa anterior: ${anterior.tasa_a_usd} (vigente desde ${anterior.fecha_vigencia})`
        : "Sin tasas anteriores para esta moneda.";
    } catch (error) {
      XPS.mostrarError(alertasTasa, error);
    }
  }

  function abrirTasa() {
    formTasa.reset();
    XPS.limpiarAlerta(alertasTasa);
    const utilizables = monedas.filter((m) => m.codigo !== MONEDA_BASE && m.activo);
    UI.opciones(formTasa.elements.moneda, utilizables, { valor: (m) => m.codigo, texto: (m) => `${m.codigo} · ${m.nombre}` });
    formTasa.elements.fecha.value = hoy();
    dialogoTasa.showModal();
    mostrarTasaAnterior();
  }

  function abrirCorreccion(tasa) {
    tasaEnCorreccion = tasa;
    formCorregir.reset();
    XPS.limpiarAlerta(alertasCorregir);
    document.getElementById("corregir-referencia").textContent = `${tasa.moneda} · vigente desde ${tasa.fecha_vigencia} · actual ${tasa.tasa_a_usd}`;
    document.getElementById("corregir-rotulo").textContent = rotulo(tasa.moneda);
    formCorregir.elements.valor.value = tasa.tasa_a_usd;
    dialogoCorregir.showModal();
  }

  /** Envía la tasa; si el backend pide confirmar el desvío, abre el diálogo y espera la decisión. */
  async function enviarTasa(envio) {
    try {
      await XPS.api(envio.ruta, { metodo: envio.metodo, cuerpo: envio.cuerpo });
      envio.dialogo.close();
      XPS.mostrarAlerta(alertas, "exito", envio.exito);
      await cargarTasas();
    } catch (error) {
      if (error instanceof XPS.ErrorApi && error.codigo === "TASA_DESVIO_REQUIERE_CONFIRMACION") {
        pendiente = envio;
        document.getElementById("desvio-mensaje").textContent = error.message;
        document.getElementById("desvio-anterior").textContent =
          `Tasa anterior: ${error.detalle.tasa_anterior} (vigente desde ${error.detalle.fecha_anterior})`;
        document.getElementById("desvio-nueva").textContent = `Tasa nueva: ${envio.cuerpo.tasa_a_usd}`;
        dialogoDesvio.showModal();
        return;
      }
      XPS.mostrarError(envio.alertas, error);
    }
  }

  document.getElementById("btn-confirmar-desvio").addEventListener("click", async () => {
    dialogoDesvio.close();
    if (pendiente) {
      const envio = { ...pendiente, cuerpo: { ...pendiente.cuerpo, confirmar_desvio: true } };
      pendiente = null;
      await enviarTasa(envio);
    }
  });

  formTasa.addEventListener("submit", async (evento) => {
    evento.preventDefault();
    XPS.limpiarAlerta(alertasTasa);
    const cuerpo = {
      moneda: formTasa.elements.moneda.value,
      fecha_vigencia: formTasa.elements.fecha.value,
      tasa_a_usd: formTasa.elements.valor.value.trim().replace(",", "."),
    };
    if (!cuerpo.moneda || !cuerpo.fecha_vigencia || !cuerpo.tasa_a_usd) {
      XPS.mostrarAlerta(alertasTasa, "error", "Complete la moneda, la fecha y la tasa.");
      return;
    }
    await enviarTasa({ ruta: "/tasas", metodo: "POST", cuerpo, dialogo: dialogoTasa, alertas: alertasTasa, exito: "Tasa registrada." });
  });

  formCorregir.addEventListener("submit", async (evento) => {
    evento.preventDefault();
    XPS.limpiarAlerta(alertasCorregir);
    const valor = formCorregir.elements.valor.value.trim().replace(",", ".");
    if (!valor) {
      XPS.mostrarAlerta(alertasCorregir, "error", "Ingrese la tasa corregida.");
      return;
    }
    await enviarTasa({
      ruta: `/tasas/${tasaEnCorreccion.id}`,
      metodo: "PATCH",
      cuerpo: { tasa_a_usd: valor },
      dialogo: dialogoCorregir,
      alertas: alertasCorregir,
      exito: "Tasa corregida.",
    });
  });

  // ---------- Inicio ----------

  const yo = await iniciarLayout("monedas.html");
  if (!yo || !UI.exigirAlguno(yo, ["tasa.editar", "costo.ver"], alertas)) {
    return;
  }
  puedeEditar = UI.tieneAlguno(yo, ["tasa.editar"]);
  for (const columna of document.querySelectorAll("[data-solo-edicion]")) {
    columna.hidden = !puedeEditar;
  }
  document.getElementById("nota-lectura").hidden = puedeEditar;

  for (const dialogo of [dialogoMoneda, dialogoTasa, dialogoCorregir, dialogoDesvio]) {
    UI.prepararDialogo(dialogo);
  }
  botonNuevaMoneda.addEventListener("click", () => abrirMoneda());
  botonNuevaTasa.addEventListener("click", abrirTasa);
  formTasa.elements.moneda.addEventListener("change", mostrarTasaAnterior);
  formTasa.elements.fecha.addEventListener("change", mostrarTasaAnterior);
  for (const filtro of [filtroMoneda, filtroDesde, filtroHasta]) {
    filtro.addEventListener("change", async () => {
      try {
        await cargarTasas();
      } catch (error) {
        XPS.mostrarError(alertas, error);
      }
    });
  }

  try {
    await cargarMonedas();
    await cargarTasas();
    herramientas.hidden = false;
    botonNuevaTasa.hidden = !puedeEditar;
    botonNuevaMoneda.hidden = !puedeEditar;
  } catch (error) {
    XPS.mostrarError(alertas, error);
  }
})();
