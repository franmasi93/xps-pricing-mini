/* E2 Tipos de identificación: config.editar (admin) crea y edita; el código no cambia. La regla la valida el backend. */
"use strict";

(async () => {
  const { crear } = XPS;
  const alertas = document.getElementById("alertas");
  const botonNuevo = document.getElementById("btn-nuevo");
  const cuerpo = document.getElementById("tabla-tipos");
  const dialogo = document.getElementById("dialogo-tipo");
  const form = document.getElementById("form-tipo");
  const alertasDialogo = document.getElementById("alertas-tipo");
  const CAMPOS = ["nombre", "regex", "formato"];
  let enEdicion = null;

  async function cargar() {
    const lista = await XPS.api("/tipos-identificacion");
    cuerpo.replaceChildren(...(lista.length ? [] : [UI.filaVacia(7, "No hay tipos de identificación.")]));
    for (const tipo of lista) {
      cuerpo.append(crear("tr", {}, [
        UI.celda("Código", [UI.texto(tipo.codigo, "cifra")]),
        UI.celda("Nombre", [UI.texto(tipo.nombre)]),
        UI.celda("Regla", [UI.texto(tipo.regex, "cifra")]),
        UI.celda("Formato que se muestra", [UI.texto(tipo.formato)]),
        UI.celda("Orden", [UI.texto(tipo.orden, "cifra")]),
        UI.celda("Estado", [UI.badgeEstado(tipo.activo)]),
        UI.celda("Acciones", [crear("div", { clase: "celda-acciones" }, [
          UI.boton("Editar", () => abrir(tipo)),
          UI.boton(tipo.activo ? "Desactivar" : "Activar", () => cambiarEstado(tipo)),
        ])]),
      ]));
    }
  }

  async function cambiarEstado(tipo) {
    XPS.limpiarAlerta(alertas);
    try {
      await XPS.api(`/tipos-identificacion/${tipo.id}`, { metodo: "PATCH", cuerpo: { activo: !tipo.activo } });
      XPS.mostrarAlerta(alertas, "exito", tipo.activo ? "Tipo desactivado." : "Tipo activado.");
      await cargar();
    } catch (error) {
      XPS.mostrarError(alertas, error);
    }
  }

  function abrir(tipo = null) {
    enEdicion = tipo;
    form.reset();
    XPS.limpiarAlerta(alertasDialogo);
    document.getElementById("titulo-tipo").textContent = tipo ? `Editar ${tipo.nombre}` : "Nuevo tipo de identificación";
    form.elements.codigo.disabled = Boolean(tipo);
    if (tipo) {
      form.elements.codigo.value = tipo.codigo;
      for (const campo of CAMPOS) form.elements[campo].value = tipo[campo];
      form.elements.orden.value = tipo.orden;
    }
    dialogo.showModal();
  }

  form.addEventListener("submit", async (evento) => {
    evento.preventDefault();
    XPS.limpiarAlerta(alertasDialogo);
    const datos = Object.fromEntries(CAMPOS.map((campo) => [campo, form.elements[campo].value.trim()]));
    datos.orden = Number(form.elements.orden.value || 0);
    if (CAMPOS.some((campo) => !datos[campo]) || (!enEdicion && !form.elements.codigo.value.trim())) {
      XPS.mostrarAlerta(alertasDialogo, "error", "Código, nombre, regla y formato son obligatorios.");
      return;
    }
    try {
      if (enEdicion) {
        const cambios = Object.fromEntries(Object.entries(datos).filter(([campo, valor]) => valor !== enEdicion[campo]));
        if (Object.keys(cambios).length) await XPS.api(`/tipos-identificacion/${enEdicion.id}`, { metodo: "PATCH", cuerpo: cambios });
      } else {
        await XPS.api("/tipos-identificacion", { metodo: "POST", cuerpo: { codigo: form.elements.codigo.value.trim().toUpperCase(), ...datos } });
      }
      dialogo.close();
      XPS.mostrarAlerta(alertas, "exito", "Tipo de identificación guardado.");
      await cargar();
    } catch (error) {
      XPS.mostrarError(alertasDialogo, error);
    }
  });

  const yo = await iniciarLayout("tipos-identificacion.html");
  if (!yo || !UI.exigirAlguno(yo, ["config.editar"], alertas)) {
    return;
  }
  UI.prepararDialogo(dialogo);
  botonNuevo.addEventListener("click", () => abrir());
  try {
    await cargar();
    document.getElementById("herramientas").hidden = false;
    botonNuevo.hidden = false;
  } catch (error) {
    XPS.mostrarError(alertas, error);
  }
})();
