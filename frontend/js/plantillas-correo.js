/* E1 Plantillas de correo (solo administrador): catálogo sincronizado con Tencent. Crear o editar el HTML lo carga en
 * Tencent (vuelve a revisión); sin permiso de la llave, se registra el ID a mano. Las variables se detectan de los {{…}}.
 */
"use strict";

(async () => {
  const { crear } = XPS;
  const alertas = document.getElementById("alertas");
  const cuerpo = document.getElementById("tabla-plantillas");
  const dialogo = document.getElementById("dialogo-plantilla");
  const form = document.getElementById("form-plantilla");
  const alertasDialogo = document.getElementById("alertas-plantilla");
  const ESTADOS = {
    SIN_REGISTRAR: ["badge badge-estado badge-inactivo", "Sin registrar"],
    EN_REVISION: ["badge badge-estado badge-alerta", "En revisión"],
    APROBADA: ["badge badge-estado badge-activo", "Aprobada"],
    RECHAZADA: ["badge badge-estado badge-critico", "Rechazada"],
    NO_ENCONTRADA: ["badge badge-estado badge-critico", "No encontrada"],
  };
  const USOS = { COTIZACION: "Cotización", BOLETIN: "Boletín", AVISO: "Aviso" };
  let puedeEditar = false;
  let enEdicion = null;

  const detectar = (html) => [...new Set([...(html || "").matchAll(/\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}/g)].map((m) => m[1]))];

  async function cargar() {
    const lista = await XPS.api(UI.consulta("/plantillas-correo", { uso: document.getElementById("filtro-uso").value }));
    cuerpo.replaceChildren(...(lista.length ? [] : [UI.filaVacia(7, "No hay plantillas con este filtro.")]));
    for (const plantilla of lista) {
      const [clase, texto] = ESTADOS[plantilla.estado_tencent] || ["badge badge-estado", plantilla.estado_tencent];
      const estado = crear("div", {}, [crear("span", { clase, texto })]);
      if (plantilla.motivo_tencent) estado.append(crear("div", { clase: "ayuda", texto: plantilla.motivo_tencent }));
      const acciones = puedeEditar ? [UI.boton("Editar", () => abrir(plantilla)),
        UI.boton(plantilla.activo ? "Desactivar" : "Activar", () => seguro(async () => {
          await XPS.api(`/plantillas-correo/${plantilla.id}`, { metodo: "PATCH", cuerpo: { activo: !plantilla.activo } });
          await cargar();
        }))] : [];
      cuerpo.append(crear("tr", {}, [
        UI.celda("Plantilla", [crear("div", {}, [UI.texto(plantilla.nombre), crear("div", { clase: "texto-suave", texto: plantilla.evento_o_servicio || "" })])]),
        UI.celda("Uso", [UI.texto(USOS[plantilla.uso] || plantilla.uso)]),
        UI.celda("ID Tencent", [UI.texto(plantilla.tencent_id ? String(plantilla.tencent_id) : null, "cifra")]),
        UI.celda("Estado en Tencent", [estado]),
        UI.celda("Variables", [UI.texto(plantilla.variables_esperadas.join(", "))]),
        UI.celda("Activa", [UI.badgeEstado(plantilla.activo)]),
        UI.celda("Acciones", [crear("div", { clase: "celda-acciones" }, acciones)]),
      ]));
    }
  }

  async function seguro(funcion, contenedor = alertas) {
    try {
      await funcion();
    } catch (error) {
      XPS.mostrarError(contenedor, error);
    }
  }

  function mostrarVariables() {
    const variables = detectar(form.elements.html.value);
    document.getElementById("variables-detectadas").textContent = variables.length
      ? `Variables detectadas (${variables.length} de 40): ${variables.join(", ")}`
      : "Sin variables detectadas.";
    document.getElementById("aviso-revision").hidden = !(enEdicion && enEdicion.tencent_id && form.elements.html.value !== (enEdicion.html || ""));
  }

  function abrir(plantilla = null) {
    enEdicion = plantilla;
    form.reset();
    XPS.limpiarAlerta(alertasDialogo);
    document.getElementById("titulo-plantilla").textContent = plantilla ? `Editar ${plantilla.nombre}` : "Nueva plantilla";
    if (plantilla) {
      for (const campo of ["nombre", "uso", "diseno", "evento_o_servicio", "asunto_sugerido", "html", "notas"]) {
        form.elements[campo].value = plantilla[campo] ?? "";
      }
      form.elements.tencent_id.value = plantilla.tencent_id ?? "";
    }
    mostrarVariables();
    dialogo.showModal();
  }

  form.elements.html.addEventListener("input", mostrarVariables);
  form.addEventListener("submit", (evento) => {
    evento.preventDefault();
    seguro(async () => {
      const datos = {};
      for (const campo of ["nombre", "uso", "diseno", "evento_o_servicio", "asunto_sugerido", "html", "notas"]) {
        datos[campo] = form.elements[campo].value.trim() || null;
      }
      datos.tencent_id = Number(form.elements.tencent_id.value) || null;
      let respuesta;
      if (enEdicion) {
        const cambios = {};
        for (const [campo, valor] of Object.entries(datos)) {
          if ((valor ?? null) !== (enEdicion[campo] ?? null)) cambios[campo] = valor;
        }
        if (cambios.html !== undefined && enEdicion.tencent_id
            && !window.confirm("Editar el HTML lo actualiza en Tencent y la plantilla vuelve a revisión. ¿Continuar?")) return;
        respuesta = Object.keys(cambios).length
          ? await XPS.api(`/plantillas-correo/${enEdicion.id}`, { metodo: "PATCH", cuerpo: cambios })
          : { avisos: [] };
      } else {
        respuesta = await XPS.api("/plantillas-correo", { metodo: "POST", cuerpo: datos });
      }
      dialogo.close();
      XPS.mostrarAlerta(alertas, "exito", ["Plantilla guardada.", ...(respuesta.avisos || [])].join(" "));
      await cargar();
    }, alertasDialogo);
  });

  const yo = await iniciarLayout("plantillas-correo.html");
  if (!yo || !UI.exigirAlguno(yo, ["boletines.ver"], alertas)) {
    return;
  }
  puedeEditar = UI.tieneAlguno(yo, ["usuario.admin"]);
  UI.prepararDialogo(dialogo);
  const botonNueva = document.getElementById("btn-nueva");
  botonNueva.addEventListener("click", () => abrir());
  document.getElementById("filtro-uso").addEventListener("change", () => seguro(cargar));
  document.getElementById("btn-sincronizar").addEventListener("click", () => seguro(async () => {
    const resultado = await XPS.api("/plantillas-correo/sincronizar", { metodo: "POST" });
    XPS.mostrarAlerta(alertas, "exito", `Sincronizadas: ${resultado.sincronizadas} · importadas: ${resultado.importadas}.`);
    await cargar();
  }));
  document.getElementById("btn-sincronizar").hidden = !puedeEditar;
  await seguro(cargar);
  document.getElementById("herramientas").hidden = false;
  botonNueva.hidden = !puedeEditar;
})();
