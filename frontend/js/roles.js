/* E2 Roles y permisos (usuario.admin): crear roles, editar nombre, descripción, permisos y estado.
 * El backend protege al Administrador y sube token_version de los usuarios del rol cuando cambian sus permisos.
 */
"use strict";

(async () => {
  const { crear } = XPS;
  const alertas = document.getElementById("alertas");
  const botonNuevo = document.getElementById("btn-nuevo");
  const dialogo = document.getElementById("dialogo-rol");
  const form = document.getElementById("form-rol");
  const alertasDialogo = document.getElementById("alertas-rol");
  const listaPermisos = document.getElementById("lista-permisos");

  let roles = [];
  let permisos = [];
  let enEdicion = null;

  const modulo = (codigo) => codigo.split(".")[0];

  function pintarRoles() {
    const cuerpo = document.getElementById("tabla-roles");
    cuerpo.replaceChildren();
    for (const rol of roles) {
      const nombre = crear("div", {}, [UI.texto(rol.nombre)]);
      nombre.append(crear("div", { clase: "ayuda cifra", texto: rol.codigo }));
      if (rol.protegido) nombre.append(crear("span", { clase: "badge badge-estado badge-alerta", texto: "Protegido" }));
      cuerpo.append(crear("tr", {}, [
        UI.celda("Rol", [nombre]),
        UI.celda("Descripción", [UI.texto(rol.descripcion || "—")]),
        UI.celda("Usuarios activos", [UI.texto(rol.usuarios_activos, "cifra")]),
        UI.celda("Permisos", [UI.texto(rol.permisos.length, "cifra")]),
        UI.celda("Estado", [UI.badgeEstado(rol.activo)]),
        UI.celda("Acciones", [crear("div", { clase: "celda-acciones" }, [
          UI.boton("Editar", () => abrir(rol)),
          ...(rol.protegido ? [] : [UI.boton(rol.activo ? "Desactivar" : "Activar", () => cambiarEstado(rol))]),
        ])]),
      ]));
    }
  }

  function pintarMatriz() {
    const visibles = roles.filter((rol) => rol.activo);
    document.getElementById("cabecera-matriz").replaceChildren(crear("tr", {}, [
      crear("th", { texto: "Permiso" }),
      ...visibles.map((rol) => crear("th", { texto: rol.nombre })),
    ]));
    const cuerpo = document.getElementById("cuerpo-matriz");
    cuerpo.replaceChildren();
    let anterior = null;
    for (const permiso of permisos) {
      if (modulo(permiso.codigo) !== anterior) {
        anterior = modulo(permiso.codigo);
        cuerpo.append(crear("tr", { clase: "fila-grupo" }, [crear("td", { texto: anterior, atributos: { colspan: visibles.length + 1 } })]));
      }
      const descripcion = crear("div", {}, [UI.texto(permiso.descripcion)]);
      descripcion.append(crear("div", { clase: "ayuda cifra", texto: permiso.codigo }));
      cuerpo.append(crear("tr", {}, [
        crear("td", {}, [descripcion]),
        ...visibles.map((rol) => {
          const tiene = rol.permisos.includes(permiso.codigo);
          return crear("td", { clase: tiene ? "marca-si" : "marca-no", texto: tiene ? "✓" : "—", atributos: { "aria-label": tiene ? "Sí" : "No" } });
        }),
      ]));
    }
  }

  async function cargar() {
    [roles, permisos] = await Promise.all([XPS.api("/roles"), XPS.api("/roles/permisos")]);
    pintarRoles();
    pintarMatriz();
  }

  async function cambiarEstado(rol) {
    XPS.limpiarAlerta(alertas);
    try {
      await XPS.api(`/roles/${rol.id}`, { metodo: "PATCH", cuerpo: { activo: !rol.activo } });
      XPS.mostrarAlerta(alertas, "exito", rol.activo ? "Rol desactivado." : "Rol activado.");
      await cargar();
    } catch (error) {
      XPS.mostrarError(alertas, error);
    }
  }

  function abrir(rol = null) {
    enEdicion = rol;
    form.reset();
    XPS.limpiarAlerta(alertasDialogo);
    document.getElementById("titulo-rol").textContent = rol ? `Editar ${rol.nombre}` : "Nuevo rol";
    form.elements.codigo.disabled = Boolean(rol);
    document.getElementById("aviso-sesiones").hidden = !rol;
    if (rol) {
      form.elements.codigo.value = rol.codigo;
      form.elements.nombre.value = rol.nombre;
      form.elements.descripcion.value = rol.descripcion || "";
    }
    listaPermisos.replaceChildren();
    let anterior = null;
    for (const permiso of permisos) {
      if (modulo(permiso.codigo) !== anterior) {
        anterior = modulo(permiso.codigo);
        listaPermisos.append(crear("p", { clase: "nav-grupo", texto: anterior }));
      }
      const id = `permiso-${permiso.codigo.replaceAll(".", "-")}`;
      const casilla = crear("input", { atributos: { id, type: "checkbox", value: permiso.codigo } });
      casilla.checked = Boolean(rol && rol.permisos.includes(permiso.codigo));
      if (rol && rol.protegido && permiso.codigo === "usuario.admin") casilla.disabled = true;
      listaPermisos.append(crear("label", { clase: "campo-check", atributos: { for: id } }, [
        casilla, `${permiso.descripcion} `, crear("span", { clase: "ayuda cifra", texto: permiso.codigo }),
      ]));
    }
    dialogo.showModal();
  }

  form.addEventListener("submit", async (evento) => {
    evento.preventDefault();
    XPS.limpiarAlerta(alertasDialogo);
    const elegidos = [...listaPermisos.querySelectorAll("input[type=checkbox]")].filter((c) => c.checked).map((c) => c.value);
    const datos = {
      nombre: form.elements.nombre.value.trim(),
      descripcion: form.elements.descripcion.value.trim() || null,
      permisos: elegidos,
    };
    if (!datos.nombre || (!enEdicion && !form.elements.codigo.value.trim())) {
      XPS.mostrarAlerta(alertasDialogo, "error", "El código y el nombre son obligatorios.");
      return;
    }
    try {
      if (enEdicion) {
        const cambios = {};
        if (datos.nombre !== enEdicion.nombre) cambios.nombre = datos.nombre;
        if (datos.descripcion !== (enEdicion.descripcion || null)) cambios.descripcion = datos.descripcion;
        if ([...elegidos].sort().join() !== [...enEdicion.permisos].sort().join()) cambios.permisos = elegidos;
        if (Object.keys(cambios).length) {
          await XPS.api(`/roles/${enEdicion.id}`, { metodo: "PATCH", cuerpo: cambios });
        }
      } else {
        await XPS.api("/roles", { metodo: "POST", cuerpo: { codigo: form.elements.codigo.value.trim().toLowerCase(), ...datos } });
      }
      dialogo.close();
      XPS.mostrarAlerta(alertas, "exito", "Rol guardado.");
      await cargar();
    } catch (error) {
      XPS.mostrarError(alertasDialogo, error);
    }
  });

  const yo = await iniciarLayout("roles.html");
  if (!yo || !UI.exigirAlguno(yo, ["usuario.admin"], alertas)) {
    return;
  }
  UI.prepararDialogo(dialogo);
  botonNuevo.addEventListener("click", () => abrir());
  try {
    await cargar();
    document.getElementById("bloque-roles").hidden = false;
    document.getElementById("bloque-matriz").hidden = false;
    botonNuevo.hidden = false;
  } catch (error) {
    XPS.mostrarError(alertas, error);
  }
})();
