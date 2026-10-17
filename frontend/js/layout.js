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
      { texto: "Usuarios", archivo: "usuarios.html", permisos: ["usuario.admin"] },
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
  return yo;
}
