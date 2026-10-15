# Especificación: ficha PDF «Estudio de pensión» (tarea `SIM-FICHA-PDF`)

Origen: la ficha de ejemplo «Estudio de pensión» de TPI (una página, hecha en Excel y exportada a
PDF) que entregó el humano el 2026-10-15. **El ejemplo contiene datos de una persona real: no se
copia a este repositorio ni se usa en pruebas.** Las pruebas usan datos sintéticos, y esta
especificación contiene solo el diseño y las reglas.

## 1. Página y tipografía

- Carta apaisada (792 × 612 pt), contenido centrado con márgenes de unos 20 pt. El ejemplo deja
  mucho espacio arriba por su origen en Excel; eso no se replica.
- Tipografía: Arial en el ejemplo, que en PDF estándar equivale a Helvetica. Las celdas de datos van
  en negrita cursiva (Helvetica-BoldOblique) y las cabeceras en negrita.
- Tamaños: 14 pt para nombre y título, 8 a 9 pt para datos, 6 pt para los rótulos de columna.

## 2. Colores (marca TPI)

| Uso | Color |
|---|---|
| Bandas y cabeceras de tabla | azul marino `#0f243e` |
| Texto claro sobre las bandas | `#b8cce4` y blanco |
| Celda destacada (valor UF) | azul claro `#b7dee8` |
| Texto de cuerpo | `#1d1b10` |
| Bordes de tabla | negro, 0,5 a 1 pt |
| Resaltado amarillo `#ffff00` | solo para totales; no se usa en el MVP |

## 3. Estructura, de arriba a abajo

**a) Banda superior** (azul marino): a la izquierda el tratamiento y el nombre del cliente («Sr.» si
el sexo es masculino, «Sra.» si es femenino); al centro el título «ESTUDIO DE PENSIÓN»; a la derecha
la fecha de generación en formato dd-mm-aaaa.

**b) Fila de datos** bajo la banda, con celdas con borde: «FECHA DE NAC: aaaa/mm/dd», «CÓNYUGE:»
(solo si hay), «T: x,xx%» (tasa de venta) y una celda destacada azul claro con el valor UF en pesos
(solo si se informó). El ejemplo también tiene «ESTADO CIVIL», «MAIL» y «RUT»: **se omiten**. Se
mantiene la decisión vigente de que el PDF no lleva RUT, correo ni teléfono del lead. «ESTADO CIVIL»
se omite porque el modelo no lo tiene.

**c) «OPCIÓN I»** (título en negrita 12 pt, sin banda). Tabla con cabecera azul marino «Renta
Vitalicia Inmediata» y, a la derecha, «Rescate Total». Debajo, una fila con «Capital: X UF» y
«T: y%». Rótulos de columna: «Años», «[UF]», «[$]Valor Actual» y, para el rescate, «[UF]».
- Una fila por opción simulada. La etiqueta es «Simple» si no hay garantía, o «Periodo Garantizado»
  con Años igual a meses garantizados dividido por 12.
- Pensión en UF con 2 decimales y formato es-CL (punto de miles y coma decimal). «$ Valor Actual» como
  entero con punto de miles, solo si hay valor UF. Después, una flecha «>>>>» y el Rescate Total en UF.
- Nota al pie, en negrita de 8 pt: «Esta Opción es vitalicia sin recálculo».

**d) «OPCIÓN II»** (solo si la simulación incluye aumento temporal). Dos bloques unidos por «>>>>»:
- Izquierda, «Aumento Temporal de Pensión» (Capital y T; columnas «Años», «Meses», «[UF]», «[$]»).
- Derecha, «Renta Vitalicia Inmediata» (Capital y T; «Sin Excedente», «Años» garantizados, «[UF]»,
  «[$]Valor Actual»), «Inflación Futura 4%» («[$]Valor Futuro») y «Rescate Total» («[UF]»).
- La misma nota «Esta Opción es vitalicia sin recálculo».

**e) Pie.** A la izquierda el bloque de contacto: nombre del ejecutivo en negrita azul marino y
debajo «Tu Pensión Inteligente». A su derecha, con íconos simples, el correo
`contacto@tupensioninteligente.cl`, el sitio `www.tupensioninteligente.cl` y la dirección
«Dr. Sotero del Río 508, Of. 612, Santiago». Van como **texto plano, no como enlaces activos**
(AC-8 de SIM-RV-V1). Sin teléfono, porque el modelo de usuario no lo tiene.

**f) Banda inferior** azul marino con el logo oficial (`official-logo-on-dark.png`, ancho cercano a
270 pt, proporción 754 × 161).

**g) Se conservan de SIM-RV-V1:** la leyenda «Estimación referencial no vinculante», la versión del
modelo, el código de verificación, el pie «Documento referencial no vinculante — Tu Pensión
Inteligente», el escape de marcado de todo texto de datos y los metadatos genéricos sin PII.

## 4. Reglas de cálculo

Se dedujeron de las filas del ejemplo y se comprobaron contra ellas (coinciden hasta el redondeo de
las pensiones mostradas). Los números de abajo son **sintéticos**, no del ejemplo.

- **Rescate Total (UF) = pensión mensual (UF) × meses garantizados.** Ejemplo: 10,00 UF con 10 años
  garantizados da 10,00 × 120 = 1.200,00 UF.
- **$ Valor Actual = pensión (UF) × valor UF ($).**
- **Valor Futuro ($) = Valor Actual × 1,04 elevado a los años de aumento temporal.** Ejemplo:
  400.000 × 1,04³ ≈ 449.946.
- **Rescate Total de la Opción II = pensión aumentada × meses del aumento + pensión base × (meses
  garantizados − meses del aumento).** Ejemplo: con aumento de 36 meses a 20,00 UF, base de
  10,00 UF y 20 años garantizados, 20,00 × 36 + 10,00 × (240 − 36) = 2.760,00 UF.

## 5. Fuera de alcance (decisiones pendientes del humano; no inventar)

- La fila «RP (AFP)» (retiro programado): es un dato de la AFP que el sistema no tiene.
- El bloque «PGU / BAC / TOTAL»: beneficios del Estado que el sistema no modela.
- La comparativa de varias opciones a la vez (3 o 4 filas por tabla, como en el ejemplo): el MVP
  muestra una fila con la opción simulada.
- El teléfono personal del ejecutivo y el estado civil: el modelo no los tiene (se omiten).
- La renta temporal con renta vitalicia diferida: el ejemplo no la cubre; se conserva su sección
  actual, con la nueva apariencia (banda, tipografía, colores y pie).
