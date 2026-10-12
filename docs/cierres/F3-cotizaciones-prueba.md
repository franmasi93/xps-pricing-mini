# F3 — Cotizaciones de prueba (compuerta)

Generado por `scripts/cotizaciones_prueba_f3.py` sobre `xps_pricing_test`, con fecha 2026-10-08. IVA leído de la configuración: 15.00 %. Tasa EUR: 1.085000 USD por EUR (vigente desde el día anterior).

Reglas del cálculo manual (§10, H7, H8, D-F3-4): unitarios y mínimos a USD con 4 decimales; subtotal de línea = max(cantidad × unitario, mínimo) a 4 decimales; totales a 2 decimales, redondeando una vez la suma; IVA solo sobre las líneas de factura con IVA, sobre la base ya redondeada; margen sin IVA. ROUND_HALF_UP en todo.

**Suma de las diferencias absolutas (líneas y totales): 0.00** (debe ser 0,00).

## (a) Aérea con tramos, volumétrico y EUR

Número **COT-2026-00001** · emitida 2026-10-08 · válida hasta 2026-11-22 · PDF `salidas/f3/COT-2026-00001_Importadora-de-Prueba-F3-S-A.pdf`

### Cálculo manual paso a paso

- **Security fee (FRA, EUR)**
  - cantidad: 160,000 kg (KG = peso cobrable); puerto en Alemania → recibo de caja
  - costo: 0.10 × tasa 1.085000 = 0.1085 USD/u; mínimo 15 × 1.085000 = 16.2750; max(160.0000 × 0.1085 = 17.3600; 16.2750) = **17.3600**
  - venta (MARKUP 20): 0.10 → 0.1200; mínimo de venta 18.0000; en USD 0.1302/u y 19.5300; max(160.0000 × 0.1302 = 20.8320; 19.5300) = **20.8320**
- **Flete AEREO FRA → GYE**
  - volumétrico 4 × 80 × 60 × 50 = 960 000 cm³ / 6000 = 160,000 kg; real 120 → cobrable 160,000 kg
  - tramo: el mayor desde_kg ≤ 160 → +100 (3,80 EUR/kg)
  - costo: 3.80 × tasa 1.085000 = 4.1230 USD/u; mínimo 75 × 1.085000 = 81.3750; max(160.0000 × 4.1230 = 659.6800; 81.3750) = **659.6800**
  - venta (MARKUP 20): 3.80 → 4.5600; mínimo de venta 90.0000; en USD 4.9476/u y 97.6500; max(160.0000 × 4.9476 = 791.6160; 97.6500) = **791.6160**
- **Handling aeroportuario (GYE)**
  - cantidad 160 kg; puerto en Ecuador → factura con IVA; aquí gana el mínimo de venta
  - costo: 0.15 × tasa 1 = 0.1500 USD/u; mínimo 25 × 1 = 25.0000; max(160.0000 × 0.1500 = 24.0000; 25.0000) = **25.0000**
  - venta (MARKUP 20): 0.15 → 0.1800; mínimo de venta 30.0000; en USD 0.1800/u y 30.0000; max(160.0000 × 0.1800 = 28.8000; 30.0000) = **30.0000**
- **Agenciamiento de aduana**
  - ENVIO = 1
  - costo: 120 × tasa 1 = 120.0000 USD/u; mínimo 0 × 1 = 0.0000; max(1 × 120.0000 = 120.0000; 0.0000) = **120.0000**
  - venta (FIJO 30): 120 → 150.0000; mínimo de venta 0.0000; en USD 150.0000/u y 0.0000; max(1 × 150.0000 = 150.0000; 0.0000) = **150.0000**
- **Entrega en Guayaquil**
  - ENVIO = 1
  - costo: 60 × tasa 1 = 60.0000 USD/u; mínimo 0 × 1 = 0.0000; max(1 × 60.0000 = 60.0000; 0.0000) = **60.0000**
  - venta (MARKUP 25): 60 → 75.0000; mínimo de venta 0.0000; en USD 75.0000/u y 0.0000; max(1 × 75.0000 = 75.0000; 0.0000) = **75.0000**

