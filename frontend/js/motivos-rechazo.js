/* E2 Motivos de rechazo: config.editar (admin) crea y edita; el código no cambia. */
"use strict";

(async () => {
  const { crear } = XPS;
  const alertas = document.getElementById("alertas");
  const botonNuevo = document.getElementById("btn-nuevo");
  const cuerpo = document.getElementById("tabla-motivos");
  const dialogo = document.getElementById("dialogo-motivo");
  const form = document.getElementById("form-motivo");
  const alertasDialogo = document.getElementById("alertas-motivo");
  let enEdicion = null;

  async function cargar() {
    const lista = await XPS.api("/motivos-rechazo");
    cuerpo.replaceChildren(...(lista.length ? [] : [UI.filaVacia(6, "No hay motivos.")]));
    for (const motivo of lista) {
      const acciones = [UI.boton("Editar", () => abrir(motivo))];
      if (motivo.codigo !== "OTRO") acciones.push(UI.boton(motivo.activo ? "Desactivar" : "Activar", () => cambiarEstado(motivo)));
      cuerpo.append(crear("tr", {}, [
        UI.celda("Código", [UI.texto(motivo.codigo, "cifra")]),
        UI.celda("Nombre", [UI.texto(motivo.nombre)]),
        UI.celda("Exige detalle", [UI.texto(motivo.exige_detalle ? "Sí" : "No")]),
        UI.celda("Orden", [UI.texto(motivo.orden, "cifra")]),
        UI.celda("Estado", [UI.badgeEstado(motivo.activo)]),
        UI.celda("Acciones", [crear("div", { clase: "celda-acciones" }, acciones)]),
      ]));
    }
  }

  async function cambiarEstado(motivo) {
    XPS.limpiarAlerta(alertas);
    try {
      await XPS.api(`/motivos-rechazo/${motivo.id}`, { metodo: "PATCH", cuerpo: { activo: !motivo.activo } });
      XPS.mostrarAlerta(alertas, "exito", motivo.activo ? "Motivo desactivado." : "Motivo activado.");
      await cargar();
    } catch (error) {
      XPS.mostrarError(alertas, error);
    }
  }

  function abrir(motivo = null) {
    enEdicion = motivo;
    form.reset();
    XPS.limpiarAlerta(alertasDialogo);
    document.getElementById("titulo-motivo").textContent = motivo ? `Editar ${motivo.nombre}` : "Nuevo motivo de rechazo";
    form.elements.codigo.disabled = Boolean(motivo);
    if (motivo) {
      form.elements.codigo.value = motivo.codigo;
      form.elements.nombre.value = motivo.nombre;
      form.elements.orden.value = motivo.orden;
      form.elements.exige_detalle.checked = motivo.exige_detalle;
    }
    form.elements.exige_detalle.disabled = Boolean(motivo && motivo.codigo === "OTRO");
    dialogo.showModal();
  }

  form.addEventListener("submit", async (evento) => {
    evento.preventDefault();
    XPS.limpiarAlerta(alertasDialogo);
    const datos = {
      nombre: form.elements.nombre.value.trim(),
      orden: Number(form.elements.orden.value || 0),
      exige_detalle: form.elements.exige_detalle.checked,
    };
    if (!datos.nombre || (!enEdicion && !form.elements.codigo.value.trim())) {
      XPS.mostrarAlerta(alertasDialogo, "error", "El código y el nombre son obligatorios.");
      return;
    }
    try {
      if (enEdicion) {
        const cambios = Object.fromEntries(Object.entries(datos).filter(([campo, valor]) => valor !== enEdicion[campo]));
        if (Object.keys(cambios).length) await XPS.api(`/motivos-rechazo/${enEdicion.id}`, { metodo: "PATCH", cuerpo: cambios });
      } else {
        await XPS.api("/motivos-rechazo", { metodo: "POST", cuerpo: { codigo: form.elements.codigo.value.trim().toUpperCase(), ...datos } });
      }
      dialogo.close();
      XPS.mostrarAlerta(alertas, "exito", "Motivo guardado.");
      await cargar();
    } catch (error) {
      XPS.mostrarError(alertasDialogo, error);
    }
  });

  const yo = await iniciarLayout("motivos-rechazo.html");
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
