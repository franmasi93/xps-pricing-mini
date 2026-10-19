/* Sidebar: menú por grupos (según los permisos de /v1/auth/yo), con íconos, grupos plegables, buscador, modo compacto
 * en escritorio y panel deslizable en el celular; bloque de perfil con la campana y Salir. */
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
      // E1-B: catálogos del perfil comercial (config.editar).
      { texto: "Catálogos del perfil", archivo: "catalogos-perfil.html", permisos: ["config.editar"] },
      // E3: notificaciones y avisos.
      { texto: "Notificaciones", archivo: "notificaciones-config.html", permisos: ["notificaciones.reglas.gestionar"] },
      { texto: "Bitácora de avisos", archivo: "notificaciones-bitacora.html", permisos: ["notificaciones.bitacora.ver"] },
      { texto: "Auditoría", archivo: "auditoria.html", permisos: ["auditoria.ver"] },
    ],
  },
];


// Íconos lineales de 18 px y trazo 2 (docs/xpressdesignsystem.md), dibujados con SVG con createElementNS.
const TRAZOS = {
  inicio: ["M3 10.5 12 3l9 7.5", "M5 9.5V21h14V9.5", "M9 21v-6h6v6"],
  tarifa: ["M20.6 13.4 13.4 20.6a2 2 0 0 1-2.8 0L3 13V3h10l7.6 7.6a2 2 0 0 1 0 2.8Z", "M7.5 7.5h.01"],
  recargo: ["M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18Z", "M12 8v8", "M8 12h8"],
  moneda: ["M12 2v20", "M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"],
  documento: ["M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z", "M14 2v6h6", "M8 13h8", "M8 17h8"],
  clientes: ["M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2", "M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z", "M22 21v-2a4 4 0 0 0-3-3.9", "M16 3.1a4 4 0 0 1 0 7.8"],
  globo: ["M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20Z", "M2 12h20", "M12 2a15 15 0 0 1 0 20 15 15 0 0 1 0-20Z"],
  enviar: ["M22 2 11 13", "M22 2 15 22l-4-9-9-4Z"],
  lista: ["M8 6h13", "M8 12h13", "M8 18h13", "M3 6h.01", "M3 12h.01", "M3 18h.01"],
  baja: ["M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2", "M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z", "M17 8l5 5", "M22 8l-5 5"],
  mapa: ["M12 22s7-7.2 7-12a7 7 0 0 0-14 0c0 4.8 7 12 7 12Z", "M12 12.5a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5Z"],
  camion: ["M10 17h4V5H2v12h3", "M14 9h4l4 4v4h-2", "M7.5 19.5a2 2 0 1 0 0-4 2 2 0 0 0 0 4Z", "M17.5 19.5a2 2 0 1 0 0-4 2 2 0 0 0 0 4Z"],
  caja: ["M21 8 12 3 3 8v8l9 5 9-5Z", "M3 8l9 5 9-5", "M12 13v8"],
  ajustes: ["M4 21v-7", "M4 10V3", "M12 21v-9", "M12 8V3", "M20 21v-5", "M20 12V3", "M1 14h6", "M9 8h6", "M17 16h6"],
  capas: ["M12 2 2 7l10 5 10-5Z", "M2 17l10 5 10-5", "M2 12l10 5 10-5"],
  ancla: ["M12 8a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z", "M12 22V8", "M5 12H2a10 10 0 0 0 20 0h-3"],
  correo: ["M4 4h16a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2Z", "M22 6l-10 7L2 6"],
  usuario: ["M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2", "M12 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z"],
  escudo: ["M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z", "M9 12l2 2 4-4"],
  rechazo: ["M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18Z", "M15 9l-6 6", "M9 9l6 6"],
  credencial: ["M3 5h18a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1Z", "M9 12.5a2 2 0 1 0 0-4 2 2 0 0 0 0 4Z", "M5.5 16a3.5 3.5 0 0 1 7 0", "M15 10h4", "M15 14h3"],
  campana: ["M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9", "M13.7 21a2 2 0 0 1-3.4 0"],
  bitacora: ["M9 2h6v4H9Z", "M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2", "M9 12h6", "M9 16h6"],
  ojo: ["M1 12s4-8 11-8 11 8 11 8-4 8-11 8S1 12 1 12Z", "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z"],
  menu: ["M3 6h18", "M3 12h18", "M3 18h18"],
  cerrar: ["M18 6 6 18", "M6 6l12 12"],
  flecha: ["M6 9l6 6 6-6"],
  buscar: ["M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16Z", "M21 21l-4.3-4.3"],
  contraer: ["M11 17l-5-5 5-5", "M18 17l-5-5 5-5"],
  salir: ["M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4", "M16 17l5-5-5-5", "M21 12H9"],
};

