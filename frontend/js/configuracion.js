/* Configuración: cada clave trae `editable` según el permiso del usuario (lo decide el backend).
 * Admin edita todo; pricing solo los días de alerta de vencimiento.
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

  const yo = await iniciarLayout("configuracion.html");
  if (!yo || !UI.exigirAlguno(yo, ["config.editar", "tarifa.editar"], alertas)) {
    return;
  }
  try {
    pintar(await XPS.api("/configuracion"));
    lista.hidden = false;
  } catch (error) {
    XPS.mostrarError(alertas, error);
  }
})();
