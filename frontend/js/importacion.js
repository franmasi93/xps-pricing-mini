/* E1-B Importación de clientes y contactos con la plantilla oficial (la usan Clientes y Listas de envío).
 * Flujo: descargar plantilla → subir .xlsx o .csv → vista previa (crear, actualizar, sin cambios, error por fila y columna)
 * → elegir "solo crear nuevos" o "crear y actualizar" → confirmar → reporte descargable (CSV) con el resultado de cada fila.
 * El diálogo se arma aquí (no hace falta marcado en la página). Nunca borra datos.
 */
"use strict";

const Importacion = (() => {
  const { crear } = XPS;
  const ACCIONES = {
    CREAR: ["badge badge-estado badge-activo", "Nuevo"],
    ACTUALIZAR: ["badge badge-estado badge-info", "Actualizar"],
    SIN_CAMBIOS: ["badge badge-estado badge-inactivo", "Sin cambios"],
    ERROR: ["badge badge-estado badge-critico", "Error"],
  };

  async function descargar(ruta) {
    const { blob, nombre } = await XPS.archivo(ruta);
    guardarBlob(blob, nombre);
  }

  function guardarBlob(blob, nombre) {
    const url = URL.createObjectURL(blob);
    const enlace = crear("a", { atributos: { href: url, download: nombre } });
    document.body.append(enlace);
    enlace.click();
    enlace.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 2000);
  }

  function leerBase64(archivo) {
    return new Promise((resolver, rechazar) => {
      const lector = new FileReader();
      lector.onload = () => resolver(String(lector.result).split(",").pop());
      lector.onerror = () => rechazar(new Error("No se pudo leer el archivo"));
      lector.readAsDataURL(archivo);
    });
  }

  function csvCelda(valor) {
    const texto = String(valor ?? "");
    return /[;"\n]/.test(texto) ? `"${texto.replace(/"/g, '""')}"` : texto;
  }

  function reporteCsv(filas) {
    const lineas = [["hoja", "fila", "tipo", "identificacion", "nombre", "email", "resultado", "detalle"].join(";")];
    for (const f of filas) {
      const detalle = f.errores.length ? f.errores.map((e) => `${e.columna}: ${e.mensaje}`).join(" | ") : f.cambios.join(", ");
      lineas.push([f.hoja, f.fila, f.tipo, f.identificacion, f.nombre, f.email, f.resultado, detalle].map(csvCelda).join(";"));
    }
    return new Blob(["﻿" + lineas.join("\n")], { type: "text/csv;charset=utf-8" });
  }

  function contador(valor, texto, tono = "") {
    return crear("div", { clase: `contador${tono ? ` indicador-${tono}` : ""}` }, [crear("strong", { texto: String(valor) }), crear("span", { texto })]);
  }

  function tablaFilas(filas, columnaResultado) {
    const cuerpo = crear("tbody");
    const visibles = filas.slice(0, 300);
    for (const f of visibles) {
      const [clase, texto] = ACCIONES[f.accion] || ["badge badge-estado", f.accion];
      const detalle = f.errores.length
        ? crear("ul", { clase: "lista-errores" }, f.errores.map((e) => crear("li", { texto: `${e.columna}: ${e.mensaje}` })))
        : UI.texto(f.cambios.length ? `Cambia: ${f.cambios.join(", ")}` : "");
      cuerpo.append(crear("tr", {}, [
        UI.celda("Fila", [UI.texto(`${f.hoja} ${f.fila}`, "cifra")]),
        UI.celda("Tipo", [UI.texto(f.tipo === "cliente" ? "Cliente" : "Contacto")]),
        UI.celda("Identificación", [UI.texto(f.identificacion, "cifra")]),
        UI.celda("Nombre", [UI.texto(f.email ? `${f.nombre} · ${f.email}` : f.nombre)]),
        UI.celda(columnaResultado ? "Resultado" : "Acción", [columnaResultado ? UI.texto(f.resultado) : crear("span", { clase, texto })]),
        UI.celda("Detalle", [detalle]),
      ]));
    }
    const tabla = crear("table", { clase: "tabla" }, [
      crear("thead", {}, [crear("tr", {}, ["Fila", "Tipo", "Identificación", "Nombre", columnaResultado ? "Resultado" : "Acción", "Detalle"]
        .map((t) => crear("th", { texto: t })))]), cuerpo]);
    const salida = [crear("div", { clase: "tabla-desplazable" }, [tabla])];
    if (filas.length > visibles.length) salida.push(crear("p", { clase: "ayuda", texto: `Se muestran ${visibles.length} de ${filas.length} filas; el reporte las trae todas.` }));
    return salida;
  }

  /**
   * Abre el asistente de importación.
   * @param {{listaId?: number|null, titulo?: string, alTerminar?: Function}} opciones
   */
  function abrir({ listaId = null, titulo = "Importar clientes desde Excel", alTerminar = null } = {}) {
    const alertas = crear("div", { atributos: { hidden: "" } });
    const entrada = crear("input", { clase: "input", atributos: { type: "file", accept: ".xlsx,.csv", id: "importacion-archivo" } });
    const revisar = crear("button", { clase: "btn btn-primario", texto: "Revisar archivo", atributos: { type: "button" } });
    const zonaPrevia = crear("div");
    const cerrar = crear("button", { clase: "btn btn-secundario", texto: "Cerrar", atributos: { type: "button" } });
    const plantilla = UI.boton("Descargar plantilla (.xlsx)", () => descargar("/clientes/importacion/plantilla.xlsx").catch((e) => XPS.mostrarError(alertas, e)));
    const ejemplo = UI.boton("Descargar CSV de ejemplo", () => descargar("/clientes/importacion/plantilla.csv").catch((e) => XPS.mostrarError(alertas, e)));
    const dialogo = crear("dialog", { clase: "dialogo dialogo-ancho", atributos: { "aria-label": titulo } }, [
      crear("h2", { texto: titulo }),
      crear("p", { clase: "ayuda", texto: listaId
        ? "Suba la plantilla oficial: se crean o actualizan los clientes y contactos, y los contactos se agregan a esta lista. Nunca se borra nada."
        : "Use la plantilla oficial (Excel o CSV). Las filas de ejemplo se ignoran solas. Nunca se borra nada." }),
      crear("div", { clase: "config-acciones" }, [plantilla, ejemplo]),
      alertas,
      crear("div", { clase: "campo" }, [crear("label", { texto: "Archivo (.xlsx o .csv)", atributos: { for: "importacion-archivo" } }), entrada]),
      crear("div", { clase: "config-acciones" }, [revisar]),
      zonaPrevia,
      crear("div", { clase: "acciones-form" }, [cerrar]),
    ]);
    document.body.append(dialogo);
    let archivo = null;
    let contenido = null;
    let huboCambios = false;
    cerrar.addEventListener("click", () => dialogo.close());
    dialogo.addEventListener("close", () => {
      dialogo.remove();
      if (huboCambios && alTerminar) alTerminar();
    });

    async function previa() {
      XPS.limpiarAlerta(alertas);
      archivo = entrada.files[0] || null;
      if (!archivo) {
        XPS.mostrarAlerta(alertas, "error", "Elija el archivo de la plantilla.");
        return;
      }
      revisar.disabled = true;
      try {
        contenido = await leerBase64(archivo);
        const datos = await XPS.api("/clientes/importacion/vista-previa", { metodo: "POST", cuerpo: { nombre: archivo.name, contenido_base64: contenido } });
        pintarPrevia(datos);
      } catch (error) {
        XPS.mostrarError(alertas, error);
      } finally {
        revisar.disabled = false;
      }
    }

    function pintarPrevia(datos) {
      const r = datos.resumen;
      const modoNuevos = crear("input", { atributos: { type: "radio", name: "modo-importacion", value: "SOLO_NUEVOS", id: "modo-nuevos" } });
      const modoTodos = crear("input", { atributos: { type: "radio", name: "modo-importacion", value: "CREAR_Y_ACTUALIZAR", id: "modo-todos" } });
      modoTodos.checked = true;
      const confirmar = crear("button", { clase: "btn btn-primario", texto: "Confirmar importación", atributos: { type: "button" } });
      confirmar.disabled = r.cambios === 0;
      confirmar.addEventListener("click", () => confirmarImportacion(modoNuevos.checked ? "SOLO_NUEVOS" : "CREAR_Y_ACTUALIZAR", confirmar));
      zonaPrevia.replaceChildren(
        crear("h3", { texto: "Vista previa" }),
        crear("div", { clase: "contadores" }, [
          contador(r.clientes_nuevos, "Clientes nuevos", "ok"), contador(r.clientes_actualizar, "Clientes a actualizar", "info"),
          contador(r.clientes_error, "Clientes con error", r.clientes_error ? "alerta" : ""),
          contador(r.contactos_nuevos, "Contactos nuevos", "ok"), contador(r.contactos_actualizar, "Contactos a actualizar", "info"),
          contador(r.contactos_error, "Contactos con error", r.contactos_error ? "alerta" : ""),
        ]),
        crear("p", { clase: "ayuda", texto: `${r.clientes_sin_cambios + r.contactos_sin_cambios} fila(s) sin cambios · ${r.ejemplos_ignorados} fila(s) de ejemplo ignoradas · ${r.cambios} cambio(s) en total. Las filas con error no se importan.` }),
        ...tablaFilas(datos.filas, false),
        crear("fieldset", { clase: "campo" }, [
          crear("legend", { texto: "¿Qué hacer con los clientes y contactos que ya existen?" }),
          crear("label", { clase: "campo-check", atributos: { for: "modo-todos" } }, [modoTodos, " Crear y actualizar"]),
          crear("label", { clase: "campo-check", atributos: { for: "modo-nuevos" } }, [modoNuevos, " Solo crear nuevos"]),
        ]),
        crear("div", { clase: "config-acciones" }, [confirmar]),
      );
    }

    async function confirmarImportacion(modo, boton) {
      XPS.limpiarAlerta(alertas);
      boton.disabled = true;
      try {
        const ruta = listaId ? `/boletines/listas/${listaId}/importar-archivo` : "/clientes/importacion/confirmar";
        const datos = await XPS.api(ruta, { metodo: "POST", cuerpo: { nombre: archivo.name, contenido_base64: contenido, modo } });
        huboCambios = true;
        const r = datos.resumen;
        const reporte = UI.boton("Descargar reporte (CSV)", () => guardarBlob(reporteCsv(datos.filas), `reporte_importacion_${archivo.name.replace(/\.[^.]+$/, "")}.csv`), "btn btn-primario btn-chico");
        zonaPrevia.replaceChildren(
          crear("h3", { texto: "Importación terminada" }),
          crear("div", { clase: "contadores" }, [
            contador(r.clientes_creados, "Clientes creados", "ok"), contador(r.clientes_actualizados, "Clientes actualizados", "info"),
            contador(r.contactos_creados, "Contactos creados", "ok"), contador(r.contactos_actualizados, "Contactos actualizados", "info"),
            contador(r.errores, "Filas con error", r.errores ? "alerta" : ""),
            ...(listaId ? [contador(r.agregados_a_lista, "Agregados a la lista", "ok")] : []),
          ]),
          crear("div", { clase: "config-acciones" }, [reporte]),
          ...tablaFilas(datos.filas, true),
        );
      } catch (error) {
        boton.disabled = false;
        XPS.mostrarError(alertas, error);
      }
    }

    revisar.addEventListener("click", previa);
    dialogo.showModal();
  }

  return { abrir, descargar, guardarBlob };
})();
