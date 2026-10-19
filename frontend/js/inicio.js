/* Pantalla de inicio: saludo según la hora, mensaje y accesos rápidos según el rol, indicadores de cotizaciones,
 * pendientes del día, "Cotizaciones recientes" (según el alcance) y, con tarifa.ver, "Tarifas por vencer".
 * Aquí no se dibuja ningún costo, para ningún rol.
 */
"use strict";

(async () => {
  const { crear } = XPS;
  const alertas = document.getElementById("alertas");
  const pendientes = [];

  const MENSAJES_ROL = {
    admin: "Tiene acceso a todo el sistema. Revise los pendientes de abajo y, cuando lo necesite, usuarios, configuración y auditoría.",
    pricing: "Mantenga al día tarifas, recargos y tasas de cambio: de ellos dependen todas las cotizaciones del equipo.",
    comercial: "Cotice, emita y envíe a sus clientes. Aquí ve cómo van sus cotizaciones y qué conviene atender hoy.",
    gerencia: "Siga las cotizaciones del equipo, su cierre y las tarifas que están por vencer.",
  };
  const ACCESOS = [
    { texto: "Nueva cotización", archivo: "cotizador.html", permisos: ["cotizacion.crear"], primario: true },
    { texto: "Cotizaciones", archivo: "cotizaciones.html", permisos: ["cotizacion.ver_todas"] },
    { texto: "Clientes", archivo: "clientes.html", permisos: ["cliente.editar"] },
    { texto: "Cargar tarifas", archivo: "tarifas.html", permisos: ["tarifa.editar"] },
    { texto: "Tasas de cambio", archivo: "monedas.html", permisos: ["tasa.editar"] },
    { texto: "Nueva campaña", archivo: "campana.html", permisos: ["boletines.campanas.gestionar"] },
    { texto: "Usuarios", archivo: "usuarios.html", permisos: ["usuario.admin"] },
  ];

  function saludo(nombre) {
    const hora = new Date().getHours();
    const momento = hora < 12 ? "Buenos días" : hora < 19 ? "Buenas tardes" : "Buenas noches";
    return `${momento}, ${nombre.split(/\s+/)[0]}`;
  }

  function pintarBienvenida(yo) {
    const hoy = new Date().toLocaleDateString("es-EC", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
    document.getElementById("fecha-hoy").textContent = hoy.charAt(0).toUpperCase() + hoy.slice(1);
    document.getElementById("saludo").textContent = saludo(yo.nombre);
    document.getElementById("detalle-rol").textContent =
      MENSAJES_ROL[yo.rol.codigo] || `Ingresó como ${yo.rol.nombre}. El menú muestra las pantallas que su rol puede usar.`;
    const accesos = ACCESOS.filter((a) => UI.tieneAlguno(yo, a.permisos)).slice(0, 4).map((a) =>
      crear("a", { clase: `btn ${a.primario ? "btn-primario" : "btn-secundario"} btn-chico`, texto: a.texto, atributos: { href: a.archivo } }));
    document.getElementById("accesos").replaceChildren(...accesos);
    document.getElementById("bienvenida").hidden = false;
  }

  function indicador(titulo, valor, ayuda, href, tono = "") {
    return crear("a", { clase: `contador indicador${tono ? ` indicador-${tono}` : ""}`, atributos: { href } }, [
      crear("strong", { texto: String(valor) }), crear("span", { texto: titulo }), crear("small", { clase: "ayuda", texto: ayuda }),
    ]);
  }

  async function total(parametros) {
    return (await XPS.api(`/cotizaciones?limit=1&${parametros}`)).total;
  }

  async function indicadores(yo) {
    const tiles = [];
    if (UI.tieneAlguno(yo, ["cotizacion.crear", "cotizacion.ver_todas"])) {
      const [borradores, enviadas, vencidas, aceptadas] = await Promise.all([
        total("estado=BORRADOR"), total("estado=ENVIADA&vencidas=false"), total("vencidas=true"), total("estado=ACEPTADA"),
      ]);
      tiles.push(
        indicador("Borradores", borradores, borradores ? "Por terminar y emitir" : "Ninguno pendiente", "cotizaciones.html"),
        indicador("Esperando respuesta", enviadas, "Enviadas al cliente", "cotizaciones.html", "info"),
        indicador("Vencidas sin respuesta", vencidas, vencidas ? "Conviene llamar o duplicar" : "Ninguna", "cotizaciones.html", vencidas ? "alerta" : ""),
        indicador("Aceptadas", aceptadas, "En total", "cotizaciones.html", "ok"),
      );
      if (borradores) pendientes.push(`Tiene ${borradores} ${borradores === 1 ? "borrador" : "borradores"} sin emitir.`);
      if (vencidas) {
        pendientes.push(`${vencidas} ${vencidas === 1 ? "cotización venció" : "cotizaciones vencieron"} sin respuesta del cliente: llame al cliente o duplíquela con tarifas vigentes.`);
      }
    }
    if (UI.tieneAlguno(yo, ["notificaciones.ver"])) {
      const { no_leidas: noLeidas } = await XPS.api("/notificaciones/mias/conteo");
      tiles.push(indicador("Notificaciones", noLeidas, noLeidas ? "Sin leer" : "Todo leído", "mis-notificaciones.html", noLeidas ? "alerta" : ""));
      if (noLeidas) pendientes.push(`Tiene ${noLeidas} ${noLeidas === 1 ? "notificación" : "notificaciones"} sin leer en la campana.`);
    }
    if (tiles.length) {
      const contenedor = document.getElementById("indicadores");
      contenedor.replaceChildren(...tiles);
      contenedor.hidden = false;
    }
  }

  async function tarifasPorVencer() {
    const [dias, tarifas] = await Promise.all([UI.diasAlerta(), XPS.api("/tarifas?por_vencer=true&activo=true")]);
    document.getElementById("por-vencer-bajada").textContent = tarifas.length
      ? `${tarifas.length} ${tarifas.length === 1 ? "tarifa activa vence" : "tarifas activas vencen"} en ${dias} días o menos. Renuévelas para que las cotizaciones no se queden sin precio.`
      : `Ninguna tarifa activa vence en los próximos ${dias} días.`;
    if (tarifas.length) {
      pendientes.push(`${tarifas.length} ${tarifas.length === 1 ? "tarifa vence" : "tarifas vencen"} en ${dias} días o menos.`);
    }
    const cuerpo = document.getElementById("tabla-por-vencer");
    cuerpo.replaceChildren(...(tarifas.length ? [] : [UI.filaVacia(5, "Todo al día: no hay tarifas por vencer.")]));
    for (const tarifa of tarifas) {
      cuerpo.append(
        crear("tr", {}, [
          UI.celda("Ruta", [UI.texto(`${tarifa.origen.codigo} → ${tarifa.destino.codigo}`, "cifra")]),
          UI.celda("Servicio", [UI.texto(tarifa.tipo_equipo ? `${tarifa.modo} ${tarifa.tipo_equipo.codigo}` : tarifa.modo)]),
          UI.celda("Proveedor", [UI.texto(tarifa.proveedor.nombre)]),
          UI.celda("Venta", [UI.monto(tarifa.precio_venta, tarifa.moneda)]),
          UI.celda("Vence", [UI.texto(tarifa.valido_hasta, "cifra")]),
        ])
      );
    }
    document.getElementById("bloque-por-vencer").hidden = false;
  }

  async function cotizacionesRecientes(yo) {
    const pagina = await XPS.api("/cotizaciones?limit=5");
    const cuerpo = document.getElementById("tabla-recientes");
    const vacio = UI.tieneAlguno(yo, ["cotizacion.crear"])
      ? "Todavía no hay cotizaciones. Empiece con «Nueva cotización»."
      : "Todavía no hay cotizaciones del equipo.";
    cuerpo.replaceChildren(...(pagina.items.length ? [] : [UI.filaVacia(5, vacio)]));
    for (const cotizacion of pagina.items) {
      const enlace = crear("a", { clase: "enlace", texto: cotizacion.etiqueta, atributos: { href: `cotizacion.html?id=${cotizacion.id}` } });
      cuerpo.append(
        crear("tr", {}, [
          UI.celda("Cotización", [enlace]),
          UI.celda("Cliente", [UI.texto(cotizacion.cliente.razon_social)]),
          UI.celda("Ruta", [UI.texto(`${cotizacion.origen.codigo} → ${cotizacion.destino.codigo}`, "cifra")]),
          UI.celda("Estado", UI.badgesCotizacion(cotizacion.estado, cotizacion.vencida)),
          UI.celda("Total USD", [UI.monto(cotizacion.total_general)]),
        ])
      );
    }
    document.getElementById("bloque-recientes").hidden = false;
  }

  function pintarPendientes() {
    const lista = document.getElementById("lista-pendientes");
    const items = pendientes.length ? pendientes : ["Todo al día: no hay pendientes urgentes."];
    lista.replaceChildren(...items.map((texto) => crear("li", { clase: pendientes.length ? "" : "pendiente-ok", texto })));
    document.getElementById("bloque-pendientes").hidden = false;
  }

  async function seguro(tarea) {
    try {
      await tarea();
    } catch (error) {
      XPS.mostrarError(alertas, error);
    }
  }

  const yo = await iniciarLayout("inicio.html");
  if (!yo) {
    return;
  }
  pintarBienvenida(yo);
  await seguro(() => indicadores(yo));
  if (UI.tieneAlguno(yo, ["cotizacion.crear", "cotizacion.ver_todas"])) {
    await seguro(() => cotizacionesRecientes(yo));
  }
  if (UI.tieneAlguno(yo, ["tarifa.ver"])) {
    await seguro(tarifasPorVencer);
  }
  pintarPendientes();
})();
