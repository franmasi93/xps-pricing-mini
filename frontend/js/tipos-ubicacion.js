/* E0 Tipos de ubicación: configuracion.servicios.gestionar (admin) crea y edita; el resto lee.
 * La regla del código (regex, mensaje y prefijo del país) la valida el backend al guardar puertos.
 */
"use strict";

(async () => {
  const { crear } = XPS;
  const alertas = document.getElementById("alertas");
  const herramientas = document.getElementById("herramientas");
  const botonNuevo = document.getElementById("btn-nuevo");
  const cuerpo = document.getElementById("tabla-tipos");
  const dialogo = document.getElementById("dialogo-tipo");
  const form = document.getElementById("form-tipo");
  const alertasDialogo = document.getElementById("alertas-tipo");

  let puedeEditar = false;
  let enEdicion = null;

  async function cargar() {
    const lista = await XPS.api("/tipos-ubicacion");
    const columnas = puedeEditar ? 6 : 5;
    cuerpo.replaceChildren(...(lista.length ? [] : [UI.filaVacia(columnas, "No hay tipos de ubicación.")]));
    for (const tipo of lista) {
      const regla = crear("div", {}, [UI.texto(tipo.regex_codigo || "2 a 10 letras o números", "cifra")]);
      if (tipo.ayuda_codigo) regla.append(crear("div", { clase: "ayuda", texto: tipo.ayuda_codigo }));
      const celdas = [
        UI.celda("Código", [UI.texto(tipo.codigo, "cifra")]),
        UI.celda("Nombre", [UI.texto(tipo.nombre)]),
        UI.celda("Regla del código", [regla]),
        UI.celda("Prefijo del país", [UI.texto(tipo.prefijo_pais ? "Sí" : "No")]),
        UI.celda("Estado", [UI.badgeEstado(tipo.activo)]),
      ];
      if (puedeEditar) {
        celdas.push(UI.celda("Acciones", [crear("div", { clase: "celda-acciones" }, [
          UI.boton("Editar", () => abrir(tipo)),
          UI.boton(tipo.activo ? "Desactivar" : "Activar", () => cambiarEstado(tipo)),
        ])]));
      }
      cuerpo.append(crear("tr", {}, celdas));
    }
  }

  async function cambiarEstado(tipo) {
    XPS.limpiarAlerta(alertas);
    try {
      await XPS.api(`/tipos-ubicacion/${tipo.id}`, { metodo: "PATCH", cuerpo: { activo: !tipo.activo } });
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
    document.getElementById("titulo-tipo").textContent = tipo ? `Editar ${tipo.codigo}` : "Nuevo tipo de ubicación";
    if (tipo) {
      for (const campo of ["codigo", "nombre", "regex_codigo", "ayuda_codigo"]) {
        form.elements[campo].value = tipo[campo] ?? "";
      }
      form.elements.prefijo_pais.checked = tipo.prefijo_pais;
    }
    dialogo.showModal();
  }

  form.addEventListener("submit", async (evento) => {
    evento.preventDefault();
    XPS.limpiarAlerta(alertasDialogo);
    const datos = {
      codigo: form.elements.codigo.value.trim().toUpperCase(),
      nombre: form.elements.nombre.value.trim(),
      regex_codigo: form.elements.regex_codigo.value.trim() || null,
      ayuda_codigo: form.elements.ayuda_codigo.value.trim() || null,
      prefijo_pais: form.elements.prefijo_pais.checked,
    };
    if (!datos.codigo || !datos.nombre) {
      XPS.mostrarAlerta(alertasDialogo, "error", "El código y el nombre son obligatorios.");
      return;
    }
    try {
      if (enEdicion) {
        const cambios = {};
        for (const [campo, valor] of Object.entries(datos)) {
          if ((valor ?? null) !== (enEdicion[campo] ?? null)) cambios[campo] = valor;
        }
        if (Object.keys(cambios).length) {
          await XPS.api(`/tipos-ubicacion/${enEdicion.id}`, { metodo: "PATCH", cuerpo: cambios });
        }
      } else {
        await XPS.api("/tipos-ubicacion", { metodo: "POST", cuerpo: datos });
      }
      dialogo.close();
      XPS.mostrarAlerta(alertas, "exito", "Tipo de ubicación guardado.");
      await cargar();
    } catch (error) {
      XPS.mostrarError(alertasDialogo, error);
    }
  });

  const yo = await iniciarLayout("tipos-ubicacion.html");
  if (!yo) {
    return;
  }
  puedeEditar = UI.tieneAlguno(yo, ["configuracion.servicios.gestionar"]);
  document.getElementById("th-acciones").hidden = !puedeEditar;
  document.getElementById("nota-lectura").hidden = puedeEditar;
  UI.prepararDialogo(dialogo);
  botonNuevo.addEventListener("click", () => abrir());
  try {
    await cargar();
    herramientas.hidden = false;
    botonNuevo.hidden = !puedeEditar;
  } catch (error) {
    XPS.mostrarError(alertas, error);
  }
})();
