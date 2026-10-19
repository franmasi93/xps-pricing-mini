/* Administración de usuarios (requiere usuario.admin; el backend lo exige igual).
 * Sin botón de borrar: la baja es activo = false.
 */
"use strict";

(async () => {
  const { crear } = XPS;
  const alertas = document.getElementById("alertas");
  const herramientas = document.getElementById("herramientas");
  const botonNuevo = document.getElementById("btn-nuevo");
  const cuerpoTabla = document.getElementById("tabla-cuerpo");
  const filtroRol = document.getElementById("filtro-rol");
  const filtroEstado = document.getElementById("filtro-estado");

  const dialogoCrear = document.getElementById("dialogo-crear");
  const formCrear = document.getElementById("form-crear");
  const alertasCrear = document.getElementById("alertas-crear");

  const dialogoEditar = document.getElementById("dialogo-editar");
  const formEditar = document.getElementById("form-editar");
  const alertasEditar = document.getElementById("alertas-editar");
  const bloqueoEditar = document.getElementById("editar-bloqueo");

  const dialogoRestablecer = document.getElementById("dialogo-restablecer");
  const formRestablecer = document.getElementById("form-restablecer");
  const alertasRestablecer = document.getElementById("alertas-restablecer");

  let yo = null;
  let roles = [];
  let adminsActivos = 0;
  let usuarioEnEdicion = null;
  let usuarioARestablecer = null;

  // ---------- Utilidades ----------

  function llenarRoles(select, conOpcionTodos, rolActual = null) {
    select.replaceChildren();
    if (conOpcionTodos) {
      select.append(crear("option", { texto: "Todos", atributos: { value: "" } }));
    }
    // E2: un rol desactivado no se asigna (se sigue viendo en el filtro y en el usuario que ya lo tiene).
    for (const rol of roles.filter((r) => conOpcionTodos || r.activo || r.codigo === rolActual)) {
      select.append(crear("option", { texto: rol.activo ? rol.nombre : `${rol.nombre} (inactivo)`, atributos: { value: rol.codigo } }));
    }
  }

  function celda(etiqueta, hijos) {
    return crear("td", { atributos: { "data-etiqueta": etiqueta } }, hijos);
  }

  function boton(texto, alHacerClic) {
    const elemento = crear("button", { clase: "btn btn-secundario btn-chico", texto, atributos: { type: "button" } });
    elemento.addEventListener("click", alHacerClic);
    return elemento;
  }

  /** Motivo por el que el backend rechazaría desactivar o quitar el rol admin; null si no aplica. */
  function motivoBloqueoAdmin(usuario) {
    if (usuario.rol.codigo !== "admin" || !usuario.activo) {
      return null;
    }
    if (usuario.id === yo.id) {
      return "No puede desactivarse ni quitarse el rol de administrador a sí mismo.";
    }
    if (adminsActivos <= 1) {
      return "Es el único administrador activo: debe quedar al menos uno.";
    }
    return null;
  }

  // ---------- Carga y tabla ----------

  async function contarAdminsActivos() {
    const lista = await XPS.api("/usuarios?rol=admin&activo=true");
    adminsActivos = lista.length;
  }

  async function cargarUsuarios() {
    const parametros = new URLSearchParams();
    if (filtroRol.value) {
      parametros.set("rol", filtroRol.value);
    }
    if (filtroEstado.value) {
      parametros.set("activo", filtroEstado.value);
    }
    const consulta = parametros.toString();
    const lista = await XPS.api(`/usuarios${consulta ? `?${consulta}` : ""}`);
    pintarTabla(lista);
  }

  async function recargar() {
    await Promise.all([contarAdminsActivos(), cargarUsuarios()]);
  }

  function pintarTabla(lista) {
    cuerpoTabla.replaceChildren();
    if (lista.length === 0) {
      cuerpoTabla.append(
        crear("tr", {}, [crear("td", { clase: "tabla-vacia", texto: "No hay usuarios con estos filtros.", atributos: { colspan: 6 } })])
      );
      return;
    }
    for (const usuario of lista) {
      const estado = usuario.activo
        ? crear("span", { clase: "badge badge-estado badge-activo", texto: "Activo" })
        : crear("span", { clase: "badge badge-estado badge-inactivo", texto: "Inactivo" });
      const acciones = crear("div", { clase: "celda-acciones" }, [
        boton("Editar", () => abrirEditar(usuario)),
        boton("Restablecer contraseña", () => abrirRestablecer(usuario)),
      ]);
      cuerpoTabla.append(
        crear("tr", {}, [
          celda("Nombre", [crear("span", { texto: usuario.nombre })]),
          celda("Email", [crear("span", { clase: "cifra", texto: usuario.email })]),
          celda("Rol", [crear("span", { clase: "badge badge-rol", texto: usuario.rol.nombre })]),
          celda("Estado", [estado]),
          celda("Último acceso", [crear("span", { clase: "cifra", texto: XPS.formatearFecha(usuario.ultimo_login) })]),
          celda("Acciones", [acciones]),
        ])
      );
    }
  }

  // ---------- Diálogos ----------

  function prepararDialogo(dialogo) {
    for (const cerrar of dialogo.querySelectorAll("[data-cerrar]")) {
      cerrar.addEventListener("click", () => dialogo.close());
    }
    for (const politica of dialogo.querySelectorAll("[data-politica]")) {
      politica.textContent = XPS.POLITICA_PASSWORD;
    }
  }

  function abrirCrear() {
    formCrear.reset();
    XPS.limpiarAlerta(alertasCrear);
    llenarRoles(formCrear.elements.rol, false);
    dialogoCrear.showModal();
    formCrear.elements.email.focus();
  }

  function abrirEditar(usuario) {
    usuarioEnEdicion = usuario;
    XPS.limpiarAlerta(alertasEditar);
    document.getElementById("editar-email").textContent = usuario.email;
    llenarRoles(formEditar.elements.rol, false, usuario.rol.codigo);
    formEditar.elements.nombre.value = usuario.nombre;
    formEditar.elements.rol.value = usuario.rol.codigo;
    formEditar.elements.activo.checked = usuario.activo;

    const motivo = motivoBloqueoAdmin(usuario);
    formEditar.elements.rol.disabled = motivo !== null;
    formEditar.elements.activo.disabled = motivo !== null;
    bloqueoEditar.textContent = motivo || "";
    bloqueoEditar.hidden = motivo === null;
    dialogoEditar.showModal();
  }

  function abrirRestablecer(usuario) {
    usuarioARestablecer = usuario;
    formRestablecer.reset();
    XPS.limpiarAlerta(alertasRestablecer);
    document.getElementById("restablecer-email").textContent = usuario.email;
    dialogoRestablecer.showModal();
  }

  async function enviarCrear(evento) {
    evento.preventDefault();
    XPS.limpiarAlerta(alertasCrear);
    const datos = {
      email: formCrear.elements.email.value.trim(),
      nombre: formCrear.elements.nombre.value.trim(),
      rol_codigo: formCrear.elements.rol.value,
      password_temporal: formCrear.elements.password.value,
    };
    if (!datos.email || !datos.nombre || !datos.rol_codigo || !datos.password_temporal) {
      XPS.mostrarAlerta(alertasCrear, "error", "Complete todos los campos.");
      return;
    }
    if (!XPS.passwordCumplePolitica(datos.password_temporal)) {
      XPS.mostrarAlerta(alertasCrear, "error", `La contraseña temporal no cumple la política: ${XPS.POLITICA_PASSWORD}`);
      return;
    }
    try {
      const creado = await XPS.api("/usuarios", { metodo: "POST", cuerpo: datos });
      dialogoCrear.close();
      XPS.mostrarAlerta(alertas, "exito", `Usuario ${creado.email} creado. Deberá cambiar la contraseña temporal al ingresar.`);
      await recargar();
    } catch (error) {
      XPS.mostrarError(alertasCrear, error);
    }
  }

  async function enviarEditar(evento) {
    evento.preventDefault();
    XPS.limpiarAlerta(alertasEditar);
    const usuario = usuarioEnEdicion;
    const nombre = formEditar.elements.nombre.value.trim();
    if (!nombre) {
      XPS.mostrarAlerta(alertasEditar, "error", "El nombre no puede estar vacío.");
      return;
    }
    const cambios = {};
    if (nombre !== usuario.nombre) {
      cambios.nombre = nombre;
    }
    if (!formEditar.elements.rol.disabled && formEditar.elements.rol.value !== usuario.rol.codigo) {
      cambios.rol_codigo = formEditar.elements.rol.value;
    }
    if (!formEditar.elements.activo.disabled && formEditar.elements.activo.checked !== usuario.activo) {
      cambios.activo = formEditar.elements.activo.checked;
    }
    if (Object.keys(cambios).length === 0) {
      dialogoEditar.close();
      XPS.mostrarAlerta(alertas, "info", "No había cambios que guardar.");
      return;
    }
    try {
      await XPS.api(`/usuarios/${usuario.id}`, { metodo: "PATCH", cuerpo: cambios });
      dialogoEditar.close();
      XPS.mostrarAlerta(alertas, "exito", `Usuario ${usuario.email} actualizado.`);
      await recargar();
    } catch (error) {
      XPS.mostrarError(alertasEditar, error);
    }
  }

  async function enviarRestablecer(evento) {
    evento.preventDefault();
    XPS.limpiarAlerta(alertasRestablecer);
    const password = formRestablecer.elements.password.value;
    if (!XPS.passwordCumplePolitica(password)) {
      XPS.mostrarAlerta(alertasRestablecer, "error", `La contraseña temporal no cumple la política: ${XPS.POLITICA_PASSWORD}`);
      return;
    }
    try {
      await XPS.api(`/usuarios/${usuarioARestablecer.id}/restablecer-password`, {
        metodo: "POST",
        cuerpo: { password_temporal: password },
      });
      dialogoRestablecer.close();
      XPS.mostrarAlerta(alertas, "exito", `Contraseña de ${usuarioARestablecer.email} restablecida.`);
      await recargar();
    } catch (error) {
      XPS.mostrarError(alertasRestablecer, error);
    }
  }

  // ---------- Inicio ----------

  yo = await iniciarLayout("usuarios.html");
  if (!yo) {
    return;
  }

  prepararDialogo(dialogoCrear);
  prepararDialogo(dialogoEditar);
  prepararDialogo(dialogoRestablecer);
  formCrear.addEventListener("submit", enviarCrear);
  formEditar.addEventListener("submit", enviarEditar);
  formRestablecer.addEventListener("submit", enviarRestablecer);
  botonNuevo.addEventListener("click", abrirCrear);

  const alFiltrar = async () => {
    XPS.limpiarAlerta(alertas);
    try {
      await cargarUsuarios();
    } catch (error) {
      XPS.mostrarError(alertas, error);
    }
  };
  filtroRol.addEventListener("change", alFiltrar);
  filtroEstado.addEventListener("change", alFiltrar);

  // Sin usuario.admin el backend responde 403 y se muestra su mensaje (la pantalla no se rompe).
  try {
    roles = await XPS.api("/roles");
    llenarRoles(filtroRol, true);
    await recargar();
    herramientas.hidden = false;
    botonNuevo.hidden = false;
  } catch (error) {
    XPS.mostrarError(alertas, error);
  }
})();
