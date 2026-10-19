/* P8 Clientes y contactos. cliente.ver lee (el comercial solo los suyos: lo filtra el backend);
 * cliente.editar escribe. Quien tiene cotizacion.ver_todas (admin) elige el comercial asignado.
 * E1-B: perfil comercial y consentimiento (pestaña de la ficha), filtros del perfil, columnas visibles por usuario,
 * importar y exportar con la plantilla oficial, y la pestaña Correos (todo lo enviado a sus contactos, con su entrega).
 */
"use strict";

(async () => {
  const { crear } = XPS;
  let tipos = []; // E2: catálogo tipo_identificacion
  const nombreTipo = (codigo) => (tipos.find((t) => t.codigo === codigo) || { nombre: codigo }).nombre;

  const alertas = document.getElementById("alertas");
  const herramientas = document.getElementById("herramientas");
  const botonNuevo = document.getElementById("btn-nuevo");
  const cuerpo = document.getElementById("tabla-clientes");
  const filtroQ = document.getElementById("filtro-q");
  const filtroActivo = document.getElementById("filtro-activo");

  const dialogoCliente = document.getElementById("dialogo-cliente");
  const formCliente = document.getElementById("form-cliente");
  const alertasCliente = document.getElementById("alertas-cliente");
  const dialogoContactos = document.getElementById("dialogo-contactos");
  const formContacto = document.getElementById("form-contacto");
  const alertasContactos = document.getElementById("alertas-contactos");

  let puedeEditar = false;
  let asignaComercial = false;
  let paises = [];
  let comerciales = [];
  let servicios = [];
  let catalogos = {}; // E1-B: tipo → [{codigo, nombre}]
  let enEdicion = null;
  let clienteContactos = null;
  let contactoEnEdicion = null;
  let ultimaLista = [];

  const nombreCatalogo = (tipo, codigo) => ((catalogos[tipo] || []).find((v) => v.codigo === codigo) || { nombre: codigo || "" }).nombre;
  const fechaCorta = (valor) => {
    if (!valor) return "";
    const [anio, mes, dia] = String(valor).slice(0, 10).split("-");
    return `${dia}/${mes}/${anio}`;
  };

  // ---------- Columnas visibles (se guardan por usuario) ----------

  const COLUMNAS = [
    { clave: "razon_social", titulo: "Razón social", valor: (c) => UI.texto(c.razon_social) },
    { clave: "identificacion", titulo: "Identificación", valor: (c) => UI.texto(`${nombreTipo(c.tipo_id)} ${c.ruc_o_id}`, "cifra") },
    { clave: "ciudad", titulo: "Ciudad", valor: (c) => UI.texto(c.ciudad ? `${c.ciudad} · ${c.pais.iso2}` : c.pais.nombre) },
    { clave: "comercial", titulo: "Comercial", valor: (c) => UI.texto(c.comercial_asignado.nombre) },
    { clave: "estado_comercial", titulo: "Estado comercial", valor: (c) => crear("span", { clase: "badge badge-rol", texto: nombreCatalogo("ESTADO_COMERCIAL", c.estado_comercial) }) },
    { clave: "tipo_cliente", titulo: "Tipo", valor: (c) => UI.texto(nombreCatalogo("TIPO_CLIENTE", c.tipo_cliente)) },
    { clave: "sector", titulo: "Sector", valor: (c) => UI.texto(nombreCatalogo("SECTOR", c.sector)) },
    { clave: "servicios_interes", titulo: "Servicios de interés", valor: (c) => UI.texto(c.servicios_interes.join(", ")) },
    { clave: "etiquetas", titulo: "Etiquetas", valor: (c) => UI.texto(c.etiquetas.join(", ")) },
    { clave: "acepta_promociones", titulo: "Acepta promociones", valor: (c) => UI.texto(c.acepta_promociones ? "Sí" : "No") },
    { clave: "ultimo_envio", titulo: "Último envío", valor: (c) => UI.texto(fechaCorta(c.ultimo_envio), "cifra") },
    { clave: "ultima_cotizacion", titulo: "Última cotización", valor: (c) => UI.texto(fechaCorta(c.ultima_cotizacion), "cifra") },
    { clave: "contacto_principal", titulo: "Contacto principal", valor: (c) => {
      const p = c.contacto_principal;
      return UI.texto(p ? (p.email ? `${p.nombre} · ${p.email}` : p.nombre) : null);
    } },
    { clave: "estado", titulo: "Registro", valor: (c) => UI.badgeEstado(c.activo) },
  ];
  const POR_DEFECTO = ["razon_social", "identificacion", "comercial", "estado_comercial", "tipo_cliente", "contacto_principal"];
  let visibles = [...POR_DEFECTO];

  function pintarSelectorColumnas() {
    const lista = document.getElementById("lista-columnas");
    lista.replaceChildren(...COLUMNAS.map((col) => {
      const id = `columna-${col.clave}`;
      const casilla = crear("input", { atributos: { id, type: "checkbox", value: col.clave } });
      casilla.checked = visibles.includes(col.clave);
      casilla.addEventListener("change", async () => {
        visibles = COLUMNAS.map((c) => c.clave).filter((clave) => document.getElementById(`columna-${clave}`).checked);
        if (!visibles.length) visibles = ["razon_social"];
        pintar(ultimaLista);
        try {
          await XPS.api("/preferencias/clientes.columnas", { metodo: "PUT", cuerpo: { valor: visibles } });
        } catch (error) {
          XPS.mostrarError(alertas, error);
        }
      });
      return crear("label", { clase: "campo-check", atributos: { for: id } }, [casilla, ` ${col.titulo}`]);
    }));
  }

  // El panel de columnas se cierra al hacer clic fuera o con Escape (no queda encima de la ficha).
  const selectorColumnas = document.getElementById("selector-columnas");
  document.addEventListener("click", (evento) => {
    if (selectorColumnas.open && !selectorColumnas.contains(evento.target)) selectorColumnas.open = false;
  });
  document.addEventListener("keydown", (evento) => {
    if (evento.key === "Escape" && selectorColumnas.open) selectorColumnas.open = false;
  });

  // ---------- Listado ----------

  function pintar(lista) {
    ultimaLista = lista;
    const columnas = COLUMNAS.filter((c) => visibles.includes(c.clave));
    document.getElementById("cabecera-clientes").replaceChildren(...columnas.map((c) => crear("th", { texto: c.titulo })), crear("th", { texto: "Acciones" }));
    cuerpo.replaceChildren(...(lista.length ? [] : [UI.filaVacia(columnas.length + 1, "No hay clientes con estos filtros.")]));
    for (const cliente of lista) {
      const acciones = [UI.boton(puedeEditar ? "Ficha" : "Ver ficha", () => abrirCliente(cliente)), UI.boton("Contactos", () => abrirContactos(cliente))];
      if (puedeEditar) {
        acciones.push(UI.boton(cliente.activo ? "Desactivar" : "Activar", () => cambiarEstado(cliente)));
      }
      cuerpo.append(crear("tr", {}, [
        ...columnas.map((c) => UI.celda(c.titulo, [c.valor(cliente)])),
        UI.celda("Acciones", [crear("div", { clase: "celda-acciones" }, acciones)]),
      ]));
    }
  }

  function filtrosPerfil() {
    const salida = {};
    for (const control of document.querySelectorAll("[data-filtro]")) {
      const valor = control.value.trim();
      if (valor) salida[control.dataset.filtro] = valor;
    }
    return salida;
  }

  async function cargar() {
    const q = filtroQ.value.trim();
    let lista;
    if (q.length >= 2) {
      lista = await XPS.api(UI.consulta("/clientes/buscar", { q }));
      if (filtroActivo.value) lista = lista.filter((c) => String(c.activo) === filtroActivo.value);
    } else {
      lista = await XPS.api(UI.consulta("/clientes", { activo: filtroActivo.value, ...filtrosPerfil() }));
    }
    pintar(lista);
  }

  async function seguro(funcion) {
    try {
      await funcion();
    } catch (error) {
      XPS.mostrarError(alertas, error);
    }
  }

  // ---------- Ficha del cliente ----------

  function cambiarPestana(nombre) {
    for (const boton of dialogoCliente.querySelectorAll("[data-pestana]")) {
      const activa = boton.dataset.pestana === nombre;
      boton.classList.toggle("activa", activa);
      boton.setAttribute("aria-selected", String(activa));
    }
    for (const panel of dialogoCliente.querySelectorAll("[data-panel]")) {
      panel.hidden = panel.dataset.panel !== nombre;
    }
    document.getElementById("acciones-cliente").hidden = nombre === "correos";
    if (nombre === "correos") seguro(cargarCorreos);
  }

  function llenarCatalogos(raiz) {
    for (const select of raiz.querySelectorAll("select[data-catalogo]")) {
      const tipo = select.dataset.catalogo;
      UI.opciones(select, catalogos[tipo] || [], { valor: (v) => v.codigo, texto: (v) => v.nombre, todos: tipo === "ESTADO_COMERCIAL" ? null : "—" });
    }
  }

  function casillas(contenedor, nombre, items, marcados) {
    contenedor.replaceChildren(...items.map((item) => {
      const id = `${nombre}-${item.codigo}`;
      const casilla = crear("input", { atributos: { id, type: "checkbox", value: item.codigo, name: nombre } });
      casilla.checked = marcados.includes(item.codigo);
      return crear("label", { clase: "campo-check", atributos: { for: id } }, [casilla, ` ${item.nombre}`]);
    }));
  }

  async function pintarInteres(cliente) {
    const zona = document.getElementById("perfil-interes");
    zona.replaceChildren();
    if (!cliente) return;
    const interes = await XPS.api(`/clientes/${cliente.id}/interes`);
    const linea = (item, extra) => crear("li", { texto: `${extra || item.codigo} · ${item.veces} vez/veces · última ${fechaCorta(item.ultima) || "—"}` });
    zona.append(
      crear("h3", { texto: "Interés calculado (lo que cotizó)" }),
      interes.servicios.length || interes.rutas.length
        ? crear("ul", { clase: "lista-interes" }, [
          ...interes.servicios.map((s) => linea(s, `Servicio ${s.codigo}`)),
          ...interes.rutas.map((r) => linea(r, `Ruta ${r.codigo} (${r.puertos})`)),
        ])
        : crear("p", { clase: "ayuda", texto: "Todavía no tiene cotizaciones emitidas." }),
    );
  }

  function abrirCliente(cliente = null) {
    enEdicion = cliente;
    formCliente.reset();
    XPS.limpiarAlerta(alertasCliente);
    document.getElementById("titulo-cliente").textContent = cliente ? cliente.razon_social : "Nuevo cliente";
    UI.opciones(formCliente.elements.pais_id, paises.filter((p) => p.activo || (cliente && p.id === cliente.pais.id)), {
      valor: (p) => p.id,
      texto: (p) => `${p.iso2} · ${p.nombre}`,
    });
    UI.opciones(formCliente.elements.tipo_id, tipos.filter((t) => t.activo || (cliente && t.codigo === cliente.tipo_id)), {
      valor: (t) => t.codigo,
      texto: (t) => `${t.nombre} (${t.formato})`,
    });
    llenarCatalogos(formCliente);
    document.getElementById("campo-comercial").hidden = !asignaComercial;
    if (asignaComercial) {
      UI.opciones(formCliente.elements.comercial_asignado_id, comerciales, { valor: (u) => u.id, texto: (u) => `${u.nombre} (${u.rol.nombre})`, todos: "Elija un comercial…" });
    }
    const valores = cliente ? {
      razon_social: cliente.razon_social, tipo_id: cliente.tipo_id, ruc_o_id: cliente.ruc_o_id, pais_id: cliente.pais.id,
      ciudad: cliente.ciudad, telefono: cliente.telefono, direccion: cliente.direccion, notas: cliente.notas,
      comercial_asignado_id: cliente.comercial_asignado.id, nombre_comercial: cliente.nombre_comercial,
      tipo_cliente: cliente.tipo_cliente, estado_comercial: cliente.estado_comercial, sector: cliente.sector,
      volumen_estimado: cliente.volumen_estimado, frecuencia: cliente.frecuencia, origen_cliente: cliente.origen_cliente,
      rutas_interes: cliente.rutas_interes.join("|"), etiquetas: cliente.etiquetas.join("|"),
      fecha_consentimiento: cliente.fecha_consentimiento, medio_consentimiento: cliente.medio_consentimiento,
    } : {
      // Nuevo cliente: Ecuador por defecto, ACTIVO y con consentimiento de relación comercial previa.
      pais_id: (paises.find((p) => p.iso2 === "EC") || {}).id, estado_comercial: "ACTIVO",
      medio_consentimiento: "RELACION_COMERCIAL_PREVIA",
    };
    for (const [campo, valor] of Object.entries(valores)) {
      if (formCliente.elements[campo]) formCliente.elements[campo].value = valor === null || valor === undefined ? "" : String(valor);
    }
    formCliente.elements.acepta_promociones.checked = cliente ? cliente.acepta_promociones : true;
    casillas(document.getElementById("perfil-servicios"), "servicios_interes", servicios.map((s) => ({ codigo: s.codigo, nombre: s.nombre })), cliente ? cliente.servicios_interes : []);
    casillas(document.getElementById("perfil-cargas"), "tipos_carga", catalogos.TIPO_CARGA || [], cliente ? cliente.tipos_carga : []);
    for (const elemento of formCliente.elements) elemento.disabled = !puedeEditar && elemento.type !== "button";
    document.getElementById("guardar-cliente").hidden = !puedeEditar;
    document.getElementById("pestana-correos").hidden = !cliente;
    document.getElementById("vista-correo").hidden = true;
    cambiarPestana("datos");
    dialogoCliente.showModal();
    pintarInteres(cliente).catch((error) => XPS.mostrarError(alertasCliente, error));
  }

  const PERFIL_LISTAS = ["rutas_interes", "etiquetas"];

  function leerCliente() {
    const datos = {};
    for (const elemento of formCliente.elements) {
      if (!elemento.name || elemento.type === "checkbox" || elemento.closest("[hidden]:not([data-panel])")) continue;
      const valor = elemento.value.trim();
      datos[elemento.name] = valor === "" ? null : valor;
    }
    datos.pais_id = datos.pais_id ? Number(datos.pais_id) : null;
    if ("comercial_asignado_id" in datos) {
      datos.comercial_asignado_id = datos.comercial_asignado_id ? Number(datos.comercial_asignado_id) : null;
    }
    if (!asignaComercial) delete datos.comercial_asignado_id;
    for (const campo of PERFIL_LISTAS) datos[campo] = (datos[campo] || "").split("|").map((v) => v.trim()).filter(Boolean);
    datos.servicios_interes = [...formCliente.querySelectorAll("input[name=servicios_interes]:checked")].map((c) => c.value);
    datos.tipos_carga = [...formCliente.querySelectorAll("input[name=tipos_carga]:checked")].map((c) => c.value);
    datos.acepta_promociones = formCliente.elements.acepta_promociones.checked;
    return datos;
  }

  function originalCliente(campo) {
    if (campo === "pais_id") return enEdicion.pais.id;
    if (campo === "comercial_asignado_id") return enEdicion.comercial_asignado.id;
    return enEdicion[campo];
  }

  const igual = (a, b) => (Array.isArray(a) || Array.isArray(b) ? JSON.stringify(a || []) === JSON.stringify(b || []) : String(a ?? "") === String(b ?? ""));

  formCliente.addEventListener("submit", async (evento) => {
    evento.preventDefault();
    XPS.limpiarAlerta(alertasCliente);
    const datos = leerCliente();
    if (asignaComercial && !datos.comercial_asignado_id) {
      XPS.mostrarAlerta(alertasCliente, "error", "Elija el comercial asignado al cliente.");
      cambiarPestana("datos");
      return;
    }
    try {
      if (enEdicion) {
        const cambios = {};
        for (const [campo, valor] of Object.entries(datos)) {
          if (!igual(valor, originalCliente(campo))) cambios[campo] = valor;
        }
        if (Object.keys(cambios).length) {
          await XPS.api(`/clientes/${enEdicion.id}`, { metodo: "PATCH", cuerpo: cambios });
        }
      } else {
        await XPS.api("/clientes", { metodo: "POST", cuerpo: datos });
      }
      dialogoCliente.close();
      XPS.mostrarAlerta(alertas, "exito", "Cliente guardado.");
      await cargar();
    } catch (error) {
      XPS.mostrarError(alertasCliente, error);
    }
  });

  async function cambiarEstado(cliente) {
    XPS.limpiarAlerta(alertas);
    try {
      await XPS.api(`/clientes/${cliente.id}`, { metodo: "PATCH", cuerpo: { activo: !cliente.activo } });
      XPS.mostrarAlerta(alertas, "exito", cliente.activo ? "Cliente desactivado." : "Cliente activado.");
      await cargar();
    } catch (error) {
      XPS.mostrarError(alertas, error);
    }
  }

  // ---------- Correos del cliente (E1-B · 6-B) ----------

  const ENTREGA = { ENTREGADO: "badge-activo", ABIERTO: "badge-activo", CLIC: "badge-activo", REBOTE_HARD: "badge-critico",
    REBOTE_SOFT: "badge-alerta", SPAM: "badge-critico", BAJA: "badge-critico", SIN_EVENTOS: "badge-inactivo" };

  async function cargarCorreos() {
    if (!enEdicion) return;
    const lista = await XPS.api(UI.consulta(`/clientes/${enEdicion.id}/correos`, {
      tipo: document.getElementById("correos-tipo").value, estado: document.getElementById("correos-estado").value }));
    const tabla = document.getElementById("tabla-correos");
    tabla.replaceChildren(...(lista.length ? [] : [UI.filaVacia(8, "No hay correos enviados a este cliente con estos filtros.")]));
    for (const item of lista) {
      tabla.append(crear("tr", {}, [
        UI.celda("Fecha", [UI.texto(item.fecha ? new Date(item.fecha).toLocaleString("es-EC") : "—", "cifra")]),
        UI.celda("Contacto", [UI.texto(item.contacto ? `${item.contacto} · ${item.email}` : item.email)]),
        UI.celda("Tipo", [UI.texto(item.tipo_nombre)]),
        UI.celda("Asunto o campaña", [UI.texto(item.asunto)]),
        UI.celda("Plantilla", [UI.texto(item.plantilla)]),
        UI.celda("Envío", [UI.texto(item.estado_envio)]),
        UI.celda("Entrega", [crear("span", { clase: `badge badge-estado ${ENTREGA[item.estado_entrega] || ""}`, texto: item.estado_entrega_nombre })]),
        UI.celda("Acciones", [crear("div", { clase: "celda-acciones" }, [
          UI.boton("Ver correo", () => verCorreo(item)),
          crear("a", { clase: "btn btn-secundario btn-chico", texto: "Origen", atributos: { href: item.enlace.replace(/^\/app\//, "") } }),
        ])]),
      ]));
    }
  }

  async function verCorreo(item) {
    try {
      const previa = await XPS.api(`/clientes/${enEdicion.id}/correos/${item.tipo}/${item.id}`);
      document.getElementById("vista-correo-titulo").textContent = previa.asunto;
      document.getElementById("vista-correo-datos").textContent = `${item.tipo_nombre} · ${previa.plantilla || "sin plantilla"} · envío ${previa.estado_envio} · entrega ${previa.estado_entrega}`;
      document.getElementById("vista-correo-marco").srcdoc = previa.html;
      const variables = Object.entries(previa.variables || {});
      document.getElementById("vista-correo-variables").replaceChildren(...(variables.length
        ? variables.map(([nombre, valor]) => crear("tr", {}, [
          UI.celda("Variable", [UI.texto(nombre, "cifra")]), UI.celda("Valor", [UI.texto(valor || "(vacía)")])]))
        : [UI.filaVacia(2, "Este correo no guardó variables.")]));
      document.getElementById("vista-correo").hidden = false;
      document.getElementById("vista-correo").scrollIntoView({ behavior: "smooth" });
    } catch (error) {
      XPS.mostrarError(alertasCliente, error);
    }
  }

  // ---------- Contactos ----------

  async function pintarContactos() {
    const [contactos, avisos] = await Promise.all([
      XPS.api(`/clientes/${clienteContactos.id}/contactos`), XPS.api(`/clientes/${clienteContactos.id}/avisos`),
    ]);
    pintarAvisosCliente(avisos);
    const cuerpoContactos = document.getElementById("tabla-contactos");
    cuerpoContactos.replaceChildren(...(contactos.length ? [] : [UI.filaVacia(10, "Este cliente todavía no tiene contactos.")]));
    for (const contacto of contactos) {
      const celdas = [
        UI.celda("Nombre", [UI.texto(contacto.nombre)]),
        UI.celda("Cargo", [UI.texto(contacto.cargo)]),
        UI.celda("Área", [UI.texto(nombreCatalogo("AREA_CONTACTO", contacto.area))]),
        UI.celda("Email", [UI.texto(contacto.email, "cifra")]),
        UI.celda("Teléfono", [UI.texto(contacto.telefono, "cifra")]),
        UI.celda("Principal", [contacto.principal ? crear("span", { clase: "badge badge-rol", texto: "Principal" }) : UI.texto(null)]),
        UI.celda("Promociones", [UI.texto(contacto.recibe_promociones ? "Recibe" : "No recibe")]),
        UI.celda("Cotizaciones", [UI.texto(contacto.recibe_cotizaciones ? "Recibe" : "No recibe")]),
        UI.celda("Estado", [UI.badgeEstado(contacto.activo)]),
      ];
      if (puedeEditar) {
        const acciones = [UI.boton("Editar", () => editarContacto(contacto))];
        if (contacto.activo && !contacto.principal) {
          acciones.push(UI.boton("Marcar principal", () => actualizarContacto(contacto, { principal: true })));
        }
        acciones.push(UI.boton(contacto.activo ? "Desactivar" : "Activar", () => actualizarContacto(contacto, { activo: !contacto.activo })));
        celdas.push(UI.celda("Acciones", [crear("div", { clase: "celda-acciones" }, acciones)]));
      }
      cuerpoContactos.append(crear("tr", {}, celdas));
    }
  }

  function limpiarFormContacto() {
    contactoEnEdicion = null;
    formContacto.reset();
    llenarCatalogos(formContacto);
    formContacto.elements.recibe_promociones.checked = true;
    formContacto.elements.recibe_cotizaciones.checked = true;
    document.getElementById("titulo-form-contacto").textContent = "Agregar contacto";
  }

  // E3: "no enviar avisos" del cliente.
  function pintarAvisosCliente(avisos) {
    let bloque = document.getElementById("avisos-cliente");
    if (!bloque) {
      bloque = crear("div", { clase: "config-acciones", atributos: { id: "avisos-cliente" } });
      document.getElementById("titulo-contactos").after(bloque);
    }
    const texto = crear("p", { clase: "ayuda", texto: avisos.activos ? "El cliente recibe avisos automáticos de sus cotizaciones." : "El cliente no recibe avisos automáticos." });
    const hijos = [texto];
    if (puedeEditar) {
      hijos.push(UI.boton(avisos.activos ? "No enviar avisos al cliente" : "Enviar avisos al cliente",
        () => cambiarAvisos(`/clientes/${clienteContactos.id}/avisos`, { activos: !avisos.activos })));
    }
    bloque.replaceChildren(...hijos);
  }

  async function cambiarAvisos(ruta, cuerpo) {
    XPS.limpiarAlerta(alertasContactos);
    try {
      await XPS.api(ruta, { metodo: "PATCH", cuerpo });
      await pintarContactos();
    } catch (error) {
      XPS.mostrarError(alertasContactos, error);
    }
  }

  async function abrirContactos(cliente) {
    clienteContactos = cliente;
    XPS.limpiarAlerta(alertasContactos);
    limpiarFormContacto();
    document.getElementById("titulo-contactos").textContent = `Contactos · ${cliente.razon_social}`;
    document.getElementById("th-acciones-contacto").hidden = !puedeEditar;
    formContacto.hidden = !puedeEditar;
    try {
      await pintarContactos();
      dialogoContactos.showModal();
    } catch (error) {
      XPS.mostrarError(alertas, error);
    }
  }

  function editarContacto(contacto) {
    contactoEnEdicion = contacto;
    document.getElementById("titulo-form-contacto").textContent = `Editar contacto · ${contacto.nombre}`;
    for (const campo of ["nombre", "cargo", "email", "telefono", "area"]) {
      formContacto.elements[campo].value = contacto[campo] || "";
    }
    for (const campo of ["principal", "recibe_promociones", "recibe_cotizaciones"]) {
      formContacto.elements[campo].checked = contacto[campo];
    }
  }

  async function actualizarContacto(contacto, cambios) {
    XPS.limpiarAlerta(alertasContactos);
    try {
      const respuesta = await XPS.api(`/clientes/${clienteContactos.id}/contactos/${contacto.id}`, { metodo: "PATCH", cuerpo: cambios });
      const aviso = respuesta.cliente_tiene_principal ? "Contacto actualizado." : "Contacto actualizado. El cliente quedó sin contacto principal.";
      XPS.mostrarAlerta(alertasContactos, respuesta.cliente_tiene_principal ? "exito" : "aviso", aviso);
      await pintarContactos();
      await cargar();
    } catch (error) {
      XPS.mostrarError(alertasContactos, error);
    }
  }

  formContacto.addEventListener("submit", async (evento) => {
    evento.preventDefault();
    XPS.limpiarAlerta(alertasContactos);
    const datos = {};
    for (const campo of ["nombre", "cargo", "email", "telefono", "area"]) {
      const valor = formContacto.elements[campo].value.trim();
      datos[campo] = valor === "" ? null : valor;
    }
    for (const campo of ["principal", "recibe_promociones", "recibe_cotizaciones"]) {
      datos[campo] = formContacto.elements[campo].checked;
    }
    if (!datos.nombre) {
      XPS.mostrarAlerta(alertasContactos, "error", "El nombre del contacto es obligatorio.");
      return;
    }
    if (contactoEnEdicion) {
      const cambios = {};
      for (const [campo, valor] of Object.entries(datos)) {
        if ((valor ?? null) !== (contactoEnEdicion[campo] ?? null)) cambios[campo] = valor;
      }
      if (Object.keys(cambios).length) await actualizarContacto(contactoEnEdicion, cambios);
      limpiarFormContacto();
      return;
    }
    try {
      await XPS.api(`/clientes/${clienteContactos.id}/contactos`, { metodo: "POST", cuerpo: datos });
      XPS.mostrarAlerta(alertasContactos, "exito", "Contacto agregado.");
      limpiarFormContacto();
      await pintarContactos();
      await cargar();
    } catch (error) {
      XPS.mostrarError(alertasContactos, error);
    }
  });
  document.getElementById("btn-cancelar-contacto").addEventListener("click", limpiarFormContacto);

  // ---------- Exportar ----------

  async function exportar() {
    XPS.limpiarAlerta(alertas);
    try {
      await Importacion.descargar(UI.consulta("/clientes/exportar.xlsx", { activo: filtroActivo.value, ...filtrosPerfil() }));
    } catch (error) {
      XPS.mostrarError(alertas, error);
    }
  }

  // ---------- Inicio ----------

  const yo = await iniciarLayout("clientes.html");
  if (!yo || !UI.exigirAlguno(yo, ["cliente.ver"], alertas)) {
    return;
  }
  puedeEditar = UI.tieneAlguno(yo, ["cliente.editar"]);
  asignaComercial = puedeEditar && UI.tieneAlguno(yo, ["cotizacion.ver_todas"]);
  document.getElementById("nota-lectura").hidden = puedeEditar;
  if (!UI.tieneAlguno(yo, ["cotizacion.ver_todas"])) {
    document.getElementById("subtitulo").textContent = "Sus clientes y contactos";
  }
  UI.prepararDialogo(dialogoCliente);
  UI.prepararDialogo(dialogoContactos);
  for (const boton of dialogoCliente.querySelectorAll("[data-pestana]")) {
    boton.addEventListener("click", () => cambiarPestana(boton.dataset.pestana));
  }
  for (const id of ["correos-tipo", "correos-estado"]) {
    document.getElementById(id).addEventListener("change", () => seguro(cargarCorreos));
  }
  botonNuevo.addEventListener("click", () => abrirCliente());
  document.getElementById("btn-importar").addEventListener("click", () => Importacion.abrir({ alTerminar: () => seguro(cargar) }));
  document.getElementById("btn-exportar").addEventListener("click", exportar);
  filtroActivo.addEventListener("change", () => seguro(cargar));
  let espera = null;
  const recargar = () => {
    window.clearTimeout(espera);
    espera = window.setTimeout(() => seguro(cargar), 300);
  };
  filtroQ.addEventListener("input", recargar);
  for (const control of document.querySelectorAll("[data-filtro]")) {
    control.addEventListener(control.tagName === "SELECT" ? "change" : "input", recargar);
  }

  try {
    const [listaTipos, listaCatalogos, listaServicios, preferencia] = await Promise.all([
      XPS.api("/tipos-identificacion"), XPS.api("/catalogos-perfil?activo=true"), XPS.api("/servicios?activo=true"),
      XPS.api("/preferencias/clientes.columnas"),
    ]);
    tipos = listaTipos;
    servicios = listaServicios;
    catalogos = {};
    for (const item of listaCatalogos) (catalogos[item.tipo] = catalogos[item.tipo] || []).push(item);
    if (Array.isArray(preferencia.valor) && preferencia.valor.length) visibles = preferencia.valor.filter((c) => COLUMNAS.some((col) => col.clave === c));
    for (const [id, tipo] of [["filtro-estado", "ESTADO_COMERCIAL"], ["filtro-tipo", "TIPO_CLIENTE"], ["filtro-sector", "SECTOR"]]) {
      UI.opciones(document.getElementById(id), catalogos[tipo] || [], { valor: (v) => v.codigo, texto: (v) => v.nombre, todos: "Todos" });
    }
    UI.opciones(document.getElementById("filtro-servicio"), servicios, { valor: (s) => s.codigo, texto: (s) => s.nombre, todos: "Todos" });
    pintarSelectorColumnas();
    if (puedeEditar) {
      paises = await XPS.api("/paises");
    }
    if (asignaComercial) {
      // Candidatos: usuarios activos cuyo rol puede crear cotizaciones (según el seed de la BD).
      const [roles, usuarios] = await Promise.all([XPS.api("/roles"), XPS.api("/usuarios?activo=true")]);
      const rolesQueCotizan = new Set(roles.filter((r) => r.permisos.includes("cotizacion.crear")).map((r) => r.codigo));
      comerciales = usuarios.filter((u) => rolesQueCotizan.has(u.rol.codigo));
    }
    await cargar();
    herramientas.hidden = false;
    botonNuevo.hidden = !puedeEditar;
    document.getElementById("btn-importar").hidden = !puedeEditar;
    document.getElementById("btn-exportar").hidden = false;
  } catch (error) {
    XPS.mostrarError(alertas, error);
  }
})();
