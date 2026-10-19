# Simulador de renta vitalicia: uso, límites y mantención

**Versión del modelo:** 1.0.0 · **Revisado sobre** `origin/main` en `4ee5fad` (asistente de 3 pasos), 2026-10-19.

Este documento responde tres preguntas: qué casos soporta el simulador, qué casos quedan fuera y qué hay que hacer para
que siga siendo confiable con el paso del tiempo. Complementa a `docs/SIM_RV_V1_MODELO.md` (las ecuaciones),
`docs/SIM_RV_V1_PENDIENTES.md` (el trabajo futuro) y `docs/specs/` (las pantallas y la ficha PDF).

## 1. Qué es y qué no es

* Es una **estimación referencial** de la pensión mensual de una renta vitalicia, en UF. Reproduce el simulador de
  Penta Vida (portal de ejecutivos) dentro de ±1 UF en los 435 casos con que se validó.
* **No es la normativa de la CMF/SP ni el código de Penta.** Se dedujo observando el portal (ingeniería inversa con datos
  ficticios). Algunas constantes son ajustes empíricos, no hechos confirmados (§8.3).
* **No persiste nada al calcular en pantalla.** Solo al descargar el PDF se registra un evento de auditoría de solo
  escritura (§2).
* Todo resultado lleva el aviso «Valores referenciales, no vinculantes».

## 2. Cómo se usa

**Quién puede:** usuarios con rol `executive` y superusuarios `ceo`/`cto`. El resto recibe 403. Cada usuario solo
simula leads que puede ver; si no, 404.

**Dónde:** detalle de un lead → «Simulador». El causante es el propio lead: su **sexo y fecha de nacimiento** salen de
su ficha (sin ellos no se puede simular).

| Paso | Qué se hace |
|---|---|
| 1. Datos de la simulación | Fecha (solo lectura: hoy, hora de Chile), tipo de pensión, tasa de venta, saldo AFP en UF, valor UF (opcional), meses garantizados, años de diferimiento, meses y % de aumento temporal. «Continuar» valida este paso. |
| 2. Grupo familiar | El causante aparece fijo en la primera fila. Se agregan, editan o eliminan un cónyuge y hasta 4 hijos (sexo, fecha de nacimiento, invalidez; en hijos, relación común o no común). |
| 3. Resultado | Tarjetas (Monto pensión, Saldo total, Tasa de venta; con renta temporal, también meses de diferimiento y renta temporal), resumen y grupo familiar. «Descargar PDF» genera el PDF y registra la auditoría. |

**Lo que el ejecutivo debe aportar y no se calcula solo:**

* **La tasa de venta.** Hoy se escribe a mano: el portal usa una tasa automática que cambia con el tiempo (2,63% el
  13-oct-2026; 2,88% antes) y no hay fuente automática (§8.4).
* **El saldo en UF.** El saldo del lead está en pesos; el simulador pide UF.
* **El valor UF** solo si se quiere ver equivalentes en pesos en el PDF.

**Mensajes de error frecuentes y qué significan:**

| Mensaje | Causa y qué hacer |
|---|---|
| «El lead no tiene sexo o fecha de nacimiento disponibles para simular.» | Completar esos datos en la ficha del lead. |
| «La edad del causante (N años) está fuera del rango validado (a–b).» | El caso no está respaldado; no se simula (§4). |
| «Un cónyuge inválido no es un escenario soportado por el simulador.» | Fuera de alcance (§5). |
| «renta temporal + RVD solo está reconstruida para causante individual, sin garantía ni aumento» | Con años de diferimiento no se admite familia, garantía ni aumento (§5). |
| Saldo, tasa, meses o porcentajes fuera de rango | Corregir el valor según la tabla de §4. |

**Qué queda registrado al descargar el PDF:** un evento append-only en `tpi.auditoria.detalle` (acción
`simulacion_renta_vitalicia`) con las entradas (incluidas las fechas de nacimiento del grupo familiar), el resultado y
un código de verificación. Sin nombres, RUT, correo ni teléfono. La retención es indefinida (decisión del humano,
2026-10-19). Si falla el registro, **no se entrega el PDF**.

## 3. Casos soportados (todos con tipo de pensión «Vejez edad»)