// Ícono de cada pantalla (por archivo: las opciones del menú no cambian de formato).
const ICONOS = {
  "inicio.html": "inicio", "tarifas.html": "tarifa", "recargos.html": "recargo", "monedas.html": "moneda",
  "cotizaciones.html": "documento", "clientes.html": "clientes", "incoterms.html": "globo", "boletines.html": "enviar",
  "listas.html": "lista", "bajas.html": "baja", "geografia.html": "mapa", "proveedores.html": "camion",
  "tipos-equipo.html": "caja", "configuracion.html": "ajustes", "servicios.html": "capas", "tipos-ubicacion.html": "ancla",
  "plantillas-correo.html": "correo", "usuarios.html": "usuario", "roles.html": "escudo", "motivos-rechazo.html": "rechazo",
  "tipos-identificacion.html": "credencial", "notificaciones-config.html": "campana",
  "notificaciones-bitacora.html": "bitacora", "auditoria.html": "ojo", "catalogos-perfil.html": "lista",
};

// Pantallas que no están en el menú pero pertenecen a un grupo (para dejarlo abierto y marcar la opción).
const PANTALLAS_HIJAS = { "cotizacion.html": "cotizaciones.html", "cotizador.html": "cotizaciones.html", "campana.html": "boletines.html" };

function icono(nombre, clase = "icono") {
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  for (const [clave, valor] of Object.entries({
    viewBox: "0 0 24 24", width: 18, height: 18, fill: "none", stroke: "currentColor", "stroke-width": 2,
    "stroke-linecap": "round", "stroke-linejoin": "round", "aria-hidden": "true", focusable: "false", class: clase,
  })) {
    svg.setAttribute(clave, String(valor));
  }
  for (const d of TRAZOS[nombre] || TRAZOS.documento) {
    const trazo = document.createElementNS(ns, "path");
    trazo.setAttribute("d", d);
    svg.append(trazo);
  }
  return svg;
}

// Preferencias de esta pestaña (modo compacto y grupos abiertos). Si el navegador no deja guardar, se usa lo de siempre.
const PREFERENCIAS_MENU = "xps-menu";
function leerPreferencias() {
  try {
    return JSON.parse(window.sessionStorage.getItem(PREFERENCIAS_MENU) || "{}");
  } catch {
    return {};
  }
}
function guardarPreferencias(cambios) {
  try {
    window.sessionStorage.setItem(PREFERENCIAS_MENU, JSON.stringify({ ...leerPreferencias(), ...cambios }));
  } catch {
    /* sin almacenamiento: no pasa nada */
  }
}

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
  const salir = document.getElementById("btn-salir");
  salir.addEventListener("click", XPS.salir);
  salir.setAttribute("title", "Salir");

  const menu = document.getElementById("menu");
  menu.replaceChildren();
  prepararPanel();
  if (yo.forzar_cambio_password) {
    return yo;
  }
  pintarMenu(menu, new Set(yo.permisos), PANTALLAS_HIJAS[archivoActual] || archivoActual);
  if (yo.permisos.includes("notificaciones.ver")) {
    pintarCampana(archivoActual);
  }
  return yo;
}

