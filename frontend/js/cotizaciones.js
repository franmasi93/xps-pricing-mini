/* P10 Lista de cotizaciones: filtros, estado y etiqueta "Vencida" (calculada por el backend). */
"use strict";

(() => {
  const { crear } = XPS;
  const POR_PAGINA = 25;
  const alertas = document.getElementById("alertas");
  const cuerpo = document.getElementById("tabla-cotizaciones");
  const filtros = {
    estado: document.getElementById("filtro-estado"),
    vencidas: document.getElementById("filtro-vencidas"),
    desde: document.getElementById("filtro-desde"),
    hasta: document.getElementById("filtro-hasta"),
  };
  let offset = 0;
  let total = 0;

  function ruta(cotizacion) {
    return crear("span", { clase: "ruta-linea" }, [
      crear("span", { clase: "ruta-origen cifra", texto: cotizacion.origen.codigo }),
      crear("span", { texto: " → " }),
      crear("span", { clase: "ruta-destino cifra", texto: cotizacion.destino.codigo }),
    ]);
  }

  function fila(cotizacion) {
    const enlace = crear("a", { clase: "enlace", texto: cotizacion.etiqueta, atributos: { href: `cotizacion.html?id=${cotizacion.id}` } });
    return crear("tr", {}, [
      UI.celda("Cotización", [enlace]),
      UI.celda("Cliente", [UI.texto(cotizacion.cliente.razon_social)]),
      UI.celda("Ruta", [ruta(cotizacion)]),
      UI.celda("Modo", [UI.texto(cotizacion.modo)]),
      UI.celda("Incoterm", [UI.texto(cotizacion.incoterm)]),
      UI.celda("Estado", UI.badgesCotizacion(cotizacion.estado, cotizacion.vencida)),
      UI.celda("Válida hasta", [UI.texto(cotizacion.valida_hasta)]),
      UI.celda("Total USD", [UI.monto(cotizacion.total_general)]),
      UI.celda("Comercial", [UI.texto(cotizacion.comercial.nombre)]),
    ]);
  }

  async function cargar() {
    XPS.limpiarAlerta(alertas);
    try {
      const pagina = await XPS.api(
        UI.consulta("/cotizaciones", {
          estado: filtros.estado.value,
          vencidas: filtros.vencidas.value,
          desde: filtros.desde.value,
          hasta: filtros.hasta.value,
          limit: POR_PAGINA,
          offset,
        })
      );
      total = pagina.total;
      cuerpo.replaceChildren(...(pagina.items.length ? pagina.items.map(fila) : [UI.filaVacia(9, "No hay cotizaciones con esos filtros")]));
      const hasta = Math.min(offset + POR_PAGINA, total);
      document.getElementById("pagina").textContent = total ? `${offset + 1}–${hasta} de ${total}` : "";
      document.getElementById("btn-anterior").disabled = offset === 0;
      document.getElementById("btn-siguiente").disabled = hasta >= total;
    } catch (error) {
      XPS.mostrarError(alertas, error);
    }
  }

  async function iniciar() {
    const yo = await iniciarLayout("cotizaciones.html");
    if (!yo || !UI.exigirAlguno(yo, ["cotizacion.crear", "cotizacion.ver_todas"], alertas)) {
      return;
    }
    const crea = UI.tieneAlguno(yo, ["cotizacion.crear"]);
    document.getElementById("btn-nueva").hidden = !crea;
    document.getElementById("nota-lectura").hidden = crea;
    document.getElementById("herramientas").hidden = false;
    for (const control of Object.values(filtros)) {
      control.addEventListener("change", () => {
        offset = 0;
        cargar();
      });
    }
    document.getElementById("btn-anterior").addEventListener("click", () => {
      offset = Math.max(0, offset - POR_PAGINA);
      cargar();
    });
    document.getElementById("btn-siguiente").addEventListener("click", () => {
      offset += POR_PAGINA;
      cargar();
    });
    await cargar();
  }

  iniciar();
})();