### Líneas: manual frente al sistema (USD)

| Concepto | Cantidad | Subtotal manual | Subtotal sistema | Fiscal | Diferencia |
|---|---|--:|--:|---|--:|
| Security fee | 160.0000 KG | 20.8320 | 20.8320 | RECIBO_CAJA | 0.00 |
| Flete AEREO FRA → GYE | 160.0000 KG | 791.6160 | 791.6160 | RECIBO_CAJA | 0.00 |
| Handling aeroportuario | 160.0000 KG | 30.0000 | 30.0000 | FACTURA | 0.00 |
| Agenciamiento de aduana | 1.0000 ENVIO | 150.0000 | 150.0000 | FACTURA | 0.00 |
| Entrega en Guayaquil | 1.0000 ENVIO | 75.0000 | 75.0000 | FACTURA | 0.00 |

### Totales

| Total | Manual | Sistema | Diferencia |
|---|--:|--:|--:|
| Recibo de caja (IVA 0 %) | 812.45 | 812.45 | 0.00 |
| Factura | 255.00 | 255.00 | 0.00 |
| IVA | 38.25 | 38.25 | 0.00 |
| Total USD | 1105.70 | 1105.70 | 0.00 |
| Costo total (interno, no sale en el PDF) | 882.04 | 882.04 | 0.00 |
| Margen (interno, no sale en el PDF) | 185.41 | 185.41 | 0.00 |
| Margen % (interno, no sale en el PDF) | 17.37 | 17.37 | 0.00 |

Avisos del sistema al proponer:

- Sin recargo cargado para SEGURO en GYE

## (b) LCL con W/M, mínimo y seguro

Número **COT-2026-00002** · emitida 2026-10-08 · válida hasta 2026-11-22 · PDF `salidas/f3/COT-2026-00002_Importadora-de-Prueba-F3-S-A.pdf`

### Cálculo manual paso a paso

- **Flete LCL CNSHA → ECGYE**
  - W/M = max(1,2000; 600 / 1000 = 0,6000) = 1,2000
  - costo: 45 × tasa 1 = 45.0000 USD/u; mínimo 90 × 1 = 90.0000; max(1.2000 × 45.0000 = 54.0000; 90.0000) = **90.0000**
  - venta (MARKUP 20): 45 → 54.0000; mínimo de venta 108.0000; en USD 54.0000/u y 108.0000; max(1.2000 × 54.0000 = 64.8000; 108.0000) = **108.0000**
- **Seguro de carga (0,35 % del valor)**
  - PCT_VALOR: 15 000 USD / 100 = 150,0000; activado a mano (se propone apagado)
  - costo: 0.35 × tasa 1 = 0.3500 USD/u; mínimo 25 × 1 = 25.0000; max(150.0000 × 0.3500 = 52.5000; 25.0000) = **52.5000**
  - venta (MARKUP 20): 0.35 → 0.4200; mínimo de venta 30.0000; en USD 0.4200/u y 30.0000; max(150.0000 × 0.4200 = 63.0000; 30.0000) = **63.0000**
- **Desconsolidación**
  - MARGEN 20 %: 35 / 0,80
  - costo: 35 × tasa 1 = 35.0000 USD/u; mínimo 0 × 1 = 0.0000; max(1 × 35.0000 = 35.0000; 0.0000) = **35.0000**
  - venta (MARGEN 20): 35 → 43.7500; mínimo de venta 0.0000; en USD 43.7500/u y 0.0000; max(1 × 43.7500 = 43.7500; 0.0000) = **43.7500**
- **THC LCL**
  - WM 1,2000; gana el mínimo
  - costo: 12 × tasa 1 = 12.0000 USD/u; mínimo 25 × 1 = 25.0000; max(1.2000 × 12.0000 = 14.4000; 25.0000) = **25.0000**
  - venta (MARKUP 20): 12 → 14.4000; mínimo de venta 30.0000; en USD 14.4000/u y 30.0000; max(1.2000 × 14.4000 = 17.2800; 30.0000) = **30.0000**