function pintarMenu(menu, permisos, archivoActual) {
  const { crear } = XPS;
  const preferencias = leerPreferencias();
  const abiertos = new Set(preferencias.abiertos || []);
  const grupos = [];

  for (const grupo of GRUPOS_MENU) {
    const visibles = grupo.opciones.filter(
      (opcion) => opcion.permisos === null || opcion.permisos.some((permiso) => permisos.has(permiso))
    );
    if (visibles.length === 0) {
      continue;
    }
    const tieneActual = visibles.some((opcion) => opcion.archivo === archivoActual);
    const id = `grupo-${grupo.titulo.toLowerCase().normalize("NFD").replace(/[^a-z]/g, "")}`;
    const lista = crear("ul", { clase: "nav", atributos: { id } });
    for (const opcion of visibles) {
      const actual = opcion.archivo === archivoActual;
      const atributos = { href: opcion.archivo, title: opcion.texto, "data-texto": opcion.texto.toLowerCase() };
      if (actual) atributos["aria-current"] = "page";
      const enlace = crear("a", { clase: actual ? "activo" : "", atributos }, [
        icono(ICONOS[opcion.archivo]), crear("span", { clase: "nav-texto", texto: opcion.texto }),
      ]);
      lista.append(crear("li", {}, [enlace]));
    }
    // "General" (una sola opción) va siempre abierto y sin título plegable.
    if (visibles.length === 1 && grupo.titulo === "General") {
      menu.append(crear("div", { clase: "nav-bloque abierto" }, [lista]));
      continue;
    }
    const abierto = tieneActual || abiertos.has(grupo.titulo);
    const boton = crear("button", {
      clase: "nav-grupo",
      atributos: { type: "button", "aria-expanded": String(abierto), "aria-controls": id },
    }, [crear("span", { texto: grupo.titulo }), icono("flecha", "icono nav-flecha")]);
    const bloque = crear("div", { clase: `nav-bloque${abierto ? " abierto" : ""}` }, [
      boton, crear("div", { clase: "nav-plegable" }, [lista]),
    ]);
    boton.addEventListener("click", () => {
      const ahora = !bloque.classList.contains("abierto");
      bloque.classList.toggle("abierto", ahora);
      boton.setAttribute("aria-expanded", String(ahora));
      const guardados = new Set(leerPreferencias().abiertos || []);
      if (ahora) guardados.add(grupo.titulo); else guardados.delete(grupo.titulo);
      guardarPreferencias({ abiertos: [...guardados] });
    });
    grupos.push(bloque);
    menu.append(bloque);
  }

  // Buscador: filtra las opciones y abre los grupos que tienen coincidencias.
  if (menu.querySelectorAll(".nav a").length > 8) {
    const campo = crear("input", {
      clase: "nav-buscar-input",
      atributos: { type: "search", placeholder: "Buscar en el menú", "aria-label": "Buscar en el menú", autocomplete: "off" },
    });
    const sinResultados = crear("p", { clase: "nav-vacio", texto: "Ninguna opción coincide.", atributos: { hidden: "" } });
    menu.prepend(crear("div", { clase: "nav-buscar" }, [icono("buscar"), campo]));
    menu.append(sinResultados);
    campo.addEventListener("input", () => {
      const texto = campo.value.trim().toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
      let total = 0;
      for (const bloque of menu.querySelectorAll(".nav-bloque")) {
        let visibles = 0;
        for (const enlace of bloque.querySelectorAll(".nav a")) {
          const coincide = !texto || enlace.dataset.texto.normalize("NFD").replace(/[̀-ͯ]/g, "").includes(texto);
          enlace.parentElement.hidden = !coincide;
          visibles += coincide ? 1 : 0;
        }
        bloque.hidden = visibles === 0;
        bloque.classList.toggle("filtrando", Boolean(texto));
        total += visibles;
      }
      sinResultados.hidden = total > 0;
    });
    campo.addEventListener("keydown", (evento) => {
      if (evento.key === "Escape") {
        campo.value = "";
        campo.dispatchEvent(new Event("input"));
      } else if (evento.key === "Enter") {
        const primero = [...menu.querySelectorAll(".nav li")].find((li) => !li.hidden && !li.closest(".nav-bloque").hidden);
        if (primero) primero.querySelector("a").click();
      }
    });
  }

  const activo = menu.querySelector(".nav a.activo");
  if (activo) {
    window.requestAnimationFrame(() => activo.scrollIntoView({ block: "nearest" }));
  }
}

