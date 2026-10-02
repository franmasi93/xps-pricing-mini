/* Cambio de la propia contraseña. Única pantalla permitida con forzar_cambio_password. */
"use strict";

(async () => {
  const formulario = document.getElementById("form-cambio");
  const alertas = document.getElementById("alertas");
  const avisoForzado = document.getElementById("aviso-forzado");
  const boton = document.getElementById("btn-guardar");
  document.getElementById("politica").textContent = XPS.POLITICA_PASSWORD;

  const yo = await iniciarLayout("cambiar-password.html", { permitirForzado: true });
  if (!yo) {
    return;
  }
  if (yo.forzar_cambio_password) {
    XPS.mostrarAlerta(avisoForzado, "aviso", "Debe cambiar su contraseña temporal antes de continuar.");
  }

  formulario.addEventListener("submit", async (evento) => {
    evento.preventDefault();
    XPS.limpiarAlerta(alertas);

    const actual = formulario.elements.actual.value;
    const nueva = formulario.elements.nueva.value;
    const confirmacion = formulario.elements.confirmacion.value;

    if (!actual || !nueva || !confirmacion) {
      XPS.mostrarAlerta(alertas, "error", "Complete los tres campos.");
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

    boton.disabled = true;
    try {
      const respuesta = await XPS.api("/auth/cambiar-password", {
        metodo: "POST",
        cuerpo: { password_actual: actual, password_nueva: nueva },
      });
      XPS.guardarToken(respuesta.access_token);
      formulario.reset();
      XPS.limpiarAlerta(avisoForzado);
      XPS.mostrarAlerta(alertas, "exito", "Contraseña actualizada. Redirigiendo al inicio…");
      window.setTimeout(() => XPS.irA("/app/inicio.html"), 1200);
    } catch (error) {
      XPS.mostrarError(alertas, error);
      boton.disabled = false;
    }
  });
})();
