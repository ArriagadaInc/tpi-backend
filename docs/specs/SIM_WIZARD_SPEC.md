# Especificación: simulador en 3 pasos (tarea `SIM-WIZARD-3-PASOS`)

> **Superada por `CRM-SIM-1-PAGINA-UNICA` (2026-10-28).** Desde esa tarea el simulador ya no es un asistente de 3 pasos:
> es una sola página con el formulario a la izquierda y el panel de resultado a la derecha, sin «Continuar» ni «Volver».
> Esta especificación se conserva como histórico del flujo original; el diseño vigente está en
> `docs/ui/referencia/simulador/` y en `docs/SIMULADOR_USO.md`.

Origen: capturas del flujo de un simulador de referencia entregadas por el humano el 2026-10-15
(5 pantallas: datos de la simulación, grupo familiar vacío, modal «Agregar beneficiario», grupo
familiar con filas y resultado). Esta especificación traduce esas capturas a texto, porque el
Developer no ve imágenes.

**Se replica el flujo y la estructura, no la marca.** La marca es la de TPI: logo oficial
(`app/web/static/img/official-logo-on-light.png` y `official-logo-on-dark.png`), la paleta del CRM
(variables CSS de `app/web/static/css/app.css`, tema claro y oscuro) y el azul marino de la ficha
(`#0f243e`, texto claro `#b8cce4`). No se usan logos, nombres ni el color naranja del simulador de
referencia en ninguna pantalla ni PDF.

## 1. Estructura general

- Título de página: «Simulador de pensión mensual».
- Indicador de 3 pasos: círculos conectados por una línea, con la etiqueta a la derecha de cada
  círculo: 1 «Datos de la simulación», 2 «Grupo familiar», 3 «Resultado». El paso activo va
  resaltado; los pasos ya completados muestran un ícono de lápiz y se pueden volver a abrir.
- Cada sección es una tarjeta de bordes redondeados con sombra suave y un título en mayúsculas
  pequeñas con ícono y color de acento.
- Botones de pie: paso 1 «Continuar»; paso 2 «Volver» y «Simular»; paso 3 «Volver» y
  «Descargar PDF».

## 2. Paso 1 — Datos de la simulación

Tarjeta «DATOS DE LA RENTA VITALICIA A SIMULAR» (cuadrícula de 4 columnas, campos con etiqueta
flotante sobre el borde):

- **Fecha de simulación\*** — solo lectura: la fecha actual de America/Santiago, calculada en el
  servidor (no editable, igual que en SIM-RV-V1).
- **Tipo de pensión\*** — lista con las opciones que la V1 soporta; hoy solo «Vejez edad»
  (preseleccionada). El escenario concreto (renta inmediata, o renta temporal con renta vitalicia
  diferida) se sigue deduciendo de los demás campos, como hasta ahora.
- **Tasa de venta (%)\*** — siempre visible y obligatoria (rango de la V1: 0,5 a 7,5; 8 solo con
  renta temporal). No hay casilla «Tasa de venta personalizada» porque el sistema no tiene una tasa
  por defecto (pendiente #2 de `docs/SIM_RV_V1_PENDIENTES.md`).
- **Meses garantizados** (0 por defecto), **Años período diferido** (0), **Meses de aumento
  temporal** (0) y **% aumento temporal** (0,00), con los rangos validados de la V1.

Tarjeta «DATOS PREVISIONALES»:

- **Saldo cuenta AFP (UF)\*** (rango de la V1: 500 a 100.000; desde 1.000 con renta temporal).
- **Valor UF ($)** opcional, solo para mostrar equivalentes en pesos en el PDF.
- No se muestra «Valor nominal bono de reconocimiento»: la V1 rechaza cualquier bono mayor que 0.

Botón «Continuar»: valida este paso en el servidor y, si hay errores, los muestra en este mismo
paso (ver `SIM-UX-AJUSTES`); si todo es válido, pasa al paso 2.

## 3. Paso 2 — Grupo familiar

Tarjeta «GRUPO FAMILIAR» con el botón «Agregar beneficiario» (abre un modal). Sin beneficiarios
muestra el texto «No se han agregado beneficiarios. Utilice el botón para agregar.».

Tabla con las columnas N°, Parentesco, Fecha nacimiento, Sexo, Condición invalidez, Padre/Madre y
Edad, más una columna de acciones (editar y eliminar, con ícono). La fila 1 es siempre el
**Causante** (el lead, con su sexo y fecha de nacimiento precargados): se muestra, pero no se edita
ni se elimina.

Modal «Agregar beneficiario» (cabecera con el color de marca y botón para cerrar):

- **Parentesco\*** (Cónyuge, Hijo/a).
- **Tipo de relación con padre/madre** — solo para hijos (común o no común); deshabilitado para el
  cónyuge.
- **Sexo\***.
- **Condición de invalidez\*** (No inválido, Inválido parcial, Inválido total).
- **Fecha de nacimiento\*** (selector de fecha) y **Edad** (calculada, solo lectura).
- Botones «Cancelar» y «Agregar».

Reglas de la V1 que el modal respeta: un solo cónyuge, máximo 4 hijos, no se ofrecen otros
parentescos, y un cónyuge inválido se rechaza con un mensaje claro.

## 4. Paso 3 — Resultado

- Tarjeta «RESULTADO DE LA SIMULACIÓN» con tres tarjetas grandes: **Monto pensión** (UF, 2
  decimales), **Saldo total** (UF) y **Tasa de venta** (%), con la cifra en el color de acento y la
  unidad debajo. En renta temporal se agregan **Renta temporal** (UF) y **Meses de diferimiento**.
- Tarjeta «RESUMEN DE SIMULACIÓN» (4 columnas): Fecha simulación, Tipo pensión, Saldo cuenta AFP
  (UF), Tasa de venta, Meses garantizados, Meses aumento temporal, % aumento temporal y Años
  diferidos.
- Tarjeta «GRUPO FAMILIAR» con la misma tabla, sin acciones.
- Aviso visible: «Valores referenciales, no vinculantes».
- Botones «Volver» y «Descargar PDF».

## 5. Comportamiento

- **El servidor es la fuente de verdad.** Toda validación (rangos, edades, CSRF, autorización 403 y
  404) y todo cálculo ocurren en el servidor; la interfaz solo guía.
- Calcular el resultado en pantalla **no persiste ni audita nada**. «Descargar PDF» genera el PDF en
  memoria y registra el evento de auditoría, como hoy (AC-9 y AC-11 de SIM-RV-V1).
- Al volver de un paso a otro se conservan los datos ingresados, sin guardarlos en base de datos.
- Los errores de validación aparecen en el mismo paso, junto al campo o en un aviso arriba.
- Accesibilidad básica: etiquetas asociadas a los campos, foco dentro del modal y cierre con Esc.
- Usable en pantallas de 1280 px y de 768 px.
- Sin dependencias nuevas: JavaScript propio en `app/web/static/js/`, sin CDN ni librerías.
- La ruta base sigue siendo `/leads/{id}/simulador`; solo la usan executive, ceo y cto.
