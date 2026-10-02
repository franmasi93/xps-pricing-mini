/* Sidebar: menú por grupos (según los permisos de /v1/auth/yo) y bloque de perfil con Salir. */
"use strict";

const GRUPOS_MENU = [
  {
    titulo: "General",
    opciones: [{ texto: "Inicio", archivo: "inicio.html", permiso: null }],
  },
  {
    titulo: "Administración",
    opciones: [{ texto: "Usuarios", archivo: "usuarios.html", permiso: "usuario.admin" }],
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
    const visibles = grupo.opciones.filter((opcion) => opcion.permiso === null || permisos.has(opcion.permiso));
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
