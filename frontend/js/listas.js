/* E1 Listas de envío: manual (buscador de contactos e importación de un CSV con emails, leído en el navegador) o por
 * filtro (servicios, tipos de equipo, orígenes, destinos, país y ciudad) con vista previa. boletines.ver lee;
 * boletines.listas.gestionar edita. Los servicios y los tipos de equipo salen de sus catálogos.
 */
"use strict";

(async () => {
  const { crear } = XPS;
  const alertas = document.getElementById("alertas");
  const cuerpo = document.getElementById("tabla-listas");
  const dialogo = document.getElementById("dialogo-lista");
  const form = document.getElementById("form-lista");
  const alertasDialogo = document.getElementById("alertas-lista");
  const SELECTORES = { servicios: "filtro-servicios", tipos_equipo: "filtro-equipos", origenes: "filtro-origenes",
    destinos: "filtro-destinos", paises: "filtro-paises", ciudades: "filtro-ciudades" };

  let puedeEditar = false;
  let enEdicion = null;
  let miembros = new Map();

  function contador(etiqueta, valor) {
    return crear("div", { clase: "contador" }, [crear("strong", { texto: String(valor) }), crear("span", { clase: "texto-suave", texto: etiqueta })]);
  }

  function pintarResumen(resumen) {
    document.getElementById("contadores-lista").replaceChildren(
      contador("contactos", resumen.total), contador("con baja", resumen.con_baja),
      contador("duplicados", resumen.duplicados), contador("recibirían", resumen.recibiran));
  }

  async function cargar() {
    const listas = await XPS.api("/boletines/listas");
    cuerpo.replaceChildren(...(listas.length ? [] : [UI.filaVacia(5, "Todavía no hay listas.")]));
    for (const lista of listas) {
      const acciones = [];
      if (puedeEditar) {
        acciones.push(UI.boton("Editar", () => abrir(lista)),
          UI.boton(lista.activo ? "Desactivar" : "Activar", () => seguro(async () => {
            await XPS.api(`/boletines/listas/${lista.id}`, { metodo: "PATCH", cuerpo: { activo: !lista.activo } });
            await cargar();
          })));
      }
      cuerpo.append(crear("tr", {}, [
        UI.celda("Lista", [crear("div", {}, [UI.texto(lista.nombre), crear("div", { clase: "texto-suave", texto: lista.descripcion || "" })])]),
        UI.celda("Tipo", [UI.texto(lista.tipo === "MANUAL" ? "Manual" : "Por filtro")]),
        UI.celda("Contactos", [UI.texto(String(lista.miembros), "cifra")]),
        UI.celda("Estado", [UI.badgeEstado(lista.activo)]),
        UI.celda("Acciones", [crear("div", { clase: "celda-acciones" }, acciones)]),
      ]));
    }
  }

  async function seguro(funcion, contenedor = alertas) {
    try {
      await funcion();
    } catch (error) {
      XPS.mostrarError(contenedor, error);
    }
  }

  function ajustarTipo() {
    const manual = form.elements.tipo.value === "MANUAL";
    document.getElementById("bloque-manual").hidden = !manual;
    document.getElementById("bloque-filtro").hidden = manual;
  }

  function pintarMiembros() {
    const tabla = document.getElementById("miembros-lista");
    tabla.replaceChildren(...(miembros.size ? [] : [UI.filaVacia(3, "La lista no tiene contactos.")]));
    for (const contacto of miembros.values()) {
      tabla.append(crear("tr", {}, [
        UI.celda("Contacto", [UI.texto(`${contacto.nombre} · ${contacto.cliente}`)]),
        UI.celda("Email", [UI.texto(contacto.email, "cifra")]),
        UI.celda("", [UI.boton("Quitar", () => { miembros.delete(contacto.id); pintarMiembros(); })]),
      ]));
    }
  }

  function filtrosDelFormulario() {
    const filtros = {};
    for (const [clave, id] of Object.entries(SELECTORES)) {
      const valores = [...document.getElementById(id).selectedOptions].map((o) => o.value);
      if (valores.length) filtros[clave] = valores;
    }
    return filtros;
  }

  async function abrir(lista = null) {
    enEdicion = lista;
    form.reset();
    XPS.limpiarAlerta(alertasDialogo);
    miembros = new Map();
    document.getElementById("titulo-lista").textContent = lista ? `Editar ${lista.nombre}` : "Nueva lista";
    document.getElementById("contadores-lista").replaceChildren();
    document.getElementById("resultados-contactos").replaceChildren();
    if (lista) {
      form.elements.nombre.value = lista.nombre;
      form.elements.descripcion.value = lista.descripcion || "";
      form.elements.tipo.value = lista.tipo;
      for (const [clave, id] of Object.entries(SELECTORES)) {
        const valores = (lista.filtros[clave] || []).map(String);
        for (const opcion of document.getElementById(id).options) opcion.selected = valores.includes(opcion.value);
      }
      const detalle = await XPS.api(`/boletines/listas/${lista.id}`);
      if (lista.tipo === "MANUAL") {
        for (const contacto of detalle.resumen.muestra) miembros.set(contacto.id, contacto);
      }
      pintarResumen(detalle.resumen);
    }
    ajustarTipo();
    pintarMiembros();
    dialogo.showModal();
  }

  let espera = null;
  document.getElementById("buscar-contacto").addEventListener("input", (evento) => {
    window.clearTimeout(espera);
    espera = window.setTimeout(() => seguro(async () => {
      const encontrados = evento.target.value.trim().length < 2 ? [] : await XPS.api(UI.consulta("/boletines/contactos", { q: evento.target.value.trim() }));
      document.getElementById("resultados-contactos").replaceChildren(...encontrados.map((c) => crear("tr", {}, [
        UI.celda("Contacto", [UI.texto(`${c.nombre} · ${c.cliente}`)]), UI.celda("Email", [UI.texto(c.email, "cifra")]),
        UI.celda("", [UI.boton("Agregar", () => { miembros.set(c.id, c); pintarMiembros(); })]),
      ])));
    }, alertasDialogo), 300);
  });

  document.getElementById("archivo-csv").addEventListener("change", (evento) => seguro(async () => {
    const archivo = evento.target.files[0];
    if (!archivo) return;
    if (!enEdicion) {
      XPS.mostrarAlerta(alertasDialogo, "error", "Guarde la lista primero y luego importe el CSV.");
      return;
    }
    const texto = await archivo.text();
    const emails = texto.split(/[\r\n,;\t]+/).map((v) => v.trim().replace(/^"|"$/g, "")).filter((v) => v.includes("@"));
    const resultado = await XPS.api(`/boletines/listas/${enEdicion.id}/importar`, { metodo: "POST", cuerpo: { emails } });
    XPS.mostrarAlerta(alertasDialogo, "exito", `Agregados: ${resultado.agregados} · ya estaban: ${resultado.ya_estaban} · sin contacto: ${resultado.sin_contacto.length}`);
    const detalle = await XPS.api(`/boletines/listas/${enEdicion.id}`);
    miembros = new Map(detalle.resumen.muestra.map((c) => [c.id, c]));
    pintarMiembros();
    pintarResumen(detalle.resumen);
  }, alertasDialogo));

  document.getElementById("btn-previa").addEventListener("click", () => seguro(async () => {
    pintarResumen(await XPS.api("/boletines/listas/vista-previa", { metodo: "POST", cuerpo: { tipo: "FILTRO", filtros: filtrosDelFormulario() } }));
  }, alertasDialogo));

  form.elements.tipo.addEventListener("change", ajustarTipo);
  form.addEventListener("submit", (evento) => {
    evento.preventDefault();
    seguro(async () => {
      const datos = {
        nombre: form.elements.nombre.value.trim(),
        descripcion: form.elements.descripcion.value.trim() || null,
        tipo: form.elements.tipo.value,
        filtros: form.elements.tipo.value === "FILTRO" ? filtrosDelFormulario() : {},
      };
      if (datos.tipo === "MANUAL") datos.contactos = [...miembros.keys()];
      if (enEdicion) {
        await XPS.api(`/boletines/listas/${enEdicion.id}`, { metodo: "PATCH", cuerpo: datos });
      } else {
        await XPS.api("/boletines/listas", { metodo: "POST", cuerpo: datos });
      }
      dialogo.close();
      XPS.mostrarAlerta(alertas, "exito", "Lista guardada.");
      await cargar();
    }, alertasDialogo);
  });

  const yo = await iniciarLayout("listas.html");
  if (!yo || !UI.exigirAlguno(yo, ["boletines.ver"], alertas)) {
    return;
  }
  puedeEditar = UI.tieneAlguno(yo, ["boletines.listas.gestionar"]);
  UI.prepararDialogo(dialogo);
  const botonNueva = document.getElementById("btn-nueva");
  botonNueva.addEventListener("click", () => seguro(() => abrir()));
  try {
    const [servicios, tipos, puertos, opciones] = await Promise.all([
      XPS.api("/servicios"), XPS.api("/tipos-equipo"), XPS.api("/puertos?activo=true"), XPS.api("/boletines/filtros"),
    ]);
    UI.opciones(document.getElementById("filtro-servicios"), servicios, { valor: (s) => s.codigo, texto: (s) => s.nombre });
    UI.opciones(document.getElementById("filtro-equipos"), tipos, { valor: (t) => t.id, texto: (t) => t.codigo });
    for (const id of ["filtro-origenes", "filtro-destinos"]) {
      UI.opciones(document.getElementById(id), puertos, { valor: (p) => p.id, texto: (p) => `${p.codigo} · ${p.nombre}` });
    }
    UI.opciones(document.getElementById("filtro-paises"), opciones.paises, { valor: (p) => p.id, texto: (p) => p.nombre });
    UI.opciones(document.getElementById("filtro-ciudades"), opciones.ciudades.map((c) => ({ c })), { valor: (x) => x.c, texto: (x) => x.c });
    await cargar();
    document.getElementById("herramientas").hidden = false;
    botonNueva.hidden = !puedeEditar;
  } catch (error) {
    XPS.mostrarError(alertas, error);
  }
})();
