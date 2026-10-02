/* Pantalla de login, con opción de cambiar la contraseña antes de ingresar.
 * El cambio reutiliza la API existente: login con la contraseña actual (sujeto al
 * bloqueo por intentos) y luego /auth/cambiar-password con ese token.
 */
"use strict";

(() => {
  const alertas = document.getElementById("alertas");
  const titulo = document.getElementById("titulo-panel");
  const bajada = document.getElementById("bajada-panel");

  const formLogin = document.getElementById("form-login");
  const botonIngresar = document.getElementById("btn-ingresar");
  const campoPassword = formLogin.elements.password;
  const botonMostrar = document.getElementById("btn-mostrar");
  const avisoMayus = document.getElementById("aviso-mayus");

  const formCambio = document.getElementById("form-cambio");
  const botonCambiar = document.getElementById("btn-cambiar");
  document.getElementById("cambio-politica").textContent = XPS.POLITICA_PASSWORD;

  const TEXTOS = {
    login: ["Iniciar sesión", "Use el email y la contraseña que le asignó el administrador."],
    cambio: ["Cambiar contraseña", "Ingrese su contraseña actual y elija una nueva."],
  };

  function mostrarVista(vista) {
    XPS.limpiarAlerta(alertas);
    const enCambio = vista === "cambio";
    formLogin.hidden = enCambio;
    formCambio.hidden = !enCambio;
    [titulo.textContent, bajada.textContent] = TEXTOS[vista];
    if (enCambio) {
      formCambio.elements.email.value = formLogin.elements.email.value.trim();
      (formCambio.elements.email.value ? formCambio.elements.actual : formCambio.elements.email).focus();
    } else {
      formCambio.reset();
      formLogin.elements.email.focus();
    }
  }

  document.getElementById("btn-ir-cambio").addEventListener("click", () => mostrarVista("cambio"));
  document.getElementById("btn-ir-login").addEventListener("click", () => mostrarVista("login"));

  // ---------- Mostrar contraseña y Bloq Mayús ----------

  botonMostrar.addEventListener("click", () => {
    const mostrar = campoPassword.type === "password";
    campoPassword.type = mostrar ? "text" : "password";
    botonMostrar.textContent = mostrar ? "Ocultar" : "Mostrar";
    botonMostrar.setAttribute("aria-pressed", String(mostrar));
    campoPassword.focus();
  });

  const revisarMayus = (evento) => {
    if (typeof evento.getModifierState === "function") {
      avisoMayus.hidden = !evento.getModifierState("CapsLock");
    }
  };
  campoPassword.addEventListener("keyup", revisarMayus);
  campoPassword.addEventListener("keydown", revisarMayus);
  campoPassword.addEventListener("blur", () => {
    avisoMayus.hidden = true;
  });

  // ---------- Errores del login (comunes a ambas vistas) ----------

  function mostrarErrorLogin(error) {
    if (error instanceof XPS.ErrorApi && error.status === 401) {
      XPS.mostrarAlerta(alertas, "error", "Credenciales inválidas");
    } else {
      // 429: el mensaje del servidor indica los minutos de bloqueo.
      XPS.mostrarError(alertas, error);
    }
  }

  async function iniciarSesion(email, password) {
    return XPS.api("/auth/login", { metodo: "POST", cuerpo: { email, password }, manejar401: false });
  }

  // ---------- Ingresar ----------

  formLogin.addEventListener("submit", async (evento) => {
    evento.preventDefault();
    XPS.limpiarAlerta(alertas);

    const email = formLogin.elements.email.value.trim();
    const password = campoPassword.value;
    if (!email || !password) {
      XPS.mostrarAlerta(alertas, "error", "Ingrese su email y su contraseña.");
      return;
    }

    botonIngresar.disabled = true;
    botonIngresar.textContent = "Ingresando…";
    try {
      const respuesta = await iniciarSesion(email, password);
      XPS.guardarToken(respuesta.access_token);
      XPS.irA(respuesta.forzar_cambio_password ? XPS.RUTA_CAMBIO : "/app/inicio.html");
    } catch (error) {
      mostrarErrorLogin(error);
      campoPassword.value = "";
      campoPassword.focus();
      botonIngresar.disabled = false;
      botonIngresar.textContent = "Ingresar";
    }
  });

  // ---------- Cambiar contraseña e ingresar ----------

  formCambio.addEventListener("submit", async (evento) => {
    evento.preventDefault();
    XPS.limpiarAlerta(alertas);

    const email = formCambio.elements.email.value.trim();
    const actual = formCambio.elements.actual.value;
    const nueva = formCambio.elements.nueva.value;
    const confirmacion = formCambio.elements.confirmacion.value;

    if (!email || !actual || !nueva || !confirmacion) {
      XPS.mostrarAlerta(alertas, "error", "Complete todos los campos.");
      return;
    }
    if (nueva !== confirmacion) {
      XPS.mostrarAlerta(alertas, "error", "La confirmación no coincide con la nueva contraseña.");
      return;
    }
    if (!XPS.passwordCumplePolitica(nueva)) {
      XPS.mostrarAlerta(alertas, "error", `La nueva contraseña no cumple la política: ${XPS.POLITICA_PASSWORD}`);
      return;
    }

    botonCambiar.disabled = true;
    botonCambiar.textContent = "Cambiando…";
    try {
      let sesion;
      try {
        sesion = await iniciarSesion(email, actual);
      } catch (error) {
        mostrarErrorLogin(error);
        formCambio.elements.actual.value = "";
        formCambio.elements.actual.focus();
        return;
      }

      XPS.guardarToken(sesion.access_token);
      try {
        const cambio = await XPS.api("/auth/cambiar-password", {
          metodo: "POST",
          cuerpo: { password_actual: actual, password_nueva: nueva },
        });
        XPS.guardarToken(cambio.access_token);
        XPS.irA("/app/inicio.html");
      } catch (error) {
        // El cambio no se aplicó: no se deja una sesión abierta a medias.
        XPS.borrarToken();
        XPS.mostrarError(alertas, error);
      }
    } finally {
      botonCambiar.disabled = false;
      botonCambiar.textContent = "Cambiar contraseña e ingresar";
    }
  });
})();
