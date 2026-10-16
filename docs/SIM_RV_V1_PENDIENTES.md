# Pendientes del simulador de renta vitalicia (para retomar después de la V1)

Fecha: 14-oct-2026. Este documento acompaña a la tarea `SIM-RV-V1` (integración en `tpi-backend`, PDF efímero, perfil ejecutivo).
La V1 incluye **solo lo validado**; todo lo demás está aquí, con su estado, lo que falta para retomarlo y un orden sugerido.

## 1. Qué incluye la V1 (todo validado contra el portal; 435/435 casos dentro de ±1 UF)

| Alcance V1 | Respaldo |
|---|---|
| Vejez edad, renta vitalicia inmediata, causante solo | ciega 22/22 |
| + cónyuge | ciega 24/24 |
| + garantía (meses) y aumento temporal (meses y %), con o sin cónyuge | ciegas 24/24 y 24/24 |
| + hijos (comunes o no; no inválidos, inválidos parciales y totales), con o sin cónyuge, hasta 4 hijos | ciegas 38/38 (la 1ª ronda falló 1 de 36; se corrigió y se revalidó) |
| Renta temporal + renta vitalicia diferida, causante solo, RVD 100%, 50% u "Otro RVD" 51–99%, 1 a 10 años de diferimiento | ciegas 30/30 y 24/24 |

Rangos realmente cubiertos (fuera de ellos el motor extrapola sin evidencia): causante 60–100 años (con cónyuge 60–92, con hijos
62–92, renta temporal 59–88); cónyuge 46–96; hijos 0–41; saldo 500–100.000 UF (renta temporal desde 1.000); tasa de venta 0,5–7,5%
(8% en renta temporal); garantía hasta 480 meses; aumento hasta 600 meses y 100%; fechas de simulación validadas 15-oct-2025 a
13-oct-2026 (desde SIM-RV-V1-VENTANA la ventana queda abierta por decisión del humano: se genera para cualquier fecha con aviso de
valores referenciales).

## 2. Fuera de la V1: qué falta y cómo retomarlo

Prioridad sugerida: A (alto valor comercial), B (medio), C (bajo o depende de terceros).

| # | Pendiente | Estado hoy | Qué se necesita para retomarlo | Prio. |
|---|---|---|---|---|
| 1 | **Revalidación periódica de la ventana de fechas (recomendable, ya no bloqueante)** | Validado hasta el 13-oct-2026. Desde `SIM-RV-V1-VENTANA` (decisión del humano 2026-10-14) la ventana queda abierta: la simulación se genera para cualquier fecha con aviso de valores referenciales; el motor conserva `VENTANA_VALIDADA` y un `warnings.warn` informativo que no llega a pantalla ni al PDF. | Campaña canaria periódica (≥ 30 casos ciegos, ver §3) y actualizar `VENTANA_VALIDADA`. Ya no es precondición de cada release; se recomienda repetirla (sugerido: mensual) para acotar la extrapolación fuera del periodo validado. | A |
| 2 | **Tasa de venta administrada por el backoffice** | V1: la ingresa el ejecutivo en el formulario. | Tabla `tpi.tasas_venta` (tipo de pensión, vigencia, tasa, autor) = migración clase D, bloqueada en AWS (decisión humana), más pantalla de administración y auditoría. Hasta entonces la tasa es un dato de entrada. | A |
| 3 | **Bono de reconocimiento** | El portal devuelve error de servidor (`NullReference`) en toda consulta con bono > 0: 19 intentos con montos, fechas, sexos, edades, tipos de pensión y tasas distintos. No hay un solo valor de cesión observado. | Una fuente externa: Excel de la aseguradora, tablas de valor de cesión de la Superintendencia de Pensiones o un ejemplo válido de otro simulador; o que Penta corrija el error. Sin eso no se puede modelar. | A |
| 4 | **Vejez anticipada** | Un solo caso de control (idéntico a vejez edad). La API del paquete avisa. | Campaña ciega de ≥ 24 casos con causantes en edades anticipadas (mujeres bajo 60, hombres bajo 65). | B |
| 5 | **Valor UF y conversión pesos ↔ UF** | V1: el ejecutivo ingresa el saldo en UF (el saldo del lead está en pesos). | Fuente de UF cacheada (CMF o mindicador.cl) con manejo de caída, o campo de valor UF en el lead. Define también cuándo mostrar equivalentes en CLP en el PDF. | B |
| 6 | **Persistencia, historial y folio** | `SIM-EVIDENCIA-ENTRADAS` guarda las entradas y el resultado como evidencia append-only de solo escritura en `tpi.auditoria.detalle` (sin nombres, RUT, correo ni teléfono); la aplicación no lo lee. Queda pendiente la política de retención (decisión humana) y mostrar la evidencia en la línea de tiempo (`SIM-HISTORIAL-LINEA-TIEMPO`). | Política de retención y de datos personales, folio correlativo, descarga posterior y vista de línea de tiempo. Decisión de producto + migración (clase D). | B |
| 7 | **Renta temporal con cónyuge, hijos o garantía** | No probado (en el portal el aumento temporal desaparece con diferimiento). | Campaña de exploración con REA para cada combinación y luego campañas ciegas. La API rechaza estas combinaciones con `NoValidadoError`. | B |
| 8 | **Parentescos no probados** | Padre, madre, conviviente civil, M/P HFNM, cónyuge inválido, parejas del mismo sexo, más de 4 hijos y un hijo nacido antes de los 16 años del causante. | Campañas dirigidas por parentesco; cada uno puede tener su propia regla. | B |
| 9 | **Invalidez parcial/total y sobrevivencia como tipo de pensión** | No exploradas (el formulario las ofrece). | Exploración del flujo de beneficiarios del portal y campañas. Probablemente tablas distintas (MI-2020 para el causante). | C |
| 10 | **`TotalCuotaMortuoriaUnitaria`** | Campo de la respuesta cuyo significado quedó sin identificar (no es `Q`). | Más datos para despejarlo; no afecta la pensión. | C |
| 11 | **Comisión de la renta temporal** | Error de hasta 0,16 UF con capital entre ~3.000 y ~25.000 UF, diferimiento ≥ 6 años y `Prima/S` bajo. El origen de κ = 0,2445 y del umbral de 3.000 UF no está identificado. | Barridos dirigidos en esa zona. No bloquea: está dentro de ±1 UF. | C |
| 12 | **Otras anomalías conocidas** | Dos o más hijos inválidos sin cónyuge: hasta 0,12 UF. Causantes de 97 años o más: hasta 0,41 UF. | Más campañas; la sensibilidad a la edad cerca de los 100 años es muy alta. | C |
| 13 | **Rangos más amplios** | La V1 rechaza (o advierte) fuera de los rangos de la sección 1. | Ampliar las campañas hacia los bordes (saldos < 500 o > 100.000 UF, tasas fuera de 0,5–8%, edades 55–59 y > 92 con familia). | C |
| 14 | **Entrega por correo / firma / marca** | La V1 solo descarga el PDF. | Decisiones de producto y de protección de datos. | C |
| 15 | **Mover el escritor de auditoría a `app/repositories/`** | El escritor del evento de auditoría vive en `app/services/simulador_auditoria.py` (abre su propia conexión con `get_db_connection`) porque el alcance de `SIM-RV-V1` no permite editar `app/repositories/**` (guarda del Harness); se aparta de la convención de capas. | Tarea posterior con ese alcance: mover el INSERT a `SolicitudRepository` (patrón `record_xlsx_export_event`) y que `simulador_service.py` lo llame por el repositorio. | C |

