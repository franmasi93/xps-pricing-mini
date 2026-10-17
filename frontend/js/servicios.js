/* E0 Servicios: configuracion.servicios.gestionar (admin) crea, edita, desactiva y borra (si nunca se usó);
 * los demás roles solo leen. La forma de cobro es un catálogo cerrado (/formas-cobro): al elegirla se muestra qué
 * unidades y campos implica. La pestaña "Tramos" existe solo en los servicios que cobran por peso con tramos.
 */
"use strict";

(async () => {
  const { crear } = XPS;
  const PERMISO = "configuracion.servicios.gestionar";
  const alertas = document.getElementById("alertas");
  const herramientas = document.getElementById("herramientas");
  const botonNuevo = document.getElementById("btn-nuevo");
  const cuerpo = document.getElementById("tabla-servicios");
  const filtroActivo = document.getElementById("filtro-activo");

  const dialogo = document.getElementById("dialogo-servicio");
  const form = document.getElementById("form-servicio");
  const alertasDialogo = document.getElementById("alertas-servicio");
  const pestanaTramos = document.getElementById("pestana-tramos");
  const formTramo = document.getElementById("form-tramo");
  const cuerpoTramos = document.getElementById("tabla-tramos");
  const TEXTOS = ["descripcion_pdf", "etiqueta_transportista", "aviso_incoterm"];

  let puedeEditar = false;
  let formas = [];
  let ubicaciones = [];
  let enEdicion = null;

  const formaDe = (codigo) => formas.find((f) => f.codigo === codigo) || null;
  const nombreUbicacion = (codigo) => (ubicaciones.find((u) => u.codigo === codigo) || { nombre: codigo }).nombre;
  const numero = (valor) => String(valor).replace(".", ",");

  // ---------- Listado ----------

  async function cargar() {
    const lista = await XPS.api(UI.consulta("/servicios", { activo: filtroActivo.value }));
    const columnas = puedeEditar ? 8 : 7;
    cuerpo.replaceChildren(...(lista.length ? [] : [UI.filaVacia(columnas, "No hay servicios con este filtro.")]));
    for (const servicio of lista) {
      const forma = formaDe(servicio.forma_cobro);
      const tramos = servicio.tramos.filter((t) => t.activo);
      const resumen = forma && forma.usa_tramos
        ? ["KG", "LB"].map((u) => {
          const desdes = tramos.filter((t) => t.unidad_peso === u).map((t) => numero(t.desde));
          return desdes.length ? `${u.toLowerCase()}: ${desdes.join(" · ")}` : null;
        }).filter(Boolean).join(" / ") || "Sin tramos"
        : "—";
      const celdas = [
        UI.celda("Orden", [UI.texto(String(servicio.orden), "cifra")]),
        UI.celda("Código", [UI.texto(servicio.codigo, "cifra")]),
        UI.celda("Nombre", [UI.texto(servicio.nombre)]),
        UI.celda("Forma de cobro", [UI.texto(forma ? forma.nombre : servicio.forma_cobro)]),
        UI.celda("Origen → destino", [UI.texto(`${nombreUbicacion(servicio.tipo_ubicacion_origen)} → ${nombreUbicacion(servicio.tipo_ubicacion_destino)}`)]),
        UI.celda("Tramos", [UI.texto(resumen, "cifra")]),
        UI.celda("Estado", [UI.badgeEstado(servicio.activo)]),
      ];
      if (puedeEditar) {
        celdas.push(UI.celda("Acciones", [crear("div", { clase: "celda-acciones" }, [
          UI.boton("Editar", () => abrir(servicio)),
          UI.boton(servicio.activo ? "Desactivar" : "Activar", () => cambiarEstado(servicio)),
          UI.boton("Borrar", () => borrar(servicio)),
        ])]));
      }
      cuerpo.append(crear("tr", {}, celdas));
    }
  }

  async function cambiarEstado(servicio) {
    XPS.limpiarAlerta(alertas);
    try {
      await XPS.api(`/servicios/${servicio.id}`, { metodo: "PATCH", cuerpo: { activo: !servicio.activo } });
      XPS.mostrarAlerta(alertas, "exito", servicio.activo
        ? `Servicio ${servicio.codigo} desactivado: ya no se ofrece para tarifas ni cotizaciones nuevas.`
        : `Servicio ${servicio.codigo} activado.`);
      await cargar();
    } catch (error) {
      XPS.mostrarError(alertas, error);
    }
  }

  async function borrar(servicio) {
    if (!window.confirm(`¿Borrar el servicio ${servicio.codigo}? Solo se puede si nunca se usó.`)) {
      return;
    }
    XPS.limpiarAlerta(alertas);
    try {
      await XPS.api(`/servicios/${servicio.id}`, { metodo: "DELETE" });
      XPS.mostrarAlerta(alertas, "exito", `Servicio ${servicio.codigo} borrado.`);
      await cargar();
    } catch (error) {
      XPS.mostrarError(alertas, error);
    }
  }

  // ---------- Formulario ----------

  function cambiarPestana(nombre) {
    for (const boton of dialogo.querySelectorAll("[data-pestana]")) {
      const activa = boton.dataset.pestana === nombre;
      boton.classList.toggle("activa", activa);
      boton.setAttribute("aria-selected", String(activa));
    }
    for (const panel of dialogo.querySelectorAll("[data-panel]")) {
      panel.hidden = panel.dataset.panel !== nombre;
    }
    XPS.limpiarAlerta(alertasDialogo);
  }

  function ajustar() {
    const forma = formaDe(form.elements.forma_cobro.value);
    document.getElementById("ayuda-forma").textContent = forma
      ? `${forma.descripcion} Unidades de tarifa: ${forma.unidades_tarifa.join(", ")}; de recargo: ${forma.unidades_recargo.join(", ")}.`
      : "";
    document.getElementById("campo-libras").hidden = !(forma && forma.admite_libras);
    document.getElementById("nota-equipo").hidden = !(forma && forma.usa_tipo_equipo);
    pestanaTramos.hidden = !(enEdicion && formaDe(enEdicion.forma_cobro) && formaDe(enEdicion.forma_cobro).usa_tramos);
  }

  function abrir(servicio = null) {
    enEdicion = servicio;
    form.reset();
    cambiarPestana("datos");
    document.getElementById("titulo-servicio").textContent = servicio ? `Editar ${servicio.codigo}` : "Nuevo servicio";
    UI.opciones(form.elements.forma_cobro, formas, { valor: (f) => f.codigo, texto: (f) => f.nombre });
    const utilizables = ubicaciones.filter((u) => u.activo || (servicio && [servicio.tipo_ubicacion_origen, servicio.tipo_ubicacion_destino].includes(u.codigo)));
    for (const campo of ["tipo_ubicacion_origen", "tipo_ubicacion_destino"]) {
      UI.opciones(form.elements[campo], utilizables, { valor: (u) => u.codigo, texto: (u) => u.nombre });
    }
    if (servicio) {
      for (const campo of ["codigo", "nombre", "forma_cobro", "tipo_ubicacion_origen", "tipo_ubicacion_destino", "orden", ...TEXTOS]) {
        form.elements[campo].value = servicio[campo] ?? "";
      }
      form.elements.permite_libras.checked = servicio.permite_libras;
      pintarTramos(servicio);
    }
    ajustar();
    dialogo.showModal();
  }

  function leer() {
    const forma = formaDe(form.elements.forma_cobro.value);
    const datos = {
      codigo: form.elements.codigo.value.trim().toUpperCase(),
      nombre: form.elements.nombre.value.trim(),
      forma_cobro: form.elements.forma_cobro.value,
      tipo_ubicacion_origen: form.elements.tipo_ubicacion_origen.value,
      tipo_ubicacion_destino: form.elements.tipo_ubicacion_destino.value,
      orden: Number(form.elements.orden.value || 0),
      permite_libras: Boolean(forma && forma.admite_libras && form.elements.permite_libras.checked),
    };
    for (const campo of TEXTOS) {
      datos[campo] = form.elements[campo].value.trim() || null;
    }
    return datos;
  }

  form.elements.forma_cobro.addEventListener("change", ajustar);

  form.addEventListener("submit", async (evento) => {
    evento.preventDefault();
    XPS.limpiarAlerta(alertasDialogo);
    const datos = leer();
    if (!datos.codigo || !datos.nombre) {
      XPS.mostrarAlerta(alertasDialogo, "error", "El código y el nombre son obligatorios.");
      return;
    }
    try {
      if (enEdicion) {
        const cambios = {};
        for (const [campo, valor] of Object.entries(datos)) {
          if ((valor ?? null) !== (enEdicion[campo] ?? null)) cambios[campo] = valor;
        }
        // Los textos del PDF no se pueden vaciar: si se borran, se conservan los guardados.
        for (const campo of ["descripcion_pdf", "etiqueta_transportista"]) {
          if (cambios[campo] === null) delete cambios[campo];
        }
        if (Object.keys(cambios).length) {
          await XPS.api(`/servicios/${enEdicion.id}`, { metodo: "PATCH", cuerpo: cambios });
        }
      } else {
        await XPS.api("/servicios", { metodo: "POST", cuerpo: datos });
      }
      dialogo.close();
      XPS.mostrarAlerta(alertas, "exito", "Servicio guardado.");
      await cargar();
    } catch (error) {
      XPS.mostrarError(alertasDialogo, error);
    }
  });

  // ---------- Pestaña Tramos ----------

  function pintarTramos(servicio) {
    const tramos = [...servicio.tramos].sort((a, b) => a.unidad_peso.localeCompare(b.unidad_peso) || a.desde - b.desde);
    cuerpoTramos.replaceChildren(...(tramos.length ? [] : [UI.filaVacia(4, "El servicio no tiene tramos. Agregue al menos el tramo desde 0.")]));
    for (const tramo of tramos) {
      cuerpoTramos.append(crear("tr", {}, [
        UI.celda("Unidad", [UI.texto(tramo.unidad_peso)]),
        UI.celda("Desde", [UI.texto(numero(tramo.desde), "cifra")]),
        UI.celda("Estado", [UI.badgeEstado(tramo.activo)]),
        UI.celda("Acciones", [crear("div", { clase: "celda-acciones" }, [
          UI.boton(tramo.activo ? "Desactivar" : "Activar", () => accionTramo(`/servicio-tramos/${tramo.id}`, "PATCH", { activo: !tramo.activo })),
          UI.boton("Borrar", () => accionTramo(`/servicio-tramos/${tramo.id}`, "DELETE")),
        ])]),
      ]));
    }
    const unidades = servicio.permite_libras ? ["KG", "LB"] : ["KG"];
    UI.opciones(formTramo.elements.unidad_peso, unidades.map((u) => ({ u })), { valor: (x) => x.u, texto: (x) => x.u });
  }

  async function recargarServicio() {
    enEdicion = await XPS.api(`/servicios/${enEdicion.id}`);
    pintarTramos(enEdicion);
    await cargar();
  }

  async function accionTramo(ruta, metodo, cuerpoPeticion) {
    XPS.limpiarAlerta(alertasDialogo);
    try {
      await XPS.api(ruta, { metodo, cuerpo: cuerpoPeticion });
      await recargarServicio();
    } catch (error) {
      XPS.mostrarError(alertasDialogo, error);
    }
  }

  formTramo.addEventListener("submit", async (evento) => {
    evento.preventDefault();
    const desde = formTramo.elements.desde.value.trim().replace(",", ".");
    if (!desde) {
      XPS.mostrarAlerta(alertasDialogo, "error", "Indique desde qué peso empieza el tramo.");
      return;
    }
    await accionTramo(`/servicios/${enEdicion.id}/tramos`, "POST", { unidad_peso: formTramo.elements.unidad_peso.value, desde });
    formTramo.elements.desde.value = "";
  });

  // ---------- Inicio ----------

  const yo = await iniciarLayout("servicios.html");
  if (!yo) {
    return;
  }
  puedeEditar = UI.tieneAlguno(yo, [PERMISO]);
  document.getElementById("th-acciones").hidden = !puedeEditar;
  document.getElementById("nota-lectura").hidden = puedeEditar;
  UI.prepararDialogo(dialogo);
  for (const boton of dialogo.querySelectorAll("[data-pestana]")) {
    boton.addEventListener("click", () => cambiarPestana(boton.dataset.pestana));
  }
  botonNuevo.addEventListener("click", () => abrir());
  filtroActivo.addEventListener("change", async () => {
    try {
      await cargar();
    } catch (error) {
      XPS.mostrarError(alertas, error);
    }
  });

  try {
    [formas, ubicaciones] = await Promise.all([XPS.api("/formas-cobro"), XPS.api("/tipos-ubicacion")]);
    await cargar();
    herramientas.hidden = false;
    botonNuevo.hidden = !puedeEditar;
  } catch (error) {
    XPS.mostrarError(alertas, error);
  }
})();
