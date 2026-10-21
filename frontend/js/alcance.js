/* D-A1: "¿Dónde aplica?" del recargo. Cada nivel es una multiselección con buscador; sin nada elegido = "Todos".
 * Los niveles dependientes se filtran: la región limita los países y el país limita los puertos. El tipo de contenedor
 * aparece si se elige un servicio que use tipo de equipo; la clase IMO, si se elige un tipo de carga IMO.
 * leer() devuelve el JSON del API ({servicios, modos, tipos_equipo, regiones, paises, puertos, puertos_origen,
 * puertos_destino, proveedores, tipos_carga, clases_imo}); resumen() da la línea "Aplica a: …".
 */
"use strict";

const Alcance = (() => {
  const { crear } = XPS;

  /**
   * @param {HTMLElement} contenedor
   * @param {object} catalogos {servicios, ubicaciones, tipos, regiones, paises, puertos, proveedores, tiposCarga}
   * @param {Function} alCambiar
   */
  function crearSelector(contenedor, catalogos, alCambiar) {
    const niveles = {};
    const IMO = new Set(catalogos.tiposCarga.filter((t) => t.pide_imo).map((t) => t.codigo));

    function nivel(clave, etiqueta, ayuda = "Ninguno = todos") {
      const id = `alcance-${clave}`;
      const buscador = crear("input", { clase: "input input-chico", atributos: { type: "search", placeholder: "Buscar…", "aria-label": `Buscar en ${etiqueta}` } });
      const lista = crear("select", { clase: "select", atributos: { id, multiple: "", size: "4", "aria-describedby": `${id}-ayuda` } });
      const campo = crear("div", { clase: "campo campo-alcance" }, [
        crear("label", { texto: etiqueta, atributos: { for: id } }), buscador, lista,
        crear("p", { clase: "ayuda", texto: ayuda, atributos: { id: `${id}-ayuda` } }),
      ]);
      const estado = { campo, lista, buscador, elegidos: new Set(), opciones: [] };
      buscador.addEventListener("input", () => pintarNivel(clave));
      lista.addEventListener("change", () => {
        const visibles = new Set([...lista.options].map((o) => o.value));
        for (const valor of visibles) estado.elegidos.delete(valor);
        for (const opcion of lista.selectedOptions) estado.elegidos.add(opcion.value);
        refrescar();
        alCambiar();
      });
      niveles[clave] = estado;
      return campo;
    }

    function pintarNivel(clave) {
      const estado = niveles[clave];
      const filtro = estado.buscador.value.trim().toLowerCase();
      const visibles = estado.opciones.filter((o) => estado.elegidos.has(o.valor) || !filtro || o.texto.toLowerCase().includes(filtro));
      estado.lista.replaceChildren(...visibles.map((o) => {
        const opcion = crear("option", { texto: o.texto, atributos: { value: o.valor } });
        opcion.selected = estado.elegidos.has(o.valor);
        return opcion;
      }));
    }

    function opcionesDe(clave) {
      const elegidos = (c) => [...niveles[c].elegidos];
      switch (clave) {
        case "servicios": return catalogos.servicios.map((s) => ({ valor: s.codigo, texto: s.nombre }));
        case "modos": return catalogos.ubicaciones.map((u) => ({ valor: u.codigo, texto: u.nombre }));
        case "tipos_equipo": {
          const servicios = catalogos.servicios.filter((s) => niveles.servicios.elegidos.has(s.codigo) && s.usa_tipo_equipo).map((s) => s.id);
          return catalogos.tipos.filter((t) => servicios.includes(t.servicio_id)).map((t) => ({ valor: String(t.id), texto: t.codigo }));
        }
        case "regiones": return catalogos.regiones.map((r) => ({ valor: String(r.id), texto: r.nombre }));
        case "paises": {
          const regiones = elegidos("regiones").map(Number);
          return catalogos.paises.filter((p) => !regiones.length || regiones.includes(p.region_id))
            .map((p) => ({ valor: String(p.id), texto: `${p.nombre} (${p.iso2})` }));
        }
        case "puertos": {
          const paises = elegidos("paises").map(Number);
          const regiones = elegidos("regiones").map(Number);
          return catalogos.puertos.filter((p) => (!paises.length || paises.includes(p.pais_id))
            && (!regiones.length || paises.length || regiones.includes(p.pais.region_id)))
            .map((p) => ({ valor: String(p.id), texto: `${p.codigo} · ${p.nombre}` }));
        }
        case "puertos_origen":
        case "puertos_destino": return catalogos.puertos.map((p) => ({ valor: String(p.id), texto: `${p.codigo} · ${p.nombre}` }));
        case "proveedores": return catalogos.proveedores.map((p) => ({ valor: String(p.id), texto: p.nombre }));
        case "tipos_carga": return catalogos.tiposCarga.map((t) => ({ valor: t.codigo, texto: t.nombre }));
        case "clases_imo": return ["1", "2", "3", "4", "5", "6", "7", "8", "9"].map((c) => ({ valor: c, texto: `Clase ${c}` }));
        default: return [];
      }
    }

    function refrescar() {
      for (const clave of Object.keys(niveles)) {
        niveles[clave].opciones = opcionesDe(clave);
        const validos = new Set(niveles[clave].opciones.map((o) => o.valor));
        for (const valor of [...niveles[clave].elegidos]) if (!validos.has(valor)) niveles[clave].elegidos.delete(valor);
        pintarNivel(clave);
      }
      niveles.tipos_equipo.campo.hidden = !niveles.tipos_equipo.opciones.length;
      niveles.clases_imo.campo.hidden = ![...niveles.tipos_carga.elegidos].some((c) => IMO.has(c));
    }

    contenedor.replaceChildren(
      nivel("servicios", "Servicio"), nivel("modos", "Modo"), nivel("tipos_equipo", "Tipo de contenedor"),
      nivel("regiones", "Región"), nivel("paises", "País"), nivel("puertos", "Puerto del lado", "Del lado del recargo (origen o destino). Ninguno = todos"),
      nivel("puertos_origen", "Ruta: puerto de origen", "Ruta exacta: elija origen Y destino"),
      nivel("puertos_destino", "Ruta: puerto de destino", "Ruta exacta: elija origen Y destino"),
      nivel("proveedores", "Proveedor de la tarifa", "Solo cuando el flete es de estos proveedores. Ninguno = todos"),
      nivel("tipos_carga", "Tipo de carga"), nivel("clases_imo", "Clase IMO"),
    );
    refrescar();

    return {
      establecer(alcance = {}) {
        for (const [clave, estado] of Object.entries(niveles)) estado.elegidos = new Set((alcance[clave] || []).map(String));
        refrescar();
        refrescar();  // dos pasadas: los dependientes se arman después de sus padres
      },
      leer() {
        const salida = {};
        for (const [clave, estado] of Object.entries(niveles)) {
          if (estado.campo.hidden || !estado.elegidos.size) continue;
          const numericos = !["servicios", "modos", "tipos_carga", "clases_imo"].includes(clave);
          salida[clave] = [...estado.elegidos].map((v) => (numericos ? Number(v) : v));
        }
        return salida;
      },
      fijarProveedor(proveedorId) {
        // El dueño del cargo fija el nivel Proveedor (un recargo de GLOVAL solo aplica a tarifas de GLOVAL).
        niveles.proveedores.elegidos = new Set(proveedorId ? [String(proveedorId)] : [...niveles.proveedores.elegidos]);
        niveles.proveedores.lista.disabled = Boolean(proveedorId);
        refrescar();
      },
      resumen(lado) {
        const texto = (clave) => [...niveles[clave].elegidos].map((v) => (niveles[clave].opciones.find((o) => o.valor === v) || { texto: v }).texto.split(" · ")[0]).join(" y ");
        const partes = [niveles.servicios.elegidos.size ? texto("servicios") : "todos los servicios"];
        if (niveles.modos.elegidos.size) partes.push(texto("modos").toLowerCase());
        if (!niveles.tipos_equipo.campo.hidden && niveles.tipos_equipo.elegidos.size) partes.push(texto("tipos_equipo"));
        const lugar = lado === "ORIGEN" ? "origen" : "destino";
        if (niveles.puertos_origen.elegidos.size || niveles.puertos_destino.elegidos.size) partes.push(`ruta ${texto("puertos_origen")} → ${texto("puertos_destino")}`);
        for (const clave of ["puertos", "paises", "regiones"]) if (niveles[clave].elegidos.size) partes.push(`${lugar} ${texto(clave)}`);
        if (!["puertos", "paises", "regiones", "puertos_origen", "puertos_destino"].some((c) => niveles[c].elegidos.size)) partes.push(`cualquier ${lugar}`);
        partes.push(niveles.proveedores.elegidos.size ? texto("proveedores") : "todos los proveedores");
        if (niveles.tipos_carga.elegidos.size) partes.push(`carga ${texto("tipos_carga")}${!niveles.clases_imo.campo.hidden && niveles.clases_imo.elegidos.size ? ` ${texto("clases_imo").toLowerCase()}` : ""}`);
        return `Aplica a: ${partes.join(" · ")}`;
      },
      servicios: () => [...niveles.servicios.elegidos],
      puertos: () => [...niveles.puertos.elegidos].map(Number),
    };
  }

  return { crearSelector };
})();
