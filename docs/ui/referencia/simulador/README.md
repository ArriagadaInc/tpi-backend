# Referencia visual aprobada del simulador (v1, 2026-10-28)

Esta carpeta guarda **el resultado aprobado por el humano** de la vista previa local del simulador de renta vitalicia rediseñado como una
sola página, sin el botón «Continuar». Es la fuente exacta de la tarea `CRM-SIM-1-PAGINA-UNICA`: el Developer **no inventa el diseño**, lo
reproduce. Se retira de `main` cuando la tarea esté cerrada.

## Qué cambia para quien usa el simulador

- Todo está en una página: a la izquierda el formulario (tarjeta 1 «Datos de la simulación» con «Opciones de la renta» plegable, y tarjeta 2
  «Grupo familiar»); a la derecha el panel de resultado, que queda fijo al desplazarse.
- **«Simular» ejecuta el proceso**: calcula en el servidor y muestra el resultado en el panel de la derecha (en celular, debajo y con
  desplazamiento automático hasta él), conservando lo ingresado. Ya no existen «Continuar» ni «Volver».
- «Descargar PDF» vive en el panel de resultado y sigue generando el PDF efímero y registrando la auditoría. «Simular» no audita ni persiste.
- Enter en un campo ejecuta «Simular» (es el primer botón de envío del formulario), nunca el PDF.
- Corrige un defecto de la versión de tres pasos: en DEV se veían los tres pasos a la vez porque la regla `.wizard-pane { display: block }`
  anulaba el atributo `hidden`, así que «Continuar» parecía no hacer nada. Con la página única el defecto deja de existir.

## Qué contiene

| Ruta | Para qué |
|---|---|
| `app/web/templates/simulador.html` | Página única: encabezado con cliente y aviso referencial, formulario en dos tarjetas, tabla del grupo familiar, barra de «Simular», panel de resultado (vacío o con resultado) y modal de beneficiario |
| `app/web/static/css/app.css` | Hoja de estilos completa de `main` (`950e8fa`) con el bloque nuevo `Simulador de pension (CRM-SIM-1)` al final y sin las reglas `.wizard-*` que dejaron de usarse (pasos, paneles, secciones, resultados, resumen y sus reglas de tema oscuro). Se conservan `.wizard-form`, `.wizard-field`, `.wizard-field-label`, `.wizard-readonly`, `.wizard-empty`, `.wizard-table` y `.wizard-modal*`, que la página y el modal siguen usando |
| `app/web/static/js/simulador_wizard.js` | Mismo modal de beneficiario; las filas de la tabla usan botones de texto «Editar» y «Quitar» (clases `sim-row-action*`), se quitó la columna N° y, tras simular en pantallas de hasta 1100 px, desplaza la vista hasta el resultado |
| `app/web/routes/simulador.py` | Se eliminan los `intent` `continuar`, `volver_paso1` y `volver_paso2`, la función `_parse_paso1_form` y el parámetro `active_step`. Un `intent` desconocido (un formulario viejo abierto durante el despliegue, o uno manipulado) se trata como `simular`: nunca genera PDF ni auditoría |
| `tests/unit/test_sim_wizard.py` | Las pruebas del asistente reescritas para la página única, igual de estrictas que las que reemplazan (ver «Pruebas») |

## Pruebas

`tests/unit/test_sim_wizard.py` de esta carpeta reemplaza al actual: las seis pruebas que dependían de los pasos se reescriben para la página
única y se agregan las del `intent` desconocido, del orden de los botones, de «Opciones de la renta» y del 422 sin resultado. Se mantienen sin
cambios las de PDF con auditoría, renta temporal, cónyuge inválido, sin CDN, JS propio, azul marino de la ficha y sin naranja. Con esta versión
pasan las 15 pruebas del archivo y las demás del simulador (`test_sim_rv_web` unitaria e integración, `test_sim_rv_regresion_portal`).

## Cómo se generó

La vista previa se construyó sobre `main` con datos ficticios (tres perfiles) y se revisó en el navegador en escritorio y celular (320 y 375 px),
en tema claro y oscuro, con la skill `ui-ux-pro-max` sobre el sistema visual existente (`docs/UI_DESIGN_SYSTEM.md`). El humano la aprobó el
2026-10-28. La frase exacta del aviso «valores referenciales (no vinculantes)» se conserva porque una prueba existente la exige.

## Cómo se aplica

Copiar cada archivo de esta carpeta a su ruta de destino (la ruta relativa dentro de esta carpeta es la ruta destino; `README.md` no se copia).
El resultado debe ser **idéntico a la referencia** ignorando diferencias de fin de línea
(`git diff --no-index --ignore-cr-at-eol <referencia> <destino>` sin diferencias). Si `app/web/static/css/app.css` cambió en `main` desde
`950e8fa`, hay que reaplicar solo las dos partes propias (el bloque `Simulador de pension (CRM-SIM-1)` y el borrado de las reglas `.wizard-*`
sin uso), no reemplazar el archivo entero.

## Qué NO es

No es un rediseño del resto del CRM ni autoriza cambios de comportamiento del cálculo: el motor `app/simulador_pension/**`, las validaciones, la
autorización (403 fuera de los perfiles permitidos, 404 si el lead no es visible), el CSRF, el PDF y la auditoría no cambian. Tampoco agrega
tipografías, scripts ni librerías. Los únicos colores literales nuevos son los del azul marino de la ficha (`#0f243e`, `#b8cce4`, `#ffffff`)
en la tarjeta de resultado, los mismos que ya usa el encabezado del modal.