- **Agenciamiento de aduana**
  - ENVIO = 1
  - costo: 120 × tasa 1 = 120.0000 USD/u; mínimo 0 × 1 = 0.0000; max(1 × 120.0000 = 120.0000; 0.0000) = **120.0000**
  - venta (FIJO 30): 120 → 150.0000; mínimo de venta 0.0000; en USD 150.0000/u y 0.0000; max(1 × 150.0000 = 150.0000; 0.0000) = **150.0000**

### Líneas: manual frente al sistema (USD)

| Concepto | Cantidad | Subtotal manual | Subtotal sistema | Fiscal | Diferencia |
|---|---|--:|--:|---|--:|
| Flete LCL CNSHA → ECGYE | 1.2000 WM | 108.0000 | 108.0000 | RECIBO_CAJA | 0.00 |
| Seguro de carga | 150.0000 PCT_VALOR | 63.0000 | 63.0000 | RECIBO_CAJA | 0.00 |
| Desconsolidación | 1.0000 ENVIO | 43.7500 | 43.7500 | FACTURA | 0.00 |
| THC LCL | 1.2000 WM | 30.0000 | 30.0000 | FACTURA | 0.00 |
| Agenciamiento de aduana | 1.0000 ENVIO | 150.0000 | 150.0000 | FACTURA | 0.00 |

### Totales

| Total | Manual | Sistema | Diferencia |
|---|--:|--:|--:|
| Recibo de caja (IVA 0 %) | 171.00 | 171.00 | 0.00 |
| Factura | 223.75 | 223.75 | 0.00 |
| IVA | 33.56 | 33.56 | 0.00 |
| Total USD | 428.31 | 428.31 | 0.00 |
| Costo total (interno, no sale en el PDF) | 322.50 | 322.50 | 0.00 |
| Margen (interno, no sale en el PDF) | 72.25 | 72.25 | 0.00 |
| Margen % (interno, no sale en el PDF) | 18.30 | 18.30 | 0.00 |

Avisos del sistema al proponer:

- Sin recargo cargado para ENTREGA_FINAL en ECGYE

## (c) FCL 40HC × 2 + 20GP × 1

Número **COT-2026-00003** · emitida 2026-10-08 · válida hasta 2026-11-22 · PDF `salidas/f3/COT-2026-00003_Importadora-de-Prueba-F3-S-A.pdf`

### Cálculo manual paso a paso

- **THC origen (Shanghai)**
  - genérico FCL: cubre 40HC y 20GP = 3 contenedores; puerto en China → recibo de caja
  - costo: 150 × tasa 1 = 150.0000 USD/u; mínimo 0 × 1 = 0.0000; max(3.0000 × 150.0000 = 450.0000; 0.0000) = **450.0000**
  - venta (MARKUP 20): 150 → 180.0000; mínimo de venta 0.0000; en USD 180.0000/u y 0.0000; max(3.0000 × 180.0000 = 540.0000; 0.0000) = **540.0000**
- **Flete FCL 20GP**
  - 1 contenedor 20GP
  - costo: 1500 × tasa 1 = 1500.0000 USD/u; mínimo 0 × 1 = 0.0000; max(1.0000 × 1500.0000 = 1500.0000; 0.0000) = **1500.0000**
  - venta (MARKUP 10): 1500 → 1650.0000; mínimo de venta 0.0000; en USD 1650.0000/u y 0.0000; max(1.0000 × 1650.0000 = 1650.0000; 0.0000) = **1650.0000**
- **Flete FCL 40HC**
  - 2 contenedores 40HC
  - costo: 2200 × tasa 1 = 2200.0000 USD/u; mínimo 0 × 1 = 0.0000; max(2.0000 × 2200.0000 = 4400.0000; 0.0000) = **4400.0000**
  - venta (MARKUP 10): 2200 → 2420.0000; mínimo de venta 0.0000; en USD 2420.0000/u y 0.0000; max(2.0000 × 2420.0000 = 4840.0000; 0.0000) = **4840.0000**
