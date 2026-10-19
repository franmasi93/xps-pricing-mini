/* Sidebar: menú por grupos (según los permisos de /v1/auth/yo) y bloque de perfil con Salir. */
"use strict";

// `permisos`: null = visible para todos; si no, basta con tener uno de la lista.
const GRUPOS_MENU = [
  {
    titulo: "General",
    opciones: [{ texto: "Inicio", archivo: "inicio.html", permisos: null }],
  },
  {
    titulo: "Tarifas",
    opciones: [
      { texto: "Tarifas", archivo: "tarifas.html", permisos: ["tarifa.ver"] },
      // P7: el comercial no la ve (la API se la permite leer para el cotizador de F3).
      { texto: "Recargos", archivo: "recargos.html", permisos: ["tarifa.editar", "costo.ver"] },
      { texto: "Monedas y tasas", archivo: "monedas.html", permisos: ["tasa.editar", "costo.ver"] },
    ],
  },
  {
    titulo: "Comercial",
    opciones: [
      // Admin, pricing y comercial crean; gerencia lee (ver_todas). Cada uno ve según su alcance.
      { texto: "Cotizaciones", archivo: "cotizaciones.html", permisos: ["cotizacion.crear", "cotizacion.ver_todas"] },
      { texto: "Clientes", archivo: "clientes.html", permisos: ["cliente.ver"] },
      { texto: "Incoterms", archivo: "incoterms.html", permisos: null },
    ],
  },
  {
    titulo: "Boletines",
    opciones: [
      // E1: boletines.ver para los 4 roles; editar depende de cada permiso de boletines.
      { texto: "Campañas", archivo: "boletines.html", permisos: ["boletines.ver"] },
      { texto: "Listas de envío", archivo: "listas.html", permisos: ["boletines.ver"] },
      { texto: "Bajas de correo", archivo: "bajas.html", permisos: ["boletines.ver"] },
    ],
  },
  {
    titulo: "Catálogos",
    opciones: [
      { texto: "Geografía", archivo: "geografia.html", permisos: ["catalogo.editar"] },
      { texto: "Proveedores", archivo: "proveedores.html", permisos: ["catalogo.editar", "costo.ver"] },
      // E0: los lee cualquier usuario con tarifas; los edita catalogo.editar.
      { texto: "Tipos de equipo", archivo: "tipos-equipo.html", permisos: ["catalogo.editar", "tarifa.ver"] },
    ],
  },
  {
    titulo: "Administración",
    opciones: [
      { texto: "Configuración", archivo: "configuracion.html", permisos: ["config.editar", "tarifa.editar"] },
      // E0: solo el administrador los edita (configuracion.servicios.gestionar).
      { texto: "Servicios", archivo: "servicios.html", permisos: ["configuracion.servicios.gestionar"] },
      { texto: "Tipos de ubicación", archivo: "tipos-ubicacion.html", permisos: ["configuracion.servicios.gestionar"] },
      // E1: catálogo de plantillas de Tencent, solo el administrador.
      { texto: "Plantillas de correo", archivo: "plantillas-correo.html", permisos: ["usuario.admin"] },
      { texto: "Usuarios", archivo: "usuarios.html", permisos: ["usuario.admin"] },
      // E2: roles y matriz de permisos (usuario.admin); motivos de rechazo y tipos de identificación (config.editar).
      { texto: "Roles y permisos", archivo: "roles.html", permisos: ["usuario.admin"] },
      { texto: "Motivos de rechazo", archivo: "motivos-rechazo.html", permisos: ["config.editar"] },
      { texto: "Tipos de identificación", archivo: "tipos-identificacion.html", permisos: ["config.editar"] },
      // E3: notificaciones y avisos.
      { texto: "Notificaciones", archivo: "notificaciones-config.html", permisos: ["notificaciones.reglas.gestionar"] },
      { texto: "Bitácora de avisos", archivo: "notificaciones-bitacora.html", permisos: ["notificaciones.bitacora.ver"] },
      { texto: "Auditoría", archivo: "auditoria.html", permisos: ["auditoria.ver"] },
    ],
  },
];

