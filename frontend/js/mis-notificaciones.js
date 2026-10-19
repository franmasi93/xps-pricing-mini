/* E3 Centro de notificaciones (notificaciones.ver): lista con enlace, marcar leída, "marcar todas" y preferencias. */
"use strict";

(async () => {
  const { crear } = XPS;
  const alertas = document.getElementById("alertas");
  const lista = document.getElementById("lista");
  const soloNoLeidas = document.getElementById("solo-no-leidas");
  const botonTodas = document.getElementById("btn-leer-todas");
  const formPreferencias = document.getElementById("form-preferencias");
  const alertasPreferencias = document.getElementById("alertas-preferencias");

  async function marcar(n) {
    if (!n.leida_en) {
      await XPS.api(`/notificaciones/mias/${n.id}/leida`, { metodo: "POST" });
      if (typeof actualizarCampana === "function") await actualizarCampana();
    }
  }

  async function cargar() {
    const notificaciones = await XPS.api(`/notificaciones/mias${soloNoLeidas.checked ? "?solo_no_leidas=true" : ""}`);
    lista.replaceChildren(...(notificaciones.length ? [] : [crear("li", { clase: "tabla-vacia", texto: "No tiene notificaciones." })]));
    for (const n of notificaciones) {
      const titulo = n.enlace
        ? crear("a", { clase: "notificacion-titulo", texto: n.titulo, atributos: { href: n.enlace.replace(/^\/app\//, "") } })
        : crear("span", { clase: "notificacion-titulo", texto: n.titulo });
      if (n.enlace) titulo.addEventListener("click", () => marcar(n));
      const cuerpo = crear("div", {}, [titulo, crear("div", { clase: "notificacion-texto", texto: n.mensaje }),
        crear("div", { clase: "ayuda", texto: new Date(n.creado_en).toLocaleString("es-EC") })]);
      const acciones = n.leida_en ? [] : [UI.boton("Marcar leída", async () => {
        try {
          await marcar(n);
          await cargar();
        } catch (error) {
          XPS.mostrarError(alertas, error);
        }
      })];
      lista.append(crear("li", { clase: n.leida_en ? "" : "no-leida" }, [cuerpo, crear("div", { clase: "celda-acciones" }, acciones)]));
    }
  }

  async function cargarPreferencias() {
    const preferencias = await XPS.api("/notificaciones/preferencias");
    document.getElementById("lista-preferencias").replaceChildren(...(preferencias.length ? [] : [crear("p", { clase: "ayuda", texto: "No hay avisos internos con correo." })]));
    for (const p of preferencias) {
      const id = `pref-${p.evento}`;
      const casilla = crear("input", { atributos: { id, type: "checkbox", name: "pref", value: p.evento } });
      casilla.checked = p.correo;
      casilla.disabled = p.obligatoria;
      document.getElementById("lista-preferencias").append(crear("label", { clase: "campo-check", atributos: { for: id } }, [
        casilla, ` ${p.nombre}${p.obligatoria ? " (obligatorio)" : ""} `, crear("span", { clase: "ayuda", texto: p.descripcion }),
      ]));
    }
  }

  formPreferencias.addEventListener("submit", async (evento) => {
    evento.preventDefault();
    XPS.limpiarAlerta(alertasPreferencias);
    const correo = Object.fromEntries([...formPreferencias.querySelectorAll("input[name=pref]:not(:disabled)")].map((c) => [c.value, c.checked]));
    try {
      await XPS.api("/notificaciones/preferencias", { metodo: "PUT", cuerpo: { correo } });
      XPS.mostrarAlerta(alertasPreferencias, "exito", "Preferencias guardadas.");
      await cargarPreferencias();
    } catch (error) {
      XPS.mostrarError(alertasPreferencias, error);
    }
  });

  const yo = await iniciarLayout("mis-notificaciones.html");
  if (!yo || !UI.exigirAlguno(yo, ["notificaciones.ver"], alertas)) {
    return;
  }
  soloNoLeidas.addEventListener("change", () => cargar().catch((error) => XPS.mostrarError(alertas, error)));
  botonTodas.addEventListener("click", async () => {
    try {
      await XPS.api("/notificaciones/mias/leer-todas", { metodo: "POST" });
      if (typeof actualizarCampana === "function") await actualizarCampana();
      await cargar();
    } catch (error) {
      XPS.mostrarError(alertas, error);
    }
  });
  try {
    await Promise.all([cargar(), cargarPreferencias()]);
    document.getElementById("bloque-lista").hidden = false;
    document.getElementById("bloque-preferencias").hidden = false;
    botonTodas.hidden = false;
  } catch (error) {
    XPS.mostrarError(alertas, error);
  }
})();
