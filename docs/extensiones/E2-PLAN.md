# E2 · Catálogos de administración: plan

Peso: 15 % de E0–E3. Fases: E2.0 base 2 % · E2.1 roles y matriz 6 % · E2.2 motivos y tipos de identificación 4 % · E2.3 textos del PDF y cierre 3 %.

## Inventario de lo que estaba fijo

| Qué | Dónde estaba | Qué pasa en E2 |
|---|---|---|
| Roles y matriz | Siembra de 0001; `GET /v1/roles` solo lectura | Pantalla Roles y permisos: crear rol, editar nombre, descripción, permisos y estado |
| Motivos de rechazo | `CHECK ck_cotizacion_motivo_rechazo`, `Literal` del schema y `<option>` en `cotizacion.html` | Catálogo `motivo_rechazo` (FK), con "exige detalle" |
| Tipos de identificación | `CHECK ck_cliente_tipo_id` y `ck_cliente_identificacion_formato`, `PATRONES_IDENTIFICACION`, `Literal` y `<option>` en `clientes.html` | Catálogo `tipo_identificacion` (FK), con regex y formato |
| Aceptación y firma del PDF | Texto fijo en `templates/cotizacion.html` | `config_textos_pdf`, congelado en la foto al emitir |
| Advertencias DDP y EXW | `ADVERTENCIA_DDP_IMPORTACION` y `ADVERTENCIA_EXW_EXPORTACION` en `services/incoterms.py` | `config_textos_pdf` |

**No se convierten en CRUD** (lo pide el prompt maestro): bloques de costo, métodos de venta, unidades, estados de la cotización ni la lista de Incoterms.

## Reglas

- **Permisos.** E2 no crea permisos nuevos:
  - roles: `usuario.admin`;
  - catálogos y textos: `config.editar`, el mismo de los datos de la empresa.
  
  Así la matriz §6.2 y sus conteos (T136, T138, T208) no cambian.
- **Rol protegido** (admin): no se desactiva ni pierde `usuario.admin`. Un rol con usuarios activos no se desactiva. Un rol inactivo no se asigna.
- **Cambiar los permisos de un rol, o desactivarlo,** sube `token_version` de sus usuarios, menos de quien hace el cambio: vuelven a entrar con el menú nuevo.
- **Los códigos no cambian una vez creados,** porque los guardan los usuarios, las cotizaciones y los clientes. Desactivar saca de las listas nuevas sin tocar lo guardado.
- **OTRO** sigue exigiendo el detalle (CHECK de F3 `ck_cotizacion_detalle_si_otro`) y no se desactiva.
- **Textos sembrados idénticos.** Un PDF emitido antes de E2 no trae textos en su foto y se dibuja con los de siempre.
- **Clientes.** Al editar un cliente sin cambiar su identificación, no se revalida: el cliente no se traba si cambió la regla.

## Verificación

- Pruebas TE2-01 a TE2-17 (`tests/test_e2_catalogos.py`) y Regla 18 doble.
- Ida y vuelta de 0009 con la foto del esquema.
- Prueba de oro del PDF: el HTML de cada cotización emitida en producción, con el código anterior y con el de E2, debe salir idéntico. También se repite la prueba de oro de E0 después de migrar.