| Caso | Respaldo | Casos del fixture |
|---|---|---|
| Renta vitalicia inmediata, causante solo | ciega 22/22 | 87 (incluye garantía y aumento) |
| + cónyuge | ciega 24/24 | 59 |
| + garantía (meses) y aumento temporal (meses y %), con o sin cónyuge | ciegas 24/24 y 24/24 | (incluidos arriba) |
| + hijos, comunes o no, no inválidos, inválidos parciales o totales, con o sin cónyuge, hasta 4 | ciegas 38/38 | 49 sin cónyuge · 104 con cónyuge |
| Renta temporal + renta vitalicia diferida, **causante solo**, 1 a 10 años de diferimiento | ciegas 30/30 y 24/24 | 136 |

Total 435/435 dentro de ±1 UF; 335 exactos a 2 decimales. El fixture es `tests/data/casos_portal.json`.

**Combinaciones.** En renta inmediata se combinan libremente: cónyuge, 0 a 4 hijos, garantía y aumento temporal. En renta
temporal solo existe el causante, sin garantía ni aumento. La relación RVD/RT que ofrece el asistente es siempre 100%
(el motor y el servidor aceptan 50% y 51–99%, pero hoy no hay dónde elegirlos).

## 4. Rangos de entrada

Fuera de estos rangos el sistema **rechaza** la simulación con un mensaje, salvo la fecha (última fila).

| Dato | Rango | Dónde se hace cumplir |
|---|---|---|
| Saldo AFP (UF) | 500 – 100.000 (renta temporal: desde 1.000) | `app/web/routes/simulador.py` |
| Tasa de venta | 0,5% – 7,5% (renta temporal: hasta 8%) | ídem |
| Meses garantizados | 0 – 480 | ídem |
| Años de diferimiento | 0 – 10 (0 = renta inmediata) | ídem |
| Meses de aumento temporal / % de aumento | 0 – 600 / 0 – 100 | ídem |
| Valor UF (opcional) | mayor que 0 y hasta 1.000.000 | ídem |
| Edad del causante | individual 60–100 · con cónyuge 60–92 · con hijos sin cónyuge 62–92 · renta temporal 59–88 | `app/services/simulador_service.py` |
| Cónyuge | uno solo, 46–96 años | ídem |
| Hijos | hasta 4, 0–41 años | ídem y formulario |
| **Fecha de simulación** | validada del 15-oct-2025 al 13-oct-2026 | **no se hace cumplir**: se calcula igual para cualquier fecha (decisión `SIM-RV-V1-VENTANA`) |

## 5. Casos fuera del simulador

