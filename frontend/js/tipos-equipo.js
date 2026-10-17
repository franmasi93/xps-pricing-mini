/* E0 Tipos de equipo: catalogo.editar crea, edita y desactiva; los demás leen. Cada tipo es de un servicio
 * que cobra por unidad de equipo (solo esos servicios se ofrecen en el formulario).
 */
"use strict";

(async () => {
  const { crear } = XPS;
  const alertas = document.getElementById("alertas");
  const herramientas = document.getElementById("herramientas");
  const botonNuevo = document.getElementById("btn-nuevo");
  const cuerpo = document.getElementById("tabla-tipos");
  const filtroServicio = document.getElementById("filtro-servicio");
  const filtroActivo = document.getElementById("filtro-activo");
  const dialogo = document.getElementById("dialogo-tipo");
  const form = document.getElementById("form-tipo");
  const alertasDialogo = document.getElementById("alertas-tipo");

  let puedeEditar = false;
  let servicios = [];
  let enEdicion = null;

  const conEquipo = () => servicios.filter((s) => s.usa_tipo_equipo);
  const nombreServicio = (id) => (servicios.find((s) => s.id === id) || { nombre: "—" }).nombre;

  async function cargar() {
    const lista = await XPS.api(UI.consulta("/tipos-equipo", { servicio_id: filtroServicio.value, activo: filtroActivo.value }));
    const columnas = puedeEditar ? 5 : 4;
    cuerpo.replaceChildren(...(lista.length ? [] : [UI.filaVacia(columnas, "No hay tipos de equipo con estos filtros.")]));
    for (const tipo of lista) {
      const celdas = [
        UI.celda("Código", [UI.texto(tipo.codigo, "cifra")]),
        UI.celda("Nombre", [UI.texto(tipo.nombre)]),
        UI.celda("Servicio", [UI.texto(nombreServicio(tipo.servicio_id))]),
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
      await XPS.api(`/tipos-equipo/${tipo.id}`, { metodo: "PATCH", cuerpo: { activo: !tipo.activo } });
      XPS.mostrarAlerta(alertas, "exito", tipo.activo ? "Tipo de equipo desactivado." : "Tipo de equipo activado.");
      await cargar();
    } catch (error) {
      XPS.mostrarError(alertas, error);
    }
  }

  function abrir(tipo = null) {
    enEdicion = tipo;
    form.reset();
    XPS.limpiarAlerta(alertasDialogo);
    document.getElementById("titulo-tipo").textContent = tipo ? `Editar ${tipo.codigo}` : "Nuevo tipo de equipo";
    const ofrecidos = conEquipo().filter((s) => s.activo || (tipo && s.id === tipo.servicio_id));
    UI.opciones(form.elements.servicio_id, ofrecidos, { valor: (s) => s.id, texto: (s) => s.nombre });
    if (tipo) {
      form.elements.codigo.value = tipo.codigo;
      form.elements.nombre.value = tipo.nombre;
      form.elements.servicio_id.value = String(tipo.servicio_id);
    }
    dialogo.showModal();
  }

  form.addEventListener("submit", async (evento) => {
    evento.preventDefault();
    XPS.limpiarAlerta(alertasDialogo);
    const datos = {
      codigo: form.elements.codigo.value.trim().toUpperCase(),
      nombre: form.elements.nombre.value.trim(),
      servicio_id: Number(form.elements.servicio_id.value) || null,
    };
    if (!datos.codigo || !datos.nombre || !datos.servicio_id) {
      XPS.mostrarAlerta(alertasDialogo, "error", "El código, el nombre y el servicio son obligatorios.");
      return;
    }
    try {
      if (enEdicion) {
        const cambios = {};
        for (const [campo, valor] of Object.entries(datos)) {
          if (valor !== enEdicion[campo]) cambios[campo] = valor;
        }
        if (Object.keys(cambios).length) {
          await XPS.api(`/tipos-equipo/${enEdicion.id}`, { metodo: "PATCH", cuerpo: cambios });
        }
      } else {
        await XPS.api("/tipos-equipo", { metodo: "POST", cuerpo: datos });
      }
      dialogo.close();
      XPS.mostrarAlerta(alertas, "exito", "Tipo de equipo guardado.");
      await cargar();
    } catch (error) {
      XPS.mostrarError(alertasDialogo, error);
    }
  });

  const yo = await iniciarLayout("tipos-equipo.html");
  if (!yo) {
    return;
  }
  puedeEditar = UI.tieneAlguno(yo, ["catalogo.editar"]);
  document.getElementById("th-acciones").hidden = !puedeEditar;
  document.getElementById("nota-lectura").hidden = puedeEditar;
  UI.prepararDialogo(dialogo);
  botonNuevo.addEventListener("click", () => abrir());
  for (const filtro of [filtroServicio, filtroActivo]) {
    filtro.addEventListener("change", async () => {
      try {
        await cargar();
      } catch (error) {
        XPS.mostrarError(alertas, error);
      }
    });
  }
  try {
    servicios = await XPS.api("/servicios");
    UI.opciones(filtroServicio, conEquipo(), { valor: (s) => s.id, texto: (s) => s.nombre, todos: "Todos" });
    await cargar();
    herramientas.hidden = false;
    botonNuevo.hidden = !puedeEditar;
  } catch (error) {
    XPS.mostrarError(alertas, error);
  }
})();
