# XPRESS · Modelo interno de pantallas (Design System)

Guía para que **todas** las pantallas del sistema (login, dashboard, envíos,
rastreo, clientes, facturación, reportes, usuarios…) se vean como una sola
aplicación. Colores **planos** (sin degradados), tipografía Inter + JetBrains Mono.

---

## 1. Paleta de colores (tokens)

### Marca
| Token | HEX | Uso |
|---|---|---|
| `--navy-900` | `#000033` | Fondos oscuros profundos, tooltips |
| `--navy-800` | `#000771` | **Color base de marca** · títulos, sidebar activo oscuro |
| `--navy-700` | `#14209A` | Acentos, avatares, íconos |
| `--navy-600` | `#20309F` | Hover de elementos navy |
| `--orange`   | `#ED4C01` | **Acento / acción** · botones primarios, activo, CTA |
| `--orange-600` | `#C63F01` | Hover de naranja |
| `--orange-50`  | `#FEF0E8` | Fondos suaves del acento (chips, item activo) |

> Regla: **azul marino = estructura e identidad**, **naranja = acción y foco**.
> El naranja se usa con moderación (1 acción principal por pantalla).

### Estados (reservados — nunca como color de marca ni de series)
| Estado | Texto/borde | Fondo | Significado |
|---|---|---|---|
| Éxito `--ok` | `#12934e` | `#e7f6ee` | Entregado, completado, +delta |
| Info `--info` | `#2563eb` | `#e8f0fe` | En reparto / en tránsito |
| Alerta `--warn` | `#c77700` | `#fdf3e3` | Pendiente, por vencer |
| Crítico `--crit` | `#d92d20` | `#fdecea` | Incidencia, error, −delta |

Los estados **siempre** llevan punto/ícono + etiqueta de texto (nunca solo color).

### Tinta (texto) y superficies
| Token | HEX | Uso |
|---|---|---|
| `--ink-900` | `#131235` | Texto principal |
| `--ink-700` | `#3a3960` | Texto secundario |
| `--ink-500` | `#6b6a8c` | Texto terciario / descripciones |
| `--ink-400` | `#9997b6` | Placeholder, íconos inactivos, etiquetas |
| `--line`    | `#e7e7f1` | Bordes y divisores |
| `--line-2`  | `#dcdceb` | Bordes hover |
| `--surface` | `#ffffff` | Tarjetas, sidebar, topbar |
| `--surface-2` | `#f6f6fb` | Inputs, fondos sutiles, filas hover |
| `--bg`      | `#eef0f8` | Fondo de la app |

### Tokens de forma
- Radios: `8px` (sm) · `12px` (md, inputs/botones) · `16px` (lg, tarjetas).
- Sombras: muy suaves, solo para elevar tarjetas (`0 10px 30px -16px rgba(0,7,113,.28)`).
- Tipografía: **Inter** (UI, pesos 400–900) · **JetBrains Mono** (guías, cifras, IDs).

---

## 2. Modelo interno de pantallas (layout)

Todas las pantallas internas comparten el mismo esqueleto:

```
┌──────────┬───────────────────────────────────────────┐
│          │  TOPBAR: título + subtítulo · buscador ·   │
│ SIDEBAR  │          notificaciones · acción primaria  │
│ 248px    ├───────────────────────────────────────────┤
│          │  CONTENIDO (padding 22–26px, grid gap 18px)│
│ · logo   │   ┌ fila de KPIs (4 tiles)                 │
│ · grupos │   ├ fila 2: gráfico (1.6fr) + panel (1fr)  │
│   de nav │   └ tabla / listado en tarjeta             │
│ · perfil │                                             │
└──────────┴───────────────────────────────────────────┘
```

- **Sidebar** (248px, blanco): logo arriba, grupos de navegación con etiqueta en
  mayúsculas, ítem activo con barra naranja + fondo `--orange-50` + texto naranja,
  bloque de perfil abajo. Íconos lineales 18px, trazo 2px.
- **Topbar** (blanco translúcido con blur, borde inferior): título `navy-800` +
  subtítulo `ink-400`, buscador a la derecha, ícono de notificaciones y **una**
  acción primaria naranja.
- **Contenido**: fondo `--bg`, todo dentro de tarjetas blancas con borde `--line`.