**Se rechazan con mensaje:** renta temporal con cónyuge, hijos, garantía o aumento (pendiente #7); cónyuge inválido (#8);
más de 4 hijos; cualquier valor fuera de los rangos de §4.

**No se ofrecen en pantalla:**

| Caso | Situación | Qué haría falta | Pendiente |
|---|---|---|---|
| Bono de reconocimiento | El portal devuelve error de servidor con cualquier bono > 0; no hay un solo valor de cesión observado. El motor lo rechaza. | Una fuente externa (Excel de la aseguradora, tablas de la Superintendencia de Pensiones) o que Penta lo corrija. | #3 |
| Vejez anticipada | El asistente solo ofrece «Vejez edad». El motor la acepta con un aviso; hay un único caso de control. | Campaña ciega de ≥ 24 casos con edades anticipadas. | #4 |
| Invalidez y sobrevivencia como tipo de pensión | No exploradas. | Exploración del portal y campañas. | #9 |
| Padre, madre, conviviente civil, M/P HFNM | No probados. | Campañas por parentesco. | #8 |
| Causante inválido | No existe forma de indicarlo. | Campañas. | #9 |
| Relación RVD/RT distinta de 100% | Soportada por el motor (validada), sin control en el asistente. | Decisión de producto. | — |

**Se calculan, pero sin respaldo (el sistema no avisa al usuario):**

| Caso | Riesgo conocido |
|---|---|
| **Cualquier fecha posterior al 13-oct-2026** (hoy incluida) | El motor emite un aviso interno que no llega a pantalla ni al PDF. Ver §8.5. |
| Causantes de 97 años o más | Error de hasta 0,41 UF. |
| Pareja del mismo sexo, hijo nacido antes de los 16 años del causante | Sin campañas; cada uno podría tener su propia regla. |
| 3 o 4 hijos | Respaldo delgado: 24 casos en total. |
| Cónyuge e hijos con causante de 60–61 años | El código admite 60–92 (rige el rango del cónyuge), pero el fixture con ambos parte en los 62. |
| Causante mujer | 135 de los 435 casos (los hombres, 300). |
| Saldos, tasas o edades en los bordes (pendiente #13) | La precisión se degrada hacia los extremos. |

**Fuera de la ficha PDF** (`docs/SIM_RV_V1_PENDIENTES.md` §5): retiro programado (RP AFP), PGU/BAC/TOTAL, comparativa de
varias opciones, teléfono del ejecutivo, estado civil. Tampoco existen folio correlativo, descarga posterior, línea de
tiempo ni envío por correo (#6, #14).

## 6. Qué entrega el PDF

* Banda con tratamiento (Sr./Sra.) y nombre del lead, «ESTUDIO DE PENSIÓN» y fecha.
* Fila de datos: fecha de nacimiento del causante, «CÓNYUGE: Sí» cuando hay cónyuge, tasa y valor UF (si se informó).
* **Renta inmediata:** Opción I (renta vitalicia inmediata y rescate total) y, solo con aumento temporal, Opción II.
* **Renta temporal:** pensión, meses de diferimiento, renta temporal mensual y equivalentes en pesos si hay valor UF.
* Pie con el ejecutivo y los datos de contacto de TPI, los supuestos y advertencias, y «Versión del modelo» y
  «Código de verificación».

**Supuestos propios de la ficha** (definidos en `docs/specs/SIM_FICHA_PDF_SPEC.md`; no salen del portal):
rescate total = pensión × meses garantizados; valor futuro con **inflación fija de 4%** anual
(`simulador_service.py`); rescate de la Opción II = pensión aumentada × meses del aumento + pensión base × (meses
garantizados − meses del aumento).

**Lo que el PDF no muestra:** el grupo familiar. Solo imprime «CÓNYUGE: Sí»; no recibe la lista de hijos ni sus datos.
La pensión depende de ellos, y hoy el documento no deja constancia. Sí quedan en pantalla (paso 3) y en la auditoría.

## 7. Precisión conocida

| Categoría | Casos | Error máximo en pensión (UF) |
|---|---|---|
| Individual | 63 | 0,12 hasta 96 años; 0,41 a los 99 |
| Cónyuge | 24 | 0,12 |
| Individual o cónyuge con garantía o aumento | 59 | 0,01 |
| Hijos | 153 | 0,04 (0,12 con 2 o más hijos inválidos y sin cónyuge) |
| Renta temporal + RVD | 136 | 0,15 (hasta ~0,16 UF con capital de ~3.000 a ~25.000 UF, 6 o más años y Prima/S bajo) |

La tolerancia que se garantiza es ±1 UF. Estas son las cifras medidas, no un compromiso adicional.

## 8. Cómo mantener el simulador vigente

### 8.1 Qué envejece y cuándo hay que actuar

| Qué | Por qué cambia | Dónde está | Disparador |
|---|---|---|---|
| **Tablas de mortalidad** (CB-H, RV-M, CB, B, MI-2020) | La CMF/SP publica tablas nuevas o ajusta los factores de mejoramiento. | `app/simulador_pension/datos/tablas_mortalidad.npz` | Publicación nueva, o el portal cambia de tablas. |
| **Factores de mejoramiento** (años 2021–2036) | El archivo solo trae 16 años. Más allá de 2036 el motor repite el factor de 2036. | ídem | Con el tiempo pesa más; ver §8.2. |
| **Constantes empíricas** (`c = −0,4568`, edad +1 mes, κ = 0,2445, tope 60 UF, umbral 3.000 UF) | Se ajustaron al comportamiento del portal en un periodo. | `mortalidad.py`, `renta_diferida.py` | El portal cambia, o la campaña canaria se degrada. |
| **Parámetros legales** (tasa de renta temporal 3,67%, cuota mortuoria 15 UF, pensiones de 60% / 50% / 15% / 11% / 50% adicional, límite de 24 años para hijos) | Cambia la normativa o la práctica de la aseguradora. | `renta_inmediata.py`, `renta_diferida.py` | Cambio normativo o del portal. |
| **Ventana de fechas validada** | Cada mes que pasa se aleja de la última campaña. | `VENTANA_VALIDADA` en `api.py` | Campaña canaria periódica (§8.5). |
| **Tasa de venta** | Cambia con el mercado; la ingresa el ejecutivo. | Formulario | Cada vez que cambie la del portal (§8.4). |
| **Inflación del PDF (4%)** | Supuesto fijo de la ficha. | `simulador_service.py` | Decisión de producto. |
| **Dependencias** (`reportlab`, `numpy`) | Vulnerabilidades y versiones. | `requirements/` | Las revisa el CI (`pip-audit`). |

### 8.2 Actualizar las tablas de mortalidad

Las tablas salen de un Excel oficial de la CMF, con una hoja por sexo y tipo, a través de `scripts/construir_tablas.py`
del paquete de referencia (`C:\desarrollos\REA\simulador_pension`). Cada tabla guarda `q(edad)` base 2020 (111 edades) y
los factores `AA(edad, año)` de 2021 a 2036. Según el uso: causante vejez, CB-H-2020 (hombre) y RV-M-2020 (mujer); cónyuge e
hijos no inválidos, CB-2020 y B-2020; hijos inválidos, MI-2020.

> **Dos cosas que hoy no están en este repositorio:** el script que construye el `.npz` (vive solo en el paquete REA) y el
> Excel original de la CMF (no lo encontré en esta máquina: busqué en `C:\desarrollos`, Descargas, Documentos y OneDrive). Antes de la primera actualización
> conviene traer el script a `scripts/` mediante una tarea y guardar la ubicación o el enlace oficial del Excel aquí.

Procedimiento:

1. Obtener el Excel nuevo de la CMF y comprobar que las hojas y columnas coinciden con las que lee el script (`HOJAS` y los
   índices de columna).
2. Generar el `.npz` y reemplazar `app/simulador_pension/datos/tablas_mortalidad.npz`.
3. **Volver a contrastar con el portal.** Las constantes empíricas se ajustaron con las tablas 2020; con tablas nuevas
   pueden dejar de calzar. Hacer una campaña ciega de ≥ 30 casos (§8.6) y regenerar el fixture, porque el actual son
   respuestas del portal con las tablas de entonces.
4. Ejecutar la regresión (§8.7). Criterio: 100% dentro de ±1 UF y sin degradar los umbrales por categoría.
5. **Subir `__version__`** en `app/simulador_pension/__init__.py`. La versión forma parte del código de verificación y se
   imprime en el PDF; así un PDF antiguo se puede reproducir con la versión de su fecha.
6. Actualizar `SIM_RV_V1_MODELO.md` (§4, precisión), `SIM_RV_V1_PENDIENTES.md`, CHANGELOG y BITACORA.

Notas sobre las tablas actuales: la tabla RV-M-2020 de mujeres pensionadas empieza en la edad 20 (las edades 0–19 están
vacías; el simulador no las usa). Con el paso de los años, una parte cada vez mayor del horizonte cae después de 2036 y
depende del factor repetido; **recomendación:** tener tablas nuevas antes de ~2030.

### 8.3 Constantes empíricas y legales

Las empíricas están marcadas *(empírica)* en `SIM_RV_V1_MODELO.md`. No se pueden verificar contra una norma, solo contra el
portal: si el portal cambia, la forma de enterarse es la campaña canaria. Si la causa es normativa (por ejemplo, otro porcentaje
de pensión de sobrevivencia), se cambia la constante en `renta_inmediata.py` o `renta_diferida.py`, se reajusta la regresión y se
sube `__version__`. Los rangos de §4 están repetidos en `api.py`, `simulador_service.py` y `simulador.py`: al ampliarlos hay
que cambiar los tres y sus pruebas.

### 8.4 Tasa de venta y valor UF

* Mientras no exista la tabla `tpi.tasas_venta` (migración clase D, pendiente #2), definir **quién informa la tasa vigente a
  los ejecutivos y con qué frecuencia**. Una tasa desactualizada produce una pensión desactualizada sin ningún aviso.
* El valor UF no se obtiene de ninguna fuente (pendiente #5): lo escribe el ejecutivo o se omite.

### 8.5 Ventana de fechas y campaña canaria

La ventana validada terminó el **13-oct-2026**. Desde entonces **toda simulación se calcula fuera del periodo respaldado**:
el motor emite un aviso interno (`warnings.warn`) que no llega a pantalla ni al PDF. Es una decisión consciente
(`SIM-RV-V1-VENTANA`, 2026-10-14) y deja de ser bloqueante, pero requiere la campaña canaria periódica. No encontré ninguna
programada.

Cada campaña, cuando se haga: ≥ 30 casos ciegos, actualizar `VENTANA_VALIDADA` en `api.py` y registrar el resultado. La
frecuencia sugerida es mensual.

### 8.6 Revalidar con el portal (resumen)

Detalle en `docs/SIM_RV_V1_PENDIENTES.md` §3. Requiere a una persona con credenciales del portal (el inicio de sesión no
se automatiza) y datos **ficticios**. Resumen: generar `etapaNN/casos.json`; **congelar las predicciones y su hash antes de
consultar**; ejecutar (~1 min por caso); puntuar con `scripts/informe_regresion.py` tras regenerar el fixture con
`scripts/generar_fixture.py`; cerrar Chrome y borrar el perfil temporal y las capturas (contienen datos de la cuenta). Las
herramientas están en `C:\desarrollos\REA\simulador_pension`.

### 8.7 Verificar tras cualquier cambio

```bash
python -m pytest tests/unit/test_sim_rv_regresion_portal.py tests/unit/test_sim_rv_validacion.py tests/unit/test_sim_rv_ventana.py -q
```

Hoy: 55 pruebas en verde. La regresión recalcula los 435 casos del fixture y exige ±1 UF. Además existen pruebas del PDF
(`test_sim_rv_pdf.py`), del código de verificación, de la auditoría y del flujo web
(`tests/unit/test_sim_rv_web.py`, `tests/integration/test_sim_rv_web.py`). La cobertura mínima del proyecto es 85%.

### 8.8 Cambiar el motor dentro del Harness

`app/simulador_pension/**` es un módulo puro (sin I/O ni importaciones del resto de `app`). La tarea del asistente de 3
pasos lo prohibía expresamente en sus restricciones. Un cambio de tablas o constantes necesita una tarea con alcance
explícito sobre esa ruta, la regresión de arriba como criterio de aceptación automático y una validación humana con casos
reales en DEV.

### 8.9 Calendario sugerido

| Cuándo | Qué |
|---|---|
| Cada mes | Campaña canaria (≥ 30 casos ciegos) y actualizar `VENTANA_VALIDADA`. |
| Cada cambio de tasa del portal | Informar la tasa nueva a los ejecutivos. |
| Cada release que toque el simulador | Las pruebas de §8.7. |
| Cuando la CMF/SP publique tablas | §8.2 completo. |
| Cada trimestre | Revisar que el Excel de la CMF y el script de tablas sigan localizables, y el estado de los pendientes #2, #3, #4. |
| Antes de ~2030 | Tener tablas con factores de mejoramiento posteriores a 2036. |

## 9. Observaciones de esta revisión

Hallazgos al revisar el código; ninguno bloquea el uso actual.

1. **La ventana de fechas ya venció y el usuario no lo sabe** (§8.5).
2. **El PDF no lista el grupo familiar** (§6). Candidato a tarea nueva: incluir una tabla «Grupo familiar»; falta decidir
   columnas y si las fechas de nacimiento de terceros deben ir en un documento que se entrega al cliente.
3. **Rango de edad con cónyuge e hijos:** el código aplica 60–92 y la evidencia empieza en 62 (§5).
4. **El script de tablas y el Excel de la CMF están fuera del repositorio** (§8.2).
5. **Opción II del PDF con aumento mayor que la garantía:** la fórmula de la ficha resta
   `pensión base × (garantía − aumento)`, que se vuelve negativo si el aumento supera a la garantía. Es lo que define la
   especificación; conviene confirmar con producto que ese es el valor que se quiere mostrar.
6. **Renta temporal desde los 59 años:** el código admite 59–88; el fixture de renta temporal parte en los 60 con la edad en
   meses del motor.
7. **El asistente no expone la relación RVD/RT** (queda en 100%) aunque el motor la valida (§3).

## 10. Referencias

* `docs/SIM_RV_V1_MODELO.md`: ecuaciones, constantes y precisión.
* `docs/SIM_RV_V1_PENDIENTES.md`: lo que falta, su estado y cómo retomarlo.
* `docs/SIM_RV_V1_REQUIREMENTS_MATRIX.md`: matriz de requisitos de la V1.
* `docs/specs/SIM_WIZARD_SPEC.md` y `docs/specs/SIM_FICHA_PDF_SPEC.md`: pantallas y ficha PDF.
* `app/simulador_pension/` (motor), `app/services/simulador_service.py`, `app/web/routes/simulador.py`.
* Paquete de referencia (investigación, campañas y scripts): `C:\desarrollos\REA\simulador_pension`.
