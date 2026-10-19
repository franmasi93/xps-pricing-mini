/* Configuración: cada clave trae `editable` según el permiso del usuario (lo decide el backend).
 * Admin edita todo; pricing solo los días de alerta de vencimiento.
 * F4 (C8): datos de la empresa para el PDF (config.editar) y correo Tencent (usuario.admin). Las llaves del
 * correo nunca llegan en claro: el backend las devuelve enmascaradas y aquí solo se escriben.
 */
"use strict";

(async () => {
  const { crear } = XPS;
  const alertas = document.getElementById("alertas");
  const lista = document.getElementById("lista-config");

  const DESCRIPCIONES = {
    iva_tasa: ["Tasa de IVA (%)", "Entre 0 y 100, con hasta 2 decimales. Se aplica al bloque Factura."],
    dias_alerta_vencimiento: ["Días de alerta de vencimiento", "Entre 1 y 365. Marca las tarifas que están por vencer."],
    condiciones_generales_pdf: ["Condiciones generales del PDF", "Texto que se imprime en las cotizaciones."],
    firma_correo: ["Firma del correo", "Firma de los correos con cotizaciones."],
  };

  function campoValor(config, id) {
    const atributos = { id, name: "valor", autocomplete: "off" };
    if (config.tipo === "TEXTO") {
      const area = crear("textarea", { clase: "input", atributos: { ...atributos, maxlength: 5000, rows: 4 } });
      area.value = config.valor;
      return area;
    }
    const entrada = crear("input", {
      clase: "input cifra",
      atributos: { ...atributos, type: "text", inputmode: config.tipo === "ENTERO" ? "numeric" : "decimal" },
    });
    entrada.value = config.valor;
    return entrada;
  }

  function pintar(configuraciones) {
    lista.replaceChildren();
    for (const config of configuraciones) {
      const [titulo, ayuda] = DESCRIPCIONES[config.clave] || [config.clave, ""];
      const id = `config-${config.clave}`;
      const alertaItem = crear("div", { atributos: { hidden: "" } });
      const bloque = crear("div", { clase: "config-item" }, [alertaItem]);

      if (config.editable) {
        const form = crear("form", { atributos: { novalidate: "" } });
        const valor = campoValor(config, id);
        form.append(
          crear("div", { clase: "campo" }, [
            crear("label", { texto: titulo, atributos: { for: id } }),
            valor,
            crear("span", { clase: "ayuda", texto: ayuda }),
          ]),
          crear("div", { clase: "config-acciones" }, [
            crear("button", { clase: "btn btn-secundario btn-chico", texto: "Guardar", atributos: { type: "submit" } }),
          ])
        );
        form.addEventListener("submit", async (evento) => {
          evento.preventDefault();
          XPS.limpiarAlerta(alertaItem);
          try {
            const guardado = await XPS.api(`/configuracion/${config.clave}`, {
              metodo: "PATCH",
              cuerpo: { valor: valor.value },
            });
            valor.value = guardado.valor;
            XPS.mostrarAlerta(alertaItem, "exito", "Guardado.");
          } catch (error) {
            XPS.mostrarError(alertaItem, error);
          }
        });
        bloque.append(form);
      } else {
        bloque.append(
          crear("div", { clase: "campo" }, [
            crear("span", { clase: "etiqueta", texto: titulo }),
            crear("span", { clase: config.tipo === "TEXTO" ? "" : "cifra", texto: config.valor }),
            crear("span", { clase: "ayuda", texto: "Solo lectura para su rol." }),
          ])
        );
      }
      lista.append(bloque);
    }
  }

  // ---------- Datos de la empresa para el PDF (A4) ----------

  const CAMPOS_EMPRESA = [
    ["empresa_departamento", "Departamento"],
    ["empresa_ciudad", "Ciudad"],
    ["empresa_telefono", "Teléfono"],
    ["empresa_celular", "Celular"],
    ["empresa_whatsapp", "WhatsApp"],
    ["empresa_horario", "Horario de atención"],
    ["empresa_direccion_matriz", "Dirección de la matriz"],
    ["pago_banco", "Banco"],
    ["pago_titular", "Titular de la cuenta"],
    ["pago_tipo_cuenta", "Tipo de cuenta"],
    ["pago_numero_cuenta", "Número de cuenta"],
    ["pago_ruc", "RUC para el pago"],
    ["clausula_fundamental", "Cláusula fundamental"],
    ["texto_legal_pie", "Texto legal del pie"],
  ];
  const LARGOS = new Set(["empresa_horario", "empresa_direccion_matriz", "clausula_fundamental", "texto_legal_pie"]);

  async function iniciarEmpresa() {
    const datos = await XPS.api("/configuracion/empresa");
    const campos = CAMPOS_EMPRESA.map(([clave, titulo]) => {
      const id = `empresa-${clave}`;
      const control = LARGOS.has(clave)
        ? crear("textarea", { clase: "input", atributos: { id, name: clave, maxlength: 2000, rows: 2 } })
        : crear("input", { clase: "input", atributos: { id, name: clave, type: "text", maxlength: 2000 } });
      control.value = datos[clave] || "";
      return crear("div", { clase: "campo" }, [crear("label", { texto: titulo, atributos: { for: id } }), control]);
    });
    document.getElementById("campos-empresa").replaceChildren(...campos);
    const form = document.getElementById("form-empresa");
    const alertasEmpresa = document.getElementById("alertas-empresa");
    // E1: whatsapp_numero se calcula del WhatsApp (sin espacios, guiones, paréntesis ni "+"; 593 si no trae código).
    const previaWhatsapp = crear("p", { clase: "ayuda", atributos: { id: "previa-whatsapp" } });
    form.elements.empresa_whatsapp.closest(".campo").append(previaWhatsapp);
    const numeroWhatsapp = (texto) => {
      let digitos = (texto || "").replace(/[\s\-()+.]/g, "");
      if (!digitos || digitos.startsWith("593")) return digitos;
      if (digitos.startsWith("0")) return `593${digitos.slice(1)}`;
      return digitos.length <= 9 ? `593${digitos}` : digitos;
    };
    const pintarWhatsapp = (enlace) => {
      const numero = numeroWhatsapp(form.elements.empresa_whatsapp.value);
      const valido = /^\d+$/.test(numero) && (numero.startsWith("593") ? numero.length === 12 : numero.length >= 11 && numero.length <= 15);
      previaWhatsapp.replaceChildren();
      if (!numero) return;
      if (!valido) {
        previaWhatsapp.textContent = "Este número no forma un enlace de WhatsApp válido.";
        return;
      }
      const url = enlace || `https://wa.me/${numero}`;
      previaWhatsapp.append("Enlace para probar: ", crear("a", { texto: url, atributos: { href: url, target: "_blank", rel: "noopener" } }));
    };
    form.elements.empresa_whatsapp.addEventListener("input", () => pintarWhatsapp(null));
    pintarWhatsapp(datos.whatsapp_enlace);
    form.addEventListener("submit", async (evento) => {
      evento.preventDefault();
      XPS.limpiarAlerta(alertasEmpresa);
      const cuerpo = Object.fromEntries(CAMPOS_EMPRESA.map(([clave]) => [clave, form.elements[clave].value]));
      try {
        const guardado = await XPS.api("/configuracion/empresa", { metodo: "PUT", cuerpo });
        for (const [clave] of CAMPOS_EMPRESA) form.elements[clave].value = guardado[clave];
        pintarWhatsapp(guardado.whatsapp_enlace);
        XPS.mostrarAlerta(alertasEmpresa, "exito", "Datos de la empresa guardados.");
      } catch (error) {
        XPS.mostrarError(alertasEmpresa, error);
      }
    });
    document.getElementById("bloque-empresa").hidden = false;
  }

  // ---------- E4: URL pública del sistema ----------

  async function iniciarSistema() {
    const form = document.getElementById("form-sistema");
    const alertasSistema = document.getElementById("alertas-sistema");
    form.elements.url_publica.value = (await XPS.api("/configuracion/sistema")).url_publica;
    form.addEventListener("submit", async (evento) => {
      evento.preventDefault();
      XPS.limpiarAlerta(alertasSistema);
      const url = form.elements.url_publica.value.trim().replace(/\/+$/, "");
      if (!window.confirm(`Todos los enlaces nuevos saldrán con ${url}. ¿El sistema ya abre en esa dirección con HTTPS?`)) return;
      try {
        form.elements.url_publica.value = (await XPS.api("/configuracion/sistema", { metodo: "PUT", cuerpo: { url_publica: url } })).url_publica;
        XPS.mostrarAlerta(alertasSistema, "exito", "URL pública guardada.");
      } catch (error) {
        XPS.mostrarError(alertasSistema, error);
      }
    });
    document.getElementById("bloque-sistema").hidden = false;
  }

  // ---------- E2: textos del PDF y advertencias de Incoterm ----------

  const CAMPOS_TEXTOS_PDF = [
    ["aceptacion_titulo", "Título de la aceptación"],
    ["aceptacion_texto", "Frase de aceptación"],
    ["firma_fecha", "Línea de la fecha"],
    ["firma_firma", "Línea de la firma"],
    ["firma_sello", "Línea del sello"],
    ["advertencia_ddp", "Advertencia DDP en importación"],
    ["advertencia_exw", "Advertencia EXW en exportación"],
  ];
  const TEXTOS_LARGOS = new Set(["aceptacion_texto", "advertencia_ddp", "advertencia_exw"]);

  async function iniciarTextosPdf() {
    const datos = await XPS.api("/textos-pdf");
    const campos = CAMPOS_TEXTOS_PDF.map(([clave, titulo]) => {
      const id = `textos-${clave}`;
      const control = TEXTOS_LARGOS.has(clave)
        ? crear("textarea", { clase: "input", atributos: { id, name: clave, maxlength: 1000, rows: 2, required: "" } })
        : crear("input", { clase: "input", atributos: { id, name: clave, type: "text", maxlength: 1000, required: "" } });
      control.value = datos[clave] || "";
      return crear("div", { clase: "campo" }, [crear("label", { texto: titulo, atributos: { for: id } }), control]);
    });
    document.getElementById("campos-textos-pdf").replaceChildren(...campos);
    const form = document.getElementById("form-textos-pdf");
    const alertasTextos = document.getElementById("alertas-textos-pdf");
    form.addEventListener("submit", async (evento) => {
      evento.preventDefault();
      XPS.limpiarAlerta(alertasTextos);
      const cuerpo = Object.fromEntries(CAMPOS_TEXTOS_PDF.map(([clave]) => [clave, form.elements[clave].value.trim()]));
      if (Object.values(cuerpo).some((valor) => !valor)) {
        XPS.mostrarAlerta(alertasTextos, "error", "Ningún texto puede quedar vacío.");
        return;
      }
      try {
        const guardado = await XPS.api("/textos-pdf", { metodo: "PUT", cuerpo });
        for (const [clave] of CAMPOS_TEXTOS_PDF) form.elements[clave].value = guardado[clave];
        XPS.mostrarAlerta(alertasTextos, "exito", "Textos guardados. Se usan desde la próxima emisión.");
      } catch (error) {
        XPS.mostrarError(alertasTextos, error);
      }
    });
    document.getElementById("bloque-textos-pdf").hidden = false;
  }

  // ---------- Correo Tencent (B2, B3, B10) ----------

  const ESTADOS_CORREO = {
    HABILITADO: ["badge badge-estado badge-activo", "Habilitado"],
    DESHABILITADO: ["badge badge-estado badge-inactivo", "Deshabilitado"],
    NO_CONFIGURADO: ["badge badge-estado badge-alerta", "No configurado"],
  };
  const c = (id) => document.getElementById(id);
  const alertasCorreo = c("alertas-correo");
  let configCorreo = null;

  function marca(valor, siTexto, noTexto) {
    if (valor === null || valor === undefined) return crear("span", { clase: "badge badge-estado badge-inactivo", texto: "Sin consultar" });
    return crear("span", { clase: `badge badge-estado ${valor ? "badge-activo" : "badge-critico"}`, texto: valor ? siTexto : noTexto });
  }

  function filaSalud(etiqueta, valor) {
    return crear("div", { clase: "salud-fila" }, [crear("span", { texto: etiqueta }), valor]);
  }

  function pintarSalud(salud) {
    const [clase, texto] = ESTADOS_CORREO[salud ? salud.estado : configCorreo.estado] || ESTADOS_CORREO.NO_CONFIGURADO;
    const filas = [filaSalud("Estado", crear("span", { clase, texto }))];
    if (salud && salud.consultado) {
      const aprobada = salud.plantilla_estado === null ? null : salud.plantilla_estado === 0;
      filas.push(
        filaSalud(`Dominio ${salud.dominio}`, marca(salud.dominio_verificado, "Verificado", "No verificado")),
        filaSalud(`Remitente ${salud.remitente}`, marca(salud.remitente_existe, "Existe", "No existe")),
        filaSalud(`Plantilla ${salud.plantilla_id}`, marca(aprobada, "Aprobada", salud.plantilla_estado_texto || "No aprobada")),
      );
      if (salud.error) filas.push(crear("div", { clase: "alerta alerta-error", texto: salud.error.mensaje }));
    } else if (salud && salud.mensaje) {
      filas.push(crear("p", { clase: "ayuda", texto: salud.mensaje }));
    }
    c("salud-correo").replaceChildren(crear("div", { clase: "etiqueta", texto: "Salud de la conexión" }), ...filas);
  }

  async function cargarPlantillas() {
    const actual = String(configCorreo.plantilla_cotizacion_id);
    // E1: la plantilla de cotización se elige del catálogo (uso COTIZACION, aprobada y activa); el valor no cambia.
    let plantillas = [];
    try {
      plantillas = (await XPS.api("/plantillas-correo?uso=COTIZACION"))
        .filter((p) => p.tencent_id && p.activo && p.estado_tencent === "APROBADA")
        .map((p) => ({ id: p.tencent_id, nombre: p.nombre, estado_texto: "aprobada" }));
    } catch (error) {
      XPS.mostrarError(alertasCorreo, error);
    }
    if (!plantillas.some((p) => String(p.id) === actual)) {
      plantillas.unshift({ id: configCorreo.plantilla_cotizacion_id, nombre: "(actual)", estado_texto: "sin verificar" });
    }
    UI.opciones(c("correo-plantilla"), plantillas, { valor: (p) => p.id, texto: (p) => `${p.id} · ${p.nombre} · ${p.estado_texto}` });
    c("correo-plantilla").value = actual;
  }

  function pintarCorreo() {
    const d = configCorreo;
    c("correo-habilitado").checked = d.habilitado;
    c("correo-region").value = d.region;
    c("correo-endpoint").value = d.endpoint;
    c("correo-remitente").value = d.remitente;
    c("correo-reply-to").value = d.reply_to;
    c("correo-bcc").value = d.bcc || "";
    c("correo-timeout").value = d.timeout_s;
    c("correo-adjunto").value = d.adjunto_max_bytes;
    c("correo-secret-id").value = "";
    c("correo-secret-key").value = "";
    c("correo-secret-id").placeholder = d.secret_id || "Sin cargar";
    c("correo-secret-key").placeholder = d.secret_key || "Sin cargar";
    c("correo-llaves").textContent = d.cifrado_disponible
      ? "Las llaves guardadas se muestran enmascaradas. Para cambiarlas escriba las dos nuevas; vacías se conservan."
      : "Falta CONFIG_CIFRADO_KEY en el servidor: no se pueden guardar llaves y el correo queda No configurado.";
    pintarSalud(null);
  }

  async function guardarCorreo(evento) {
    evento.preventDefault();
    XPS.limpiarAlerta(alertasCorreo);
    const cuerpo = {
      habilitado: c("correo-habilitado").checked,
      region: c("correo-region").value.trim(),
      endpoint: c("correo-endpoint").value.trim(),
      remitente: c("correo-remitente").value.trim(),
      reply_to: c("correo-reply-to").value.trim(),
      bcc: c("correo-bcc").value.trim() || null,
      plantilla_cotizacion_id: Number(c("correo-plantilla").value),
      timeout_s: Number(c("correo-timeout").value),
      adjunto_max_bytes: Number(c("correo-adjunto").value),
    };
    const secretId = c("correo-secret-id").value.trim();
    const secretKey = c("correo-secret-key").value.trim();
    if (secretId || secretKey) {
      cuerpo.secret_id = secretId;
      cuerpo.secret_key = secretKey;
    }
    try {
      configCorreo = await XPS.api("/correo/config", { metodo: "PUT", cuerpo });
      pintarCorreo();
      await cargarPlantillas();
      XPS.mostrarAlerta(alertasCorreo, "exito", "Configuración de correo guardada.");
    } catch (error) {
      XPS.mostrarError(alertasCorreo, error);
    }
  }

  async function probar() {
    XPS.limpiarAlerta(alertasCorreo);
    const boton = c("btn-probar");
    boton.disabled = true;
    boton.textContent = "Probando…";
    try {
      pintarSalud(await XPS.api("/correo/probar?refrescar=true", { metodo: "POST" }));
    } catch (error) {
      XPS.mostrarError(alertasCorreo, error);
    } finally {
      boton.disabled = false;
      boton.textContent = "Probar conexión";
    }
  }

  async function enviarPrueba(evento) {
    evento.preventDefault();
    XPS.limpiarAlerta(alertasCorreo);
    const boton = c("btn-prueba");
    boton.disabled = true;
    boton.textContent = "Enviando…";
    try {
      const resultado = await XPS.api("/correo/enviar-prueba", { metodo: "POST", cuerpo: { email: c("prueba-email").value.trim() } });
      XPS.mostrarAlerta(alertasCorreo, "exito", `Correo de prueba enviado a ${resultado.destinatario} · MessageId ${resultado.message_id}`);
    } catch (error) {
      XPS.mostrarError(alertasCorreo, error);
    } finally {
      boton.disabled = false;
      boton.textContent = "Enviar correo de prueba";
    }
  }

  async function iniciarCorreo() {
    configCorreo = await XPS.api("/correo/config");
    pintarCorreo();
    await cargarPlantillas();
    c("form-correo").addEventListener("submit", guardarCorreo);
    c("btn-probar").addEventListener("click", probar);
    c("form-prueba").addEventListener("submit", enviarPrueba);
    c("bloque-correo").hidden = false;
  }

  const yo = await iniciarLayout("configuracion.html");
  if (!yo || !UI.exigirAlguno(yo, ["config.editar", "tarifa.editar"], alertas)) {
    return;
  }
  try {
    pintar(await XPS.api("/configuracion"));
    lista.hidden = false;
    if (UI.tieneAlguno(yo, ["config.editar"])) {
      await iniciarSistema();
      await iniciarEmpresa();
      await iniciarTextosPdf();
    }
    if (UI.tieneAlguno(yo, ["usuario.admin"])) await iniciarCorreo();
  } catch (error) {
    XPS.mostrarError(alertas, error);
  }
})();
