# Bitacora del Proyecto

## Proposito

Este documento es una bitacora viva para dar continuidad tecnica al proyecto.
La idea es que cualquier desarrollador pueda abrir este archivo y entender:

- que se hizo
- por que se hizo
- que problemas aparecieron
- como se resolvieron
- que falta por hacer
- que riesgos siguen abiertos

## Reglas de Actualizacion

- Agregar nuevas entradas arriba del historial, con fecha ISO `YYYY-MM-DD`.
- Registrar tareas, hallazgos, decisiones, riesgos y siguiente paso concreto.
- Cada vez que se actualice README.md, docs/ o documentacion operativa relevante, actualizar tambien esta bitacora en la misma tarea.
- No registrar secretos, passwords, endpoints con credenciales, ni datos personales reales.
- Si una tarea queda incompleta, dejar el ultimo estado confiable y el paso exacto para retomarla.
- Si una tarea toca base de datos o infraestructura, documentar impacto y rollback.
- En lo posible, enlazar archivos y documentos relevantes del repo.

### 2026-10-21 - CRM: los adjuntos se simplifican a dos pasos y sin tabla (CRM-ADJUNTOS-COMENTARIOS)

- Decisión del humano: el mismo día de definir el diseño (PR #107) se pidió una forma más simple que una tabla de adjuntos. Se
  aprobó un diseño **sin tabla** y **sin re-codificar imágenes** en la primera versión.
- Nuevo diseño: el archivo y sus datos (tipo verificado, tamaño, SHA-256, quién lo subió) viven en S3 con clave `leads/<id_lead>/<uuid>`;
  la nota guarda una marca `[adjunto:<tipo>:<uuid>]` que agrega el servidor; el antivirus es GuardDuty Malware Protection for S3, que
  etiqueta cada objeto, y una política del bucket impide leer lo que no tenga `NO_THREATS_FOUND`; los eventos se auditan en `tpi.auditoria`.
  `tpi.auditoria` no sirve de registro porque su contrato prohíbe usar `detalle` como almacén de relaciones operativas.
- Efecto en el backlog: de cuatro pasos a dos. Se eliminan la tabla con su migración 010 (clase D) y el paso del antivirus. Quedan
  `CRM-ADJUNTOS-1-INFRA-S3` (bucket, permisos y GuardDuty; lo aplica el humano con Claude interactivo) y `CRM-ADJUNTOS-2-CODIGO`
  (clase C, porque agrega variables al compose de despliegue de DEV).
- Riesgos aceptados además de la visibilidad: al no re-codificar, EXIF y GPS de las imágenes quedan visibles; no hay transacción entre S3 y
  la nota (puede quedar un objeto huérfano si falla el borrado tras un error); no se puede consultar por SQL qué leads tienen adjuntos.
  Camino de vuelta: migrar a una tabla con los datos de las marcas y de S3.
- Cambio de este PR (solo documentación y backlog): `docs/ADJUNTOS_COMENTARIOS_DISENO.md` reescrito y `tasks/backlog.yaml` actualizado.

### 2026-10-21 - CRM: diseño de los adjuntos en las notas del lead (CRM-ADJUNTOS-COMENTARIOS)

- Decisiones del humano: PDF, PNG y JPEG verificados por contenido; 10 MB por archivo, 5 por nota y 25 MB por petición; **vista en línea**
  (imágenes en el detalle y PDF en una pestaña nueva) además de la descarga; retención mientras exista el lead y borrado a solicitud del
  titular (Ley 21.719); cada subida, vista y descarga auditada; visibles para **todos los usuarios con acceso al lead**.
- Riesgo aceptado: la interfaz enmascara los datos personales, pero un archivo no se puede enmascarar (una foto de una cédula la vería
  cualquier usuario con acceso al lead). Compensaciones: aviso al subir, auditoría de cada vista, borrado a solicitud y revisión tras el
  primer mes. Se deja constancia en `docs/SEGURIDAD.md` al implementar.
- Hallazgo que condiciona el diseño: las notas no son una entidad; son texto agregado a `tpi.leads.comentarios` (máximo 1000 caracteres
  por nota). Los adjuntos serán una tabla propia ligada al lead, que se sube junto con la nota, sin migrar las notas.
- Cambio de este PR (solo documentación y backlog): `docs/ADJUNTOS_COMENTARIOS_DISENO.md` y la división en cuatro pasos en el backlog:
  bucket S3 y permisos (clase C), tabla y migración 010 (clase D), código con interruptor apagado (clase A) y antivirus con habilitación
  (clase C). Los pasos 1 y 2 son independientes. `CRM-ADJUNTOS-COMENTARIOS` queda como paraguas y no se activa.

### 2026-10-21 - Seguridad: Streamlit retirado y Pillow 13 desplegados; excepción de pip-audit cerrada (SEG-DESACOPLAR-STREAMLIT)

- Resultado: el humano aceptó AC-7 y AC-8 en DEV (inicio de sesión en el backoffice, lista y detalle de leads, asistente del simulador con
  el PDF y su logo, y API pública). La tarea terminó en la ronda 0, sin rechazos del Reviewer.
- Cambio (PR #103, `0c9b165`; 58 archivos, +365 y −3128 líneas): el código legado de Streamlit salió del repositorio, `pillow` subió a
  13.0.0 y se retiró la excepción de `pip-audit` (8 avisos de Pillow 12.3.0, PR #99, que vencía el 2026-11-20) junto con su prueba guardia.
  `pip-audit` pasa sin excepciones en el CI y en el publish. Al irse Streamlit hubo que declarar `uvicorn`, `Jinja2`, `python-multipart`
  e `itsdangerous`, que antes llegaban como dependencias transitivas.
- Release: publish a ECR en el primer intento (run 39622446165, escaneo COMPLETE sin hallazgos en las dos imágenes). Despliegue con un único
  `update-environment` por version label, convergió en unos 46 s, entorno Ready/Green/Ok, sin rollback. Verificación automática PASS
  (smoke HTTP 5/5, 0 coincidencias en los patrones de PII, secretos y `Traceback`).
- Es una tarea de clase C que cambia la aplicación: tras el merge pasó por `BLOCKED_HUMAN` y el humano resolvió hacia
  `PREPARING_DEPLOYMENT`. La definición de la tarea lo decía de forma explícita y el flujo funcionó sin ambigüedad.
- Bloqueos del guard durante el desarrollo (dos sesiones del Developer, sin pérdida de trabajo): (1) el nombre del SDK de AWS escrito en un
  comando de shell, porque la regla de `policies.yaml` busca esa palabra en cualquier comando; (2) la creación de un script suelto en la raíz
  del worktree, que el guard no permite y que había sugerido el propio humano. Ambos eran de forma, no de fondo; el humano dejó notas en
  `progress/current.md` y el Developer continuó desde su trabajo previo y entregó.
- Incidente menor: la sesión AWS expiró antes del release. El orquestador lo detectó antes de lanzar al Deployer y pidió reautenticar,
  sin perder estado.
- Lecciones:
  - Una instrucción al Developer no puede pedir algo que el guard prohíbe: las rutas permitidas y las reglas de texto de `policies.yaml` se
    revisan antes de dar una indicación operativa.
  - Las dependencias exclusivas de Streamlit (altair, pandas, pyarrow, pydeck, protobuf y watchdog, entre otras) salieron del lock de
    runtime; `jsonschema` pasó al lock de desarrollo porque lo usa `scripts/harness/common.py`. El lock de desarrollo se verificó con
    `pip install --dry-run`, que resuelve sin conflictos.
  - Con la excepción de Pillow cerrada vuelve a ser posible aceptar archivos de usuarios sin una excepción de seguridad vigente: se
    desbloquea la dependencia de `CRM-ADJUNTOS-COMENTARIOS` (sigue pendiente de decisiones del humano).
- Pendiente: el humano borra `.streamlit/` en un PR aparte (el guard no lo permite al Developer). Quedan residuos cosméticos sin efecto
  en el runtime (docstrings en `app/`, texto en `scripts/generate_coverage_report.py`, `check_streamlit.py` en la raíz y los diagramas de
  `docs/ARCHITECTURE.md`); se registran en el backlog como `SEG-LIMPIEZA-RESIDUOS-STREAMLIT`.

### 2026-10-21 - Harness: tarea SEG-DESACOPLAR-STREAMLIT cerrada (DONE)

- Titulo: Retirar Streamlit del proyecto y subir Pillow a 13 para eliminar la excepcion de pip-audit
- Evidencia: `evidence/SEG-DESACOPLAR-STREAMLIT/` y `tasks/completed/SEG-DESACOPLAR-STREAMLIT.yaml`.
- release_sha: `0c9b16599c84e1bd4c3e198f6efa4733f1785e76`
- pr_number: `103`
- application_version: `h3-seg-desacoplar-streamlit-0c9b165-domainlocked-r1`
- bundle_sha256: `c187fd6bf9bb9997efdce754068e5729621e3f3b8a0ab6a940f7ed4b419b4d39`
- lkg: `h3-sim-historial-eventos-antiguos-793e718-domainlocked-r1`
- deployment: `success`
- deployed_commit: `0c9b16599c84e1bd4c3e198f6efa4733f1785e76`
- verification: `PASS`

### 2026-10-21 - Seguridad: retirada de Streamlit del runtime y Pillow 13 (SEG-DESACOPLAR-STREAMLIT, en desarrollo)

- Cambio (change_class C, `allow_lockfile_update` solo para quitar Streamlit y subir Pillow): se retira el código legado de Streamlit
  (`app/streamlit_app.py`, `app/backoffice_app.py`, `app/pages/`, `app/presentation/`, `app/internal_tools/`, `app/components/ui.py`,
  `app/auth/guards.py` y `app/runtime.py`) junto con las pruebas que solo lo ejercitaban. La API y la web no cambian de comportamiento.
- Se mueven sin reescribir los helpers que la web/API sí usan: `get_public_site_url`/`get_public_simulator_url` a
  `app/components/urls.py`, `format_currency_clp` a `app/components/formatting.py` y `log_health_status` a `app/database/healthcheck.py`.
- Dependencias: `streamlit` y sus dependencias exclusivas salen de `requirements/runtime.lock`; `pillow` sube a 13.0.0. Se declaran
  explícitamente `uvicorn`, `Jinja2`, `python-multipart` e `itsdangerous`, que antes llegaban transitivamente vía Streamlit.
- Dockerfile sin `STREAMLIT_*` ni `COPY .streamlit`, con `CMD` uvicorn `app.web.main:app` en `:8501`; el backoffice de `docker-compose.yml`
  local hace lo mismo. El compose de despliegue (ECR) ya usaba uvicorn y no cambia.
- Se cierra la excepción de `pip-audit` para los 8 avisos de Pillow 12.3.0: fuera los `--ignore-vuln` de `ci.yml` y
  `publish-dev-ecr-images.yml`, fuera `tests/security/test_excepcion_pip_audit_pillow.py` y actualizada la sección de `docs/SEGURIDAD.md`.
  `pip-audit --requirement requirements/runtime.lock` pasa sin excepciones.
- Nuevo test `tests/unit/test_streamlit_retired.py`: importa ambos entrypoints con `streamlit` bloqueado y comprueba estáticamente que
  ningún archivo de `app/` lo importa.

### 2026-10-21 - Publish de ECR: la espera del escaneo sube a 20 minutos (H3.2-ECR-SCAN-WAIT)

- Cambio (PR #101, `dfb1d7f`): el paso del escaneo de `publish-dev-ecr-images.yml` espera hasta 20 minutos, con sondeo cada 15 segundos,
  mediante el script `scripts/release/wait_for_ecr_scan.py`. Los fallos tienen mensajes propios: el escaneo no terminó en el plazo (aclara
  que no hay hallazgos verificados y apunta a la recuperación), el escaneo terminó en `FAILED` o `UNSUPPORTED_IMAGE`, o hay hallazgos
  HIGH/CRITICAL. El gate sigue cerrando en falso: sin escaneo `COMPLETE` con CRITICAL=0 y HIGH=0 no se arma el bundle. El procedimiento de
  recuperación (revisar el escaneo, borrar las dos imágenes del release por sus tags inmutables y relanzar con el mismo SHA) quedó en
  `docs/DEV_EB_DEPLOYMENT_RUNBOOK.md`.
- Resultado: clase C con `deploy_required: false`; cerró sola al hacer merge (`merged_no_deploy`), sin pasar por `BLOCKED_HUMAN`. Confirma la
  lección de `H3.2-ECR-LIFECYCLE`: una tarea de infraestructura sin cambio de la aplicación se define con `deploy_required: false`.
- Validación real diferida: el workflow solo se ejercita en el próximo release; mientras tanto lo cubren pruebas estáticas del YAML y del
  script con el CLI de AWS simulado (5 escenarios). Observación del Reviewer: el script se detiene en la primera imagen con fallo, sin evaluar
  la segunda; sigue siendo fail-closed.
- Incidente: el Developer (DeepSeek) se detuvo a los 22 minutos con `402 Insufficient Balance` cuando el PR ya estaba en verde. El supervisor
  paró con `failed` y la tarea quedó intacta en `DEVELOPING`; tras recargar el saldo, el Developer entregó en menos de 5 minutos. Lección: un
  `failed` con 402 no es un fallo de la tarea; se recarga el saldo y se relanza el orquestador.
- Límite que no resuelve: un escaneo atascado más de 20 minutos (como el del 2026-10-20) sigue fallando el publish; para eso está el
  procedimiento documentado.

### 2026-10-21 - Harness: tarea H3.2-ECR-SCAN-WAIT cerrada (DONE)

- Titulo: Publish de imagenes a ECR: esperar el escaneo hasta 20 minutos y fallar con un mensaje claro
- Evidencia: `evidence/H3.2-ECR-SCAN-WAIT/` y `tasks/completed/H3.2-ECR-SCAN-WAIT.yaml`.
- release_sha: `f82180fc57b479ddde307c12e2bdce41c0e045fa`
- pr_number: `101`

### 2026-10-21 - Publish a ECR: esperar el escaneo hasta 20 minutos y fallar con mensajes claros (H3.2-ECR-SCAN-WAIT, en desarrollo)

- Contexto: el publish del release fallo dos veces (2026-10-16 y 2026-10-20) porque el escaneo de ECR no terminaba en los 5 minutos que esperaba el workflow y quedaba atascado mas de 20-47 minutos (lo normal es de 14 a 35 s). El workflow tampoco distinguia entre «escaneo lento», «escaneo fallido» y «hallazgos reales».
- Cambio (change_class C, sin despliegue): `publish-dev-ecr-images.yml` espera hasta `SCAN_TIMEOUT_MINUTES=20` minutos (sondeo cada `SCAN_POLL_SECONDS=15` s) a que ambas imagenes (`tpi-dev-app` y `tpi-dev-caddy`) tengan el escaneo `COMPLETE`, con gate fail-closed (`CRITICAL=0` y `HIGH=0`; `IN_PROGRESS` nunca cuenta como exito). La logica de espera se extrae a `scripts/release/wait_for_ecr_scan.py`.
- Mensajes de fallo: (a) no termino en el plazo (aclarando que NO hay hallazgos verificados, con los digests y la recuperacion); (b) termino en `FAILED` o `UNSUPPORTED_IMAGE`; (c) hallazgos HIGH/CRITICAL con el detalle.
- Recuperacion cuando el publish falla por el escaneo: revisar el estado del escaneo de ambos digests, borrar las dos imagenes del release (los tags son inmutables, lo hace el humano) y relanzar el workflow con el mismo SHA. Documentado en `docs/DEV_EB_DEPLOYMENT_RUNBOOK.md`.
- Sin cambios de permisos IAM/OIDC, de la politica de tags ni de la publicacion de imagenes; no se toca el paso de pip-audit ni la excepcion de Pillow.
- Siguiente paso: correr las pruebas locales (sin BD) y entregar a revision.

### 2026-10-21 - Simulador: línea de tiempo tolerante a eventos antiguos desplegada e incidente de release (SIM-HISTORIAL-EVENTOS-ANTIGUOS)

- Resultado: el humano aceptó AC-5 y AC-6 en DEV. El lead que daba «Internal Server Error» abre sin error y su línea de tiempo muestra
  sus 5 simulaciones: 4 antiguas con la nota «Registro anterior al guardado de entradas…» y 1 completa con su detalle.
- Incidente en el release (cronología, 2026-10-20):
  1. El CI del PR #97 falló en `Security Audit`: `certifi 2026.7.22` (GHSA-6q48-6c7w-9gw2). Se corrigió con el PR #98
     (`certifi 2026.10.19`); el Developer trajo `main` a su rama y entregó.
  2. El publish del release `793e718` falló: el escaneo de ECR no terminó en los 5 minutos del workflow y quedó atascado más de
     47 minutos (lo normal es de 14 a 35 s). El Deployer se detuvo en `BLOCKED_HUMAN` (`preparation_failed`).
  3. Se borraron las dos imágenes del release con una herramienta de una sola vez (espera opcional del escaneo, frase de
     confirmación, probada con 19 escenarios simulados) y se relanzó el publish. Volvió a fallar, esta vez en `Security Audit`:
     8 avisos nuevos de `pillow 12.3.0`, corregidos solo en Pillow 13.0.0.
  4. `streamlit` (hasta la 1.66.0) exige `pillow<13`, por lo que no se podía subir. Además el workflow audita el lock del commit
     que publica, así que `793e718` no podía pasar sin cambiar el workflow.
  5. Decisión del humano: excepción acotada de `pip-audit` para esos 8 IDs (PR #99, vence 2026-11-20, vigilada por una prueba del
     CI). El publish de `793e718` terminó bien (run 39516711668, escaneo COMPLETE sin hallazgos); el humano resolvió a
     `PREPARING_DEPLOYMENT`; siguieron candidato, gate, despliegue, verificación y aceptación.
- Lecciones:
  - El workflow de publicación toma su definición de `main` pero audita el lock del commit que publica: una excepción puesta en
    `main` también vale para un commit ya mergeado, lo que evitó rehacer el release.
  - Un escaneo de ECR puede atascarse; esperar a uno atascado no sirve, hay que borrar las imágenes y volver a publicar para que se
    escaneen de nuevo. La espera de 5 minutos del workflow es corta.
  - Los avisos de dependencias aparecen sin cambiar el código: un PR verde por la mañana puede fallar por la tarde.
  - Antes de aceptar una excepción de seguridad hay que preguntar por los planes del producto: la futura función de adjuntos en los
    comentarios invalidó el argumento «la app no recibe archivos de usuarios» y obligó a ponerle vencimiento y una guardia.
- Backlog (definido en este PR de cierre): `H3.2-ECR-SCAN-WAIT` y `SEG-DESACOPLAR-STREAMLIT` (decisión del humano: retirar el código
  legado de Streamlit, no aislarlo), listas para activar; `CRM-ADJUNTOS-COMENTARIOS` (bloqueada hasta la anterior, con los resguardos
  como requisitos) y `SIM-CANARIA-MENSUAL` (requiere una persona con credenciales del portal).
- Estado: la excepción de Pillow sigue vigente hasta 2026-11-20 o hasta que `SEG-DESACOPLAR-STREAMLIT` la elimine, lo que ocurra
  primero; ningún archivo de usuarios puede aceptarse antes.

### 2026-10-21 - Harness: tarea SIM-HISTORIAL-EVENTOS-ANTIGUOS cerrada (DONE)

- Titulo: Linea de tiempo del lead: no fallar con simulaciones registradas antes de guardar sus entradas
- Evidencia: `evidence/SIM-HISTORIAL-EVENTOS-ANTIGUOS/` y `tasks/completed/SIM-HISTORIAL-EVENTOS-ANTIGUOS.yaml`.
- release_sha: `793e718aaf8f4dcd52e1cd12644f8b514984202f`
- pr_number: `97`
- application_version: `h3-sim-historial-eventos-antiguos-793e718-domainlocked-r1`
- bundle_sha256: `8c341278fdf069cd925219bf6d7004c963ac485738a04a4c17c3a6f5e000aa79`
- lkg: `h3-sim-historial-linea-tiempo-e4476c3-domainlocked-r1`
- deployment: `success`
- deployed_commit: `793e718aaf8f4dcd52e1cd12644f8b514984202f`
- verification: `PASS`

### 2026-10-20 - Seguridad: excepción acotada de pip-audit para 8 avisos de Pillow 12.3.0

- Hallazgo: poco después del bump de `certifi` (#98) `pip-audit` empezó a reportar 8 avisos en `pillow 12.3.0`
  (CVE-2026-112395, 112397, 112400, 112404, 112895, 112896, 112897 y 112899), todos corregidos solo en Pillow 13.0.0. Eso hizo
  fallar el `Security Audit` del CI y del workflow de publicación, y dejó el release `793e718` de `SIM-HISTORIAL-EVENTOS-ANTIGUOS`
  sin poder publicarse (el workflow audita el lock del commit que publica).
- Por qué no se actualiza: `streamlit` (1.60.0 y también la última, 1.66.0) exige `pillow<13`. Streamlit no puede salir del runtime
  todavía: `app.web.main` y la API lo importan a través de `app.auth` (`guards.py`) y `app.components.ui`.
- Riesgo evaluado: los avisos exigen abrir una imagen o un PDF enviado por un atacante. La aplicación no recibe archivos de
  usuarios, no usa Pillow directamente y solo abre el logo fijo del repositorio (vía `reportlab`).
- Decisión del humano (2026-10-20): excepción acotada a esos 8 IDs, en `ci.yml` y en `publish-dev-ecr-images.yml`, con fecha de
  vencimiento 2026-11-20. Como el workflow de publicación toma su definición de `main`, también aplica al publicar el commit
  `793e718` ya mergeado.
- Resguardos: nueva prueba `tests/security/test_excepcion_pip_audit_pillow.py` que falla si los workflows difieren de los 8 IDs
  documentados, si aparece código que reciba archivos de usuarios, si cambia la versión de Pillow o si llega el vencimiento.
  Sección «Excepciones de pip-audit» en `docs/SEGURIDAD.md` con la condición de salida.
- Motivo de fondo de los resguardos: el humano planea una función de adjuntos (imágenes y PDF) en los comentarios del CRM. La
  excepción deja de ser válida en ese momento, así que la salida (Pillow >= 13 vía desacople de Streamlit) es requisito previo.
- Siguiente paso: tareas `SEG-DESACOPLAR-STREAMLIT` y `CRM-ADJUNTOS-COMENTARIOS` en el backlog (se agregan en el PR de cierre de
  la tarea en curso) y reintento del publish de `793e718`.

### 2026-10-20 - Línea de tiempo del lead: tolerar simulaciones anteriores a SIM-EVIDENCIA-ENTRADAS (SIM-HISTORIAL-EVENTOS-ANTIGUOS, en desarrollo)

- Tarea `SIM-HISTORIAL-EVENTOS-ANTIGUOS` (clase A, fast path version-only): el detalle del lead no debe fallar por la forma
  de un evento de simulación. Las simulaciones registradas antes de `SIM-EVIDENCIA-ENTRADAS` (2026-10-16) tienen un
  `detalle` con solo `actor_subject`, `role`, `tipo_escenario`, `version_modelo` y `codigo_verificacion`; la vista
  `tpi.v_historial_simulaciones` devuelve `entradas` y `resultado` en `NULL`, y la plantilla del detalle encadenaba
  `item.entradas.causante.sexo` sobre un valor indefinido, lo que en Jinja lanza `UndefinedError` y tumba la página del
  lead con un 500.
- Corrección en `app/web/presentation.py`: `build_timeline_items` normaliza `entradas` y `resultado` a una forma segura
  (claves fijas con fallback `None`; `causante` y `beneficiarios` normalizados) y marca los eventos antiguos con
  `es_legacy` (`entradas` y `resultado` ambos `NULL`). La plantilla (`app/web/templates/lead_detail_panel.html`) muestra
  para esos eventos «Simulación generada» con ejecutivo, escenario, versión del modelo y código, más la nota «Registro
  anterior al guardado de entradas: solo se conservan escenario, version y codigo», sin el detalle desplegable; los
  eventos con evidencia completa se muestran como hasta ahora.
- La presentación y la plantilla toleran cualquier dato faltante o nulo (entradas o resultado ausentes, causante ausente,
  beneficiarios vacíos, beneficiarios con campos faltantes y fechas nulas) sin producir un 500. Sin cambios de base de
  datos, vistas, `scripts/sql/**`, `app/simulador_pension/**` ni `app/auth/**`.
- Pruebas: unitarias de presentación (`tests/unit/test_sim_historial_timeline_presentation.py`), de render del detalle
  (`tests/unit/test_web_app.py`) y de integración en PostgreSQL (`tests/integration/test_audit_simulation_view.py`) con
  filas de ambas formas (antigua y completa) leídas a través de `tpi.v_historial_simulaciones`.

### 2026-10-20 - Seguridad: certifi 2026.7.22 → 2026.10.19 (GHSA-6q48-6c7w-9gw2)

- Hallazgo: el CI del PR #97 (`SIM-HISTORIAL-EVENTOS-ANTIGUOS`) falló en `Security Audit`: `pip-audit` reportó 1 vulnerabilidad
  conocida en `certifi 2026.7.22` (GHSA-6q48-6c7w-9gw2, corregida en `2026.10.19`). El aviso se publicó entre el último CI verde
  de `main` (2026-10-20 14:49 UTC) y las 20:11 UTC, así que afecta a cualquier PR hasta que `main` lo incorpore.
- Efecto en el Harness: la tarea no puede tocar dependencias y el guard `g_developer_evidence_valid` rechaza evidencia con un gate
  en rojo, por lo que el Developer se detuvo correctamente (`no_progress`) en lugar de falsear la evidencia.
- Cambio: `requirements/runtime.lock`, una línea: `certifi==2026.10.19` (última versión publicada). `dev.lock` no incluye `certifi`.
- Verificación: `pip-audit --requirement requirements/runtime.lock` da «No known vulnerabilities found» con el cambio y reproduce
  la vulnerabilidad con el lock anterior.
- Solo dependencia transitiva de ejecución: sin cambios de código, base de datos ni configuración.
- Siguiente paso: tras el merge, el PR de la tarea en curso debe traer `main` a su rama para que su CI pase.

### 2026-10-20 - Simulador: migración 009 aplicada en DEV y defecto con eventos antiguos (SIM-HISTORIAL-LINEA-TIEMPO)

- Migración 009 aplicada y verificada en AWS DEV por el humano (2026-10-20, 10:34 hora de Chile) con una herramienta de una sola
  vez que simula primero y deshace (ROLLBACK), pide una frase de confirmación, usa el SQL exacto del commit `e4476c3` (huella
  `6a5247dc14d6`) y verifica antes y después del COMMIT. Resultado: vista `tpi.v_historial_simulaciones` creada con
  `security_barrier` y las 9 columnas esperadas; `tpi_app` con SELECT sobre la vista y sin SELECT/UPDATE/DELETE sobre
  `tpi.auditoria`; `PUBLIC` sin privilegios; la vista mostró 15 simulaciones, igual que la tabla. PostgreSQL 17.9, usuario
  `tpi_admin`. Luego el humano resolvió el bloqueo hacia `PREPARING_DEPLOYMENT`.
- Despliegue: versión `h3-sim-historial-linea-tiempo-e4476c3-domainlocked-r1`. Verificación PASS (smoke 6/6 y 0 coincidencias
  en los 8 patrones de logs). Aceptados AC-2, AC-5 y AC-6.
- Defecto hallado por el humano al verificar: un lead de DEV con simulaciones anteriores a `SIM-EVIDENCIA-ENTRADAS` mostraba
  solo «Internal Server Error». Causa: esos eventos (2026-10-14 a 2026-10-16) tienen un `detalle` con solo cinco metadatos
  (`actor_subject`, `role`, `tipo_escenario`, `version_modelo`, `codigo_verificacion`); la vista devuelve `entradas` y
  `resultado` en NULL; `build_timeline_items` los normaliza a `{}` y la plantilla lee `item.entradas.causante.sexo`, que en
  Jinja lanza `UndefinedError` y tumba toda la página del lead (500). Reproducido con la plantilla real y confirmado en DEV:
  ese lead tiene 4 eventos antiguos y 1 completo.
- Por qué no se detectó: ni las pruebas del Developer, ni la revisión, ni la definición de la tarea consideraron la evidencia
  anterior a `SIM-EVIDENCIA-ENTRADAS`. Las pruebas usaron solo eventos con el esquema nuevo.
- Lección: una presentación que lee datos históricos se prueba con cada forma que el dato ha tenido en el tiempo. Al definir una
  tarea que lee datos existentes, consultar en DEV las formas reales (por ejemplo `entradas IS NULL`) y exigirlo en un criterio.
- Decisión del humano (2026-10-20): aceptar esta tarea y corregir con una tarea nueva, clase A y P0:
  `SIM-HISTORIAL-EVENTOS-ANTIGUOS`, definida en el PR de cierre. Hasta que se despliegue, los leads con simulaciones de ese
  periodo siguen fallando en DEV.

### 2026-10-20 - Harness: tarea SIM-HISTORIAL-LINEA-TIEMPO cerrada (DONE)

- Titulo: Linea de tiempo del lead: mostrar las simulaciones generadas
- Evidencia: `evidence/SIM-HISTORIAL-LINEA-TIEMPO/` y `tasks/completed/SIM-HISTORIAL-LINEA-TIEMPO.yaml`.
- release_sha: `e4476c325395d849c32b1c521687e1d56f6ee22e`
- pr_number: `95`
- application_version: `h3-sim-historial-linea-tiempo-e4476c3-domainlocked-r1`
- bundle_sha256: `d6f6015d921f19dbaac49b8bcadcf165fbd95c27faaca679c4c2961893fcd6da`
- lkg: `h3-sim-wizard-3-pasos-4ee5fad-domainlocked-r1`
- deployment: `success`
- deployed_commit: `e4476c325395d849c32b1c521687e1d56f6ee22e`
- verification: `PASS`

### 2026-10-20 - Simulador: línea de tiempo del lead con las simulaciones generadas (en desarrollo, DEVELOPING)

- Tarea `SIM-HISTORIAL-LINEA-TIEMPO` (clase D, db_path): mostrar en la línea de tiempo del detalle del lead cada
  simulación generada, con toda la evidencia registrada, leyéndola de una vista de solo lectura sobre `tpi.auditoria`
  (mismo patrón que asignaciones y cambios de estado).
- Migración `009` (`scripts/sql/009_create_historial_simulaciones.sql` + `009_drop_historial_simulaciones.sql`):
  - Vista `tpi.v_historial_simulaciones` con `security_barrier`, filtro fijo `accion = 'simulacion_renta_vitalicia'`
    AND `tabla_afectada = 'tpi.leads'`.
  - Columnas: `id_auditoria`, `id_lead`, `fecha_hora`, `actor_subject`, `tipo_escenario`, `version_modelo`,
    `codigo_verificacion`, `entradas` (JSONB completo) y `resultado` (JSONB completo). No se censura ningún dato
    registrado (decisión del humano 2026-10-19).
  - `REVOKE ALL FROM PUBLIC`; `GRANT SELECT` solo a `tpi_app`; sin `SELECT` directo sobre `tpi.auditoria`. Sin índice
    nuevo: reutiliza `auditoria_state_history_idx` de la migración `008` (sus columnas líderes coinciden con el filtro).
- Aplicación: `SolicitudRepository.get_lead_simulation_events` (lee solo la vista), `SolicitudService`, la presentación
  de la línea de tiempo (`build_timeline_items` con `kind='simulation'`) y el template del detalle (resumen + detalle
  desplegable con entradas y resultado). La visibilidad sigue las reglas vigentes del detalle del lead.
- Bootstrap de tests (`scripts/init_test_database.py`) actualizado con la vista; pruebas unitarias (scripts y
  presentación) e integración (`tests/integration/test_audit_simulation_view.py`) sobre PostgreSQL.
- Procedimiento de aplicación y reversa en AWS DEV (para el humano) documentado en `docs/database/04_MIGRATIONS.md`
  (Notas sobre `009`): preflight/postflight con `tpi_admin`, aplicación única y reversa idempotente.
- Impacto y rollback: solo crea/elimina la vista y su grant; no toca `tpi.auditoria` ni los objetos de `007`/`008`.
- Siguiente paso: revisión independiente del PR y, tras el merge, aplicar la migración en AWS DEV vía Human Gate.

### 2026-10-19 - Simulador: el Excel y el script de las tablas de mortalidad pasan al repositorio

- Pedido del humano: traer al repositorio el script y el Excel de los que salen las tablas de mortalidad, y dejarlo todo
  documentado en el manual de uso del simulador (`docs/SIMULADOR_USO.md`).
- Nueva carpeta `scripts/tablas_mortalidad/`:
  - `tablas-mortalidad-cmf.xlsx`: Excel de la CMF sin editar (141.411 bytes, descargado el 2026-10-13).
  - `procedencia.json`: fuente, norma (NCG N.º 495 de la CMF), fecha, tamaño, `sha256` y verificaciones ya hechas.
  - `construir_tablas.py`: el script de la investigación (REA), con tres cambios: escribe en este repositorio, valida los
    encabezados del Excel antes de leer y tiene el modo `--verificar`.
  - `README.md`: qué contiene el resultado, qué tabla usa el simulador en cada rol, comandos y procedimiento de actualización.
- Comprobación: el `.npz` que ya usaba el motor se reconstruye idéntico desde el Excel (los 12 arreglos, incluidos los
  valores vacíos de la tabla de mujeres pensionadas antes de los 20 años). No cambia ningún valor del motor ni su versión.
- Prueba nueva `tests/unit/test_tablas_mortalidad.py` (8 pruebas): falla en el CI si el Excel deja de coincidir con
  `procedencia.json`, si el `.npz` deja de reconstruirse desde el Excel, si cambia la estructura de las tablas, o si un Excel
  con otra estructura no produce un error claro.
- Manual de uso: §8.1, §8.2 (insumos, comandos, protección del CI y procedimiento), §8.7, §8.9, §9 (hallazgo 4 resuelto) y §10.
- Solo herramientas, datos públicos y documentación: sin cambios de código de la aplicación, base de datos ni despliegue.
- Siguiente paso: consolidar la campaña canaria en un único script y programar la primera campaña (la ventana validada
  venció el 2026-10-13); contrastar la convención de la columna «2036*» con la documentación oficial.

### 2026-10-19 - Simulador: corrección del documento de uso (`docs/SIMULADOR_USO.md`)

- Corrección al documento mergeado en #90: sí se encontró el Excel de la CMF del que salen las tablas de mortalidad (la
  búsqueda inicial se quedó corta). Está en el workspace de REA
  (`homologacion_simulador/entrega-2026-10-13-v1/investigacion/ejecucion-vejez-edad/tablas-mortalidad-cmf.xlsx`) y la CMF
  publica un archivo del mismo tamaño. El script que construye el `.npz` sigue solo en `REA/simulador_pension/scripts`.
- Se incorporan: nombres oficiales de las tablas, su vigencia (NCG N.° 495 de la CMF, 24-feb-2023; rigen desde el 1-jul-2023;
  según el sitio oficial, uso máximo de 6 años, o sea revisión hacia mediados de 2029), la comparación de 3.636 valores
  contra el módulo de la SP y la convención sin verificar para los años posteriores a 2036.
- Se detalla la campaña canaria (qué es, qué hace falta, cobertura sugerida, qué hacer con el resultado y las fragilidades
  de la herramienta actual).
- Solo documentación: sin cambios de código, base de datos ni despliegue.
- Siguiente paso: tareas para (1) traer al repositorio el script y el Excel de las tablas y (2) consolidar la campaña
  canaria en un único script; programar la primera campaña, porque la ventana validada venció el 2026-10-13.

### 2026-10-19 - Harness: tarea SIM-WIZARD-3-PASOS cerrada (DONE)

- Titulo: Simulador: asistente de 3 pasos (datos, grupo familiar, resultado) con la marca de TPI
- Evidencia: `evidence/SIM-WIZARD-3-PASOS/` y `tasks/completed/SIM-WIZARD-3-PASOS.yaml`.
- release_sha: `4ee5fad2f57abe0842a5beaede4bf981299d953e`
- pr_number: `89`
- application_version: `h3-sim-wizard-3-pasos-4ee5fad-domainlocked-r1`
- bundle_sha256: `9bbcbac1881e8660cf10642f93b094796987316b953b6bc2ea3eebf49cc001e0`
- lkg: `h3-sim-evidencia-entradas-a7859af-domainlocked-r1`
- deployment: `success`
- deployed_commit: `4ee5fad2f57abe0842a5beaede4bf981299d953e`
- verification: `PASS`

### 2026-10-19 - Simulador: documento de uso y mantención (`docs/SIMULADOR_USO.md`)

- Pedido del humano durante la verificación de `SIM-WIZARD-3-PASOS`: documentar qué casos soporta el simulador, cuáles
  quedan fuera y qué hay que hacer para mantenerlo vigente (por ejemplo, las tablas de mortalidad).
- Se revisó el motor (`app/simulador_pension`), el servicio, la ruta y el asistente; se ejecutaron las pruebas de
  regresión, validación y ventana (55 en verde) y se midió la cobertura real del fixture de 435 casos.
- Solo documentación: sin cambios de código, base de datos ni despliegue. Se enlaza desde `docs/INDEX.md`.
- Hallazgos que quedan anotados en el documento (§9), sin acción obligatoria:
  - La ventana de fechas validada terminó el 2026-10-13; el motor avisa internamente pero la pantalla y el PDF no.
  - El PDF no lista el grupo familiar: solo imprime «CÓNYUGE: Sí» y no recibe los hijos. Decisión del humano
    (2026-10-19): se mantiene así, no se agrega.
  - El script que construye las tablas de mortalidad y el Excel de la CMF no están en el repositorio.
  - Con cónyuge e hijos el código admite causantes desde 60 años y la evidencia empieza en 62.
- Siguiente paso: programar la campaña canaria mensual (ventana de fechas) y ubicar el script y el Excel de las tablas.


### 2026-10-19 - Simulador: asistente de 3 pasos con la marca de TPI (en desarrollo, DEVELOPING)

- Tarea `SIM-WIZARD-3-PASOS` (clase A, fast path version-only): rehacer la pantalla del simulador como un asistente de
  3 pasos (Datos de la simulación, Grupo familiar, Resultado) con el flujo y la estructura del simulador de referencia y
  la marca de TPI, sin cambios en el motor, el alcance validado ni la autorización.
- Cambios:
  - `app/web/routes/simulador.py`: el POST despacha por `intent` (`continuar`, `volver_paso1`/`volver_paso2`, `simular`,
    `descargar_pdf`); `simular` calcula en el servidor y muestra el resultado en el paso 3 sin persistir ni auditar, y
    `descargar_pdf` conserva la generación del PDF efímero con su evento append-only de auditoría. Se agrega
    `tipo_pension` y el rechazo del cónyuge inválido (pendiente #8 de `docs/SIM_RV_V1_PENDIENTES.md`).
  - `app/web/templates/simulador.html`: asistente de 3 pasos, indicador de pasos, tabla del grupo familiar con modal de
    beneficiario, tarjetas de resultado, resumen y aviso «Valores referenciales, no vinculantes».
  - `app/web/static/js/simulador_wizard.js`: JavaScript propio (sin CDN) que gestiona el modal y la tabla de beneficiarios
    a partir de los inputs ocultos del formulario.
  - `app/web/static/css/app.css`: estilos del asistente con los tokens del CRM y el azul marino `#0f243e` de la ficha; sin
    el naranja del simulador de referencia.
- Decisión documentada: la relación RVD/RT queda oculta en 100 en el asistente, porque el simulador de referencia no la
  expone en su paso de datos; el motor y la API siguen aceptando 50/51–99 (sin cambios en el alcance validado).
- Sin migraciones, grants, vistas, constraints ni infraestructura (clase A); el motor `app/simulador_pension/**`,
  `app/auth/**` y las dependencias no cambian.
- Pruebas nuevas: `tests/unit/test_sim_wizard.py` (flujo del asistente, validación por paso, no auditoría en `simular`,
  marca TPI y JS propio). La cobertura y la suite completa las valida el CI del PR.

### 2026-10-19 - Simulador: la evidencia de entradas se retiene de forma indefinida

- Decision del humano (2026-10-19): la evidencia de entradas y resultado del simulador (`tpi.auditoria.detalle`, accion
  `simulacion_renta_vitalicia`, creada por `SIM-EVIDENCIA-ENTRADAS`) se conserva **de forma indefinida**, sin purga ni
  expiracion. Cierra la politica de retencion que estaba pendiente.
- Efecto en el trabajo pendiente: `SIM-HISTORIAL-LINEA-TIEMPO` ya no depende de esa decision.
- Sin cambios de codigo, de base de datos ni de despliegue: solo documentacion
  (`docs/SIM_RV_V1_MODELO.md`, `docs/SIM_RV_V1_PENDIENTES.md`, `CHANGELOG.md`).
- Riesgo abierto: el detalle guarda fechas de nacimiento vinculadas a un lead por `id_lead` (sin nombres, RUT, correo ni
  telefono). Queda anotada la revision normativa de la retencion indefinida con asesoria legal (Ley 19.628 y su reemplazo,
  Ley 21.719): si se exigiera un plazo o un mecanismo de supresion, se decide en una tarea nueva; una purga de un registro
  append-only requiere migracion (clase D) aplicada por el humano. No es asesoria legal.
- La entrada del 2026-10-15 de `SIM-EVIDENCIA-ENTRADAS` que dice «retencion pendiente» es historia y no se reescribe; esta
  entrada la reemplaza.

### 2026-10-19 - Harness: tarea H3.2-ECR-LIFECYCLE cerrada (DONE)

- Titulo: Lifecycle de ECR compatible con rollback: conservar 100 imagenes
- Evidencia: `evidence/H3.2-ECR-LIFECYCLE/` y `tasks/completed/H3.2-ECR-LIFECYCLE.yaml`.
- release_sha: `2b0fea25cd9e6b1ad336121719f4fb6362740f58`
- pr_number: `85`
- Aplicacion en AWS DEV (humano, 2026-10-19): politica de `deployment/ecr/lifecycle-policy.json` aplicada en `tpi-dev-app` y `tpi-dev-caddy` (regla de retencion de 20 a 100 imagenes); vista previa previa con 20 imagenes por repositorio: 0 expiraciones; verificada con `get-lifecycle-policy`.
- Cierre MANUAL (humano): la tarea, de infraestructura y sin cambio de la aplicacion, se definio con `deploy_required: true`. Tras aplicar y verificar la politica, el humano resolvio hacia `VERIFYING`, que no tiene salida valida sin evidencia de aprobacion y de despliegue que la tarea nunca tuvo (`verified` la exige; `verify_failed` habria sido un fallo inventado), y el Deployer quedo detenido por una lectura de `ecr get-lifecycle-policy` no permitida en `VERIFYING`. Se cerro con un script de una sola vez que registra `manual_close` (actor humano) en el historial y ejecuta el cierre oficial del Harness. Leccion: una tarea de infraestructura que aplica el humano sin cambio de la aplicacion debe definirse con `deploy_required: false` (cierra sola al hacer merge, `merged_no_deploy`) o resolverse hacia `PREPARING_DEPLOYMENT`.

### 2026-10-19 - H3.2-ECR-LIFECYCLE: lifecycle de ECR conserva 100 imagenes (en desarrollo, DEVELOPING)

- Título: Lifecycle de ECR compatible con rollback: conservar 100 imágenes.
- Clase C (infraestructura): sin fast path; tras el merge la transición obligatoria es `merged_non_fast_path`
  hacia `BLOCKED_HUMAN` y el humano aplica la política en AWS DEV.
- Riesgo documentado desde 2026-09-14: la política anterior (`imageCountMoreThan: 20`) podía expirar imágenes
  requeridas por el LKG. Decisión del humano (2026-10-19): elevar el tope a 100; la aplicación la ejecuta el
  humano (el Harness no la aplica: `ecr put-lifecycle-policy` está denegado a los agentes).
- Cambios:
  - `deployment/ecr/lifecycle-policy.json`: regla 1 sin cambios (capas sin etiqueta a los 7 días); regla 2 pasa
    de `imageCountMoreThan: 20` a `imageCountMoreThan: 100` (`tagStatus: any`, acción `expire`). Un único archivo
    sirve a `tpi-dev-app` y `tpi-dev-caddy`.
  - Nuevo `tests/unit/test_ecr_lifecycle_policy.py` (sin AWS, corre en CI): falla si no hay reglas, hay prioridades
    repetidas, una regla expira por antigüedad imágenes con etiqueta o el conteo de retención baja de 100.
  - Nuevo `docs/ECR_LIFECYCLE_POLICY.md`: por qué 100, procedimiento de aplicación y verificación
    (put/get-lifecycle-policy y vista previa start/get-lifecycle-policy-preview) para `tpi-dev-app` y
    `tpi-dev-caddy`, reversa (reaplicar el JSON anterior desde git) y constancia de que las comprobaciones de
    digests del LKG en el preflight y en la revisión del candidato se mantienen. Lista las notas `keep-20` en
    `agents/` (rutas protegidas) para actualizarlas aparte.
  - `docs/INDEX.md` y `CHANGELOG.md` actualizados.
- Impacto y rollback: conserva más imágenes, no menos; costo residual de almacenamiento marginal. Reversa:
  reaplicar el JSON anterior desde git (documentado en `docs/ECR_LIFECYCLE_POLICY.md`).
- No se tocan `app/**`, `.github/**`, `Dockerfile`, `deployment/` fuera de `deployment/ecr/`, `environments/**`,
  `agents/**`, `harness/**` ni `scripts/harness/**`.
- Siguiente paso: correr gates de calidad, abrir/actualizar PR y `submit_for_review`.

### 2026-10-16 - Harness: tarea SIM-EVIDENCIA-ENTRADAS cerrada (DONE)

- Titulo: Simulador: guardar entradas y resultado como evidencia (solo escritura)
- Evidencia: `evidence/SIM-EVIDENCIA-ENTRADAS/` y `tasks/completed/SIM-EVIDENCIA-ENTRADAS.yaml`.
- release_sha: `a7859af73491a050b8c327cf21a0004acf995ae0`
- pr_number: `83`
- application_version: `h3-sim-evidencia-entradas-a7859af-domainlocked-r1`
- bundle_sha256: `0a495da76209e6becde56b5036732a162a69238f68d26fd61a4d94fe8b18d9f2`
- lkg: `h3-sim-rv-v1-ventana-5024922-domainlocked-r1`
- deployment: `success`
- deployed_commit: `a7859af73491a050b8c327cf21a0004acf995ae0`
- verification: `PASS`

### 2026-10-16 - SIM-EVIDENCIA-ENTRADAS: guardar entradas y resultado como evidencia (en desarrollo, DEVELOPING)

- Titulo: Simulador: guardar entradas y resultado como evidencia (solo escritura).
- Clase A (fast path, solo aplicacion): sin migraciones, grants, vistas, constraints ni infraestructura.
- Decision del humano (2026-10-15): reemplaza el AC-10 de `SIM-RV-V1` («no se persiste ninguna entrada ni resultado»). Las
  entradas y el resultado de cada simulacion se guardan como evidencia append-only de solo escritura en
  `tpi.auditoria.detalle`, sin nombres, RUT, correo ni telefono. La politica de retencion queda pendiente de decision del
  humano y mostrarla en la linea de tiempo es `SIM-HISTORIAL-LINEA-TIEMPO`.
- Cambios:
  - `app/services/simulador_auditoria.py`: el `detalle` pasa a ser versionado (`schema_version`) y `record_simulacion_event`
    recibe las entradas (causante, saldo, tasa, garantia, aumento, diferimiento, relacion RVD/RT, valor UF y beneficiarios) y
    el resultado (pension y, en renta temporal, renta temporal y meses de diferimiento); se agrega `build_detalle` puro.
  - `app/services/simulador_service.py` y `app/web/routes/simulador.py`: el evento se registra con las entradas y el resultado
    reales de la simulacion, conservando el fail-closed (si el INSERT falla no se entrega el PDF).
  - `tests/unit/test_sim_rv_auditoria.py` y `tests/unit/test_sim_rv_web.py` ajustados; nuevo
    `tests/unit/test_sim_rv_evidencia_entradas.py` (estructura versionada, sin PII y reproducibilidad del resultado y del
    codigo); `tests/integration/test_sim_rv_web.py` verifica el detalle sin PII (nombre con marcado y caracteres especiales)
    y la reproducibilidad desde PostgreSQL.
  - `docs/SIM_RV_V1_REQUIREMENTS_MATRIX.md` (AC-10 y AC-11), `docs/SIM_RV_V1_PENDIENTES.md` (#6) y `docs/SIM_RV_V1_MODELO.md`
    reflejan la decision del humano; `CHANGELOG.md` actualizado.
- No cambia el motor `app/simulador_pension/**`, la logica numerica, los rangos validados, la autorizacion ni el escape de
  marcado del PDF; no se toca `app/repositories/**`.
- Siguiente paso: correr gates de calidad, abrir/actualizar PR y `submit_for_review`.

### 2026-10-16 - Harness: tarea SIM-RV-V1-VENTANA cerrada (DONE)

- Titulo: Simulador RV: ventana de validacion abierta, con aviso de valores referenciales
- Evidencia: `evidence/SIM-RV-V1-VENTANA/` y `tasks/completed/SIM-RV-V1-VENTANA.yaml`.
- release_sha: `502492257e505884716d14c2529dd0d08bcb421d`
- pr_number: `81`
- application_version: `h3-sim-rv-v1-ventana-5024922-domainlocked-r1`
- bundle_sha256: `c1fd91f28df57caf85978d23540a620e1b7d8557195ebe46a7be631dc09280db`
- lkg: `h3-sim-ficha-pdf-dd6be12-domainlocked-r1`
- deployment: `success`
- deployed_commit: `502492257e505884716d14c2529dd0d08bcb421d`
- verification: `PASS`

### 2026-10-16 - SIM-RV-V1-VENTANA: ventana de validacion abierta con aviso de valores referenciales (en desarrollo, DEVELOPING)

- Titulo: Simulador RV: ventana de validacion abierta, con aviso de valores referenciales.
- Clase A (fast path, solo aplicacion): sin migraciones, grants, vistas, constraints ni infraestructura.
- Decision del humano (2026-10-14): la ventana validada del simulador queda abierta; ya no bloquea ni advierte por fecha y solo se
  mantiene el aviso de que los valores son referenciales (no vinculantes).
- Cambios:
  - `app/services/simulador_service.py`: se eliminan `clasificar_ventana` y `VENTANA_ADVERTENCIA_DIAS`; `generar_pdf` pierde el
    parametro `advertencia_ventana` y su parrafo, y en la leyenda se agrega la seccion «Supuestos y advertencias» con el aviso
    permanente de valores referenciales (no vinculantes).
  - `app/web/routes/simulador.py`: se eliminan las lineas que usaban `clasificar_ventana` y el 422 por vencimiento de la ventana;
    el contexto del formulario ya no expone `advertencia_ventana`.
  - `app/web/templates/simulador.html`: el bloque condicional de aviso de ventana vencida se reemplaza por un aviso permanente de
    valores referenciales (no vinculantes).
  - `tests/unit/test_sim_rv_ventana.py` reemplazado por pruebas de que cualquier fecha genera y de que el aviso referencial esta en
    el PDF; `tests/unit/test_sim_rv_web.py` y `tests/unit/test_sim_rv_pdf.py` ajustados al nuevo contrato.
  - `docs/SIM_RV_V1_REQUIREMENTS_MATRIX.md` (AC-6 y matriz de contenido del PDF), `docs/SIM_RV_V1_PENDIENTES.md` (§1 y #1) y
    `docs/SIM_RV_V1_MODELO.md` (§5) reflejan la decision del humano; `CHANGELOG.md` actualizado.
- No cambia el motor `app/simulador_pension/**` (conserva `VENTANA_VALIDADA` y su `warnings.warn` informativo) ni el alcance
  validado de la V1 (435/435 casos dentro de ±1 UF, rangos por escenario, autorizacion, CSRF, escape de marcado, headers del PDF
  y auditoria sin PII).
- Siguiente paso: correr gates de calidad, abrir/actualizar PR y `submit_for_review`.

### 2026-10-16 - Harness: tarea SIM-FICHA-PDF cerrada (DONE)

- Titulo: Simulador: ficha PDF con el formato 'Estudio de pension' de TPI
- Evidencia: `evidence/SIM-FICHA-PDF/` y `tasks/completed/SIM-FICHA-PDF.yaml`.
- release_sha: `dd6be124595426e6646b94d5b19c19a864e2c5a8`
- pr_number: `79`
- application_version: `h3-sim-ficha-pdf-dd6be12-domainlocked-r1`
- bundle_sha256: `de97beb63b279bc07ae4d154e1054a1b99409c597c6acc413939e01a40bb6c9e`
- lkg: `h3-sim-ux-ajustes-1f50505-domainlocked-r1`
- deployment: `success`
- deployed_commit: `dd6be124595426e6646b94d5b19c19a864e2c5a8`
- verification: `PASS`

### 2026-10-16 - SIM-FICHA-PDF: ficha PDF «Estudio de pensión» (en desarrollo, DEVELOPING)

- Titulo: Simulador: ficha PDF con el formato «Estudio de pensión» de TPI.
- Clase A (fast path, solo aplicacion): sin migraciones, grants, vistas, constraints ni infraestructura.
- Diseño fuente de verdad: `docs/specs/SIM_FICHA_PDF_SPEC.md` (la ficha de ejemplo no se copia ni se usa en pruebas por contener datos de una persona real).
- Cambios:
  - `app/services/simulador_service.py`: `generar_pdf` pasa de A4 a carta apaisada (792×612 pt) con el formato de la ficha «Estudio de pensión»: banda superior azul marino `#0f243e` (tratamiento + nombre, título «ESTUDIO DE PENSIÓN» y fecha), fila de datos (fecha de nacimiento, cónyuge, tasa de venta y valor UF destacado), tablas «OPCIÓN I» (Renta Vitalicia Inmediata + Rescate Total) y «OPCIÓN II» (Aumento Temporal de Pensión + Inflación Futura 4% + Rescate Total) cuando hay aumento temporal, pie de contacto corporativo en texto plano y banda inferior con `official-logo-on-dark.png`. Se agregan los cálculos derivados (`_rescate_opcion_i`, `_valor_actual`, `_valor_futuro`, `_rescate_opcion_ii`, `_pension_aumentada`) y el formato es-CL (`_uf`, `_clp`).
  - `app/web/routes/simulador.py`: `generar_pdf` ahora recibe `sexo_causante`, `causante_nacimiento`, `tiene_conyuge`, `saldo_uf`, meses de garantía/aumento, porcentaje de aumento y años diferidos; se eliminan `_parametros_pdf` y el cálculo de `edad_causante` (ya no se usan).
  - `tests/unit/test_sim_rv_pdf.py`: estructura de la ficha (AC-1), cálculos derivados con datos sintéticos (AC-2), pie y contacto sin PII (AC-3) y conservación de SIM-RV-V1 (AC-4).
  - `docs/SIM_RV_V1_REQUIREMENTS_MATRIX.md` (matriz de contenido del PDF) y `docs/SIM_RV_V1_PENDIENTES.md` (fuera de alcance §5) actualizados.
- Se conservan de SIM-RV-V1: leyenda «Estimación referencial no vinculante», versión del modelo, código de verificación, escape de marcado, metadatos genéricos sin PII y ausencia de RUT, correo y teléfono del lead; la renta temporal con RVD conserva su sección con la nueva apariencia.
- Fuera de alcance documentado (no se inventa): fila «RP (AFP)», bloque «PGU / BAC / TOTAL», comparativa de varias opciones, teléfono personal del ejecutivo, estado civil y renta temporal con RVD (ver `docs/SIM_RV_V1_PENDIENTES.md` §5).
- Siguiente paso: correr gates de calidad, abrir/actualizar PR y `submit_for_review`.

### 2026-10-16 - Harness: tarea SIM-UX-AJUSTES cerrada (DONE)

- Titulo: CRM y simulador: aviso de edad en pantalla, navegacion y nombre sin 'Lite'
- Evidencia: `evidence/SIM-UX-AJUSTES/` y `tasks/completed/SIM-UX-AJUSTES.yaml`.
- release_sha: `1f5050537e44d631c685dd78e7277932284c81fa`
- pr_number: `75`
- application_version: `h3-sim-ux-ajustes-1f50505-domainlocked-r1`
- bundle_sha256: `82cfe13688bdad7614501b93c3bdc7d10693eee920b4788da22795e2c46da555`
- lkg: `h3-sim-rv-v1-1308441-domainlocked-r1`
- deployment: `success`
- deployed_commit: `1f5050537e44d631c685dd78e7277932284c81fa`
- verification: `PASS`

### 2026-10-15 - SIM-UX-AJUSTES: aviso de edad en pantalla, navegacion y nombre sin 'Lite' (en desarrollo, DEVELOPING)

- Titulo: CRM y simulador: aviso de edad en pantalla, navegacion y nombre sin 'Lite'.
- Clase A (fast path, solo aplicacion): sin migraciones, grants, vistas, constraints ni infraestructura.
- Cambios:
  - `app/web/routes/simulador.py`: los POST del simulador ya no responden `PlainTextResponse` 422; ahora
    re-renderizan `simulador.html` en la misma pantalla con un aviso arriba (`simulador_errores`) y los valores
    ingresados (`form_values`), conservando HTTP 422 y los flujos 403/404/CSRF/anónimo.
  - `app/web/templates/simulador.html`: aviso de errores y re-poblado de los campos del formulario.
  - `app/web/templates/lead_detail_panel.html`: se elimina el bloque `lead-hero-actions` con el botón antiguo
    «Abrir simulación»; queda solo el panel nuevo «Abrir simulador» (executive/ceo/cto).
  - `app/web/templates/base.html`: «Volver al sitio» → «Home» y «Salir» → «Cerrar sesión».
  - «CRM Lite» → «CRM» en todo texto visible (títulos, cabecera, insignia, kickers, login y app Streamlit) y en
    las pruebas que lo afirmaban; no se renombran rutas, módulos, archivos de prueba ni identificadores, y no se
    reescribe la documentación histórica.
- Siguiente paso: correr gates de calidad, abrir/actualizar PR y `submit_for_review`.

### 2026-10-14 - Harness: tarea SIM-RV-V1 cerrada (DONE)

- Titulo: Simulador de renta vitalicia en el CRM con PDF efimero (perfil ejecutivo), V1 solo validado
- Evidencia: `evidence/SIM-RV-V1/` y `tasks/completed/SIM-RV-V1.yaml`.
- release_sha: `13084414558f59a7b1e30dd859199469c2a62318`
- pr_number: `69`
- application_version: `h3-sim-rv-v1-1308441-domainlocked-r1`
- bundle_sha256: `b91612eacdd0698661ceca28247199d6dd4254c1a675fbae6af969daa5431895`
- lkg: `h3-logo-png-cb628dc-domainlocked-r1`
- deployment: `success`
- deployed_commit: `13084414558f59a7b1e30dd859199469c2a62318`
- verification: `PASS`

### 2026-10-14 - SIM-RV-V1: simulador de renta vitalicia (en desarrollo, DEVELOPING)

- Titulo: Simulador de renta vitalicia en el CRM con PDF efimero (perfil ejecutivo), V1 solo validado.
- Motor puro portado a `app/simulador_pension` (sin cambios en la logica numerica); orquestacion en
  `app/services/simulador_service.py` (PDF efimero, codigo de verificacion, clasificacion de escenario y ventana).
- Decision de alcance (AC-11): el guard del Harness no permite editar `app/repositories/**` en esta tarea, asi
  que el escritor del evento de auditoria vive en un modulo NUEVO `app/services/simulador_auditoria.py`, que usa
  `get_db_connection` de `app.database.connection` con el mismo patron de INSERT append-only de
  `record_xlsx_export_event` (`tpi.auditoria`, `accion='simulacion_renta_vitalicia'`, `tabla_afectada='tpi.leads'`,
  `detalle` JSON sin PII). Se aparta de la convencion de capas; mover a `app/repositories/` en una tarea posterior
  con ese alcance (ver `docs/SIM_RV_V1_PENDIENTES.md` item 15).
- Siguiente paso: completar rutas web, plantillas, pruebas, gates de calidad y `submit_for_review`.
### 2026-10-14 - Harness: tarea TASK-002 cerrada (DONE)

- Titulo: Aplicar logo oficial PNG en CRM Lite (variante clara y oscura)
- Evidencia: `evidence/TASK-002/` y `tasks/completed/TASK-002.yaml`.
- release_sha: `cb628dcb7550bed4bd7a5912c22595f650cc53c9`
- pr_number: `68`
- application_version: `h3-logo-png-cb628dc-domainlocked-r1`
- bundle_sha256: `22f4f98440bdb822918797a6924ce3b600fd4f246b379880aab72a04a04b32c0`
- lkg: `h3-logo-zlib-04e3f1a-domainlocked-r1`
- deployment: `success`
- deployed_commit: `cb628dcb7550bed4bd7a5912c22595f650cc53c9`
- verification: `PASS`

### 2026-10-13 - Harness: tarea TASK-001 cancelada

- Titulo: Desplegar logo oficial de CRM Lite a DEV (release)
- Evidencia: `evidence/TASK-001/` y `tasks/completed/TASK-001.yaml`.
- release_sha: `04e3f1a80aa0c609aef8a0724419f5f21f299c8f`
- pr_number: `66`
- application_version: `h3-logo-zlib-04e3f1a-domainlocked-r1`
- bundle_sha256: `7026a0791cf7ab5c1c0a22cf9021b656b2f98c1a7a93fc568efba34ca8336a76`
- lkg: `h3-3-7-tema-claro-oscuro-6f0f5bb-domainlocked-r1`
- deployment: `success`
- deployed_commit: `04e3f1a80aa0c609aef8a0724419f5f21f299c8f`
- verification: `FAIL`

### 2026-10-12 - Harness: tarea CRM-LITE-OFFICIAL-LOGO cancelada

- Titulo: Reemplazar logo temporal de CRM Lite por logo oficial
- Evidencia: `evidence/CRM-LITE-OFFICIAL-LOGO/` y `tasks/completed/CRM-LITE-OFFICIAL-LOGO.yaml`.
- release_sha: `6a5acd4d23d623c14b67158dd0ef202f1cbfa431`
- pr_number: `64`

### 2026-10-01 - Harness: tarea H3.3.7 cerrada (DONE)

- Titulo: Tema claro y oscuro para CRM Lite
- Evidencia: `evidence/H3.3.7/` y `tasks/completed/H3.3.7.yaml`.
- release_sha: `6f0f5bb1e934742cd8e8572d4a401f8bf29ab1c7`
- pr_number: `60`
- application_version: `h3-3-7-tema-claro-oscuro-6f0f5bb-domainlocked-r1`
- bundle_sha256: `efa590b9e0daef786ce1f4b69ea8026c1a160b39d8dac06999d1c79b7f82d8aa`
- lkg: `h3-3-6-xlsx-export-5f5b3d3-domainlocked-r1`
- deployment: `success`
- deployed_commit: `6f0f5bb1e934742cd8e8572d4a401f8bf29ab1c7`
- verification: `PASS`

### 2026-09-23 - Harness: tarea H3.3.6 cerrada (DONE)

- Titulo: Exportacion ejecutiva XLSX segura
- Evidencia: `evidence/H3.3.6/` y `tasks/completed/H3.3.6.yaml`.
- release_sha: `5f5b3d37bf122f1d4438583b973fd03763aecebe`
- pr_number: `58`
- application_version: `h3-3-6-xlsx-export-5f5b3d3-domainlocked-r1`
- bundle_sha256: `8fbd2526a6e311bdcfb0c2f72cdd20a7ba9f6a056de04562957214946332cb32`
- lkg: `h3-3-5-asesores-cartera-78bf33b-domainlocked-r1`
- deployment: `success`
- deployed_commit: `5f5b3d37bf122f1d4438583b973fd03763aecebe`
- verification: `PASS`

### 2026-09-22 - Harness: tarea H3.3.5 cerrada (DONE)

- Titulo: Asesores DEV y cartera propia
- Evidencia: `evidence/H3.3.5/` y `tasks/completed/H3.3.5.yaml`.
- release_sha: `78bf33bcb946fc442a8e5488cdf0d2f89fd190c2`
- pr_number: `57`
- application_version: `h3-3-5-asesores-cartera-78bf33b-domainlocked-r1`
- bundle_sha256: `f7e661411bbaacaf456a95405fd0e787136ac6cb04eb790fd78039d7938731f1`
- lkg: `h3-3-4-historial-dashboard-3051a62-domainlocked-r1`
- deployment: `success`
- deployed_commit: `78bf33bcb946fc442a8e5488cdf0d2f89fd190c2`
- verification: `PASS`

### 2026-09-21 - Harness: tarea H3.3.4 cerrada (DONE)

- Titulo: Historial integral de estados y Dashboard Ejecutivo CRM
- Evidencia: `evidence/H3.3.4/` y `tasks/completed/H3.3.4.yaml`.
- release_sha: `3051a6271e1626b40fe24a744abe097cab1ab0fe`
- pr_number: `56`
- application_version: `h3-3-4-historial-dashboard-3051a62-domainlocked-r1`
- bundle_sha256: `bcbe935885dc50d279cd19c5f0ddf696449b29d7305c2e5506dc0a5afa9916d0`
- lkg: `h3-3-3-historial-web-ux-c5e738c-domainlocked-r1`
- deployment: `success`
- deployed_commit: `3051a6271e1626b40fe24a744abe097cab1ab0fe`
- verification: `PASS`

### 2026-09-17 - Harness: tarea H3.3.3 cerrada (DONE)

- Titulo: Historial operativo y navegacion Web UX
- Evidencia: `evidence/H3.3.3/` y `tasks/completed/H3.3.3.yaml`.
- release_sha: `c5e738c21ba202d9c664652412e6820628b18e3c`
- pr_number: `54`
- application_version: `h3-3-3-historial-web-ux-c5e738c-domainlocked-r1`
- bundle_sha256: `6b6450b53df7e54a1d80ab637819d2f7dbc059e9435cd59221b549cfda949695`
- lkg: `h3-3-2-superusuarios-ceo-cto-fec33e7-domainlocked-r1`
- deployment: `success`
- deployed_commit: `c5e738c21ba202d9c664652412e6820628b18e3c`
- verification: `PASS`

### 2026-09-16 - Harness: tarea H3.3.2 cerrada (DONE)

- Titulo: Modelo de superusuarios CEO/CTO e identidades DEV
- Evidencia: `evidence/H3.3.2/` y `tasks/completed/H3.3.2.yaml`.
- release_sha: `fec33e7951f862c95b2436b09b969e5ef1915769`
- pr_number: `53`
- application_version: `h3-3-2-superusuarios-ceo-cto-fec33e7-domainlocked-r1`
- bundle_sha256: `ddc5abe2047b624b5a5a1a8aa0615048b54291077bd0d1ffaff7c4fc9e273800`
- lkg: `h3-3-1-rbac-pii-4aac143-domainlocked-r1`
- deployment: `success`
- deployed_commit: `fec33e7951f862c95b2436b09b969e5ef1915769`
- verification: `PASS`

### 2026-09-16 - Harness: tarea H3.3.1 cerrada (DONE)

- Titulo: Completar RBAC/PII y asignacion manual en DEV
- Evidencia: `evidence/H3.3.1/` y `tasks/completed/H3.3.1.yaml`.
- release_sha: `4aac143a396934186342bab5ec97b3df5e53085c`
- pr_number: `52`
- application_version: `h3-3-1-rbac-pii-4aac143-domainlocked-r1`
- bundle_sha256: `e49628affe9279b80764a12ec5b724f60e5b89eb5b8c72bb6d519c9a99e8f72c`
- lkg: `h3-3-crm-web-43101be-domainlocked-r1`
- deployment: `success`
- deployed_commit: `4aac143a396934186342bab5ec97b3df5e53085c`
- verification: `PASS`

### 2026-09-12 - Cierre H3.3 (CLOSED WITH DEFERRED ACCEPTANCE ITEMS) y handoff

Entrada de referencia operativa vigente. Las entradas anteriores de H3.3 y los
hostnames/hashes historicos quedan como HISTORICO; esta entrada manda.

#### Punto exacto del desarrollo

- H3.3 funcional cerrado con excepciones aceptadas por el owner:
  `CLOSED WITH DEFERRED ACCEPTANCE ITEMS`.
- PR funcional #14 mergeado por squash. Merge SHA
  `89a1c58643fc228024243d474c47986ab272257f`.
- Candidate validado/desplegado: `43101be7835088f93267bee85b0f11c8bc879867`.
- Main CI de cierre: run `34701799998` -> success.
- Issue de seguimiento: #50 `H3.3.1 — completar RBAC/PII y asignacion manual en DEV`.

#### Runtime AWS DEV vigente (estado observado, no intencion)

- Account `821656895812`, region `us-east-2`.
- EB environment `tpi-backoffice-dev-green`, application `tpi-backoffice`.
- VersionLabel: `h3-3-crm-web-43101be-domainlocked-r1`.
- Estado: Ready / Green / Ok.
- Publico: https://dev.tupensioninteligente.cl -> HTTPS/TLS OK.
- Backoffice: https://backoffice.dev.tupensioninteligente.cl -> HTTPS/TLS OK, login operativo.
- API `/api/v1/catalogs` -> 200 (conectividad DB confirmada).
- Sin redirect a genialabs.cl.
- CNAME EB: `tpi-backoffice-dev-ecr.us-east-2.elasticbeanstalk.com`.

#### Release domain-locked (fast path version-only)

- PR #49 merge SHA `e4f63f1ba525df78ddebc8c724838978ed1f65c4`.
- Bundle SHA256 `007b14d4b439ea59afd13106b71edafbf902e564085581e7577770261c97282f`.
- Bucket `elasticbeanstalk-us-east-2-821656895812`, key
  `tpi-backoffice/dev-releases/h3-3-crm-web-43101be-domainlocked-r1/007b14d4b439ea59afd13106b71edafbf902e564085581e7577770261c97282f.zip`.
- El compose lleva las 4 variables TPI literales (tupensioninteligente.cl +
  zona `Z07053592LX0W8GJXNI1C`); app/caddy fijados por digest (43101be).
- Cutover: `aws elasticbeanstalk update-environment --version-label
  h3-3-crm-web-43101be-domainlocked-r1` SIN `--option-settings`.

#### Fast path DEV (lo que SÍ funciono y pasa a ser el camino de aplicacion)

1. candidate inmutable (imagenes por digest);
2. bundle determinista y verificable por SHA256;
3. Application Version nueva;
4. `update-environment --version-label <target>` (sin option settings, sin IAM/Route53/red/DB);
5. esperar Ready / Green / Ok;
6. smoke funcional inmediato;
7. rollback = `update-environment --version-label <VersionLabel conocida>`.

Para releases de aplicacion, NO modificar option settings, IAM, Route53, red ni
DB en el mismo cutover. Ver `TPI_Contrato_CICD_AWS_v2.md`.

#### Camino que NO debe repetirse (leccion registrada)

La promocion con UpdateEnvironment + option settings (cambio de configuracion)
disparo dependencias caller-side sucesivas y costosas:

- `ec2:DescribeSubnets` -> `ec2:DescribeSecurityGroups` -> `ec2:DescribeVpcs` ->
  `ec2:DescribeImages`;
- luego S3/CloudFormation: `Service:AmazonCloudFormation, Message:S3 error: Access Denied`;
- la accion Commands de CodePipeline mostro expiracion/autorizacion de token al esperar demasiado.

Leccion: NO desarrollar IAM por ciclo `AccessDenied -> agregar permiso -> retry`.
Los cambios de infraestructura requieren contrato completo, service roles/IaC y
una ruta separada del deploy de aplicacion.

#### CodePipeline / H3.2

- Promote queda disabled.
- El pipeline actual no es el camino obligatorio hasta industrializarlo en H3.2.
- No borrar el trabajo: es evidencia/base, pero requiere rediseño para separar
  promocion de aplicacion de cambios de infraestructura.

#### Rollback / artefactos a preservar (no borrar/recrear)

- `h3-3-crm-web-28cf009-r1` (runtime legacy pre-cutover; rollback version-only).
- `h3-3-domain-baseline-28cf009-caddy43101be-r1` (AV de fase-1, UNPROCESSED).
- `h3-3-crm-web-43101be-domainlocked-r1` (runtime vigente).
- No reutilizar nombres de Application Version.

#### Base de datos

- Migraciones 005 y 006 ya aplicadas y verificadas en DEV. NO reejecutar.
- Relacion operacional en `tpi.asignaciones` (`raw_payload` NO es fuente).
- Auditoria funcional en `tpi.auditoria`.

#### Deuda funcional H3.3.1 (issue #50) — pendiente funcional, no infraestructura

- CEO/CTO aun ve PII ofuscada en DEV.
- El control de asignacion manual no aparece en la UI observada.
- Diferido: smoke end-to-end de asignacion y validacion read-only de
  `tpi.leads` / `tpi.asignaciones` / `tpi.auditoria`.
- Confirmar una sola asignacion activa por lead y actor auditado.
- Al retomarlo: diagnosticar primero autorizacion/roles y renderizado de la
  accion en aplicacion. No tocar AWS/IAM/deploy salvo evidencia nueva.

#### Orden recomendado para el siguiente equipo

1. Leer esta entrada + `TPI_Contrato_CICD_AWS_v2.md`.
2. Resolver #50 H3.3.1 como cambio funcional aislado.
3. Desplegar fixes H3.3.1 por fast path version-only.
4. Smoke autenticado inmediato tras runtime green.
5. Validar DB con identidad read-only, sin exponer passwords.
6. Reanudar H3.2 solo despues: automatizar version-only + IaC/service roles.
7. Antes de PROD cerrar: IaC del control plane, service roles explicitos, smoke
   automatizado con usuario sintetico, identidad DB read-only de inspeccion,
   politica de rollback/retencion, observabilidad y evidencia por release.

#### Principios a conservar

- Seguridad server-side (PII/RBAC).
- Minimo privilegio y separacion de responsabilidades.
- Releases inmutables y reproducibles.
- Trazabilidad mecanica commit -> digest -> bundle -> Application Version -> runtime.
- Rollback explicito y probado.
- Tests unitarios, integracion, seguridad y smoke funcional.
- Ningun secreto en Git, logs o bitacora.
- Ningun cambio de infraestructura improvisado durante un release funcional.
- Diseñar DEV -> QA -> PROD sin copiar excepciones ad hoc.
- Documentar siempre estado observado, no solo intencion.

### 2026-09-11 - Remediacion minima de supply-chain de la imagen app

- El tag oficial inmutable `python:3.12.14-alpine3.24` continua resolviendo al
  digest `sha256:b64631e04e4920160c50fbe8d8df828f7f35f06f425cb44aa09bca53e708a35a`.
- El scan ECR del candidate no elegible atribuyo el finding a la fuente
  `util-linux 2.42.1-r0`. La inspeccion del APK DB de la base confirma que el
  unico APK instalado con ese origen es `libuuid 2.42.1-r0`; el indice oficial
  Alpine 3.24 publica `libuuid 2.42.3-r1` del mismo origen.
- Se conserva la base fijada y se actualiza exclusivamente `libuuid` con una
  version explicita. No se usa `apk upgrade` global ni se modifican dependencias
  Python, funcionalidad H3.3 ni recursos AWS.
- CI compara el inventario APK de la base y la app, exige que el unico delta sea
  `libuuid 2.42.1-r0 -> 2.42.3-r1`, conserva Python 3.12.14 y valida el
  arranque/readiness del contenedor contra PostgreSQL efimero.

### 2026-09-10 - Preparacion del cierre TLS/domain contract de H3.3

Contexto:

- La promocion H3.3 anterior termino saludable sobre
  `h3-3-crm-web-28cf009-r1`, que permanece inmutable.
- AWS Agent Toolkit confirmo en la cuenta `821656895812` que la hosted zone
  publica delegada es `dev.tupensioninteligente.cl.` con ID
  `Z07053592LX0W8GJXNI1C`; no existe una hosted zone apex TPI en la cuenta.
- El environment conservaba las direcciones historicas `genialabs.cl` y la
  policy fisica ACME ya apuntaba a la zona TPI, pero autorizaba solo el TXT del
  hostname publico.

Cambios preparados:

- Caddy obtiene el hosted zone ID desde `TPI_ROUTE53_HOSTED_ZONE_ID`.
- El Compose AWS exige las cuatro variables no secretas del contrato DEV.
- La policy Route 53 versionada limita cambios a TXT sobre los challenges
  publico y backoffice en la zona delegada TPI.
- El preflight independiente y el de promocion comparan los cuatro valores
  exactos sin imprimir el resto del environment.
- Se actualizaron los allowlists runtime del sitio publico y del backoffice y
  se agregaron pruebas de regresion.

Pendiente:

- CI, candidate inmutable nuevo, aplicacion/verificacion de la policy fisica,
  cutover controlado, promocion unica, TLS/smoke H3.3 y cierre de PR `#14`.
- Antes de mutar AWS debe resolverse mecanicamente el orden atomico entre el
  preflight exacto y el cambio de VersionLabel/configuracion, sin arrancar una
  revision de Caddy con dominio y hosted zone incompatibles.

### 2026-08-25 - Registro historico de cutover DEV

> Registro historico: los hostnames, version labels y permisos descritos a
> continuacion no representan el contrato runtime DEV vigente.

Contexto:

- Se habilito el nuevo dominio DEV oficial `https://dev.tupensioninteligente.cl`.
- El objetivo fue dejar HTTPS valido, mantener rollback y preservar `dev.genialabs.cl` como respaldo temporal.

Resumen tecnico cronologico:

- Se verifico primero la resolucion DNS y el flujo HTTP hacia el environment AWS DEV.
- El handshake HTTPS inicial fallo, por lo que se descarto un problema basico de DNS o conectividad.
- Se confirmo por logs de Caddy que el hostname nuevo llegaba a la config activa y que Caddy intentaba ACME DNS-01.
- La primera causa raiz identificada fue IAM insuficiente para Route 53.
- La segunda causa raiz fue un `hosted_zone_id` hardcodeado en `deployment/caddy/Caddyfile` que estaba compartido entre dominios y apuntaba a la zona de `dev.genialabs.cl`.
- Se separo la configuracion DNS-01 por hosted zone:
  - `dev.genialabs.cl` -> `Z0562050FYDQE12LRGMA`
  - `dev.tupensioninteligente.cl` -> `Z07053592LX0W8GJXNI1C`
- Se valido el runtime real de Caddy dentro de `tpi-backoffice-dev-green` y luego se desplego una nueva version reproducible.
- Se realizo cutover DNS controlado del alias publico para `dev.tupensioninteligente.cl` hacia `tpi-backoffice-dev-green`.
- Se confirmo TLS valido, smoke read-only y preservacion del dominio legado como respaldo temporal.

Evidencia de release:

- Commit: `47fa0c92e2fb9fc916309ac219410fffb08f7cbc`
- VersionLabel: `h2-5d-ecr-47fa0c9`
- Bundle: `s3://elasticbeanstalk-us-east-2-821656895812/deployments/h2-5d-ecr-47fa0c9.zip`
- SHA256: `e62d039cdfe4e11e1c6fc1aacf13cb6182ba2480217ca5e395eaa520e2621cb7`

Siguiente paso:

- Mantener observacion de estabilidad del nuevo dominio.
- No retirar todavia `dev.genialabs.cl` hasta que el corte de operacion quede formalmente cerrado.
- Consolidar los aprendizajes en la documentacion de despliegue reproducible.

### 2026-08-25 - Registro historico de cierre H3.3 CRM Lite Web UX

Contexto:

- H3.3 quedo validado funcionalmente en AWS DEV como CRM Lite Web UX.
- La validacion manual del producto sobre `https://backoffice.dev.genialabs.cl` fue satisfactoria.

Datos de cierre:

- Hito: `H3.3 — CRM Lite Web UX`
- Status: `CLOSED`
- Human UX Acceptance: `PASS`
- Git SHA: `1574d79920342d3da2bac8296de9020b8162c68f`
- App digest: `sha256:1f5bca0350e3f3229516643b1f1f5dcf05f6f13e826c6a444aa8640302b73922`
- EB Version: `h3-3-crm-web-1574d79-r1`
- URL: `https://backoffice.dev.genialabs.cl`

Siguiente paso:

- No realizar mas cambios funcionales ni de infraestructura sobre este hito.
- Si se requiere ajustar documentacion historica adicional, hacerlo en una PR exclusivamente documental.

Referencia canonica:

- [docs/H3_3_CRM_LITE_WEB_UX.md](H3_3_CRM_LITE_WEB_UX.md)
- [docs/PROJECT_STATUS.md](PROJECT_STATUS.md)
- [docs/DECISIONES_TECNICAS.md](DECISIONES_TECNICAS.md)

### 2026-08-22 - H3.1 CRM Lite cerrado formalmente

Contexto:

- H3.1 quedo validado funcional y tecnicamente sobre `feat/h3-1-crm-lite`.
- El cierre Git fue completado con `main` en `ad22d37048176aa80ab139f56c3ef6903f6e430e` y el runtime productivo ya habia sido verificado previamente desde `d9bc2670bca87a71130d8e7088b56dd7976b82f5`.

Datos de cierre:

- PR: `#8`
- Final PR HEAD: `58a11fdcd0b1a9b1bca6679ebe463e0964659c7f`
- Merged main: `ad22d37048176aa80ab139f56c3ef6903f6e430e`
- CI final: `#58`
- Lint: PASS
- Tests: PASS
- Security: PASS
- Docker: PASS
- Productive runtime validated from: `d9bc2670bca87a71130d8e7088b56dd7976b82f5`
- App digest: `sha256:e70d799ed6b5da252a7f90bc412b8a75ba37082377f3e3bc46ca7025571ca01b`
- AWS DEV: validated
- Database structural changes: none

Pendientes movidos a H3.2:

- reproducible deployment chain
- CI post-merge observability
- runtime verification automation
- cleanup log observability

Siguiente paso:

- Reanudar H3.2 desde el contrato de release y la documentacion ya aprobada, sin descartar ningun trabajo realizado.

### 2026-08-17 - H2.5C local demo preparation

Contexto:

- AWS account-plan work is blocked externally. A complete local rehearsal is
  required without AWS, RDS, SNS, Secrets Manager or HTTPS.

Tareas realizadas:

- Added `docker-compose.local.yml` with local PostgreSQL and the existing
  idempotent schema initializer, while keeping the AWS-oriented Compose file
  free of a database service.
- Parameterized Caddy site addresses and upstreams. The local defaults are
  loopback-only HTTP `tpi.localhost` and `backoffice.tpi.localhost`; future AWS
  deployment must set public domain addresses explicitly.
- Documented an untracked Argon2id local user, fake local HMAC, disabled SNS,
  lifecycle commands and the manual Caddy fallback.

Seguridad:

- `AUTH_USERS_JSON` is supplied only to backoffice from `.env.local`.
- H2.3 cleanup remains impossible in local mode; reset the local volume instead.
- No AWS resource, secret or network configuration was changed.

### 2026-08-17 - H2.5C idempotency hardening pending local validation

Contexto:

- The public API remains local only. No AWS, DNS, IAM, Secrets Manager, RDS or
  deployment change is authorized or executed.

Tareas realizadas:

- Renamed the idempotency HMAC configuration to the dedicated
  `API_IDEMPOTENCY_HMAC_SECRET` contract. Public API startup fails closed when
  it is absent and it is explicitly separate from database and auth secrets.
- Confirmed the PostgreSQL algorithm reserves `idempotency_key` with its primary
  key plus `INSERT ... ON CONFLICT` in the same transaction as lead creation.
  A PostgreSQL concurrency test covers two simultaneous equal requests.
- Updated the short-lived lead FK to `ON DELETE SET NULL` so the approved DEV
  cleanup path is not blocked. The migration grants only the required table
  privileges to `tpi_app`; `scripts/sql/003_drop_api_idempotency.sql` is the
  documented reversal after disabling the public API.

Pendiente:

- Complete quality gates in an environment with normal temporary, Docker and
  Git permissions before any commit or push.

### 2026-08-16 - H2.5C public static frontend and HTTP API (local only)

Contexto:

- H2.5C replaces the cloned frontend lead transport through WhatsApp with a
  same-origin, versioned HTTP API. No AWS, DNS, billing, IAM, secret, security
  group, Route 53 or deployment change is authorized or executed.

Tareas realizadas:

- Versioned `front/`, corrected JPEG extensions/MIME references, removed binary
  duplicates and added the mandatory synthetic-data DEV banner.
- Added `app/api` FastAPI adapter with `GET /api/v1/catalogs` and
  `POST /api/v1/leads`, explicit public-to-application DTO mapping, safe errors,
  request size limit, security headers, same-origin operation and no CORS.
- Added PostgreSQL-backed idempotency in `tpi.api_idempotency` through the
  versioned `scripts/sql/003_create_api_idempotency.sql` migration. It stores no
  payload or PII and uses a runtime HMAC key.
- Preserved `SolicitudService` as the only public lead business entrypoint and
  SNS publication as best effort strictly after commit.
- Changed local Compose/Caddy topology to static front + API on the public host
  and Streamlit backoffice on the private hostname.

Validacion local parcial:

- Applied the idempotency schema only to the local test database and passed the
  new integration cases for replay, conflict and notification failure.
- No AWS RDS change was made.

Pendiente:

- Complete full quality-gate validation and review before any push or AWS work.
- The runtime HMAC key must be supplied from a future exact secret; no secret
  has been created in this iteration.

Siguiente paso:

- Finish local tests, Docker/Compose/Caddy validation and commit the isolated
  H2.5C changes after review.

### 2026-08-16 - H2.5 public/private presentation separation

Contexto:

- H2.5 was corrected before AWS work: public lead capture must remain available
  without login, while the backoffice remains private.
- No AWS, billing-plan, DNS, Route 53, IAM, Secrets Manager, network, or
  deployment change is authorized in this iteration.

Tareas realizadas:

- Split Streamlit into the public `app/streamlit_app.py` entrypoint and private
  `app/backoffice_app.py` entrypoint.
- Reused `SolicitudService`, Pydantic requests, PostgreSQL repositories, and
  post-commit SNS behavior through a public presentation component.
- Kept `app/auth` unchanged in responsibility and applied it only to private
  entrypoints/pages.
- Changed Compose/Caddy declaration to route proposed public and backoffice
  hostnames to separate internal Streamlit services.
- Added public/private boundary tests and updated developer, architecture, CEO,
  and decision documentation.

Seguridad:

- The public Compose service does not receive `AUTH_USERS_JSON`.

### H2.5D temporary DEV DNS

- `dev.genialabs.cl` and `backoffice.dev.genialabs.cl` are the temporary AWS
  DEV hostnames. DNS and Caddy configuration are deployment concerns; the
  application core remains independent of the hostname.
- The public front sends `noindex,nofollow` in HTML and Caddy's
  `X-Robots-Tag`. Production TPI and its data remain outside this environment.
- Invalid auth configuration remains fail-closed for backoffice and does not
  prevent public lead capture.
- Port 8501 remains internal to Compose; no infrastructure rules changed.

Pendiente:

- Run complete local quality gates and review the refactor before any AWS work.
- After approval, separately decide account upgrade, domain registration,
  Route 53, auth secret, IAM, Caddy deployment, and access rules.

Siguiente paso:

- Complete local validation only; do not perform AWS operations.

### 2026-08-15 - H2.5 SimpleDevAuth local preparation

Contexto:

- H2.5 approved the DEV-only SimpleDevAuth, Caddy, and Docker Compose design.
- No AWS, DNS, IAM, Secrets Manager, user, Security Group, or deployment change
  is authorized until the external DNS CNAME is confirmed.

Tareas realizadas:

- Added the `app/auth` boundary with an immutable user contract, provider
  protocol, Argon2id SimpleDevAuth adapter, common guards, logout, and
  per-session throttling.
- Added safe auth settings with `AUTH_ENABLED=false` as the versioned default
  and a fail-closed mode for AWS DEV, production, malformed users config, and
  unknown auth modes.
- Prepared Docker Compose with Caddy as the only host listener and Streamlit on
  the internal Docker network.
- Added an exact-resource IAM policy template, tests, CI Compose validation,
  CEO validation guide, and development guide.

Seguridad:

- No password, password hash, user, AWS secret, IAM change, or network rule was
  created or committed.
- The future runtime secret is `tpi/dev/auth-users`; it will contain Argon2id
  hashes only and be injected only after explicit infrastructure approval.

Pendiente:

- Confirm control of the DNS zone and create the approved CNAME for
  `dev.tupensioninteligente.cl` outside this repository.
- Only then create the auth secret, attach the exact IAM permission, open
  80/443, deploy Compose, create the approved DEV user, and run the HTTPS smoke
  test.

Siguiente paso:

- Wait for DNS confirmation; do not perform AWS changes before it arrives.

## Snapshot Actual

Fecha de referencia: `2026-08-07`

- App principal: Streamlit
- Lenguaje: Python
- Base de datos: PostgreSQL
- Esquema principal: `tpi`
- Driver de acceso: `psycopg`
- Pool de conexiones: `psycopg_pool`
- Configuracion central: `app/config/settings.py`
- Capa de conexion: `app/database/connection.py`
- Healthcheck: `app/database/healthcheck.py`
- Servicio principal: `app/services/solicitud_service.py`
- Repositorio principal: `app/repositories/solicitud_repository.py`

## Estado Actual del Proyecto

- El MVP local funciona para registrar, consultar y visualizar metricas basicas.
- La conexion segura a PostgreSQL/Amazon RDS ya esta implementada en codigo.
- La configuracion por ambiente ya esta centralizada y tipada.
- El rol de aplicacion `tpi_app` ya tiene un script versionado de permisos.
- La validacion manual contra `tpi-postgres-dev` ya fue completada con `tpi_app`, SSL y limpieza posterior del dato sintetico.
- El hito AWS RDS ya fue mergeado a `main` y la CI posterior al merge quedo verde.
- El esquema contiene tablas de auditoria/eventos, pero el backoffice actual no las consume como auditoria funcional; la "trazabilidad" de la UI sigue siendo analitica sobre `tpi.leads`.
- No existe operacion de eliminacion ni desactivacion desde el backoffice.

## Donde Partir Si Tomas el Proyecto Hoy

Orden recomendado:

1. Leer `docs/AWS_RDS_CONNECTION.md`
2. Leer `docs/DECISIONES_TECNICAS.md`
3. Revisar `app/config/settings.py`
4. Revisar `app/database/connection.py`
5. Revisar `app/repositories/solicitud_repository.py`
6. Revisar `app/services/solicitud_service.py`
7. Ejecutar `python scripts/verify_database_connection.py`
8. Ejecutar `pytest`

## Mapa Rapido del Backoffice

Tablas realmente usadas por la app:

- Solo lectura:
  - `tpi.catalogo_afp`
  - `tpi.catalogo_genero`
  - `tpi.catalogo_estado_civil`
- Lectura y escritura:
  - `tpi.personas`
  - `tpi.leads`
  - `tpi.consentimientos`

Archivos clave:

- `app/streamlit_app.py`
- `app/pages/1_registrar_solicitud.py`
- `app/pages/2_solicitudes_registradas.py`
- `app/pages/3_trazabilidad.py`
- `scripts/sql/001_create_tpi_app_role.sql`
- `scripts/verify_database_connection.py`

## Historial Incremental

### 2026-08-15 - H2.5 preflight SimpleDevAuth y Caddy

Contexto:

- Se reemplazo el preflight previo ALB/Cognito por una propuesta temporal y
  explicitamente DEV ONLY: Caddy HTTPS delante de Streamlit y SimpleDevAuth
  desacoplado mediante `app/auth/`.

Hallazgos y decision propuesta:

- Elastic Beanstalk Docker puede usar Docker Compose con un proxy propio; Caddy
  seria el unico contenedor que expone 80/443 y Streamlit quedaria interno en
  8501.
- La cuenta AWS no tiene Hosted Zone Route 53. El DNS publico actual delega en
  DataTecno y no existe el CNAME `dev.tupensioninteligente.cl`; se requiere
  confirmar control administrativo y aprobar el registro antes de ACME.
- El secreto propuesto `tpi/dev/auth-users` contiene solo hashes Argon2id y
  metadata minima. El role EB recibira lectura unicamente sobre su ARN exacto.
- El modo SimpleDevAuth tendra guard fail-closed, sesion Streamlit sin password
  ni hash, logout y throttle por sesion. Produccion debera migrar a HTTPS
  administrado y OIDC con un IdP profesional.

Estado:

- No se crearon ni modificaron recursos, usuarios, secretos, DNS, IAM ni
  Security Groups. Se requiere aprobacion del preflight y confirmacion DNS.
- Detalle completo: `docs/H2_5_SIMPLE_DEV_AUTH_PREFLIGHT.md`.

### 2026-08-15 - H2.4 notificaciones extensibles de leads

Contexto:

- H2.4 introduce una capacidad post-commit para notificar `lead.created` sin
  acoplar el flujo de negocio a email, SNS ni boto3.

Decisiones y hallazgos:

- `LeadCreatedEvent` es un contrato versionado y sin PII: solo UUIDs,
  timestamp UTC, ambiente y fuente.
- `SolicitudService` publica despues del commit del Repository y tolera el
  fallo del publisher; el lead confirmado nunca se revierte por SNS.
- SNS Standard usa el topic `tpi-dev-lead-created`. La suscripcion email
  aprobada no se versiona y fue confirmada manualmente antes del smoke test.
- El rol EB recibe un inline policy con `sns:Publish` solamente sobre el ARN
  exacto del topic. El secreto administrativo y PostgreSQL no se modifican.

Validacion:

- Unit e integracion cubren payload sin PII, publisher deshabilitado/fallido,
  commit antes de publicar y persistencia del lead cuando falla SNS.
- La regresion local completa paso: 226 tests, cobertura 88.49%, Ruff, Black,
  MyPy, Bandit y pip-audit verdes. Los seis warnings Altair existentes no son
  bloqueantes.
- Se desplego `h2-4-9ea12f10e674` en `tpi-backoffice-dev`, que regreso a
  `Ready/Green`; contenedor healthy y endpoints raiz y `/_stcore/health` con
  HTTP 200 desde la IP autorizada.
- Las propiedades runtime exclusivas de DEV habilitan notificaciones y apuntan
  al topic SNS; los defaults versionados permanecen apagados.
- Smoke test real: el lead ficticio se confirmo en RDS, SNS publico el evento
  sin PII, se recibio el email operacional y el UUID coincidio. La limpieza
  H2.3 posterior dejo el lead inexistente y cero consentimientos asociados.
- CloudWatch conserva logs por siete dias. La consulta de conteo de patrones
  sensibles sobre stdout/stderr no encontro coincidencias en la ventana del
  deployment; no se registraron secretos ni PII en la evidencia revisada.

Siguiente paso:

- Crear o actualizar el PR draft H2.4 contra `main` y esperar CI verde antes
  de solicitar revision. La integracion GitHub local no tiene permiso para
  crear PRs; la rama ya fue publicada.

### 2026-08-14 - H2.3 limpieza controlada de leads ficticios en AWS DEV

Contexto:

- H2.3 habilita el flujo de datos ficticios crear, consultar y limpiar solo en AWS DEV.

Decisiones y hallazgos:

- La habilitacion exige `APP_ENV=aws-dev` y `DEV_DELETE_ENABLED=true`; cualquier otro ambiente queda denegado en Service.
- El inventario de RDS encontro referencias a `leads` desde `asignaciones`, `auditoria`, `campanas_atribucion`, `citas`, `consentimientos`, `eventos_lead`, `fichas_diagnosticas` e `ingesta_google_sheets`.
- `auditoria` tambien referencia `personas`, por lo que H2.3 conserva personas y no concede DELETE sobre esa tabla.
- La transaccion borra solo consentimientos y el lead. Una FK operacional bloquea la operacion y revierte todo.
- Los scripts `scripts/sql/dev/002_enable_test_cleanup.sql` y `002_disable_test_cleanup.sql` otorgan y revocan DELETE solo en consentimientos y leads para `tpi_app` en DEV.

Validacion:

- Unit, integration PostgreSQL, E2E y security cubren guard de ambiente, UUID invalido, doble ejecucion, SQL parametrizado, persona compartida y rollback por FK.
- La UI requiere checkbox y texto `ELIMINAR`, y registra eventos sin PII usando solo el UUID interno del lead.
- Se aplico `002_enable_test_cleanup.sql` desde una conexion administrativa temporal con `tpi_admin`. `tpi_app` quedo sin atributos administrativos, sin DELETE en `personas` ni tablas operacionales, y con DELETE solo en `tpi.leads` y `tpi.consentimientos`.
- Se desplego `h2-3-3d5ded341436` en `tpi-backoffice-dev`. La configuracion versionada conserva `DEV_DELETE_ENABLED=false`; la propiedad efectiva `true` existe solo en el environment DEV.
- El contenedor desplegado esta healthy y corre como `appuser`; los checks confirmaron `APP_ENV=aws-dev`, salud PostgreSQL completa, HTTP 200 en raiz y `/_stcore/health`, y banner visible de ambiente DEV.
- El smoke test AWS con datos sinteticos completo crear, consultar, eliminar y verificar ausencia de lead/consentimiento, conservando la persona. La revision agregada de CloudWatch stdout/stderr no encontro patrones de password, token, email, telefono ni RUT; la retencion es siete dias.

Seguridad y rollback:

- `tpi/dev/database-admin-password` se usa solo desde el perfil local administrativo `tpi-dev`; el rol de Elastic Beanstalk conserva acceso unicamente al secreto de aplicacion. Ningun valor de secreto se versiona ni se registra.
- Para revertir H2.3: configurar `DEV_DELETE_ENABLED=false` en `tpi-backoffice-dev`, reiniciar o redeployar y ejecutar `scripts/sql/dev/002_disable_test_cleanup.sql` con `tpi_admin`. RDS, H2.2 y los permisos de creacion/consulta permanecen intactos.

### 2026-08-14 - H2.2 correccion de empaquetado para CI

Contexto:

- El PR H2.2 agrego el directorio declarativo `deployment/`, y setuptools intento descubrirlo como un segundo paquete Python durante la instalacion editable de CI.

Correccion:

- Se declaro `[tool.setuptools.packages.find]` con `include = ["app*"]` en `pyproject.toml`.
- `deployment/` permanece fuera del paquete distribuible y conserva su funcion de configuracion de Elastic Beanstalk e IAM.

Validacion:

- `python -m pip install --no-deps -e .` completo correctamente.
- La regresion completa, cobertura, Ruff, Black, MyPy, Bandit, pip-audit y Docker build se ejecutaron sin modificar runtime, reglas de negocio ni infraestructura AWS.

### 2026-08-14 - H2.2 despliegue real Streamlit en AWS DEV

Contexto:

- Se aprobo el pre-flight y se publico el artefacto Streamlit existente en Elastic Beanstalk, sin cambios de negocio.

Tareas realizadas:

- Se creo el SG `tpi-backoffice-dev-sg` con HTTP solo desde la IP autorizada `/32`.
- Se agrego al SG RDS existente una regla TCP 5432 con origen exclusivo en el SG de aplicacion; la regla administrativa DBeaver se mantuvo intacta.
- Se crearon los roles IAM de instancia y de servicio para Elastic Beanstalk, con lectura limitada al secreto DEV de base de datos y SSM para diagnostico sin SSH publico.
- Se creo la aplicacion `tpi-backoffice` y el environment `tpi-backoffice-dev` en Docker Amazon Linux 2023, Single Instance `t3.micro`.
- Se habilito CloudWatch Logs con retencion de siete dias.
- Se documento el despliegue, operaciones, costos, troubleshooting y rollback en `docs/H2_2_AWS_DEV_DEPLOYMENT.md`.

Seguridad y decisiones:

- `DATABASE_PASSWORD` se inyecta desde Secrets Manager por Elastic Beanstalk; no se leyo ni versiono su valor.
- La instancia tiene solo el SG dedicado. Se configuro `DisableDefaultEC2SecurityGroup=true`, no hay SSH ni 8501 expuestos, y RDS no tiene 5432 abierto a Internet.
- El primer bundle incluyo por error `docker-compose.yml`, por lo que Elastic Beanstalk intento usar servicios locales. Se corrigio con `.gitattributes` y `export-ignore`; el bundle final usa solo el Dockerfile del repositorio.

Resultados:

- Environment `Ready/Green`, instancia `running`, Docker `healthy` y usuario de contenedor `appuser`.
- `/_stcore/health` y la pagina principal respondieron HTTP 200 desde la IP autorizada.
- El healthcheck interno confirmo conexion PostgreSQL con SSL, esquema `tpi` y acceso a `tpi.leads`.
- El CI del PR termino con `194 passed`, 83.42 por ciento de cobertura y seis warnings no bloqueantes. Ruff, Black, MyPy, Bandit, pip-audit y Docker build quedaron verdes.

Riesgos y pendientes:

- El environment es HTTP temporal y Single Instance; autenticacion, HTTPS y alta disponibilidad siguen fuera de H2.2.
- RDS mantiene `PubliclyAccessible=true` por alcance aprobado; su proteccion efectiva depende del SG restringido.
- No avanzar a H2.3 sin aprobacion explicita.

### 2026-08-14 - H2.2 pre-flight completado con perfil AWS TPI

Contexto:

- Se autentico el perfil local `tpi-dev` mediante `aws login` para la cuenta TPI y se valido la identidad antes de cualquier cambio AWS.

Hallazgos:

- Cuenta validada: `8216...5812`; region efectiva para H2.2: `us-east-2`.
- RDS `tpi-postgres-dev` esta `available`, usa PostgreSQL 17.9, base `tpi`, puerto 5432 y cifrado en reposo.
- El RDS esta en la VPC por defecto `vpc-0f86145db5a906b73`, con tres subredes activas en `us-east-2a`, `us-east-2b` y `us-east-2c`.
- La VPC tiene DNS habilitado, subredes con asignacion publica y una ruta por defecto hacia Internet Gateway.
- RDS es publicamente direccionable, pero su Security Group `tpi-postgres-admin-sg` permite PostgreSQL solo desde una IP administrativa individual `/32`; no existe acceso `0.0.0.0/0` a 5432.
- Backups: un dia de retencion; Multi-AZ: deshabilitado; deletion protection: habilitado; logs PostgreSQL: habilitados.

Decision:

- Es viable crear posteriormente un Security Group de aplicacion Elastic Beanstalk en la misma VPC y autorizarlo como origen TCP 5432 en el Security Group de RDS.
- La regla administrativa existente se conserva; no se modificaron RDS, VPC, IAM, Secrets Manager ni Security Groups durante este pre-flight.

Riesgos a resolver antes del despliegue:

- RDS es `PubliclyAccessible=true`; H2.2 debe mantener su SG restringido y no agregar reglas publicas para PostgreSQL.
- La VPC actual es de subredes publicas y Single Instance; es adecuada para DEV de bajo costo, no para un entorno productivo de alta disponibilidad.

### 2026-08-14 - H2.2 pre-flight AWS DEV bloqueado por RDS no localizado

Contexto:

- Se inicio H2.2 para publicar Streamlit en Elastic Beanstalk Single Instance, sin cambios de negocio.
- Se actualizo `main` y se creo la rama `feat/h2-2-aws-dev-deployment`.

Pre-flight realizado:

- La identidad AWS configurada respondio correctamente y la region activa es `us-east-1`.
- La CI del commit H2.1 mergeado en `main` finalizo en estado `success`.
- La consulta no destructiva de RDS en la region activa no encontro la instancia `tpi-postgres-dev` ni otras instancias RDS disponibles.

Decision:

- No se crearon recursos Elastic Beanstalk, IAM, Secrets Manager ni Security Groups.
- No se modifico RDS ni su red.
- No se puede continuar sin confirmar la cuenta y region donde existe el RDS DEV o el identificador correcto de la instancia.

Siguiente paso:

- Recibir la cuenta/region autorizada y el identificador RDS correctos, luego repetir el inventario de red antes de cualquier cambio AWS.

### 2026-08-14 - H2.2 pre-flight repetido en us-east-2 confirma cuenta AWS distinta

Contexto:

- Se recibio la correccion de region `us-east-2`, el identificador `tpi-postgres-dev` y su endpoint RDS esperado.

Resultado:

- La identidad AWS activa pertenece a la cuenta enmascarada `0514...8454`; solo existe el perfil local `default` y su region configurada sigue siendo `us-east-1`.
- La consulta se ejecuto explicitamente con `--region us-east-2` y RDS respondio `DBInstanceNotFound` para `tpi-postgres-dev`.
- El endpoint proporcionado resuelve DNS en `us-east-2`, por lo que la instancia existe, pero no pertenece a la cuenta AWS activa o no es visible para sus credenciales.

Decision:

- No se puede obtener de manera autorizada el estado, VPC, subnet group, Security Groups, cifrado, backups ni configuracion de red de RDS.
- No se crearon ni modificaron recursos AWS.

Siguiente paso:

- Configurar o asumir el perfil/rol de la cuenta propietaria de RDS y repetir el pre-flight en `us-east-2` antes de crear Elastic Beanstalk o cualquier regla de red.

### 2026-08-11 - Cierre tecnico H2.1: gates, lockfiles y compatibilidad Pydantic

Contexto:

- La preparacion inicial de despliegue quedo implementada, pero faltaba hacer exigible su calidad en CI y resolver un warning propio de Pydantic.

Tareas realizadas:

- Se migro la configuracion de modelos Pydantic a `ConfigDict` y se agrego una prueba de regresion para el metadata del schema.
- Se configuro cobertura minima global de 80 por ciento.
- Se convirtieron Bandit y `pip-audit` en quality gates bloqueantes.
- Se agrego el build de Docker como job obligatorio de CI.
- Se agregaron `requirements/runtime.lock` y `requirements/dev.lock`; Docker instala solo el lock de runtime.
- Se documento la Definition of Done permanente en `docs/ENGINEERING_STANDARDS.md`.

Decisiones:

- Los lockfiles fijan versiones exactas y se actualizaran de forma deliberada mediante pull request.
- `pip-audit` evalua el lock de runtime, evitando findings de paquetes ajenos al proyecto presentes en entornos compartidos.

Resultados de cierre:

- `docker build -t tpi-backoffice-h21 .` y `docker compose up --build` construyeron la imagen y levantaron PostgreSQL y Streamlit localmente.
- Streamlit respondio `200 ok` en `/_stcore/health`; el healthcheck del contenedor quedo `healthy` y el proceso corrio como `appuser`.
- `pytest tests -q --cov-fail-under=80` termino con `194 passed` y 82.92 por ciento de cobertura.
- Ruff, Black, MyPy y Bandit terminaron sin findings bloqueantes.
- `pip-audit` detecto cinco vulnerabilidades de GitPython 3.1.57; se actualizo el lock a 3.1.58 y la auditoria final quedo sin vulnerabilidades conocidas.

Warnings pendientes:

- Altair emite un warning de inferencia de tipo Vega-Lite para `interval` en pruebas de trazabilidad.
- Pytest puede emitir warnings de cache y limpieza de temporales en Windows por permisos del filesystem.
- Ambos warnings son externos al comportamiento de aplicacion y no bloquean la suite.

Pendiente:

- Consolidar los commits H2.1, publicar la rama y abrir PR contra `main`. No desplegar en AWS dentro de este hito.

### 2026-08-12 - Preparación técnica H2.1 para despliegue AWS DEV

Contexto:

- Se inició la preparación técnica para dejar Streamlit listo para un despliegue reproducible en AWS DEV sin ejecutar todavía el despliegue.
- El foco fue reforzar el arranque, la observabilidad, el healthcheck, la containerización y la documentación operativa.

Tareas realizadas:

- Se agregó `app/runtime.py` para centralizar logging, arranque seguro y manejo controlado de errores.
- Se agregó `scripts/healthcheck_runtime.py` como readiness check del contenedor.
- Se creó `.streamlit/config.toml` para que Streamlit escuche en `0.0.0.0`, en modo headless y con telemetría desactivada.
- Se endureció `Dockerfile` con Python 3.12 explícito, usuario no privilegiado, copia mínima de artefactos y healthcheck real.
- Se actualizó `docker-compose.yml` para validar readiness del servicio Streamlit.
- Se reforzaron `.gitignore` y `.dockerignore` para secretos, certificados y artefactos locales.
- Se actualizó `run_streamlit.bat` para un arranque portable en Windows.
- Se agregaron tests unitarios para runtime, healthcheck y aliases de ambiente.
- Se agregaron tests de integración para el healthcheck completo.
- Se documentó la preparación en `docs/H2_1_PREPARACION_DESPLIEGUE.md` y se enlazó desde `README.md`.

Aprendizajes:

- Streamlit necesita una configuración explícita para host no local si se quiere usar el mismo artefacto dentro de contenedores y servicios administrados.
- El healthcheck del contenedor no puede limitarse a “el proceso existe”; debe verificar también la dependencia principal.
- El logging debe salir por stdout/stderr y nunca depender de archivos locales para que sea usable por CloudWatch o por el runtime que corresponda.

Desafios:

- La suite completa de tests tarda lo suficiente como para requerir una ventana de ejecución amplia.
- En Windows, `pytest` deja warnings de limpieza de temp/cache ajenos a la lógica del proyecto.

Como se resolvio:

- Se validó primero la suite unitaria e integración de forma separada.
- Se aisló y volvió a verificar la regresión E2E de consultas antes de cerrar el bloque técnico.

Pendiente:

- Ejecutar la batería completa de calidad con tiempo suficiente y dejar el resumen final consolidado.

Siguiente paso:

- Correr `pytest tests -q`, `ruff`, `black`, `mypy`, `bandit` y `pip-audit` para consolidar evidencia.

### 2026-08-07 - Hito AWS RDS cerrado y mergeado a main

Contexto:

- El PR `#2` quedo aprobado despues de cerrar la validacion manual en Amazon RDS, dejar la CI verde y confirmar que no quedaron datos ficticios residuales en `tpi-postgres-dev`.

Tareas realizadas:

- Se corrigio la suite E2E de Streamlit para que `AppTest.from_file(...)` use rutas absolutas derivadas de la raiz real del repositorio.
- Se agrego un helper reutilizable en `tests/streamlit_test_utils.py` y una prueba unitaria de regresion para esa resolucion portable.
- Se verifico que la violacion `leads_afp_id_fkey` vista en logs de CI provenia de un test negativo de rollback y no de un defecto real de fixtures o catalogos.
- Se hizo `squash and merge` del PR `#2` hacia `main` con el commit final `976e7860cb4d534ed18a24989704c23f3708124c`.
- Se elimino la rama remota `feat-aws-rds-connection` despues de confirmar el merge.

Resultados:

- `main` contiene la integracion segura con Amazon RDS, el rol `tpi_app`, SSL obligatorio en AWS, el pool reutilizable, el healthcheck, las pruebas y el fix de `StreamlitDuplicateElementKey`.
- Los workflows post-merge en `main` quedaron en verde: `Lint & Format`, `Tests` y `Security Audit`.
- La validacion manual AWS quedo cerrada con estado final consistente: `79 -> 80 -> 79` leads y `0` personas asociadas al RUT ficticio al cierre.

Aprendizajes:

- Los tests E2E de Streamlit no deben depender del directorio actual de ejecucion; la ruta del script debe resolverse desde la raiz del repo.
- Un error de FK en logs de PostgreSQL no implica necesariamente un bug de aplicacion; primero hay que separar si viene de un test negativo esperado o de un flujo real.

Siguiente paso:

- Abrir el siguiente frente funcional sobre una base ya estabilizada: autenticacion/autorizacion, auditoria funcional o despliegue productivo, segun prioridad de negocio.

### 2026-08-07 - Cierre de validacion manual AWS y alineacion documental

Contexto:

- La validacion manual contra Amazon RDS `tpi-postgres-dev` quedo completada con `tpi_app`, SSL y limpieza posterior del dato sintetico.
- El estado final de RDS volvio a `79` leads y `0` personas asociadas al RUT ficticio.

Hallazgos relevantes:

- El esquema `tpi` contiene tablas operativas adicionales relacionadas por FK con `leads` y `personas`, incluyendo `auditoria`, `eventos_lead`, `citas`, `asignaciones`, `campanas_atribucion`, `fichas_diagnosticas` e `ingesta_google_sheets`.
- La UI actual del backoffice no consume esas tablas, pero ya no se debe documentar que el esquema carece de auditoria o eventos.

Alineacion realizada:

- El SQL versionado de `tpi_app` se ajusto al minimo privilegio validado: `CONNECT`, `USAGE`, `SELECT` sobre catalogos y `SELECT/INSERT/UPDATE` sobre `personas`, `leads` y `consentimientos`.
- Se eliminaron del script los grants genericos sobre secuencias y `ALTER DEFAULT PRIVILEGES`, porque el esquema validado no tiene secuencias y esos permisos ampliaban alcance innecesariamente.

Resultado:

- Flujo validado: Streamlit local -> pool psycopg -> SSL -> `tpi_app` -> Amazon RDS PostgreSQL.
- Estado final confirmado en AWS: `79` leads, sin datos ficticios residuales.

### 2026-08-07 - Correccion de bug en busqueda por RUT

Contexto:

- La validacion manual del backoffice contra Amazon RDS `tpi-postgres-dev` quedo correcta para conexion, lectura e insercion usando `tpi_app`.
- Durante esa validacion aparecio un error menor en `Solicitudes Registradas -> Buscar por RUT`.

Problema observado:

- La busqueda encontraba la solicitud correcta.
- El listado y el detalle podian renderizarse.
- Adicionalmente aparecia el mensaje `Error en la Busqueda` con texto generico.

Causa raiz:

- `render_solicitud_table()` reutilizaba el mismo `key` de Streamlit para los botones de detalle en el tab de listado y en el tab de busqueda.
- Si el mismo `id_lead` aparecia en ambos tabs durante el mismo render, Streamlit lanzaba `StreamlitDuplicateElementKey`.

Como se resolvio:

- Se agrego `key_prefix` a `render_solicitud_table()` en `app/components/ui.py`.
- La pagina `app/pages/2_solicitudes_registradas.py` ahora usa namespaces distintos: `listado` y `busqueda`.
- Se agrego una prueba de regresion E2E en `tests/e2e/test_consulta_solicitudes.py`.

Resultado:

- La busqueda ya no muestra el error generico en el escenario reproducido.
- No hubo cambios de arquitectura, permisos ni consultas SQL.
- La cobertura total subio a 83 por ciento en la suite completa posterior al fix.

Pendiente:

- Si se quiere reconfirmar el fix contra `aws-dev`, volver a cargar un entorno con `APP_ENV=aws-dev`, porque el entorno activo al cierre de esta correccion estaba resolviendo `local`.

### 2026-08-07 - Creacion de bitacora viva

Contexto:

- Se detecto la necesidad de dejar una memoria tecnica operativa para continuidad del proyecto.
- El repositorio tiene varias piezas de documentacion, pero no un hilo cronologico consolidado.
- Se definio ademas la regla de mantenimiento: toda actualizacion documental relevante debe reflejarse tambien en esta bitacora.

Tareas realizadas:

- Se creo esta bitacora en `docs/BITACORA.md`.
- Se consolido el estado actual del proyecto, sus piezas criticas y los siguientes pasos.
- Se dejo una estructura repetible para seguir agregando entradas.

Aprendizajes:

- La documentacion existente explica arquitectura, testing y despliegue, pero no reemplaza una bitacora incremental.
- Para continuidad real, el valor no esta solo en el "que", sino en el "por que", el "bloqueo" y el "siguiente paso".

Proximo paso:

- Mantener este archivo actualizado al cierre de cada tarea relevante.

### 2026-08-06 - 2026-08-07 - Conexion segura a PostgreSQL y AWS RDS implementada en codigo

Contexto:

- El proyecto necesitaba soportar local, testing, `aws-dev` y futura produccion sin hardcodear credenciales.
- La base `tpi` ya estaba restaurada en Amazon RDS y habia que dejar el backoffice listo para conectarse de forma segura.

Tareas realizadas:

- Se centralizo la configuracion de BD en `app/config/settings.py`.
- Se definio precedencia de configuracion:
  1. `DATABASE_URL`
  2. Variables `DATABASE_*`
  3. Defaults seguros solo para `APP_ENV=local`
- Se reforzo el pool reutilizable en `app/database/connection.py`.
- Se agrego clasificacion segura de errores de BD en `app/database/errors.py`.
- Se mejoro el healthcheck para validar `SELECT 1`, esquema, tabla `tpi.leads` y usuario efectivo.
- Se sanearon mensajes mostrados por Streamlit para no exponer informacion sensible.
- Se creo `scripts/sql/001_create_tpi_app_role.sql` para el rol de aplicacion `tpi_app`.
- Se documento la operacion en `docs/AWS_RDS_CONNECTION.md`.
- Se agregaron pruebas unitarias e integracion para configuracion, pool, errores y runtime de BD.

Resultados verificados:

- `pytest tests/ -p no:cacheprovider` -> `175 passed`
- Cobertura total -> `82%`
- `ruff check app tests scripts` -> OK
- `black --check app tests scripts` -> OK
- `mypy app --ignore-missing-imports` -> OK
- `bandit -r app -ll` -> OK
- `pip-audit` sobre dependencias del proyecto -> sin vulnerabilidades conocidas

Desafios encontrados:

- Habia documentacion con valores sensibles o demasiado parecidos a secretos reales.
- `pip-audit` detecto vulnerabilidades en los minimos de `pydantic-settings` y `python-dotenv`.
- En Windows, `pip-audit` requirio manejo especial por restricciones del directorio temporal.

Como se resolvio:

- Se reemplazaron ejemplos riesgosos por placeholders seguros en documentacion.
- Se elevaron los minimos de `pydantic-settings` a `2.14.2` y `python-dotenv` a `1.2.2`.
- Se ejecuto `pip-audit` de forma acotada sobre dependencias del proyecto, no sobre todo el entorno compartido.

Decisiones importantes:

- No se introdujo SQLAlchemy como segunda forma de acceso a BD.
- Se mantuvo `UPDATE` en `tpi_app`, pero sin `DELETE`.
- No se agrego RDS Proxy todavia; queda solo documentado para una etapa de mayor concurrencia.

Pendiente inmediato:

- Validacion manual contra `tpi-postgres-dev` usando `tpi_app`.

### 2026-08-07 - Preparacion de validacion manual en AWS RDS

Contexto:

- Se aprobo provisionalmente la implementacion local y se paso a cerrar solo la validacion manual contra Amazon RDS.

Hallazgos:

- El backoffice no usa tablas separadas de auditoria o eventos.
- La pagina de "trazabilidad" consume metricas y listados sobre `tpi.leads`.
- El MVP no tiene una operacion de UI para eliminar o desactivar leads.

Decision tomada:

- Crear el lead ficticio desde Streamlit usando `tpi_app`.
- Eliminarlo manualmente despues con `tpi_admin`.
- Dejar la ausencia de auditoria real registrada como deuda tecnica, sin implementarla en esta tarea.

Bloqueo actual:

- Falta ejecutar operativamente la creacion/habilitacion de `tpi_app` en RDS y luego validar la app contra `tpi-postgres-dev`.

Siguiente paso exacto:

- Abrir `psql` como `tpi_admin`, confirmar owners de tablas/secuencias y luego aplicar los grants para `tpi_app` sin exponer passwords en linea de comandos.

### 2026-08-01 - Validacion MVP1 local documentada

Contexto:

- El MVP1 quedo validado para demostracion local antes del trabajo de AWS.

Estado consolidado:

- Registro de solicitudes funcionando.
- Consulta de solicitudes funcionando.
- Trazabilidad basica funcionando.
- Validadores de RUT, email y telefono operativos.
- Persistencia en PostgreSQL local funcionando.

Documentos de referencia:

- `docs/INFORME_CORRECCION_MVP1.md`
- `docs/MVP1_VALIDACION.md`
- `docs/PROJECT_STATUS.md`

## Aprendizajes Acumulados

- No introducir una segunda estrategia de conexion a BD si `psycopg` + `psycopg_pool` ya cubre el caso.
- En Streamlit, el pool debe vivir fuera del rerun normal o quedar cacheado como recurso.
- Los healthchecks utiles no solo prueban `SELECT 1`; tambien deben probar esquema, tabla critica y usuario efectivo.
- Este repo no tiene migraciones formales; el esquema minimo vivo esta reflejado en `scripts/init_test_database.py`.
- La app hoy no tiene ciclo de vida para "desactivar" leads; si eso pasa a ser requisito, hay que diseniarlo explicitamente.
- La documentacion no debe incluir secretos reales ni placeholders ambiguos que parezcan credenciales activas.

## Desafios Recurrentes y Como Resolverlos

### 1. Confusion entre ambientes

Sintoma:

- La app parece funcionar en local, pero apunta a otra base o a otra combinacion de variables.

Resolucion:

- Revisar `APP_ENV`.
- Revisar precedencia entre `DATABASE_URL` y `DATABASE_*`.
- Ejecutar `python scripts/verify_database_connection.py`.

### 2. Errores de conexion poco accionables

Sintoma:

- El usuario ve solo un fallo generico en Streamlit.

Resolucion:

- Revisar logs del modulo de BD.
- Confirmar si el error es DNS, timeout, credenciales, SSL o pool.
- Ver `app/database/errors.py`.

### 3. Diferencia entre "trazabilidad" y "auditoria"

Sintoma:

- Se asume que la app ya registra eventos o historial de cambios.

Resolucion:

- Aclarar que el esquema si contiene tablas de auditoria/eventos, pero la UI actual no las consume como auditoria funcional.
- Si se necesita auditoria real en el backoffice, planificar la integracion explicita de esas tablas o un flujo nuevo de eventos.

### 4. Limpieza de datos de prueba

Sintoma:

- Se necesita crear un lead sintetico en ambientes compartidos.

Resolucion:

- Crear solo datos ficticios claramente identificables.
- Registrar conteo inicial y final.
- Si la app no soporta eliminacion, limpiar manualmente con rol administrativo y dejar trazabilidad de la accion.

## Deuda Tecnica

- Integrar en el backoffice una auditoria funcional sobre las tablas/eventos existentes o redisenar ese flujo si el modelo actual no alcanza.
- Autenticacion y autorizacion por roles.
- Operacion formal para desactivar o archivar leads.
- Integracion de secretos de produccion con AWS Secrets Manager.
- Uso de `sslmode=verify-full` con CA bundle en produccion.
- Migrar modelos Pydantic desde `Config` class-based a configuracion moderna.

## Proximos Pasos

### Operativos inmediatos

1. Definir la siguiente prioridad despues del cierre AWS: autenticacion, auditoria funcional o despliegue productivo controlado.
2. Si el siguiente paso es despliegue, preparar inyeccion de secretos via entorno o AWS Secrets Manager sin reintroducir credenciales en archivos versionados.
3. Si el siguiente paso es funcional, decidir si la UI debe consumir tablas de `auditoria`/`eventos_lead` existentes o si se requiere otro modelo de trazabilidad.
4. Mantener `scripts/verify_database_connection.py` como smoke test previo a cualquier cambio de ambiente.

### Proximos pasos funcionales

1. Autenticacion del backoffice.
2. Roles y permisos de usuario.
3. Auditoria de eventos.
4. Edicion controlada de solicitudes.
5. Flujo oficial de archivado o baja logica.

## Nice to Have

- Runbook de incidentes operativos.
- Script automatizado para smoke test seguro por ambiente.
- Pagina interna de diagnostico tecnico para administradores.
- Makefile o task runner unico para pruebas, lint y validaciones.
- Dashboard de salud tecnica con pool, latencia y errores de BD.

## Checklist de Retoma

Antes de continuar el proyecto, verificar:

- `.env` local presente y no versionado
- `APP_ENV` correcto
- base objetivo correcta
- `python scripts/verify_database_connection.py`
- `pytest`
- `git status --short`
- lectura de esta bitacora y de `docs/AWS_RDS_CONNECTION.md`

## Plantilla de Nueva Entrada

Usar esta estructura:

```md
### YYYY-MM-DD - Titulo breve

Contexto:

- ...

Tareas realizadas:

- ...

Aprendizajes:

- ...

Desafios:

- ...

Como se resolvio:

- ...

Pendiente:

- ...

Siguiente paso:

- ...
```