### Inventario de componentes (reutilizables)
1. **KPI tile** — ícono en cuadro de color, delta (verde ↑ / rojo ↓), valor grande
   en mono, etiqueta, sparkline plano.
2. **Card** — cabecera (`h3` + descripción + control opcional: segmentado / enlace)
   y cuerpo.
3. **Gráfico** — líneas 2.5px, grid recesivo `--line`, área de relleno **plano**
   con opacidad baja (sin degradado), crosshair punteado + tooltip navy al pasar el
   mouse. Una serie no lleva leyenda; ≥2 series sí. Nunca doble eje Y.
4. **Tabla** — cabeceras en mayúsculas `ink-400`, filas con hover `--surface-2`,
   guías/fechas en mono, celda de estado con **badge**.
5. **Badge de estado** — punto + texto, con los 4 colores de estado reservados.
6. **Botones** — primario naranja sólido; secundario/ghost blanco con borde.
7. **Inputs** — fondo `--surface-2`, borde `--line`, foco naranja con halo
   `0 0 0 4px rgba(237,76,1,.14)`.

### Reglas rápidas
- Colores **planos**: nada de `linear-gradient`/`radial-gradient` en rellenos.
- Máximo **una** acción primaria naranja por pantalla.
- Cifras, IDs de guía y fechas → JetBrains Mono.
- Estados con ícono + etiqueta, nunca solo por color.
- Espaciado base 4px; separación entre tarjetas 18px.
- Todo cabe en “una sola hoja”: cada vista es un archivo/route que se monta en el
  mismo shell (sidebar + topbar).

---

## 3. Prompt reutilizable (para generar nuevas pantallas)

> Copia esto y solo cambia la parte de **“Pantalla a construir”**.

```
Eres un diseñador/desarrollador front-end. Construye una pantalla web para el
sistema postal XPRESS como archivo HTML único (CSS embebido, sin librerías,
opcionalmente JS vanilla). Debe integrarse en un dashboard, así que respeta
EXACTAMENTE este design system:

IDENTIDAD
- Marca: XPRESS (mensajería/red postal del Ecuador). Logo: flecha "»" naranja + "XPRESS".
- Estética: limpia, corporativa, moderna tipo SaaS. Colores PLANOS, sin degradados.
- Tipografía: Inter (UI) y JetBrains Mono (cifras, guías, fechas).

PALETA (usar tal cual)
- Marca: navy #000771 (base), #14209A/#20309F (acentos), naranja #ED4C01 (acción),
  naranja hover #C63F01, naranja suave #FEF0E8.
- Estados (reservados, con ícono+texto): éxito #12934e/#e7f6ee, info #2563eb/#e8f0fe,
  alerta #c77700/#fdf3e3, crítico #d92d20/#fdecea.
- Tinta: #131235 / #3a3960 / #6b6a8c / #9997b6. Líneas #e7e7f1.
  Superficies: #ffffff (tarjetas), #f6f6fb (inputs), #eef0f8 (fondo app).

LAYOUT
- Shell fijo: sidebar 248px (blanco, nav con grupos, ítem activo = barra naranja +
  fondo #FEF0E8 + texto naranja) + topbar (título navy + subtítulo, buscador,
  notificaciones y UNA acción primaria naranja) + contenido en tarjetas blancas
  sobre fondo #eef0f8, gap 18px.

REGLAS
- Radios 8/12/16px. Sombras muy suaves. Íconos lineales 18px, trazo 2px.
- Máximo una acción primaria naranja por pantalla.
- Cifras/IDs/fechas en JetBrains Mono. Estados siempre con punto/ícono + etiqueta.
- Gráficos: líneas finas, grid recesivo, relleno plano de baja opacidad (sin
  degradado), tooltip navy al pasar el mouse, sin doble eje Y, leyenda solo si hay
  ≥2 series.
- Responsive: en móvil el contenido se apila y el sidebar colapsa.

PANTALLA A CONSTRUIR
[describe aquí: p. ej. "Listado de Envíos con filtros por estado y fecha, tabla
paginada con guía, cliente, origen→destino, estado, courier y acciones; panel
lateral de detalle del envío con línea de tiempo de rastreo".]
```

---

*Archivos de referencia:* `dashboard.html` (modelo de pantalla) y `index.html`
(acceso). Ambos comparten esta misma paleta y lenguaje visual.