/** Botón ☰ y fondo del panel en el celular, y botón de modo compacto en el escritorio. */
function prepararPanel() {
  const { crear } = XPS;
  const sidebar = document.querySelector(".sidebar");
  const area = document.querySelector(".area");
  if (!sidebar || !area || document.getElementById("barra-movil")) return;
  sidebar.id = sidebar.id || "panel-menu";

  const abrir = crear("button", {
    clase: "btn-icono", atributos: { type: "button", "aria-label": "Abrir el menú", "aria-controls": sidebar.id, "aria-expanded": "false" },
  }, [icono("menu")]);
  const logo = document.querySelector(".sidebar-logo").cloneNode(true);
  logo.className = "barra-movil-logo";
  const barra = crear("div", { clase: "barra-movil", atributos: { id: "barra-movil" } }, [abrir, logo]);
  area.prepend(barra);

  const fondo = crear("div", { clase: "panel-fondo", atributos: { "aria-hidden": "true" } });
  document.body.append(fondo);
  const cerrar = crear("button", { clase: "btn-icono panel-cerrar", atributos: { type: "button", "aria-label": "Cerrar el menú" } }, [icono("cerrar")]);
  sidebar.prepend(cerrar);

  const movil = window.matchMedia("(max-width: 900px)");
  const alternar = (abierto) => {
    document.body.classList.toggle("menu-abierto", abierto);
    abrir.setAttribute("aria-expanded", String(abierto));
    if (abierto) {
      (sidebar.querySelector(".nav a.activo") || cerrar).focus();
    } else if (movil.matches) {
      abrir.focus();
    }
  };
  abrir.addEventListener("click", () => alternar(true));
  cerrar.addEventListener("click", () => alternar(false));
  fondo.addEventListener("click", () => alternar(false));
  document.addEventListener("keydown", (evento) => {
    if (evento.key === "Escape" && document.body.classList.contains("menu-abierto")) alternar(false);
  });
  sidebar.addEventListener("click", (evento) => {
    if (evento.target.closest(".nav a") && movil.matches) document.body.classList.remove("menu-abierto");
  });
  movil.addEventListener("change", () => alternar(false));

  // Modo compacto (solo íconos) en el escritorio.
  const compacto = crear("button", {
    clase: "btn-icono nav-compactar", atributos: { type: "button", "aria-label": "Contraer el menú", title: "Contraer el menú" },
  }, [icono("contraer")]);
  // Fila de herramientas sobre el perfil: campana (si aplica) a la izquierda y "contraer" a la derecha.
  sidebar.querySelector(".perfil").before(crear("div", { clase: "sidebar-herramientas", atributos: { id: "sidebar-herramientas" } }, [compacto]));
  const aplicarCompacto = (activo) => {
    document.body.classList.toggle("menu-compacto", activo);
    const texto = activo ? "Expandir el menú" : "Contraer el menú";
    compacto.setAttribute("aria-label", texto);
    compacto.setAttribute("title", texto);
  };
  aplicarCompacto(Boolean(leerPreferencias().compacto));
  compacto.addEventListener("click", () => {
    const activo = !document.body.classList.contains("menu-compacto");
    aplicarCompacto(activo);
    guardarPreferencias({ compacto: activo });
  });
}

/** E3: campana con el contador de notificaciones no leídas, sobre el perfil (y en la barra del celular). */
async function pintarCampana(archivoActual) {
  const fila = document.getElementById("sidebar-herramientas") || document.querySelector(".perfil");
  if (!fila || document.getElementById("campana")) return;
  const crearCampana = (id) => XPS.crear("a", {
    clase: `campana${archivoActual === "mis-notificaciones.html" ? " activo" : ""}`,
    atributos: { id, href: "mis-notificaciones.html", "aria-label": "Mis notificaciones", title: "Mis notificaciones" },
  }, [icono("campana"), XPS.crear("span", { clase: "campana-contador", atributos: { hidden: "" } })]);
  fila.prepend(crearCampana("campana"));
  const barra = document.getElementById("barra-movil");
  if (barra) barra.append(crearCampana("campana-movil"));
  await actualizarCampana();
}

async function actualizarCampana() {
  const campanas = document.querySelectorAll(".campana");
  if (!campanas.length) return;
  try {
    const { no_leidas: noLeidas } = await XPS.api("/notificaciones/mias/conteo");
    for (const campana of campanas) {
      const contador = campana.querySelector(".campana-contador");
      contador.textContent = noLeidas > 99 ? "99+" : String(noLeidas);
      contador.hidden = noLeidas === 0;
      campana.setAttribute("aria-label", `Mis notificaciones (${noLeidas} sin leer)`);
    }
  } catch {
    for (const contador of document.querySelectorAll(".campana-contador")) contador.hidden = true;
  }
}
