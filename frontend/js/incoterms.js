/* Matriz de Incoterms. La vista de cada sentido usa las listas que calcula el backend
 * (bloques_importacion / bloques_exportacion): el frontend no calcula el complemento.
 * Solo config.editar (admin) edita.
 */
"use strict";

(async () => {
  const { crear } = XPS;
  const alertas = document.getElementById("alertas");
  const herramientas = document.getElementById("herramientas");
  const cabecera = document.getElementById("cabecera-matriz");
  const cuerpo = document.getElementById("tabla-matriz");

  const dialogo = document.getElementById("dialogo-incoterm");
  const form = document.getElementById("form-incoterm");
  const alertasDialogo = document.getElementById("alertas-incoterm");
  const contenedorBloques = document.getElementById("incoterm-bloques");

  const BLOQUES = [
    ["recogida_origen", "Recogida origen"],
    ["despacho_export", "Despacho export"],
    ["gastos_origen", "Gastos origen"],
    ["flete_principal", "Flete principal"],
    ["seguro", "Seguro"],
    ["gastos_destino", "Gastos destino"],
    ["despacho_import", "Despacho import"],
    ["entrega_final", "Entrega final"],
  ];
  const TEXTOS = {
    IMPORTACION: ["Importación: el cliente es el comprador", "✓ = XPRESS lo cotiza · — = lo paga el vendedor en origen. El seguro siempre se propone apagado (opcional)."],
    EXPORTACION: ["Exportación: el cliente es el vendedor", "✓ = XPRESS lo cotiza (complemento de la importación) · — = lo paga el comprador. El seguro siempre se propone apagado (opcional)."],
  };

  let sentido = "IMPORTACION";
  let puedeEditar = false;
  let incoterms = [];
  let enEdicion = null;

  function pintarCabecera() {
    const columnas = [crear("th", { texto: "Incoterm" })];
    for (const [, etiqueta] of BLOQUES) {
      columnas.push(crear("th", { texto: etiqueta }));
    }
    columnas.push(crear("th", { texto: "Modo" }));
    if (puedeEditar) {
      columnas.push(crear("th", { texto: "Acciones" }));
    }
    cabecera.replaceChildren(crear("tr", {}, columnas));
  }

  function marca(incluido, bloque) {
    if (!incluido) {
      return crear("span", { clase: "marca-no", texto: "—" });
    }
    return crear("span", { clase: "marca-si", texto: bloque === "seguro" ? "✓ opc." : "✓" });
  }

  function pintarMatriz() {
    const [titulo, bajada] = TEXTOS[sentido];
    document.getElementById("titulo-matriz").textContent = titulo;
    document.getElementById("bajada-matriz").textContent = bajada;
    cuerpo.replaceChildren();
    for (const incoterm of incoterms) {
      const incluidos = new Set(sentido === "IMPORTACION" ? incoterm.bloques_importacion : incoterm.bloques_exportacion);
      const advertencia = sentido === "IMPORTACION" ? incoterm.advertencia_importacion : incoterm.advertencia_exportacion;
      const nombre = crear("div", {}, [
        crear("strong", { clase: "cifra", texto: incoterm.codigo }),
        crear("div", { clase: "texto-suave", texto: incoterm.nombre }),
      ]);
      if (!incoterm.activo) {
        nombre.append(UI.badgeEstado(false));
      }
      if (advertencia) {
        nombre.append(crear("div", { clase: "ayuda", texto: advertencia }));
      }
      const celdas = [UI.celda("Incoterm", [nombre])];
      for (const [bloque, etiqueta] of BLOQUES) {
        celdas.push(UI.celda(etiqueta, [marca(incluidos.has(bloque), bloque)]));
      }
      celdas.push(UI.celda("Modo", [UI.texto(incoterm.solo_maritimo ? "Solo marítimo" : "Todos")]));
      if (puedeEditar) {
        celdas.push(UI.celda("Acciones", [UI.boton("Editar", () => abrir(incoterm))]));
      }
      cuerpo.append(crear("tr", {}, celdas));
    }
  }

  function cambiarSentido(nuevo) {
    sentido = nuevo;
    for (const boton of document.querySelectorAll("[data-sentido]")) {
      const activo = boton.dataset.sentido === nuevo;
      boton.classList.toggle("activo", activo);
      boton.setAttribute("aria-pressed", String(activo));
    }
    pintarMatriz();
  }

  function abrir(incoterm) {
    enEdicion = incoterm;
    XPS.limpiarAlerta(alertasDialogo);
    document.getElementById("titulo-incoterm").textContent = `Editar ${incoterm.codigo}`;
    form.elements.nombre.value = incoterm.nombre;
    contenedorBloques.replaceChildren();
    for (const [bloque, etiqueta] of BLOQUES) {
      const casilla = crear("input", { atributos: { type: "checkbox", name: bloque, id: `bloque-${bloque}` } });
      casilla.checked = incoterm[bloque];
      contenedorBloques.append(crear("label", { clase: "campo-check", atributos: { for: `bloque-${bloque}` } }, [casilla, etiqueta]));
    }
    form.elements.solo_maritimo.checked = incoterm.solo_maritimo;
    form.elements.activo.checked = incoterm.activo;
    dialogo.showModal();
  }

  form.addEventListener("submit", async (evento) => {
    evento.preventDefault();
    XPS.limpiarAlerta(alertasDialogo);
    const cambios = {};
    const nombre = form.elements.nombre.value.trim();
    if (!nombre) {
      XPS.mostrarAlerta(alertasDialogo, "error", "El nombre no puede estar vacío.");
      return;
    }
    if (nombre !== enEdicion.nombre) {
      cambios.nombre = nombre;
    }
    for (const campo of [...BLOQUES.map(([bloque]) => bloque), "solo_maritimo", "activo"]) {
      if (form.elements[campo].checked !== enEdicion[campo]) {
        cambios[campo] = form.elements[campo].checked;
      }
    }
    try {
      if (Object.keys(cambios).length) {
        await XPS.api(`/incoterms/${enEdicion.codigo}`, { metodo: "PATCH", cuerpo: cambios });
      }
      dialogo.close();
      XPS.mostrarAlerta(alertas, "exito", `Incoterm ${enEdicion.codigo} actualizado.`);
      incoterms = await XPS.api("/incoterms");
      pintarMatriz();
    } catch (error) {
      XPS.mostrarError(alertasDialogo, error);
    }
  });

  // ---------- Inicio ----------

  const yo = await iniciarLayout("incoterms.html");
  if (!yo) {
    return;
  }
  puedeEditar = UI.tieneAlguno(yo, ["config.editar"]);
  document.getElementById("nota-edicion").hidden = !puedeEditar;
  UI.prepararDialogo(dialogo);
  for (const boton of document.querySelectorAll("[data-sentido]")) {
    boton.addEventListener("click", () => cambiarSentido(boton.dataset.sentido));
  }

  try {
    incoterms = await XPS.api("/incoterms");
    pintarCabecera();
    pintarMatriz();
    herramientas.hidden = false;
  } catch (error) {
    XPS.mostrarError(alertas, error);
  }
})();
