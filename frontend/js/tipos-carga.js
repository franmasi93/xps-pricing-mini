/* D-T2 Tipos de carga (catalogo.editar): crear, renombrar, ordenar, marcar "pide datos IMO" y activar o desactivar.
 * GENERAL es el tipo por defecto: no se desactiva ni pide datos IMO.
 */
"use strict";

(async () => {
  const { crear } = XPS;
  const alertas = document.getElementById("alertas");
  const cuerpo = document.getElementById("tabla-valores");
  const dialogo = document.getElementById("dialogo-valor");
  const form = document.getElementById("form-valor");
  const alertasDialogo = document.getElementById("alertas-valor");
  let enEdicion = null;

  async function cargar() {
    const lista = await XPS.api("/tipos-carga");
    cuerpo.replaceChildren(...(lista.length ? [] : [UI.filaVacia(6, "No hay tipos de carga.")]));
    for (const item of lista) {
      const acciones = [UI.boton("Editar", () => abrir(item))];
      if (item.codigo !== "GENERAL") acciones.push(UI.boton(item.activo ? "Desactivar" : "Activar", () => cambiarEstado(item)));
      cuerpo.append(crear("tr", {}, [
        UI.celda("Código", [UI.texto(item.codigo, "cifra")]),
        UI.celda("Nombre", [UI.texto(item.nombre)]),
        UI.celda("Pide datos IMO", [UI.texto(item.pide_imo ? "Sí" : "No")]),
        UI.celda("Orden", [UI.texto(item.orden, "cifra")]),
        UI.celda("Estado", [UI.badgeEstado(item.activo)]),
        UI.celda("Acciones", [crear("div", { clase: "celda-acciones" }, acciones)]),
      ]));
    }
  }

  async function cambiarEstado(item) {
    XPS.limpiarAlerta(alertas);
    try {
      await XPS.api(`/tipos-carga/${item.id}`, { metodo: "PATCH", cuerpo: { activo: !item.activo } });
      await cargar();
    } catch (error) {
      XPS.mostrarError(alertas, error);
    }
  }

  function abrir(item = null) {
    enEdicion = item;
    form.reset();
    XPS.limpiarAlerta(alertasDialogo);
    document.getElementById("titulo-valor").textContent = item ? `Editar ${item.codigo}` : "Nuevo tipo de carga";
    form.elements.codigo.disabled = Boolean(item);
    if (item) {
      form.elements.codigo.value = item.codigo;
      form.elements.nombre.value = item.nombre;
      form.elements.orden.value = item.orden;
      form.elements.pide_imo.checked = item.pide_imo;
    }
    form.elements.pide_imo.disabled = Boolean(item && item.codigo === "GENERAL");
    dialogo.showModal();
  }

  form.addEventListener("submit", async (evento) => {
    evento.preventDefault();
    XPS.limpiarAlerta(alertasDialogo);
    const datos = { nombre: form.elements.nombre.value.trim(), orden: Number(form.elements.orden.value || 0), pide_imo: form.elements.pide_imo.checked };
    if (!datos.nombre) {
      XPS.mostrarAlerta(alertasDialogo, "error", "El nombre es obligatorio.");
      return;
    }
    try {
      if (enEdicion) {
        await XPS.api(`/tipos-carga/${enEdicion.id}`, { metodo: "PATCH", cuerpo: datos });
      } else {
        const codigo = form.elements.codigo.value.trim();
        if (!codigo) {
          XPS.mostrarAlerta(alertasDialogo, "error", "El código es obligatorio (por ejemplo IMO).");
          return;
        }
        await XPS.api("/tipos-carga", { metodo: "POST", cuerpo: { codigo, ...datos } });
      }
      dialogo.close();
      XPS.mostrarAlerta(alertas, "exito", "Tipo de carga guardado.");
      await cargar();
    } catch (error) {
      XPS.mostrarError(alertasDialogo, error);
    }
  });

  const yo = await iniciarLayout("tipos-carga.html");
  if (!yo || !UI.exigirAlguno(yo, ["catalogo.editar"], alertas)) {
    return;
  }
  UI.prepararDialogo(dialogo);
  document.getElementById("btn-nuevo").hidden = false;
  document.getElementById("btn-nuevo").addEventListener("click", () => abrir());
  try {
    await cargar();
    document.getElementById("herramientas").hidden = false;
  } catch (error) {
    XPS.mostrarError(alertas, error);
  }
})();
