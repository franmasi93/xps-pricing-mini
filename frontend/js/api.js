/* Cliente de la API /v1, manejo del token y utilidades de DOM seguras.
 * Todo dato del servidor o del usuario se pinta con textContent / createElement.
 */
"use strict";

const XPS = (() => {
  const CLAVE_TOKEN = "xps_pricing_token";
  const RUTA_LOGIN = "/app/login.html";
  const RUTA_CAMBIO = "/app/cambiar-password.html";
  const MENSAJE_GENERICO = "Ocurrió un error inesperado. Intente nuevamente.";

  // ---------- Token (sessionStorage: se borra al cerrar la pestaña) ----------

  function obtenerToken() {
    try {
      return sessionStorage.getItem(CLAVE_TOKEN);
    } catch {
      return null;
    }
  }

  function guardarToken(token) {
    try {
      sessionStorage.setItem(CLAVE_TOKEN, token);
    } catch {
      /* Sin almacenamiento disponible: la sesión no persiste entre pantallas. */
    }
  }

  function borrarToken() {
    try {
      sessionStorage.removeItem(CLAVE_TOKEN);
    } catch {
      /* Nada que borrar. */
    }
  }

  function irA(ruta) {
    window.location.replace(ruta);
  }

  function salir() {
    borrarToken();
    irA(RUTA_LOGIN);
  }

  // ---------- Errores ----------

  class ErrorApi extends Error {
    constructor(status, codigo, mensaje, redirigiendo = false) {
      super(mensaje);
      this.status = status;
      this.codigo = codigo;
      this.redirigiendo = redirigiendo;
    }
  }

  function interpretarError(datos) {
    const detalle = datos && datos.detail;
    if (detalle && typeof detalle === "object" && !Array.isArray(detalle) && typeof detalle.mensaje === "string") {
      return { codigo: typeof detalle.codigo === "string" ? detalle.codigo : null, mensaje: detalle.mensaje };
    }
    if (Array.isArray(detalle)) {
      // 422 de validación de FastAPI: se nombran los campos, nunca el cuerpo crudo.
      const campos = detalle
        .map((error) => (Array.isArray(error.loc) ? error.loc[error.loc.length - 1] : null))
        .filter((campo) => typeof campo === "string" && campo !== "body");
      const lista = [...new Set(campos)].join(", ");
      return {
        codigo: "VALIDACION",
        mensaje: lista ? `Revise los datos ingresados: ${lista}.` : "Revise los datos ingresados.",
      };
    }
    return { codigo: null, mensaje: MENSAJE_GENERICO };
  }

  // ---------- Llamada a la API ----------

  async function api(ruta, { metodo = "GET", cuerpo, manejar401 = true } = {}) {
    const headers = { Accept: "application/json" };
    const token = obtenerToken();
    if (token) {
      headers.Authorization = `Bearer ${token}`;
    }
    if (cuerpo !== undefined) {
      headers["Content-Type"] = "application/json";
    }

    let respuesta;
    try {
      respuesta = await fetch(`/v1${ruta}`, {
        method: metodo,
        headers,
        body: cuerpo !== undefined ? JSON.stringify(cuerpo) : undefined,
      });
    } catch {
      throw new ErrorApi(0, "SIN_CONEXION", "No se pudo conectar con el servidor. Revise su conexión.");
    }

    let datos = null;
    try {
      datos = await respuesta.json();
    } catch {
      datos = null;
    }
    if (respuesta.ok) {
      return datos;
    }

    const { codigo, mensaje } = interpretarError(datos);
    if (respuesta.status === 401 && manejar401) {
      borrarToken();
      irA(RUTA_LOGIN);
      throw new ErrorApi(401, codigo, mensaje, true);
    }
    if (respuesta.status === 403 && codigo === "PASSWORD_CAMBIO_REQUERIDO") {
      irA(RUTA_CAMBIO);
      throw new ErrorApi(403, codigo, mensaje, true);
    }
    throw new ErrorApi(respuesta.status, codigo, mensaje);
  }

  // ---------- DOM seguro ----------

  function crear(etiqueta, { clase, texto, atributos } = {}, hijos = []) {
    const elemento = document.createElement(etiqueta);
    if (clase) {
      elemento.className = clase;
    }
    if (texto !== undefined && texto !== null) {
      elemento.textContent = String(texto);
    }
    if (atributos) {
      for (const [nombre, valor] of Object.entries(atributos)) {
        elemento.setAttribute(nombre, String(valor));
      }
    }
    for (const hijo of hijos) {
      elemento.append(hijo);
    }
    return elemento;
  }

  function mostrarAlerta(contenedor, tipo, mensaje) {
    contenedor.replaceChildren(crear("div", { clase: `alerta alerta-${tipo}`, texto: mensaje, atributos: { role: "alert" } }));
    contenedor.hidden = false;
  }

  function limpiarAlerta(contenedor) {
    contenedor.replaceChildren();
    contenedor.hidden = true;
  }

  function mostrarError(contenedor, error) {
    if (error instanceof ErrorApi && error.redirigiendo) {
      return;
    }
    const mensaje = error instanceof ErrorApi ? error.message : MENSAJE_GENERICO;
    mostrarAlerta(contenedor, "error", mensaje);
  }

  function formatearFecha(valor) {
    if (!valor) {
      return "—";
    }
    const fecha = new Date(valor);
    if (Number.isNaN(fecha.getTime())) {
      return "—";
    }
    return fecha.toLocaleString("es-EC", { dateStyle: "short", timeStyle: "short" });
  }

  // ---------- Política de contraseña (la real la valida el backend) ----------

  const POLITICA_PASSWORD = "Entre 10 y 128 caracteres, con al menos una letra y un número.";

  function passwordCumplePolitica(password) {
    return password.length >= 10 && password.length <= 128 && /\p{L}/u.test(password) && /\p{Nd}/u.test(password);
  }

  return {
    RUTA_LOGIN,
    RUTA_CAMBIO,
    POLITICA_PASSWORD,
    ErrorApi,
    api,
    obtenerToken,
    guardarToken,
    borrarToken,
    irA,
    salir,
    crear,
    mostrarAlerta,
    limpiarAlerta,
    mostrarError,
    formatearFecha,
    passwordCumplePolitica,
  };
})();
