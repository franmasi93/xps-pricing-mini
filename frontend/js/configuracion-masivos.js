/* E1 Configuración → Envíos masivos (solo usuario.admin): remitente (elegido de los remitentes de la cuenta), lotes,
 * pausa, topes, reserva para cotizaciones y avisos, horario, calentamiento, PDF por defecto, correos de prueba y texto
 * legal. Muestra los cupos de hoy.
 */
"use strict";

(async () => {
  const { crear } = XPS;
  const form = document.getElementById("form-masivos");
  const alertas = document.getElementById("alertas-masivos");
  const NUMEROS = ["tamano_lote", "pausa_segundos", "tope_diario", "tope_hora", "reserva_pct", "limite_filas", "hora_desde",
    "hora_hasta", "calentamiento_inicio", "calentamiento_incremento"];
  const TEXTOS = ["reply_to", "dias_envio", "correos_prueba", "texto_legal"];
  let actual = null;

  function contador(etiqueta, valor) {
    return crear("div", { clase: "contador" }, [crear("strong", { texto: String(valor) }), crear("span", { clase: "texto-suave", texto: etiqueta })]);
  }

  function pintar(datos) {
    actual = datos;
    for (const campo of [...NUMEROS, ...TEXTOS]) form.elements[campo].value = datos[campo] ?? "";
    form.elements.adjuntar_pdf.checked = datos.adjuntar_pdf;
    form.elements.calentamiento.checked = datos.calentamiento;
    if (![...form.elements.remitente.options].some((o) => o.value === datos.remitente)) {
      form.elements.remitente.append(crear("option", { texto: datos.remitente || "(sin remitente)", atributos: { value: datos.remitente || "" } }));
    }
    form.elements.remitente.value = datos.remitente || "";
    document.getElementById("cupos-masivos").replaceChildren(
      contador("tope diario efectivo", datos.tope_diario_efectivo), contador("cupo de boletines hoy", datos.cupo_boletines_hoy),
      contador("enviados hoy (total)", datos.enviados_hoy.total), contador("en la última hora", datos.enviados_ultima_hora),
      contador("en horario de envío", datos.en_horario ? "Sí" : "No"));
  }

  form.addEventListener("submit", async (evento) => {
    evento.preventDefault();
    XPS.limpiarAlerta(alertas);
    const cambios = {};
    for (const campo of NUMEROS) {
      const valor = Number(form.elements[campo].value);
      if (valor !== actual[campo]) cambios[campo] = valor;
    }
    for (const campo of [...TEXTOS, "remitente"]) {
      const valor = form.elements[campo].value.trim();
      if (valor !== (actual[campo] || "")) cambios[campo] = valor;
    }
    for (const campo of ["adjuntar_pdf", "calentamiento"]) {
      if (form.elements[campo].checked !== actual[campo]) cambios[campo] = form.elements[campo].checked;
    }
    try {
      if (Object.keys(cambios).length) pintar(await XPS.api("/correo/masivos", { metodo: "PUT", cuerpo: cambios }));
      XPS.mostrarAlerta(alertas, "exito", "Envíos masivos guardados.");
    } catch (error) {
      XPS.mostrarError(alertas, error);
    }
  });

  try {
    const yo = await XPS.api("/auth/yo");
    if (!yo.permisos.includes("usuario.admin")) return;
    const datos = await XPS.api("/correo/masivos");
    const remitentes = new Set([datos.remitente].filter(Boolean));
    try {
      const config = await XPS.api("/correo/config");
      if (config.remitente) remitentes.add(config.remitente);
    } catch (error) {
      XPS.mostrarError(alertas, error);
    }
    remitentes.add("XPRESS LOGISTICS <tarifas@notificaciones.xpress.ec>");
    UI.opciones(form.elements.remitente, [...remitentes].map((r) => ({ r })), { valor: (x) => x.r, texto: (x) => x.r });
    pintar(datos);
    document.getElementById("bloque-masivos").hidden = false;
  } catch (error) {
    XPS.mostrarError(alertas, error);
  }
})();
