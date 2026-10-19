/* P8 Clientes y contactos. cliente.ver lee (el comercial solo los suyos: lo filtra el backend);
 * cliente.editar escribe. Quien tiene cotizacion.ver_todas (admin) elige el comercial asignado.
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
  let enEdicion = null;
  let clienteContactos = null;
  let contactoEnEdicion = null;

  // ---------- Listado ----------

  function pintar(lista) {
    cuerpo.replaceChildren(...(lista.length ? [] : [UI.filaVacia(7, "No hay clientes con estos filtros.")]));
    for (const cliente of lista) {
      const acciones = [UI.boton("Contactos", () => abrirContactos(cliente))];
      if (puedeEditar) {
        acciones.push(
          UI.boton("Editar", () => abrirCliente(cliente)),
          UI.boton(cliente.activo ? "Desactivar" : "Activar", () => cambiarEstado(cliente))
        );
      }
      const principal = cliente.contacto_principal;
      cuerpo.append(
        crear("tr", {}, [
          UI.celda("Razón social", [UI.texto(cliente.razon_social)]),
          UI.celda("Identificación", [UI.texto(`${nombreTipo(cliente.tipo_id)} ${cliente.ruc_o_id}`, "cifra")]),
          UI.celda("País", [UI.texto(cliente.pais.nombre)]),
          UI.celda("Comercial", [UI.texto(cliente.comercial_asignado.nombre)]),
          UI.celda("Contacto principal", [UI.texto(principal ? (principal.email ? `${principal.nombre} · ${principal.email}` : principal.nombre) : null)]),
          UI.celda("Estado", [UI.badgeEstado(cliente.activo)]),
          UI.celda("Acciones", [crear("div", { clase: "celda-acciones" }, acciones)]),
        ])
      );
    }
  }

  async function cargar() {
    const q = filtroQ.value.trim();
    let lista;
    if (q.length >= 2) {
      lista = await XPS.api(UI.consulta("/clientes/buscar", { q }));
      if (filtroActivo.value) lista = lista.filter((c) => String(c.activo) === filtroActivo.value);
    } else {
      lista = await XPS.api(UI.consulta("/clientes", { activo: filtroActivo.value }));
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

  // ---------- Cliente ----------

  function abrirCliente(cliente = null) {
    enEdicion = cliente;
    formCliente.reset();
    XPS.limpiarAlerta(alertasCliente);
    document.getElementById("titulo-cliente").textContent = cliente ? "Editar cliente" : "Nuevo cliente";
    UI.opciones(formCliente.elements.pais_id, paises.filter((p) => p.activo || (cliente && p.id === cliente.pais.id)), {
      valor: (p) => p.id,
      texto: (p) => `${p.iso2} · ${p.nombre}`,
    });
    UI.opciones(formCliente.elements.tipo_id, tipos.filter((t) => t.activo || (cliente && t.codigo === cliente.tipo_id)), {
      valor: (t) => t.codigo,
      texto: (t) => `${t.nombre} (${t.formato})`,
    });
    document.getElementById("campo-comercial").hidden = !asignaComercial;
    if (asignaComercial) {
      UI.opciones(formCliente.elements.comercial_asignado_id, comerciales, { valor: (u) => u.id, texto: (u) => `${u.nombre} (${u.rol.nombre})`, todos: "Elija un comercial…" });
    }
    if (cliente) {
      const valores = {
        razon_social: cliente.razon_social,
        tipo_id: cliente.tipo_id,
        ruc_o_id: cliente.ruc_o_id,
        pais_id: cliente.pais.id,
        ciudad: cliente.ciudad,
        telefono: cliente.telefono,
        direccion: cliente.direccion,
        notas: cliente.notas,
        comercial_asignado_id: cliente.comercial_asignado.id,
      };
      for (const [campo, valor] of Object.entries(valores)) {
        formCliente.elements[campo].value = valor === null || valor === undefined ? "" : String(valor);
      }
    }
    dialogoCliente.showModal();
  }

  function leerCliente() {
    const datos = {};
    for (const elemento of formCliente.elements) {
      if (!elemento.name || elemento.closest("[hidden]")) continue;
      const valor = elemento.value.trim();
      datos[elemento.name] = valor === "" ? null : valor;
    }
    datos.pais_id = datos.pais_id ? Number(datos.pais_id) : null;
    if ("comercial_asignado_id" in datos) {
      datos.comercial_asignado_id = datos.comercial_asignado_id ? Number(datos.comercial_asignado_id) : null;
    }
    return datos;
  }

  function originalCliente(campo) {
    if (campo === "pais_id") return enEdicion.pais.id;
    if (campo === "comercial_asignado_id") return enEdicion.comercial_asignado.id;
    return enEdicion[campo];
  }

  formCliente.addEventListener("submit", async (evento) => {
    evento.preventDefault();
    XPS.limpiarAlerta(alertasCliente);
    const datos = leerCliente();
    if (asignaComercial && !datos.comercial_asignado_id) {
      XPS.mostrarAlerta(alertasCliente, "error", "Elija el comercial asignado al cliente.");
      return;
    }
    try {
      if (enEdicion) {
        const cambios = {};
        for (const [campo, valor] of Object.entries(datos)) {
          if (String(valor ?? "") !== String(originalCliente(campo) ?? "")) cambios[campo] = valor;
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

  // ---------- Contactos ----------

  async function pintarContactos() {
    const contactos = await XPS.api(`/clientes/${clienteContactos.id}/contactos`);
    const cuerpoContactos = document.getElementById("tabla-contactos");
    cuerpoContactos.replaceChildren(...(contactos.length ? [] : [UI.filaVacia(7, "Este cliente todavía no tiene contactos.")]));
    for (const contacto of contactos) {
      const celdas = [
        UI.celda("Nombre", [UI.texto(contacto.nombre)]),
        UI.celda("Cargo", [UI.texto(contacto.cargo)]),
        UI.celda("Email", [UI.texto(contacto.email, "cifra")]),
        UI.celda("Teléfono", [UI.texto(contacto.telefono, "cifra")]),
        UI.celda("Principal", [contacto.principal ? crear("span", { clase: "badge badge-rol", texto: "Principal" }) : UI.texto(null)]),
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
    document.getElementById("titulo-form-contacto").textContent = "Agregar contacto";
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
    for (const campo of ["nombre", "cargo", "email", "telefono"]) {
      formContacto.elements[campo].value = contacto[campo] || "";
    }
    formContacto.elements.principal.checked = contacto.principal;
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
    for (const campo of ["nombre", "cargo", "email", "telefono"]) {
      const valor = formContacto.elements[campo].value.trim();
      datos[campo] = valor === "" ? null : valor;
    }
    datos.principal = formContacto.elements.principal.checked;
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
  botonNuevo.addEventListener("click", () => abrirCliente());
  filtroActivo.addEventListener("change", () => seguro(cargar));
  let espera = null;
  filtroQ.addEventListener("input", () => {
    window.clearTimeout(espera);
    espera = window.setTimeout(() => seguro(cargar), 300);
  });

  try {
    tipos = await XPS.api("/tipos-identificacion");
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
  } catch (error) {
    XPS.mostrarError(alertas, error);
  }
})();