- **Emisión de BL**
  - ENVIO = 1
  - costo: 80 × tasa 1 = 80.0000 USD/u; mínimo 0 × 1 = 0.0000; max(1 × 80.0000 = 80.0000; 0.0000) = **80.0000**
  - venta (FIJO 20): 80 → 100.0000; mínimo de venta 0.0000; en USD 100.0000/u y 0.0000; max(1 × 100.0000 = 100.0000; 0.0000) = **100.0000**
- **THC destino genérico (20GP)**
  - el genérico FCL queda solo para el 20GP
  - costo: 140 × tasa 1 = 140.0000 USD/u; mínimo 0 × 1 = 0.0000; max(1.0000 × 140.0000 = 140.0000; 0.0000) = **140.0000**
  - venta (MARKUP 20): 140 → 168.0000; mínimo de venta 0.0000; en USD 168.0000/u y 0.0000; max(1.0000 × 168.0000 = 168.0000; 0.0000) = **168.0000**
- **THC destino 40HC**
  - el específico 40HC gana para los 2 de 40HC
  - costo: 180 × tasa 1 = 180.0000 USD/u; mínimo 0 × 1 = 0.0000; max(2.0000 × 180.0000 = 360.0000; 0.0000) = **360.0000**
  - venta (MARKUP 20): 180 → 216.0000; mínimo de venta 0.0000; en USD 216.0000/u y 0.0000; max(2.0000 × 216.0000 = 432.0000; 0.0000) = **432.0000**
- **Agenciamiento de aduana**
  - ENVIO = 1
  - costo: 120 × tasa 1 = 120.0000 USD/u; mínimo 0 × 1 = 0.0000; max(1 × 120.0000 = 120.0000; 0.0000) = **120.0000**
  - venta (FIJO 30): 120 → 150.0000; mínimo de venta 0.0000; en USD 150.0000/u y 0.0000; max(1 × 150.0000 = 150.0000; 0.0000) = **150.0000**

### Líneas: manual frente al sistema (USD)

| Concepto | Cantidad | Subtotal manual | Subtotal sistema | Fiscal | Diferencia |
|---|---|--:|--:|---|--:|
| THC origen | 3.0000 CONTENEDOR | 540.0000 | 540.0000 | RECIBO_CAJA | 0.00 |
| Flete FCL CNSHA → ECGYE 20GP | 1.0000 CONTENEDOR | 1650.0000 | 1650.0000 | RECIBO_CAJA | 0.00 |
| Flete FCL CNSHA → ECGYE 40HC | 2.0000 CONTENEDOR | 4840.0000 | 4840.0000 | RECIBO_CAJA | 0.00 |
| Emisión de BL | 1.0000 ENVIO | 100.0000 | 100.0000 | FACTURA | 0.00 |
| THC destino | 1.0000 CONTENEDOR | 168.0000 | 168.0000 | FACTURA | 0.00 |
| THC destino | 2.0000 CONTENEDOR | 432.0000 | 432.0000 | FACTURA | 0.00 |
| Agenciamiento de aduana | 1.0000 ENVIO | 150.0000 | 150.0000 | FACTURA | 0.00 |

### Totales

| Total | Manual | Sistema | Diferencia |
|---|--:|--:|--:|
| Recibo de caja (IVA 0 %) | 7030.00 | 7030.00 | 0.00 |
| Factura | 850.00 | 850.00 | 0.00 |
| IVA | 127.50 | 127.50 | 0.00 |
| Total USD | 8007.50 | 8007.50 | 0.00 |
| Costo total (interno, no sale en el PDF) | 7050.00 | 7050.00 | 0.00 |
| Margen (interno, no sale en el PDF) | 830.00 | 830.00 | 0.00 |
| Margen % (interno, no sale en el PDF) | 10.53 | 10.53 | 0.00 |

Avisos del sistema al proponer:

- Sin recargo cargado para ENTREGA_FINAL en ECGYE

## Revisión de François

Revisado y aprobado por François Ramírez el 2026-10-12.