## 3. Cómo revalidar o ampliar con REA (procedimiento)

Requiere una persona con credenciales del portal, porque el inicio de sesión no se automatiza.

1. Abrir Chrome con depuración remota y un perfil temporal; la persona inicia sesión en el portal de ejecutivos.
2. Generar la campaña: crear `etapaNN/casos.json` y **congelar las predicciones del paquete y calcular su hash antes de consultar**.
3. Ejecutar la campaña (≈ 1 min por caso; reintentar los que fallan por estado de la página).
4. Puntuar con el informe de regresión después de regenerar el fixture.
5. Criterio: 100% dentro de ±1 UF y sin degradación de los umbrales por categoría de la regresión.
6. Cerrar Chrome, borrar el perfil temporal y las capturas crudas (contienen datos de la cuenta).

Todas las consultas usan datos ficticios; hasta hoy se hicieron 457 simulaciones en la cuenta autorizada.

## 4. Referencias

* `docs/SIM_RV_V1_MODELO.md` (ecuaciones y precisión).
* Motor portado: `app/simulador_pension` (sin cambios en la lógica numérica respecto del paquete de referencia).
* Fixture de regresión: `tests/data/casos_portal.json` (435 casos del portal).
* Paquete de referencia (fuente de la ingeniería inversa): `C:\desarrollos\REA\simulador_pension`.

## 5. Fuera de alcance de la ficha «Estudio de pensión» (SIM-FICHA-PDF)

Decisiones documentadas en `docs/specs/SIM_FICHA_PDF_SPEC.md` §5; no se inventan y quedan aquí para
retomarlas cuando existan los datos o la decisión de producto:

| # | Elemento del ejemplo omitido | Motivo |
|---|---|---|
| 1 | Fila «RP (AFP)» (retiro programado) | Dato de la AFP que el sistema no tiene. |
| 2 | Bloque «PGU / BAC / TOTAL» | Beneficios del Estado que el sistema no modela. |
| 3 | Comparativa de varias opciones a la vez | El MVP muestra una fila con la opción simulada. |
| 4 | Teléfono personal del ejecutivo | El modelo de usuario no lo tiene. |
| 5 | Estado civil | El modelo no lo tiene. |
| 6 | Renta temporal con renta vitalicia diferida | El ejemplo no la cubre; se conserva la sección actual con la nueva apariencia. |
