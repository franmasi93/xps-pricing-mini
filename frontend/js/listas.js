/* E1 Listas de envío: manual (buscador de contactos; importación con la plantilla oficial o correos pegados de contactos
 * existentes) o por filtro (servicios, tipos de equipo, orígenes, destinos, país y ciudad) con vista previa.
 * E1-B: condiciones del perfil comercial y del interés calculado, combinadas con Y u O. boletines.ver lee;
 * boletines.listas.gestionar edita. Los valores salen de los catálogos.
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
  let catalogos = {};
  let servicios = [];
  const CAMPOS = [
    ["tipo_cliente", "Tipo de cliente", "TIPO_CLIENTE"], ["estado_comercial", "Estado comercial", "ESTADO_COMERCIAL"],
    ["sector", "Sector", "SECTOR"], ["volumen_estimado", "Volumen", "VOLUMEN"], ["frecuencia", "Frecuencia", "FRECUENCIA"],
    ["origen_cliente", "Cómo llegó", "ORIGEN_CLIENTE"], ["medio_consentimiento", "Medio de consentimiento", "MEDIO_CONSENTIMIENTO"],
    ["servicios_interes", "Servicios de interés", "SERVICIOS"], ["tipos_carga", "Tipos de carga", "TIPO_CARGA"],
    ["rutas_interes", "Rutas de interés (CN>EC)", null], ["etiquetas", "Etiquetas", null],
    ["acepta_promociones", "Acepta promociones", "SI_NO"], ["pais", "País del cliente (ISO2)", null], ["ciudad", "Ciudad", null],
    ["area_contacto", "Área del contacto", "AREA_CONTACTO"], ["cotizo_servicio", "Cotizó el servicio", "SERVICIOS"],
    ["cotizo_ruta", "Cotizó la ruta (CN>EC o CNSHA>ECGYE)", null],
  ];

  function opcionesDe(tipo) {
    if (tipo === "SERVICIOS") return servicios.map((s) => ({ codigo: s.codigo, nombre: s.nombre }));
    if (tipo === "SI_NO") return [{ codigo: "SI", nombre: "Sí" }, { codigo: "NO", nombre: "No" }];
    return catalogos[tipo] || [];
  }

  function filaCondicion(condicion = { campo: "tipo_cliente", valores: [] }) {
    const fila = crear("div", { clase: "condicion" });
    const campo = crear("select", { clase: "select", atributos: { "aria-label": "Campo" } });
    UI.opciones(campo, CAMPOS, { valor: (c) => c[0], texto: (c) => c[1] });
    campo.value = condicion.campo;
    const valores = crear("div");
    const meses = crear("input", { clase: "input cifra", atributos: { type: "number", min: 1, max: 60, value: condicion.meses || 6, "aria-label": "Meses hacia atrás", title: "Meses hacia atrás" } });
    const quitar = UI.boton("Quitar", () => fila.remove());
    const pintarValores = () => {
      const definicion = CAMPOS.find((c) => c[0] === campo.value);
      meses.hidden = !campo.value.startsWith("cotizo_");
      if (definicion[2]) {
        const select = crear("select", { clase: "select", atributos: { multiple: "", "aria-label": "Valores" } });
        UI.opciones(select, opcionesDe(definicion[2]), { valor: (v) => v.codigo, texto: (v) => v.nombre });
        for (const opcion of select.options) opcion.selected = (condicion.valores || []).includes(opcion.value);
        valores.replaceChildren(select);
      } else {
        const entrada = crear("input", { clase: "input", atributos: { type: "text", placeholder: "Varios separados por |", "aria-label": "Valores" } });
        entrada.value = (condicion.valores || []).join("|");
        valores.replaceChildren(entrada);
      }
    };
    campo.addEventListener("change", () => { condicion = { campo: campo.value, valores: [] }; pintarValores(); });
    pintarValores();
    fila.append(campo, valores, meses, quitar);
    fila.leer = () => {
      const control = valores.firstChild;
      const lista = control.tagName === "SELECT" ? [...control.selectedOptions].map((o) => o.value)
        : control.value.split("|").map((v) => v.trim()).filter(Boolean);
      const salida = { campo: campo.value, valores: lista };
      if (campo.value.startsWith("cotizo_")) salida.meses = Number(meses.value || 6);
      return salida;
    };
    return fila;
  }

  function contador(etiqueta, valor) {
    return crear("div", { clase: "contador" }, [crear("strong", { texto: String(valor) }), crear("span", { clase: "texto-suave", texto: etiqueta })]);
  }

  function pintarResumen(resumen) {
    document.getElementById("contadores-lista").replaceChildren(
      contador("contactos", resumen.total), contador("con baja", resumen.con_baja),
      contador("sin consentimiento", resumen.sin_consentimiento ?? 0),
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
    const condiciones = [...document.getElementById("condiciones").children].map((f) => f.leer()).filter((c) => c.valores.length);
    if (condiciones.length) {
      filtros.condiciones = condiciones;
      filtros.combinar = document.getElementById("combinar-condiciones").value;
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
    document.getElementById("condiciones").replaceChildren();
    document.getElementById("combinar-condiciones").value = "Y";
    if (lista) {
      for (const condicion of lista.filtros.condiciones || []) document.getElementById("condiciones").append(filaCondicion(condicion));
      document.getElementById("combinar-condiciones").value = lista.filtros.combinar || "Y";
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

  async function refrescarMiembros() {
    const detalle = await XPS.api(`/boletines/listas/${enEdicion.id}`);
    miembros = new Map(detalle.resumen.muestra.map((c) => [c.id, c]));
    pintarMiembros();
    pintarResumen(detalle.resumen);
  }

  document.getElementById("btn-importar-oficial").addEventListener("click", () => {
    if (!enEdicion) {
      XPS.mostrarAlerta(alertasDialogo, "error", "Guarde la lista primero y luego importe la plantilla.");
      return;
    }
    Importacion.abrir({ listaId: enEdicion.id, titulo: `Importar clientes a «${enEdicion.nombre}»`,
      alTerminar: () => seguro(refrescarMiembros, alertasDialogo) });
  });

  document.getElementById("btn-pegar-emails").addEventListener("click", () => seguro(async () => {
    if (!enEdicion) {
      XPS.mostrarAlerta(alertasDialogo, "error", "Guarde la lista primero y luego agregue los correos.");
      return;
    }
    const texto = document.getElementById("pegar-emails").value;
    const emails = texto.split(/[\r\n,;\t ]+/).map((v) => v.trim().replace(/^"|"$/g, "")).filter((v) => v.includes("@"));
    const resultado = await XPS.api(`/boletines/listas/${enEdicion.id}/importar`, { metodo: "POST", cuerpo: { emails } });
    XPS.mostrarAlerta(alertasDialogo, "exito", `Agregados: ${resultado.agregados} · ya estaban: ${resultado.ya_estaban} · sin contacto: ${resultado.sin_contacto.length}`);
    document.getElementById("pegar-emails").value = "";
    await refrescarMiembros();
  }, alertasDialogo));

  document.getElementById("btn-condicion").addEventListener("click", () => document.getElementById("condiciones").append(filaCondicion()));

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
    const [listaServicios, tipos, puertos, opciones, listaCatalogos] = await Promise.all([
      XPS.api("/servicios"), XPS.api("/tipos-equipo"), XPS.api("/puertos?activo=true"), XPS.api("/boletines/filtros"),
      XPS.api("/catalogos-perfil?activo=true"),
    ]);
    servicios = listaServicios;
    for (const item of listaCatalogos) (catalogos[item.tipo] = catalogos[item.tipo] || []).push(item);
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