/**
 * Carga el usuario actual y arma el layout.
 * @param {string} archivoActual  nombre del HTML de la pantalla (para marcar el menú).
 * @param {{permitirForzado?: boolean}} opciones  true solo en cambiar-password.html.
 * @returns {Promise<object|null>}  el JSON de /v1/auth/yo, o null si se está redirigiendo.
 */
async function iniciarLayout(archivoActual, { permitirForzado = false } = {}) {
  if (!XPS.obtenerToken()) {
    XPS.irA(XPS.RUTA_LOGIN);
    return null;
  }

  let yo;
  try {
    yo = await XPS.api("/auth/yo");
  } catch (error) {
    const alertas = document.getElementById("alertas");
    if (alertas) {
      XPS.mostrarError(alertas, error);
    }
    return null;
  }

  if (yo.forzar_cambio_password && !permitirForzado) {
    XPS.irA(XPS.RUTA_CAMBIO);
    return null;
  }

  const iniciales = yo.nombre
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((palabra) => palabra[0].toUpperCase())
    .join("");
  document.getElementById("usuario-avatar").textContent = iniciales;
  document.getElementById("usuario-nombre").textContent = yo.nombre;
  document.getElementById("usuario-rol").textContent = yo.rol.nombre;
  document.getElementById("btn-salir").addEventListener("click", XPS.salir);

  const menu = document.getElementById("menu");
  menu.replaceChildren();
  if (yo.forzar_cambio_password) {
    return yo;
  }

  const permisos = new Set(yo.permisos);
  for (const grupo of GRUPOS_MENU) {
    const visibles = grupo.opciones.filter(
      (opcion) => opcion.permisos === null || opcion.permisos.some((permiso) => permisos.has(permiso))
    );
    if (visibles.length === 0) {
      continue;
    }
    const lista = XPS.crear("ul", { clase: "nav" });
    for (const opcion of visibles) {
      const actual = opcion.archivo === archivoActual;
      const enlace = XPS.crear("a", {
        texto: opcion.texto,
        clase: actual ? "activo" : "",
        atributos: actual ? { href: opcion.archivo, "aria-current": "page" } : { href: opcion.archivo },
      });
      lista.append(XPS.crear("li", {}, [enlace]));
    }
    menu.append(XPS.crear("p", { clase: "nav-grupo", texto: grupo.titulo }), lista);
  }
  if (permisos.has("notificaciones.ver")) {
    pintarCampana(archivoActual);
  }
  return yo;
}

/** E3: campana con el contador de notificaciones no leídas, junto al perfil. Lleva a "Mis notificaciones". */
async function pintarCampana(archivoActual) {
  const perfil = document.querySelector(".perfil");
  if (!perfil || document.getElementById("campana")) return;
  const contador = XPS.crear("span", { clase: "campana-contador", atributos: { id: "campana-contador", hidden: "" } });
  const campana = XPS.crear("a", {
    clase: `campana${archivoActual === "mis-notificaciones.html" ? " activo" : ""}`,
    atributos: { id: "campana", href: "mis-notificaciones.html", "aria-label": "Mis notificaciones", title: "Mis notificaciones" },
  }, [XPS.crear("span", { texto: "🔔", atributos: { "aria-hidden": "true" } }), contador]);
  perfil.prepend(campana);
  await actualizarCampana();
}

async function actualizarCampana() {
  const contador = document.getElementById("campana-contador");
  if (!contador) return;
  try {
    const { no_leidas: noLeidas } = await XPS.api("/notificaciones/mias/conteo");
    contador.textContent = noLeidas > 99 ? "99+" : String(noLeidas);
    contador.hidden = noLeidas === 0;
    document.getElementById("campana").setAttribute("aria-label", `Mis notificaciones (${noLeidas} sin leer)`);
  } catch {
    contador.hidden = true;
  }
}
