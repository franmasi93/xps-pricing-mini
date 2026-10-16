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

  /** Etiqueta del estado de vigencia calculado por el backend (FUTURA, VIGENTE, POR_VENCER, VENCIDA). */
  function badgeVigencia(estado, diasAlerta) {
    const etiquetas = {
      FUTURA: ["badge badge-estado badge-info", "Futura"],
      VIGENTE: ["badge badge-estado badge-activo", "Vigente"],
      POR_VENCER: ["badge badge-estado badge-alerta", `Vence en ≤${diasAlerta} días`],
      VENCIDA: ["badge badge-estado badge-critico", "Vencida"],
    };
    const [clase, texto] = etiquetas[estado] || ["badge badge-estado badge-inactivo", estado];
    return crear("span", { clase, texto });
  }

  /** Lee los días de alerta de la configuración (los ve cualquier usuario con sesión). */
  async function diasAlerta() {
    const configuracion = await XPS.api("/configuracion");
    const clave = configuracion.find((c) => c.clave === "dias_alerta_vencimiento");
    return clave ? clave.valor : "7";
  }

  /** Monto tal como lo envía el backend (texto con 4 decimales) más la moneda; nunca se calcula aquí. */
  function monto(valor, moneda) {
    if (valor === null || valor === undefined) {
      return texto(null);
    }
    return crear("span", { clase: "cifra", texto: moneda ? `${valor} ${moneda}` : valor });
  }

  /** Estado de la cotización; "Vencida" es una etiqueta calculada por el backend, no un estado. */
  function badgesCotizacion(estado, vencida) {
    const clases = {
      BORRADOR: "badge badge-estado badge-inactivo",
      EMITIDA: "badge badge-estado badge-info",
      ENVIADA: "badge badge-estado badge-info",
      ACEPTADA: "badge badge-estado badge-activo",
      RECHAZADA: "badge badge-estado badge-critico",
    };
    const etiquetas = [crear("span", { clase: clases[estado] || "badge badge-estado", texto: estado })];
    if (vencida) {
      etiquetas.push(crear("span", { clase: "badge badge-estado badge-alerta", texto: "Vencida" }));
    }
    return etiquetas;
  }

  /** Paginador "Anterior · x–y de N · Siguiente" (F5-A2). alCambiar(nuevaPagina) recarga la lista. */
  function paginador(contenedor, porPagina, alCambiar) {
    return function pintarPaginador(total, pagina) {
      const desde = total ? pagina * porPagina + 1 : 0;
      const hasta = Math.min(total, (pagina + 1) * porPagina);
      const anterior = boton("Anterior", () => alCambiar(pagina - 1));
      const siguiente = boton("Siguiente", () => alCambiar(pagina + 1));
      anterior.disabled = pagina === 0;
      siguiente.disabled = hasta >= total;
      contenedor.replaceChildren(anterior, crear("span", { clase: "texto-suave", texto: `${desde}–${hasta} de ${total}` }), siguiente);
      contenedor.hidden = total <= porPagina && pagina === 0;
    };
  }

  return {
    SIN_PERMISO,
    paginador,
    badgesCotizacion,
    tieneAlguno,
    exigirAlguno,
    celda,
    texto,
    boton,
    badgeEstado,
    badgeVigencia,
    diasAlerta,
    monto,
    filaVacia,
    opciones,
    prepararDialogo,
    consulta,
  };
})();
