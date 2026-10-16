/* F5-A1 Auditoría (auditoria.ver): filtros por entidad, usuario y fechas; tabla paginada con el detalle
 * antes → después de cada campo. Las llaves del correo llegan enmascaradas desde el backend; aquí no se calcula nada.
 */
"use strict";

(async () => {
  const { crear } = XPS;
  const alertas = document.getElementById("alertas");
  const POR_PAGINA = 25;
  const ACCIONES = { CREAR: "badge-activo", EDITAR: "badge-info", DESACTIVAR: "badge-inactivo" };
  const filtros = {
    entidad: document.getElementById("filtro-entidad"),
    usuario_id: document.getElementById("filtro-usuario"),
    desde: document.getElementById("filtro-desde"),
    hasta: document.getElementById("filtro-hasta"),
  };
  let pagina = 0;

  function valorLegible(valor) {
    if (valor === null || valor === undefined || valor === "") return "—";
    if (typeof valor === "object") return JSON.stringify(valor);
    return String(valor);
  }

  /** Una fila por campo que cambió: "campo: antes → después". */
  function detalle(registro) {
    const antes = registro.valores_antes || {};
    const despues = registro.valores_despues || {};
    const campos = [...new Set([...Object.keys(antes), ...Object.keys(despues)])];
    const filas = campos
      .filter((campo) => JSON.stringify(antes[campo]) !== JSON.stringify(despues[campo]))
      .map((campo) => crear("div", { clase: "auditoria-cambio" }, [
        crear("span", { clase: "etiqueta", texto: `${campo}: ` }),
        crear("span", { texto: `${valorLegible(antes[campo])} → ${valorLegible(despues[campo])}` }),
      ]));
    if (registro.nota) filas.unshift(crear("div", { clase: "texto-suave", texto: registro.nota }));
    return filas.length ? filas : [UI.texto(null)];
  }

  function pintar(registros) {
    const cuerpo = document.getElementById("tabla-auditoria");
    if (!registros.length) {
      cuerpo.replaceChildren(UI.filaVacia(5, "Sin registros con esos filtros"));
      return;
    }
    cuerpo.replaceChildren(...registros.map((r) => crear("tr", {}, [
      UI.celda("Fecha", [UI.texto(XPS.formatearFecha(r.fecha), "cifra")]),
      UI.celda("Usuario", [UI.texto(r.usuario_nombre)]),
      UI.celda("Entidad", [UI.texto(`${r.entidad} #${r.entidad_id}`)]),
      UI.celda("Acción", [crear("span", { clase: `badge badge-estado ${ACCIONES[r.accion] || ""}`, texto: r.accion })]),
      UI.celda("Detalle", detalle(r)),
    ])));
  }

  const pintarPaginador = UI.paginador(document.getElementById("paginador-auditoria"), POR_PAGINA, (nueva) => {
    pagina = Math.max(0, nueva);
    cargar().catch((error) => XPS.mostrarError(alertas, error));
  });

  async function cargar() {
    const parametros = { limit: POR_PAGINA, offset: pagina * POR_PAGINA };
    for (const [clave, control] of Object.entries(filtros)) parametros[clave] = control.value.trim();
    const datos = await XPS.api(UI.consulta("/auditoria", parametros));
    pintar(datos.items);
    pintarPaginador(datos.total, pagina);
  }

  const yo = await iniciarLayout("auditoria.html");
  if (!yo || !UI.exigirAlguno(yo, ["auditoria.ver"], alertas)) {
    return;
  }
  try {
    const usuarios = await XPS.api("/auditoria/usuarios");
    UI.opciones(filtros.usuario_id, usuarios, { valor: (u) => u.id, texto: (u) => u.nombre, todos: "Todos" });
    for (const control of Object.values(filtros)) {
      control.addEventListener("change", () => {
        pagina = 0;
        cargar().catch((error) => XPS.mostrarError(alertas, error));
      });
    }
    await cargar();
    document.getElementById("herramientas").hidden = false;
  } catch (error) {
    XPS.mostrarError(alertas, error);
  }
})();
