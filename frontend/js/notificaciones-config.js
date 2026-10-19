/* E3 Configuración de notificaciones (notificaciones.reglas.gestionar): interruptor global de avisos a clientes,
 * "aplicar desde", tope semanal y horario hábil; eventos agrupados (clientes, internos, resúmenes) con su regla.
 */
"use strict";

(async () => {
  const { crear } = XPS;
  const alertas = document.getElementById("alertas");
  const formConfig = document.getElementById("form-config");
  const alertasConfig = document.getElementById("alertas-config");
  const dialogo = document.getElementById("dialogo-regla");
  const form = document.getElementById("form-regla");
  const alertasRegla = document.getElementById("alertas-regla");
  const DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"];
  const TIPOS = {
    CONTACTO_COTIZACION: "Contacto de la cotización",
    CONTACTO_PRINCIPAL: "Contacto principal del cliente",
    COMERCIAL: "Comercial de la cotización",
    ACTOR: "Quien lo envió o creó",
  };
  const PARAMETROS = {
    dias: "Días", repeticiones: "Recordatorios", intervalo: "Días entre recordatorios", ventana: "Días de ventana",
    meses: "Meses hacia atrás", dias_nueva: "Días de tarifa nueva", umbral_pct: "Umbral (%)", hora: "Hora del envío",
    dia_semana: "Día de la semana (1 = lunes)", adjuntar_pdf: "Adjuntar el PDF vigente", pasos: "Siguientes pasos (uno por línea)",
  };

  let eventos = [];
  let roles = [];
  let plantillas = [];
  let enEdicion = null;

  // ---------- Interruptor global ----------

  document.getElementById("dias-habiles").replaceChildren(...DIAS.map((dia, i) => {
    const id = `dia-${i + 1}`;
    return crear("label", { clase: "campo-check", atributos: { for: id } }, [
      crear("input", { atributos: { id, type: "checkbox", value: String(i + 1), name: "dias" } }), ` ${dia}`]);
  }));

  function pintarConfig(config) {
    for (const radio of formConfig.querySelectorAll("input[name=modo_externo]")) radio.checked = radio.value === config.modo_externo;
    formConfig.elements.aplicar_desde.value = config.aplicar_desde || "";
    formConfig.elements.tope_semanal_cliente.value = config.tope_semanal_cliente;
    formConfig.elements.hora_desde.value = config.hora_desde;
    formConfig.elements.hora_hasta.value = config.hora_hasta;
    const dias = new Set(config.dias_habiles.split(","));
    for (const casilla of formConfig.querySelectorAll("input[name=dias]")) casilla.checked = dias.has(casilla.value);
    document.getElementById("ultima-evaluacion").textContent = config.ultima_evaluacion
      ? `Última evaluación: ${new Date(config.ultima_evaluacion).toLocaleString("es-EC")}` : "Aún no se ha evaluado.";
  }

  formConfig.addEventListener("submit", async (evento) => {
    evento.preventDefault();
    XPS.limpiarAlerta(alertasConfig);
    const modo = formConfig.querySelector("input[name=modo_externo]:checked").value;
    if (modo === "ACTIVO" && !window.confirm("Con ACTIVO los avisos se envían a los clientes reales. ¿Continuar?")) return;
    const cuerpo = {
      modo_externo: modo,
      aplicar_desde: formConfig.elements.aplicar_desde.value || null,
      tope_semanal_cliente: Number(formConfig.elements.tope_semanal_cliente.value),
      hora_desde: Number(formConfig.elements.hora_desde.value),
      hora_hasta: Number(formConfig.elements.hora_hasta.value),
      dias_habiles: [...formConfig.querySelectorAll("input[name=dias]:checked")].map((c) => c.value).join(","),
    };
    if (cuerpo.aplicar_desde === null) delete cuerpo.aplicar_desde;
    try {
      pintarConfig(await XPS.api("/notificaciones/config", { metodo: "PUT", cuerpo }));
      XPS.mostrarAlerta(alertasConfig, "exito", "Configuración guardada.");
    } catch (error) {
      XPS.mostrarError(alertasConfig, error);
    }
  });

  // ---------- Eventos y reglas ----------

  function resumenDestinatarios(regla) {
    const d = regla.destinatarios || {};
    const partes = [...(d.tipos || []).map((t) => TIPOS[t] || t), ...(d.roles || []).map((r) => `Rol ${(roles.find((x) => x.codigo === r) || { nombre: r }).nombre}`)];
    if ((d.usuarios || []).length) partes.push(`${d.usuarios.length} usuario(s)`);
    partes.push(...(d.correos || []));
    const canales = [regla.canal_correo ? "correo" : null, regla.canal_interno ? "campana" : null].filter(Boolean).join(" y ");
    return `${partes.join(", ") || "—"} · por ${canales}`;
  }

  function filas(lista) {
    const salida = [];
    for (const evento of lista) {
      for (const regla of evento.reglas) {
        const nombre = crear("div", {}, [UI.texto(evento.nombre)]);
        nombre.append(crear("div", { clase: "ayuda", texto: evento.descripcion }));
        salida.push(crear("tr", {}, [
          UI.celda("Evento", [nombre]),
          UI.celda("Regla", [UI.texto(regla.nombre)]),
          UI.celda("Destinatarios", [UI.texto(resumenDestinatarios(regla))]),
          UI.celda("Estado", [UI.badgeEstado(regla.activo)]),
          UI.celda("Acciones", [crear("div", { clase: "celda-acciones" }, [
            UI.boton("Editar", () => abrir(evento, regla)),
            UI.boton(regla.activo ? "Desactivar" : "Activar", () => cambiarEstado(regla)),
          ])]),
        ]));
      }
    }
    return salida.length ? salida : [UI.filaVacia(5, "Sin reglas.")];
  }

  async function cargar() {
    eventos = await XPS.api("/notificaciones/eventos");
    document.getElementById("tabla-externos").replaceChildren(...filas(eventos.filter((e) => e.audiencia === "EXTERNA")));
    document.getElementById("tabla-internos").replaceChildren(...filas(eventos.filter((e) => e.audiencia === "INTERNA" && e.tipo !== "RESUMEN")));
    document.getElementById("tabla-resumenes").replaceChildren(...filas(eventos.filter((e) => e.tipo === "RESUMEN")));
  }

  async function cambiarEstado(regla) {
    XPS.limpiarAlerta(alertas);
    try {
      await XPS.api(`/notificaciones/reglas/${regla.id}`, { metodo: "PATCH", cuerpo: { activo: !regla.activo } });
      await cargar();
    } catch (error) {
      XPS.mostrarError(alertas, error);
    }
  }

  function casilla(nombre, valor, texto, marcada) {
    const id = `${nombre}-${valor}`;
    const input = crear("input", { atributos: { id, type: "checkbox", value: valor, name: nombre } });
    input.checked = marcada;
    return crear("label", { clase: "campo-check", atributos: { for: id } }, [input, ` ${texto}`]);
  }

  function abrir(evento, regla) {
    enEdicion = { evento, regla };
    form.reset();
    XPS.limpiarAlerta(alertasRegla);
    document.getElementById("titulo-regla").textContent = `${evento.nombre}`;
    document.getElementById("regla-descripcion").textContent = `${evento.descripcion} Variables: ${evento.variables.join(", ")}.`;
    form.elements.nombre.value = regla.nombre;
    form.elements.canal_correo.checked = regla.canal_correo;
    form.elements.canal_interno.checked = regla.canal_interno;
    form.elements.canal_interno.disabled = evento.audiencia === "EXTERNA";
    const externo = evento.audiencia === "EXTERNA";
    const tipos = externo ? ["CONTACTO_COTIZACION", "CONTACTO_PRINCIPAL"] : ["COMERCIAL", "ACTOR"];
    const d = regla.destinatarios || {};
    document.getElementById("regla-tipos").replaceChildren(...tipos.map((t) => casilla("tipo", t, TIPOS[t], (d.tipos || []).includes(t))));
    document.getElementById("regla-roles").replaceChildren(...(externo ? [] : roles.filter((r) => r.activo).map(
      (r) => casilla("rol", r.codigo, `Rol ${r.nombre}`, (d.roles || []).includes(r.codigo)))));
    form.elements.correos.value = (d.correos || []).join(", ");
    const parametros = document.getElementById("regla-parametros");
    parametros.replaceChildren();
    for (const [clave, valor] of Object.entries(regla.parametros || {})) {
      const id = `parametro-${clave}`;
      let control;
      if (typeof valor === "boolean") {
        control = crear("input", { atributos: { id, type: "checkbox", "data-parametro": clave, "data-tipo": "bool" } });
        control.checked = valor;
      } else if (Array.isArray(valor)) {
        control = crear("textarea", { clase: "input", atributos: { id, rows: 3, "data-parametro": clave, "data-tipo": "lista" } });
        control.value = valor.join("\n");
      } else {
        control = crear("input", { clase: "input cifra", atributos: { id, type: "number", min: 0, max: 1000, "data-parametro": clave, "data-tipo": "numero" } });
        control.value = valor;
      }
      parametros.append(crear("div", { clase: "campo" }, [crear("label", { texto: PARAMETROS[clave] || clave, atributos: { for: id } }), control]));
    }
    UI.opciones(form.elements.plantilla_id, plantillas, { valor: (p) => p.id, texto: (p) => `${p.nombre} (${p.tencent_id || "sin ID"} · ${p.estado_tencent})`, todos: "Sin plantilla" });
    form.elements.plantilla_id.value = regla.plantilla_id ? String(regla.plantilla_id) : "";
    form.elements.agrupacion.value = regla.agrupacion;
    form.elements.obligatoria.checked = regla.obligatoria;
    form.elements.obligatoria.disabled = externo;
    form.elements.activo.checked = regla.activo;
    dialogo.showModal();
  }

  form.addEventListener("submit", async (evento) => {
    evento.preventDefault();
    XPS.limpiarAlerta(alertasRegla);
    const parametros = {};
    for (const control of document.querySelectorAll("#regla-parametros [data-parametro]")) {
      const tipo = control.dataset.tipo;
      parametros[control.dataset.parametro] = tipo === "bool" ? control.checked
        : tipo === "lista" ? control.value.split("\n").map((l) => l.trim()).filter(Boolean) : Number(control.value);
    }
    const cuerpo = {
      nombre: form.elements.nombre.value.trim(),
      canal_correo: form.elements.canal_correo.checked,
      canal_interno: form.elements.canal_interno.checked,
      destinatarios: {
        tipos: [...form.querySelectorAll("input[name=tipo]:checked")].map((c) => c.value),
        roles: [...form.querySelectorAll("input[name=rol]:checked")].map((c) => c.value),
        usuarios: (enEdicion.regla.destinatarios || {}).usuarios || [],
        correos: form.elements.correos.value.split(/[,;\s]+/).map((c) => c.trim()).filter(Boolean),
      },
      parametros,
      plantilla_id: form.elements.plantilla_id.value ? Number(form.elements.plantilla_id.value) : null,
      agrupacion: form.elements.agrupacion.value,
      obligatoria: form.elements.obligatoria.checked,
      activo: form.elements.activo.checked,
    };
    try {
      await XPS.api(`/notificaciones/reglas/${enEdicion.regla.id}`, { metodo: "PATCH", cuerpo });
      dialogo.close();
      XPS.mostrarAlerta(alertas, "exito", "Regla guardada.");
      await cargar();
    } catch (error) {
      XPS.mostrarError(alertasRegla, error);
    }
  });

  const yo = await iniciarLayout("notificaciones-config.html");
  if (!yo || !UI.exigirAlguno(yo, ["notificaciones.reglas.gestionar"], alertas)) {
    return;
  }
  UI.prepararDialogo(dialogo);
  try {
    const [config, listaRoles, listaPlantillas] = await Promise.all([
      XPS.api("/notificaciones/config"),
      UI.tieneAlguno(yo, ["usuario.admin"]) ? XPS.api("/roles") : Promise.resolve([]),
      UI.tieneAlguno(yo, ["boletines.ver"]) ? XPS.api("/plantillas-correo?uso=AVISO") : Promise.resolve([]),
    ]);
    roles = listaRoles;
    plantillas = listaPlantillas;
    pintarConfig(config);
    await cargar();
    for (const id of ["bloque-config", "bloque-clientes", "bloque-internos", "bloque-resumenes"]) document.getElementById(id).hidden = false;
  } catch (error) {
    XPS.mostrarError(alertas, error);
  }
})();
