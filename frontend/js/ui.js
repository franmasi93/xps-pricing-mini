/* Piezas de interfaz compartidas por las pantallas de catálogos (F1).
 * Todo se arma con createElement / textContent (XPS.crear); nunca se inyecta HTML como texto.
 */
"use strict";

const UI = (() => {
  const { crear } = XPS;
  const SIN_PERMISO = "No tiene permiso para esta acción";

  function tieneAlguno(yo, permisos) {
    const propios = new Set(yo.permisos);
    return permisos.some((permiso) => propios.has(permiso));
  }

  /** Si el usuario no tiene ninguno de los permisos, muestra el aviso y devuelve false. */
  function exigirAlguno(yo, permisos, alertas) {
    if (tieneAlguno(yo, permisos)) {
      return true;
    }
    XPS.mostrarAlerta(alertas, "error", SIN_PERMISO);
    return false;
  }

  function celda(etiqueta, hijos) {
    return crear("td", { atributos: { "data-etiqueta": etiqueta } }, hijos);
  }

  function texto(valor, clase) {
    return crear("span", { clase, texto: valor === null || valor === undefined || valor === "" ? "—" : valor });
  }

  function boton(textoBoton, alHacerClic, clase = "btn btn-secundario btn-chico") {
    const elemento = crear("button", { clase, texto: textoBoton, atributos: { type: "button" } });
    elemento.addEventListener("click", alHacerClic);
    return elemento;
  }

  function badgeEstado(activo) {
    return activo
      ? crear("span", { clase: "badge badge-estado badge-activo", texto: "Activo" })
      : crear("span", { clase: "badge badge-estado badge-inactivo", texto: "Inactivo" });
  }

  function filaVacia(columnas, mensaje) {
    return crear("tr", {}, [crear("td", { clase: "tabla-vacia", texto: mensaje, atributos: { colspan: columnas } })]);
  }

  function opciones(select, items, { valor, texto: textoOpcion, todos = null }) {
    const actual = select.value;
    select.replaceChildren();
    if (todos !== null) {
      select.append(crear("option", { texto: todos, atributos: { value: "" } }));
    }
    for (const item of items) {
      select.append(crear("option", { texto: textoOpcion(item), atributos: { value: valor(item) } }));
    }
    if ([...select.options].some((opcion) => opcion.value === actual)) {
      select.value = actual;
    }
  }

  /** Conecta los botones [data-cerrar] de un diálogo. */
  function prepararDialogo(dialogo) {
    for (const cerrar of dialogo.querySelectorAll("[data-cerrar]")) {
      cerrar.addEventListener("click", () => dialogo.close());
    }
  }

  /** Parámetros de búsqueda sin los vacíos. */
  function consulta(ruta, parametros) {
    const limpios = new URLSearchParams();
    for (const [clave, valor] of Object.entries(parametros)) {
      if (valor !== "" && valor !== null && valor !== undefined) {
        limpios.set(clave, valor);
      }
    }
    const texto = limpios.toString();
    return texto ? `${ruta}?${texto}` : ruta;
  }

  return { SIN_PERMISO, tieneAlguno, exigirAlguno, celda, texto, boton, badgeEstado, filaVacia, opciones, prepararDialogo, consulta };
})();
