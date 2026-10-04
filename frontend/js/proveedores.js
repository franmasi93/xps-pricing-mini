/* Proveedores: catalogo.editar edita; costo.ver (gerencia) solo lee. El backend exige igual. */
"use strict";

(async () => {
  const { crear } = XPS;
  const alertas = document.getElementById("alertas");
  const herramientas = document.getElementById("herramientas");
  const botonNuevo = document.getElementById("btn-nuevo");
  const cuerpo = document.getElementById("tabla-proveedores");
  const filtroQ = document.getElementById("filtro-q");
  const filtroPais = document.getElementById("filtro-pais");
  const filtroActivo = document.getElementById("filtro-activo");

  const dialogo = document.getElementById("dialogo-proveedor");
  const form = document.getElementById("form-proveedor");
  const alertasDialogo = document.getElementById("alertas-proveedor");
  const CAMPOS_OPCIONALES = ["contacto", "email", "telefono", "notas"];

  let puedeEditar = false;
  let paises = [];
  let enEdicion = null;

  async function cargarProveedores() {
    const lista = await XPS.api(
      UI.consulta("/proveedores", { q: filtroQ.value.trim(), pais_id: filtroPais.value, activo: filtroActivo.value })
    );
    const columnas = puedeEditar ? 7 : 6;
    cuerpo.replaceChildren(...(lista.length ? [] : [UI.filaVacia(columnas, "No hay proveedores con estos filtros.")]));
    for (const proveedor of lista) {
      const celdas = [
        UI.celda("Nombre", [UI.texto(proveedor.nombre)]),
        UI.celda("País", [UI.texto(`${proveedor.pais.iso2} · ${proveedor.pais.nombre}`)]),
        UI.celda("Contacto", [UI.texto(proveedor.contacto)]),
        UI.celda("Email", [UI.texto(proveedor.email, "cifra")]),
        UI.celda("Teléfono", [UI.texto(proveedor.telefono, "cifra")]),
        UI.celda("Estado", [UI.badgeEstado(proveedor.activo)]),
      ];
      if (puedeEditar) {
        celdas.push(
          UI.celda("Acciones", [
            crear("div", { clase: "celda-acciones" }, [
              UI.boton("Editar", () => abrir(proveedor)),
              UI.boton(proveedor.activo ? "Desactivar" : "Activar", () => cambiarEstado(proveedor)),
            ]),
          ])
        );
      }
      cuerpo.append(crear("tr", {}, celdas));
    }
  }

  function abrir(proveedor = null) {
    enEdicion = proveedor;
    form.reset();
    XPS.limpiarAlerta(alertasDialogo);
    document.getElementById("titulo-proveedor").textContent = proveedor ? "Editar proveedor" : "Nuevo proveedor";
    const utilizables = paises.filter((p) => p.activo || (proveedor && p.id === proveedor.pais_id));
    UI.opciones(form.elements.pais, utilizables, { valor: (p) => p.id, texto: (p) => `${p.iso2} · ${p.nombre}` });
    if (proveedor) {
      form.elements.nombre.value = proveedor.nombre;
      form.elements.pais.value = String(proveedor.pais_id);
      for (const campo of CAMPOS_OPCIONALES) {
        form.elements[campo].value = proveedor[campo] || "";
      }
    }
    dialogo.showModal();
  }

  async function cambiarEstado(proveedor) {
    XPS.limpiarAlerta(alertas);
    try {
      await XPS.api(`/proveedores/${proveedor.id}`, { metodo: "PATCH", cuerpo: { activo: !proveedor.activo } });
      XPS.mostrarAlerta(alertas, "exito", proveedor.activo ? "Proveedor desactivado." : "Proveedor activado.");
      await cargarProveedores();
    } catch (error) {
      XPS.mostrarError(alertas, error);
    }
  }

  form.addEventListener("submit", async (evento) => {
    evento.preventDefault();
    XPS.limpiarAlerta(alertasDialogo);
    const datos = { nombre: form.elements.nombre.value.trim(), pais_id: Number(form.elements.pais.value) };
    for (const campo of CAMPOS_OPCIONALES) {
      datos[campo] = form.elements[campo].value.trim() || null;
    }
    if (!datos.nombre || !datos.pais_id) {
      XPS.mostrarAlerta(alertasDialogo, "error", "El nombre y el país son obligatorios.");
      return;
    }
    try {
      if (enEdicion) {
        const cambios = {};
        for (const [campo, valor] of Object.entries(datos)) {
          if ((valor ?? null) !== (enEdicion[campo] ?? null)) {
            cambios[campo] = valor;
          }
        }
        if (Object.keys(cambios).length) {
          await XPS.api(`/proveedores/${enEdicion.id}`, { metodo: "PATCH", cuerpo: cambios });
        }
      } else {
        await XPS.api("/proveedores", { metodo: "POST", cuerpo: datos });
      }
      dialogo.close();
      XPS.mostrarAlerta(alertas, "exito", "Proveedor guardado.");
      await cargarProveedores();
    } catch (error) {
      XPS.mostrarError(alertasDialogo, error);
    }
  });

  // ---------- Inicio ----------

  const yo = await iniciarLayout("proveedores.html");
  if (!yo || !UI.exigirAlguno(yo, ["catalogo.editar", "costo.ver"], alertas)) {
    return;
  }
  puedeEditar = UI.tieneAlguno(yo, ["catalogo.editar"]);
  document.getElementById("th-acciones").hidden = !puedeEditar;
  document.getElementById("nota-lectura").hidden = puedeEditar;

  UI.prepararDialogo(dialogo);
  botonNuevo.addEventListener("click", () => abrir());
  const recargar = async () => {
    try {
      await cargarProveedores();
    } catch (error) {
      XPS.mostrarError(alertas, error);
    }
  };
  filtroPais.addEventListener("change", recargar);
  filtroActivo.addEventListener("change", recargar);
  let espera = null;
  filtroQ.addEventListener("input", () => {
    window.clearTimeout(espera);
    espera = window.setTimeout(recargar, 300);
  });

  try {
    paises = await XPS.api("/paises");
    UI.opciones(filtroPais, paises, { valor: (p) => p.id, texto: (p) => `${p.iso2} · ${p.nombre}`, todos: "Todos" });
    await cargarProveedores();
    herramientas.hidden = false;
    botonNuevo.hidden = !puedeEditar;
  } catch (error) {
    XPS.mostrarError(alertas, error);
  }
})();
