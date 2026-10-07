/* Pantalla de inicio: bienvenida y, con tarifa.ver, el bloque "Tarifas por vencer".
 * El bloque muestra solo datos de venta: aquí no se dibuja ningún costo, para ningún rol.
 */
"use strict";

(async () => {
  const { crear } = XPS;

  async function tarifasPorVencer() {
    const [dias, tarifas] = await Promise.all([UI.diasAlerta(), XPS.api("/tarifas?por_vencer=true&activo=true")]);
    document.getElementById("por-vencer-bajada").textContent =
      `Tarifas activas que vencen en ${dias} días o menos (plazo de la configuración).`;
    const cuerpo = document.getElementById("tabla-por-vencer");
    cuerpo.replaceChildren(...(tarifas.length ? [] : [UI.filaVacia(5, "No hay tarifas por vencer.")]));
    for (const tarifa of tarifas) {
      cuerpo.append(
        crear("tr", {}, [
          UI.celda("Ruta", [UI.texto(`${tarifa.origen.codigo} → ${tarifa.destino.codigo}`, "cifra")]),
          UI.celda("Modo", [UI.texto(tarifa.tipo_equipo ? `${tarifa.modo} ${tarifa.tipo_equipo.codigo}` : tarifa.modo)]),
          UI.celda("Proveedor", [UI.texto(tarifa.proveedor.nombre)]),
          UI.celda("Venta", [UI.monto(tarifa.precio_venta, tarifa.moneda)]),
          UI.celda("Vence", [UI.texto(tarifa.valido_hasta, "cifra")]),
        ])
      );
    }
    document.getElementById("bloque-por-vencer").hidden = false;
  }

  const yo = await iniciarLayout("inicio.html");
  if (!yo) {
    return;
  }
  document.getElementById("saludo").textContent = `Bienvenido, ${yo.nombre}`;
  document.getElementById("detalle-rol").textContent = `Ingresó con el rol ${yo.rol.nombre}.`;
  document.getElementById("bienvenida").hidden = false;

  if (UI.tieneAlguno(yo, ["tarifa.ver"])) {
    try {
      await tarifasPorVencer();
    } catch (error) {
      XPS.mostrarError(document.getElementById("alertas"), error);
    }
  }
})();
