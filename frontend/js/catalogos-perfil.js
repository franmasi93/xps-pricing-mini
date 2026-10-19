/* E1-B Catálogos del perfil comercial (config.editar): crear, renombrar, ordenar y activar o desactivar valores.
 * Los estados comerciales son fijos. Los valores alimentan la plantilla de importación y la ficha del cliente.
 */
"use strict";

(async () => {
  const { crear } = XPS;
  const alertas = document.getElementById("alertas");
  const filtro = document.getElementById("filtro-tipo");
  const cuerpo = document.getElementById("tabla-valores");
  const dialogo = document.getElementById("dialogo-valor");
  const form = document.getElementById("form-valor");
  const alertasDialogo = document.getElementById("alertas-valor");
  const TIPOS = [
    ["TIPO_CLIENTE", "Tipos de cliente"], ["ESTADO_COMERCIAL", "Estados comerciales (fijos)"], ["SECTOR", "Sectores"],
    ["TIPO_CARGA", "Tipos de carga"], ["FRECUENCIA", "Frecuencias"], ["VOLUMEN", "Volúmenes"],
    ["ORIGEN_CLIENTE", "Cómo llegó el cliente"], ["AREA_CONTACTO", "Áreas de contacto"],
    ["MEDIO_CONSENTIMIENTO", "Medios de consentimiento"],
  ];
  let enEdicion = null;

  async function cargar() {
    const lista = await XPS.api(UI.consulta("/catalogos-perfil", { tipo: filtro.value }));
    cuerpo.replaceChildren(...(lista.length ? [] : [UI.filaVacia(5, "Este catálogo no tiene valores.")]));
    for (const item of lista) {
      const acciones = item.fijo ? [UI.texto("Fijo")] : [
        UI.boton("Editar", () => abrir(item)),
        UI.boton(item.activo ? "Desactivar" : "Activar", () => cambiarEstado(item)),
      ];
      cuerpo.append(crear("tr", {}, [
        UI.celda("Código", [UI.texto(item.codigo, "cifra")]),
        UI.celda("Nombre", [UI.texto(item.nombre)]),
        UI.celda("Orden", [UI.texto(item.orden, "cifra")]),
        UI.celda("Estado", [UI.badgeEstado(item.activo)]),
        UI.celda("Acciones", [crear("div", { clase: "celda-acciones" }, acciones)]),
      ]));
    }
    document.getElementById("btn-nuevo").hidden = filtro.value === "ESTADO_COMERCIAL";
  }

  async function cambiarEstado(item) {
    XPS.limpiarAlerta(alertas);
    try {
      await XPS.api(`/catalogos-perfil/${item.id}`, { metodo: "PATCH", cuerpo: { activo: !item.activo } });
      await cargar();
    } catch (error) {
      XPS.mostrarError(alertas, error);
    }
  }

  function abrir(item = null) {
    enEdicion = item;
    form.reset();
    XPS.limpiarAlerta(alertasDialogo);
    document.getElementById("titulo-valor").textContent = item ? `Editar ${item.codigo}` : `Nuevo valor · ${TIPOS.find((t) => t[0] === filtro.value)[1]}`;
    form.elements.codigo.disabled = Boolean(item);
    if (item) {
      form.elements.codigo.value = item.codigo;
      form.elements.nombre.value = item.nombre;
      form.elements.orden.value = item.orden;
    }
    dialogo.showModal();
  }

  form.addEventListener("submit", async (evento) => {
    evento.preventDefault();
    XPS.limpiarAlerta(alertasDialogo);
    const datos = { nombre: form.elements.nombre.value.trim(), orden: Number(form.elements.orden.value || 0) };
    if (!datos.nombre) {
      XPS.mostrarAlerta(alertasDialogo, "error", "El nombre es obligatorio.");
      return;
    }
    try {
      if (enEdicion) {
        await XPS.api(`/catalogos-perfil/${enEdicion.id}`, { metodo: "PATCH", cuerpo: datos });
      } else {
        await XPS.api("/catalogos-perfil", { metodo: "POST", cuerpo: { tipo: filtro.value, codigo: form.elements.codigo.value.trim() || null, ...datos } });
      }
      dialogo.close();
      XPS.mostrarAlerta(alertas, "exito", "Valor guardado.");
      await cargar();
    } catch (error) {
      XPS.mostrarError(alertasDialogo, error);
    }
  });

  const yo = await iniciarLayout("catalogos-perfil.html");
  if (!yo || !UI.exigirAlguno(yo, ["config.editar"], alertas)) {
    return;
  }
  UI.prepararDialogo(dialogo);
  UI.opciones(filtro, TIPOS, { valor: (t) => t[0], texto: (t) => t[1] });
  filtro.addEventListener("change", () => cargar().catch((error) => XPS.mostrarError(alertas, error)));
  document.getElementById("btn-nuevo").addEventListener("click", () => abrir());
  try {
    await cargar();
    document.getElementById("herramientas").hidden = false;
  } catch (error) {
    XPS.mostrarError(alertas, error);
  }
})();
