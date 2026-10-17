/* Geografía: regiones, países y puertos (catalogo.editar). Sin borrar: se activa o desactiva. */
"use strict";

(async () => {
  const { crear } = XPS;
  const alertas = document.getElementById("alertas");
  const herramientas = document.getElementById("herramientas");
  const botonNuevo = document.getElementById("btn-nuevo");

  const TEXTO_NUEVO = { regiones: "Nueva región", paises: "Nuevo país", puertos: "Nuevo puerto" };
  // E0: los tipos de puerto salen del catálogo de tipos de ubicación (Administración → Tipos de ubicación).
  let tipos = [];

  let pestana = "regiones";
  let regiones = [];
  let paises = [];
  let enEdicion = null;

  const filtros = {
    regionActivo: document.getElementById("filtro-region-activo"),
    paisRegion: document.getElementById("filtro-pais-region"),
    paisActivo: document.getElementById("filtro-pais-activo"),
    puertoQ: document.getElementById("filtro-puerto-q"),
    puertoTipo: document.getElementById("filtro-puerto-tipo"),
    puertoPais: document.getElementById("filtro-puerto-pais"),
    puertoActivo: document.getElementById("filtro-puerto-activo"),
  };

  const dialogos = {
    region: { dialogo: document.getElementById("dialogo-region"), form: document.getElementById("form-region"), alertas: document.getElementById("alertas-region"), titulo: document.getElementById("titulo-region") },
    pais: { dialogo: document.getElementById("dialogo-pais"), form: document.getElementById("form-pais"), alertas: document.getElementById("alertas-pais"), titulo: document.getElementById("titulo-pais") },
    puerto: { dialogo: document.getElementById("dialogo-puerto"), form: document.getElementById("form-puerto"), alertas: document.getElementById("alertas-puerto"), titulo: document.getElementById("titulo-puerto") },
  };

  // ---------- Carga de listas para los selectores ----------

  async function cargarListasBase() {
    [regiones, paises, tipos] = await Promise.all([XPS.api("/regiones"), XPS.api("/paises"), XPS.api("/tipos-ubicacion")]);
    UI.opciones(filtros.puertoTipo, tipos, { valor: (t) => t.codigo, texto: (t) => t.nombre, todos: "Todos" });
    UI.opciones(filtros.paisRegion, regiones, { valor: (r) => r.id, texto: (r) => `${r.codigo} · ${r.nombre}`, todos: "Todas" });
    UI.opciones(filtros.puertoPais, paises, { valor: (p) => p.id, texto: (p) => `${p.iso2} · ${p.nombre}`, todos: "Todos" });
  }

  // ---------- Tablas ----------

  function accionesFila(recurso, ruta, item) {
    return crear("div", { clase: "celda-acciones" }, [
      UI.boton("Editar", () => abrir(recurso, item)),
      UI.boton(item.activo ? "Desactivar" : "Activar", () => cambiarEstado(ruta, item)),
    ]);
  }

  async function cargarRegiones() {
    const lista = await XPS.api(UI.consulta("/regiones", { activo: filtros.regionActivo.value }));
    const cuerpo = document.getElementById("tabla-regiones");
    cuerpo.replaceChildren(...(lista.length ? [] : [UI.filaVacia(4, "No hay regiones con estos filtros.")]));
    for (const region of lista) {
      cuerpo.append(
        crear("tr", {}, [
          UI.celda("Código", [UI.texto(region.codigo, "cifra")]),
          UI.celda("Nombre", [UI.texto(region.nombre)]),
          UI.celda("Estado", [UI.badgeEstado(region.activo)]),
          UI.celda("Acciones", [accionesFila("region", "regiones", region)]),
        ])
      );
    }
  }

  async function cargarPaises() {
    const lista = await XPS.api(
      UI.consulta("/paises", { region_id: filtros.paisRegion.value, activo: filtros.paisActivo.value })
    );
    const cuerpo = document.getElementById("tabla-paises");
    cuerpo.replaceChildren(...(lista.length ? [] : [UI.filaVacia(5, "No hay países con estos filtros.")]));
    for (const pais of lista) {
      cuerpo.append(
        crear("tr", {}, [
          UI.celda("ISO", [UI.texto(pais.iso2, "cifra")]),
          UI.celda("Nombre", [UI.texto(pais.nombre)]),
          UI.celda("Región", [UI.texto(pais.region.nombre)]),
          UI.celda("Estado", [UI.badgeEstado(pais.activo)]),
          UI.celda("Acciones", [accionesFila("pais", "paises", pais)]),
        ])
      );
    }
  }

  async function cargarPuertos() {
    const lista = await XPS.api(
      UI.consulta("/puertos", {
        q: filtros.puertoQ.value.trim(),
        tipo: filtros.puertoTipo.value,
        pais_id: filtros.puertoPais.value,
        activo: filtros.puertoActivo.value,
      })
    );
    const cuerpo = document.getElementById("tabla-puertos");
    cuerpo.replaceChildren(...(lista.length ? [] : [UI.filaVacia(6, "No hay puertos con estos filtros.")]));
    for (const puerto of lista) {
      cuerpo.append(
        crear("tr", {}, [
          UI.celda("Código", [UI.texto(puerto.codigo, "cifra")]),
          UI.celda("Nombre", [UI.texto(puerto.nombre)]),
          UI.celda("Tipo", [UI.texto(nombreTipo(puerto.tipo))]),
          UI.celda("País", [UI.texto(`${puerto.pais.iso2} · ${puerto.pais.nombre}`)]),
          UI.celda("Estado", [UI.badgeEstado(puerto.activo)]),
          UI.celda("Acciones", [accionesFila("puerto", "puertos", puerto)]),
        ])
      );
    }
  }

  const CARGAS = { regiones: cargarRegiones, paises: cargarPaises, puertos: cargarPuertos };

  function nombreTipo(codigo) {
    const tipo = tipos.find((t) => t.codigo === codigo);
    return tipo ? tipo.nombre : codigo;
  }

  function ayudaCodigo() {
    const tipo = tipos.find((t) => t.codigo === dialogos.puerto.form.elements.tipo.value);
    document.getElementById("ayuda-puerto-codigo").textContent = (tipo && tipo.ayuda_codigo) || "";
  }

  async function recargar() {
    await cargarListasBase();
    await CARGAS[pestana]();
  }

  async function seguro(funcion) {
    try {
      await funcion();
    } catch (error) {
      XPS.mostrarError(alertas, error);
    }
  }

  // ---------- Pestañas ----------

  function cambiarPestana(nueva) {
    pestana = nueva;
    for (const boton of document.querySelectorAll("[data-pestana]")) {
      const activa = boton.dataset.pestana === nueva;
      boton.classList.toggle("activa", activa);
      boton.setAttribute("aria-selected", String(activa));
    }
    for (const panel of document.querySelectorAll("[data-panel]")) {
      panel.hidden = panel.dataset.panel !== nueva;
    }
    botonNuevo.textContent = TEXTO_NUEVO[nueva];
    XPS.limpiarAlerta(alertas);
    seguro(CARGAS[nueva]);
  }

  // ---------- Diálogos de alta y edición ----------

  function abrir(recurso, item = null) {
    enEdicion = item;
    const { dialogo, form, alertas: alertasDialogo, titulo } = dialogos[recurso];
    form.reset();
    XPS.limpiarAlerta(alertasDialogo);
    titulo.textContent = `${item ? "Editar" : "Nuevo"} ${{ region: "región", pais: "país", puerto: "puerto" }[recurso]}`;
    if (recurso === "region") {
      form.elements.codigo.value = item ? item.codigo : "";
      form.elements.nombre.value = item ? item.nombre : "";
    } else if (recurso === "pais") {
      const utilizables = regiones.filter((r) => r.activo || (item && r.id === item.region_id));
      UI.opciones(form.elements.region, utilizables, { valor: (r) => r.id, texto: (r) => `${r.codigo} · ${r.nombre}` });
      form.elements.iso2.value = item ? item.iso2 : "";
      form.elements.nombre.value = item ? item.nombre : "";
      if (item) form.elements.region.value = String(item.region_id);
    } else {
      const utilizables = paises.filter((p) => p.activo || (item && p.id === item.pais_id));
      UI.opciones(form.elements.pais, utilizables, { valor: (p) => p.id, texto: (p) => `${p.iso2} · ${p.nombre}` });
      const utilizablesTipo = tipos.filter((t) => t.activo || (item && t.codigo === item.tipo));
      UI.opciones(form.elements.tipo, utilizablesTipo, { valor: (t) => t.codigo, texto: (t) => t.nombre });
      if (item) form.elements.tipo.value = item.tipo;
      ayudaCodigo();
      form.elements.codigo.value = item ? item.codigo : "";
      form.elements.nombre.value = item ? item.nombre : "";
      if (item) form.elements.pais.value = String(item.pais_id);
    }
    dialogo.showModal();
  }

  function datosDe(recurso, form) {
    if (recurso === "region") {
      return { codigo: form.elements.codigo.value, nombre: form.elements.nombre.value };
    }
    if (recurso === "pais") {
      return { iso2: form.elements.iso2.value, nombre: form.elements.nombre.value, region_id: Number(form.elements.region.value) };
    }
    return {
      codigo: form.elements.codigo.value,
      nombre: form.elements.nombre.value,
      pais_id: Number(form.elements.pais.value),
      tipo: form.elements.tipo.value,
    };
  }

  /** En edición solo se envían los campos que cambiaron (PATCH parcial). */
  function cambiosDe(datos, item) {
    const cambios = {};
    for (const [campo, valor] of Object.entries(datos)) {
      if (String(valor).trim() !== String(item[campo])) {
        cambios[campo] = valor;
      }
    }
    return cambios;
  }

  const RUTAS = { region: "regiones", pais: "paises", puerto: "puertos" };

  function conectarFormulario(recurso) {
    const { dialogo, form, alertas: alertasDialogo } = dialogos[recurso];
    UI.prepararDialogo(dialogo);
    form.addEventListener("submit", async (evento) => {
      evento.preventDefault();
      XPS.limpiarAlerta(alertasDialogo);
      const datos = datosDe(recurso, form);
      if (Object.values(datos).some((valor) => valor === "" || Number.isNaN(valor) || valor === 0)) {
        XPS.mostrarAlerta(alertasDialogo, "error", "Complete todos los campos.");
        return;
      }
      try {
        if (enEdicion) {
          const cambios = cambiosDe(datos, enEdicion);
          if (Object.keys(cambios).length) {
            await XPS.api(`/${RUTAS[recurso]}/${enEdicion.id}`, { metodo: "PATCH", cuerpo: cambios });
          }
        } else {
          await XPS.api(`/${RUTAS[recurso]}`, { metodo: "POST", cuerpo: datos });
        }
        dialogo.close();
        XPS.mostrarAlerta(alertas, "exito", "Cambios guardados.");
        await recargar();
      } catch (error) {
        XPS.mostrarError(alertasDialogo, error);
      }
    });
  }

  async function cambiarEstado(ruta, item) {
    XPS.limpiarAlerta(alertas);
    try {
      await XPS.api(`/${ruta}/${item.id}`, { metodo: "PATCH", cuerpo: { activo: !item.activo } });
      XPS.mostrarAlerta(alertas, "exito", item.activo ? "Registro desactivado." : "Registro activado.");
      await recargar();
    } catch (error) {
      XPS.mostrarError(alertas, error);
    }
  }

  // ---------- Inicio ----------

  const yo = await iniciarLayout("geografia.html");
  if (!yo || !UI.exigirAlguno(yo, ["catalogo.editar"], alertas)) {
    return;
  }

  for (const recurso of Object.keys(dialogos)) {
    conectarFormulario(recurso);
  }
  dialogos.puerto.form.elements.tipo.addEventListener("change", ayudaCodigo);
  for (const boton of document.querySelectorAll("[data-pestana]")) {
    boton.addEventListener("click", () => cambiarPestana(boton.dataset.pestana));
  }
  botonNuevo.addEventListener("click", () => abrir({ regiones: "region", paises: "pais", puertos: "puerto" }[pestana]));
  filtros.regionActivo.addEventListener("change", () => seguro(cargarRegiones));
  filtros.paisRegion.addEventListener("change", () => seguro(cargarPaises));
  filtros.paisActivo.addEventListener("change", () => seguro(cargarPaises));
  for (const filtro of [filtros.puertoTipo, filtros.puertoPais, filtros.puertoActivo]) {
    filtro.addEventListener("change", () => seguro(cargarPuertos));
  }
  let espera = null;
  filtros.puertoQ.addEventListener("input", () => {
    window.clearTimeout(espera);
    espera = window.setTimeout(() => seguro(cargarPuertos), 300);
  });

  try {
    await recargar();
    herramientas.hidden = false;
    botonNuevo.hidden = false;
  } catch (error) {
    XPS.mostrarError(alertas, error);
  }
})();
