# Changelog

Todos los cambios notables en este proyecto serán documentados en este archivo.

El formato está basado en [Keep a Changelog](https://keepachangelog.com/) y este proyecto adhiere a [Semantic Versioning](https://semver.org/).

---

## [Unreleased]

### 🐛 Corregido

- **Falsos positivos de los indicadores de logs del Harness** (`HARNESS-LOGS-FALSOS-POSITIVOS-CADDY`)
  - Los robots de internet que piden rutas como `/secrets.json` o `/token` dejaban la palabra en el registro de acceso de Caddy y bloqueaban `verified` (indicadores fuertes, que nunca se degradan). En `harness/policies.yaml`, `password`, `cookie`, `secret` y `token` pasan a `"<palabra> -bytes_read"`: `bytes_read` aparece solo en las líneas de acceso de Caddy (validado contra los logs reales de DEV: 1.641 de 1.641, ninguna otra), así que la app y los eventos TLS siguen vigilados. `Authorization -REDACTED`, `Bearer` y `raw_payload` no cambian.
  - Se actualizan la guía del Deployer (`aws-observability`) y las pruebas de `test_log_scan.py`, que fijan los patrones declarados y que los antiguos, sin exclusión, siguen fallando cerrado.
- **Publish de imágenes a ECR fijado en `ubuntu-24.04`** (incidente del release `db51f95`, 2026-10-23)
  - `ubuntu-latest` pasó a `ubuntu-26.04`, donde `docker build` + `docker push` suben a ECR un índice OCI con un manifiesto de atestación. ECR no puede escanear un índice (`UnsupportedImageTypeException`), así que el gate de escaneo vencía sin resultado y el publish fallaba cerrado.
  - `publish-dev-ecr-images.yml` fija todos sus jobs en `ubuntu-24.04`, con una prueba que lo vigila; el runbook documenta el síntoma, la causa y la comprobación del tipo de manifiesto. Para recuperar un publish ya hecho: borrar las dos imagenes del release y relanzar el workflow con el mismo SHA.

### ♻️ Retirado

- **Retirada de Streamlit del runtime y Pillow 13** (SEG-DESACOPLAR-STREAMLIT)
  - Se elimina el código legado de Streamlit: `app/streamlit_app.py`, `app/backoffice_app.py`, `app/pages/`, `app/presentation/`, `app/internal_tools/`, `app/components/ui.py`, `app/auth/guards.py` y `app/runtime.py`, junto con las pruebas que solo los ejercitaban.
  - Los helpers que la web y la API sí usaban se movieron sin reescribirlos a módulos sin Streamlit: `get_public_site_url`/`get_public_simulator_url` a `app/components/urls.py`, `format_currency_clp` a `app/components/formatting.py` y `log_health_status` a `app/database/healthcheck.py`.
  - `streamlit` y sus dependencias exclusivas salen de `requirements/runtime.lock`; `pillow` sube a 13.0.0 (era la dependencia que bloqueaba el bump por `pillow<13` de Streamlit). Se declaran explícitamente `uvicorn`, `Jinja2`, `python-multipart` e `itsdangerous`, que antes llegaban de forma transitiva vía Streamlit.
  - El Dockerfile ya no instala ni configura Streamlit (sin `STREAMLIT_*`, sin `COPY .streamlit`) y su `CMD` por defecto arranca la web con uvicorn en `:8501`; el backoffice del `docker-compose.yml` local hace lo mismo (el compose de despliegue ya usaba uvicorn y no cambia).
  - Se elimina el directorio `.streamlit/` (solo contenía `config.toml`, la configuración de Streamlit para host no local); en el PR de la tarea solo se había quitado el `COPY` del Dockerfile.
  - La excepción de `pip-audit` para los 8 avisos de Pillow 12.3.0 queda cerrada: se eliminan los `--ignore-vuln` de `ci.yml` y `publish-dev-ecr-images.yml`, la prueba `tests/security/test_excepcion_pip_audit_pillow.py` y la sección correspondiente de `docs/SEGURIDAD.md` (que ahora deja constancia del cierre). `pip-audit` vuelve a correr sin excepciones.
  - Nuevo test `tests/unit/test_streamlit_retired.py`: importa `app.web.main` y `app.api.main` con el módulo `streamlit` bloqueado y verifica estáticamente que ningún archivo de `app/` lo importa.
  - La API y la web no cambian de comportamiento (rutas, autorización y respuestas idénticas); el historial de git conserva el código retirado.

### ✅ Agregado

- **Agenda de reuniones del CRM** (CRM-AGENDA-2-CALENDARIO)
  - Módulo propio de agenda (`app/models/agenda.py`, `app/repositories/agenda_repository.py`, `app/services/agenda_service.py`) sobre `tpi.citas` (migración 010): agendar, reagendar, cancelar (con motivo) y marcar realizada o no asistió, con responsable de la asesoría y quién agendó. Cada acción cambia el estado del lead reutilizando `update_lead_status` (misma validación y auditoría) y deja un evento `cita_*` en `tpi.auditoria` (`tabla_afectada = 'tpi.citas'`), todo en la misma transacción.
  - Validación server-side del horario (lunes a viernes 09:00–19:00 de Chile, inicio cada 15 minutos, duración 30/45/60, sin agendar en el pasado) y de la modalidad (Google Meet, Llamada, Presencial), con pruebas de los dos cambios de hora de Chile.
  - Responsable validado contra la base: solo filas activas de `tpi.asesores` con `atiende_reuniones`; el Runner solo elige Socios, el Coordinador se elige a sí mismo o a un Socio, y el Socio elige a un Socio o al Coordinador dueño de la cartera del lead; un Coordinador nunca es responsable de leads ajenos. El formulario solo ofrece las opciones válidas.
  - `GET /agenda` con vista de semana (navegación anterior/siguiente/hoy) y de lista, filtro por responsable, para todos los perfiles autenticados. Un lead fuera del alcance aparece sin nombre, sin id y sin enlace en la respuesta del servidor (el Socio ve todo).
  - Tarjeta «Reunión» en el detalle del lead con la reunión agendada (o la última) y las acciones permitidas al perfil; entrada «Agenda» en el menú superior para todos los perfiles. Si la base falla o faltan las columnas de la migración 010, la agenda muestra un aviso y el resto del CRM sigue funcionando.
  - Matriz de permisos rol × acción × alcance (Runner, Coordinador, Socio, roles de solo lectura y roles heredados) probada en el servidor; el Runner recibe un rechazo real al intentar marcar realizada o no asistió.
  - Documentación de uso en `docs/AGENDA_USO.md`; sin dependencias nuevas.

- **Ampliación de `tpi.citas` y `tpi.asesores` para la agenda de reuniones** (CRM-AGENDA-1-MIGRACION)
  - Migración de clase D `scripts/sql/010_extend_citas_agenda.sql` (y su reversa `010_drop_citas_agenda.sql`): `tpi.citas` gana responsable obligatorio (`id_asesor NOT NULL`), `fecha_hora_fin` (CHECK > `fecha_hora`), quién agendó (`agendada_por_subject`/`agendada_por_nombre`), `nota`, `motivo_cancelacion` y `updated_at`; CHECK de `estado_cita` (`agendada`, `realizada`, `no_asistio`, `cancelada`); un índice único parcial (una reunión agendada por lead) y una restricción `EXCLUDE USING gist` (un responsable no se pisa, requiere `btree_gist`); `tpi.asesores` gana `atiende_reuniones`; `tpi_app` recibe `SELECT, INSERT, UPDATE` sobre `tpi.citas` sin `DELETE`.
  - `scripts/init_test_database.py` crea `tpi.citas` en su forma final y `tpi.asesores.atiende_reuniones` para las pruebas de integración de la agenda.
  - `scripts/dev_usuarios.py` gana `socios` (alta idempotente de CEO/CTO como responsables, rol `socio`) y `marcar-coordinadores` (marca a los Coordinadores por `advisor_id`), ambos plan por defecto y con validación de la migración aplicada.
  - Documentación en `docs/database/` (02, 04 y 08) y pruebas de contrato, unitarias e integración.

- **Documentación del inventario de DEV y herramienta de reinicio de datos**
  - `docs/database/08_DEV_DATA_INVENTORY.md`: procedencia de los datos de DEV, inventario con fecha (2026-10-24), orden de dependencias de las claves foráneas, ubicación de los adjuntos en S3, consultas útiles y el procedimiento de reinicio.
  - `docs/database/02_PHYSICAL_SCHEMA.md` y `01_ARCHITECTURE.md`: las cinco tablas operativas del pipeline (`campanas_atribucion`, `eventos_lead`, `citas`, `fichas_diagnosticas`, `ingesta_google_sheets`) y el mapa de relaciones.
  - `scripts/dev_reset_leads.py` (solo para el humano, solo contra DEV por el túnel, con `tpi_admin`): `--inspeccionar` (solo lectura), simulación por defecto y `--ejecutar` con frase de confirmación; borra los leads sintéticos con sus tablas dependientes y los adjuntos de S3 y siembra 100 leads ficticios completos en los 12 estados (50 hombres de 62 a 68 años y 50 mujeres de 57 a 63, con género, estado civil y AFP de los catálogos, consentimiento, atribución de campaña, evento e ingesta). Pruebas en `tests/unit/test_dev_reset_leads.py`.

- **Revisión previa a producción de los adjuntos de notas** (CRM-ADJUNTOS-REVISION-PREPROD)
  - Informe `docs/ADJUNTOS_REVISION_PREPROD.md` con los seis puntos abiertos (archivos incrustados, visibilidad, EXIF/GPS,
    retención y borrado, costo de GuardDuty y streams comprimidos): cómo funciona hoy con referencias al código, riesgo,
    opciones, recomendación propuesta y la pregunta para el humano. No decide nada ni cambia el comportamiento.
  - Script de solo lectura `scripts/adjuntos_revision_preprod.py`: mide el uso real en `tpi.auditoria` con agregados (sin
    PII, sin SHA-256 y sin identificadores) usando la conexión de la aplicación.
  - Pruebas de caracterización que fijan los límites conocidos sin cambiarlos (`tests/unit/test_attachments_known_limitations.py`)
    y pruebas del script (`tests/unit/test_adjuntos_revision_preprod.py`).

- **Ajustes de los adjuntos: rechazos por causa, estados de escaneo y borrado visible** (CRM-ADJUNTOS-3-AJUSTES)
  - Los rechazos de subida ahora dicen el motivo concreto de cada archivo, con su posición («Archivo 2 de 3») y sin repetir su nombre ni su contenido; se validan todos los archivos y se informan todos los fallos juntos, y sigue siendo todo o nada (si falla uno no se sube ninguno). El código `unsafe_pdf` se divide por causa: `pdf_encrypted`, `pdf_javascript`, `pdf_launch` y `pdf_embedded_files`, y cada rechazo se audita con su código específico. Para PDF cifrado o con scripts el mensaje sugiere volver a guardarlo con «Imprimir y Guardar como PDF».
  - Las reglas de PDF respetan dónde termina cada nombre (espacio, delimitador de PDF o fin de datos, tras decodificar los escapes `#xx`): `/JS`, `/JavaScript`, `/Launch` y `/Encrypt` siguen rechazando, pero `/JSON` o `/EmbeddedFiles` ya no se confunden con ellos.
  - Los PDF con archivos incrustados se permiten (decisión del humano, opción B) con condiciones: JavaScript, `/Launch` y los cifrados se siguen rechazando; el dato `archivos_incrustados` queda en la auditoría; la marca `[adjunto:pdfe:<uuid>]` distingue estos PDF y la nota muestra «Contiene archivos incrustados: ábrelo en el navegador»; el ajuste `ATTACHMENTS_ALLOW_PDF_EMBEDDED_FILES` (verdadero por defecto) permite volver al rechazo.
  - El borrado de un adjunto reemplaza su marca en `tpi.leads.comentarios` por `[adjunto-eliminado:<tipo>:<uuid>]` con un UPDATE parametrizado acotado al lead (el objeto de S3 se borra primero; si ese borrado falla, la nota no se toca). La nota muestra «Archivo eliminado» sin imagen ni enlaces, también para los PDF.
  - La página del lead lee la etiqueta `GuardDutyMalwareScanStatus` (solo lectura, `s3:GetObjectTagging`) de los adjuntos de los últimos 30 minutos y muestra «Escaneando», «Bloqueado: se detectó una amenaza», «Bloqueado: no se pudo escanear» o «No disponible»; tope de 20 consultas por página y las notas más antiguas no consultan S3.
  - `GET /leads/{id}/adjuntos/{uuid}` responde con una página HTML sencilla y escapada (404, `X-Content-Type-Options: nosniff`, `Cache-Control: no-store`) cuando el objeto no está disponible, idéntica para un lead no visible, un uuid sin marca y un objeto no disponible.

- **Adjuntos en las notas de seguimiento del lead** (CRM-ADJUNTOS-2-CODIGO)
  - El detalle del lead permite adjuntar imágenes (PNG y JPEG) y PDF a una nota de seguimiento: subida multipart en `POST /leads/{id}/comments`, vista en línea y descarga en `GET /leads/{id}/adjuntos/{uuid}` y borrado en `POST /leads/{id}/adjuntos/{uuid}/eliminar` (solo `ceo`/`cto`).
  - Validación por contenido en `app/attachments/validation.py`: el tipo lo decide el contenido (firma PNG/JPEG o `%PDF-`), nunca la extensión ni el `Content-Type` declarado; se leen solo las dimensiones de los encabezados sin decodificar píxeles (tope de 50 millones de píxeles) y se rechazan SVG, HTML, GIF, TIFF, WebP, ejecutables y PDF con `/JS`, `/JavaScript`, `/Launch`, `/EmbeddedFile` o `/Encrypt` (incluidos los escapes `#xx` de los nombres).
  - Almacenamiento privado en S3 detrás de una interfaz inyectable (`app/attachments/storage.py`, patrón de `app/notifications/sns.py`): clave `leads/<id_lead>/<uuid>` generada por el servidor, metadatos con tipo/tamaño/SHA-256/sujeto/fecha (nunca el nombre original) y sin etiquetas de la app; un 403 o un `NoSuchKey` de S3 se tratan igual («adjunto no disponible»).
  - Sin tabla nueva: la relación nota-adjunto es la marca `[adjunto:<tipo>:<uuid>]` en `tpi.leads.comentarios`, agregada solo por el servidor; las marcas se quitan del texto mostrado y de la exportación XLSX, y el texto del usuario que las imite se neutraliza.
  - Cada subida, rechazo, vista, descarga y borrado audita en `tpi.auditoria` (`acciones` `adjunto_subido`, `adjunto_rechazado`, `adjunto_visto`, `adjunto_descargado` y `adjunto_eliminado`; `tabla_afectada` = `tpi.leads`), sin nombres de archivo ni contenido.
  - Configuración fail-closed: `ATTACHMENTS_ENABLED` (falso por defecto), `ATTACHMENTS_BUCKET` (obligatorio si se enciende) y `ATTACHMENTS_S3_REGION`; el compose de despliegue enciende la función solo en el backoffice con valores literales, y localmente queda apagada.

- **Línea de tiempo del lead: simulaciones generadas** (SIM-HISTORIAL-LINEA-TIEMPO)
  - Nueva vista de solo lectura `tpi.v_historial_simulaciones` (migración `009`, `change_class D`) sobre `tpi.auditoria` filtrada por `accion = 'simulacion_renta_vitalicia'`, que expone la evidencia completa de cada simulación (ejecutivo, escenario, versión del modelo, código de verificación, las entradas completas —causante y beneficiarios con sus fechas de nacimiento, invalidez y relación— y el resultado completo), sin censurar ningún dato registrado (decisión del humano, 2026-10-19). `security_barrier`, `REVOKE ALL FROM PUBLIC` y `GRANT SELECT` solo a `tpi_app`; sin `SELECT` directo sobre `tpi.auditoria`. Rollback idempotente en `scripts/sql/009_drop_historial_simulaciones.sql`.
  - El detalle del lead muestra cada simulación en la línea de tiempo (junto a asignaciones, cambios de estado y notas), ordenadas por fecha, con un resumen «Simulación generada» (ejecutivo, escenario, pensión mensual en UF y código) y un detalle desplegable con todas las entradas y el resultado. La aplicación lee **solo** la vista, nunca `tpi.auditoria`.
  - La visibilidad sigue las reglas vigentes del detalle del lead (un `advisor` solo ve leads de su cartera; 404 si no es visible).

- **Tablas de mortalidad del simulador reproducibles desde el repositorio** (`scripts/tablas_mortalidad/`)
  - Se incorporan el Excel de la CMF del que salen las tablas (sin editar, con `procedencia.json`: fuente, norma, fecha, tamaño y `sha256`) y el script que construye `app/simulador_pension/datos/tablas_mortalidad.npz`, con validación de encabezados y modo `--verificar`.
  - El `.npz` que ya usaba el motor se reconstruye idéntico desde el Excel; no cambia ningún valor ni la versión del modelo.
  - Prueba nueva `tests/unit/test_tablas_mortalidad.py`: el CI falla si el Excel, `procedencia.json` y el `.npz` dejan de ser coherentes.
  - Documentado en `docs/SIMULADOR_USO.md` (§8.2) y en `scripts/tablas_mortalidad/README.md`.

- **Documento de uso y mantención del simulador** (`docs/SIMULADOR_USO.md`)
  - Casos soportados y fuera de alcance, rangos de entrada, qué entrega el PDF y la precisión medida.
  - Qué hay que hacer para mantener el simulador vigente: tablas de mortalidad (origen, procedimiento de actualización), constantes empíricas y legales, tasa de venta, ventana de fechas y campaña canaria.
  - Solo documentación: sin cambios de código, base de datos ni despliegue.

- **Simulador: asistente de 3 pasos con la marca de TPI** (SIM-WIZARD-3-PASOS)
  - La pantalla del simulador (`/leads/{id}/simulador`) se rehace como un asistente de 3 pasos: 1 «Datos de la simulación», 2 «Grupo familiar» y 3 «Resultado», con un indicador de pasos conectados por una línea; los pasos completados muestran un lápiz y permiten volver conservando lo ingresado.
  - Paso 1: fecha de simulación de solo lectura (fecha actual de `America/Santiago` calculada en el servidor), tipo de pensión («Vejez edad»), tasa de venta, meses garantizados, años de período diferido, meses y % de aumento temporal, saldo en UF y valor UF opcional, con los rangos validados de la V1. «Continuar» valida este paso en el servidor y muestra los errores en el mismo paso.
  - Paso 2: el causante (el lead) aparece como primera fila sin editarse ni eliminarse; el cónyuge y hasta 4 hijos se agregan, editan y eliminan con un modal (parentesco, tipo de relación con padre/madre solo para hijos, sexo, condición de invalidez, fecha de nacimiento y edad calculada). Se respetan las reglas de la V1 (un cónyuge, máximo 4 hijos, cónyuge inválido rechazado).
  - Paso 3: tarjetas de Monto pensión, Saldo total y Tasa de venta (más Renta temporal y Meses de diferimiento en renta temporal), resumen de la simulación, grupo familiar y el aviso «Valores referenciales, no vinculantes». «Simular» calcula el resultado en pantalla **sin persistir ni auditar**; «Descargar PDF» genera el PDF en memoria y registra el evento de auditoría (como hasta ahora).
  - Marca de TPI: logo oficial (topbar compartido), paleta del CRM y azul marino `#0f243e` de la ficha (paso activo y cabecera del modal). Sin logos, nombres ni el naranja del simulador de referencia; sin librerías ni CDN nuevos (JavaScript propio en `app/web/static/js/simulador_wizard.js`).
  - El motor, la autorización (403 fuera de executive/ceo/cto), la validación, el cálculo y el escape del PDF no cambian. La relación RVD/RT queda oculta en 100 (el asistente replica la estructura del simulador de referencia, que no la expone; el motor y la API siguen aceptando 50/51–99).

- **Simulador de renta vitalicia en el CRM (perfil ejecutivo)** (SIM-RV-V1)
  - Motor puro `app/simulador_pension` que reproduce el simulador de referencia dentro de ±1 UF (435/435 casos del fixture).
  - Panel y formulario en el detalle del lead, visible solo para `executive` y superusuarios `ceo`/`cto` (403 real para el resto).
  - PDF efímero en memoria con escape de marcado, sin RUT, correo ni teléfono del lead.
  - Evento funcional append-only en `tpi.auditoria` sin PII (`app/services/simulador_auditoria.py`).
  - Dependencia nueva: `reportlab==5.0.1`.

- **Evidencia de entradas y resultado del simulador** (SIM-EVIDENCIA-ENTRADAS)
  - El evento append-only de la generación del PDF (`tpi.auditoria.detalle`, acción `simulacion_renta_vitalicia`) pasa a ser un detalle versionado (`schema_version`) que guarda, además de los metadatos funcionales (ejecutivo, escenario, versión del modelo y código de verificación), las entradas de la simulación (causante, saldo, tasa, garantía, aumento, diferimiento, relación RVD/RT, valor UF y beneficiarios: cónyuge e hijos) y el resultado (pensión y, en renta temporal, renta temporal y meses de diferimiento).
  - El detalle es de solo escritura (la aplicación no lo lee), no altera el lead y no contiene nombres, RUT, correo ni teléfono; la retención es indefinida (decisión del humano, 2026-10-19), sin purga ni expiración, y queda pendiente su revisión normativa.
  - Las entradas guardadas bastan para reproducir el resultado y el código de verificación.

### 🔒 Seguridad

- **Excepción acotada de `pip-audit` para 8 avisos de `pillow` 12.3.0** (corregidos solo en Pillow 13.0.0; `streamlit` exige `pillow<13`)
  - Ignorados por ID en `ci.yml` y `publish-dev-ecr-images.yml`, con vencimiento 2026-11-20 y condición de salida documentada en `docs/SEGURIDAD.md`. Motivo: la aplicación no recibe archivos de usuarios.
  - Prueba `tests/security/test_excepcion_pip_audit_pillow.py`: el CI falla si los workflows difieren de los 8 IDs, si aparece código que reciba archivos de usuarios, si cambia la versión de Pillow o si vence la fecha.

- **`certifi` 2026.7.22 → 2026.10.19** (`requirements/runtime.lock`): corrige GHSA-6q48-6c7w-9gw2, que `pip-audit` empezó a reportar el 2026-10-20 y hacía fallar el `Security Audit` de cualquier PR. Dependencia transitiva de ejecución; sin cambios de código.

### 🔄 Cambiado

- **Armonía visual del CRM aplicada desde la referencia aprobada** (CRM-UI-1-ARMONIA-VISUAL)
  - Se reproduce en `app/web/` la referencia aprobada por el humano (`docs/ui/referencia/ui1/`): un solo estilo de botones, campos, tarjetas y chips de estado; iconos de sol/luna (tema), cerrar sesión y exportar XLSX; logo más grande; y los textos que el humano pidió retirar (la bajada de la lista de leads, la bajada técnica del dashboard y el aviso de la migración 008 del detalle del lead).
  - Tipografía **Plus Jakarta Sans alojada en el propio sitio** (`app/web/static/fonts/PlusJakartaSans-latin.woff2` + `OFL.txt`), con `@font-face { font-display: swap; }` y sin pedidos a `fonts.googleapis.com` ni `fonts.gstatic.com`.
  - El listado de leads muestra la columna **Edad** (años cumplidos, calculada en la consulta) en lugar del RUT; la búsqueda por RUT sigue funcionando y el detalle conserva el RUT completo para quien puede verlo. El enmascarado de RUT, correo y teléfono no cambia.
  - El botón de tema es un icono accesible con `aria-label`, `title` y `aria-pressed`; el chip de ambiente solo aparece en la barra superior. Sin cambios de rutas, permisos, HTMX, CSRF ni consultas (salvo la edad); la exportación XLSX conserva exactamente sus columnas permitidas.

- **Publish a ECR: esperar el escaneo hasta 20 minutos y fallar con mensajes claros** (H3.2-ECR-SCAN-WAIT)
  - El paso de escaneo de `publish-dev-ecr-images.yml` espera hasta `SCAN_TIMEOUT_MINUTES=20` minutos (sondeo cada `SCAN_POLL_SECONDS=15` s) a que ambas imagenes (`tpi-dev-app` y `tpi-dev-caddy`) tengan el escaneo `COMPLETE`, con gate fail-closed: `CRITICAL=0` y `HIGH=0` en ambas imagenes; `IN_PROGRESS` nunca cuenta como exito y los tags siguen siendo inmutables.
  - Los fallos se distinguen con mensajes propios: (a) el escaneo no termino en el plazo, aclarando que NO hay hallazgos verificados, con los digests y el procedimiento de recuperacion; (b) termino en `FAILED` o `UNSUPPORTED_IMAGE`; (c) hay hallazgos HIGH/CRITICAL, con el detalle como hasta ahora.
  - La logica de espera se extrae a `scripts/release/wait_for_ecr_scan.py` (CLI de AWS inyectable para pruebas). Sin cambios de permisos IAM/OIDC ni de la politica de tags ni de la publicacion de imagenes.
  - Recuperacion cuando el publish falla por el escaneo: revisar el estado del escaneo de ambos digests, borrar las dos imagenes del release (los tags son inmutables, lo hace el humano) y relanzar el workflow con el mismo SHA; documentada en `docs/DEV_EB_DEPLOYMENT_RUNBOOK.md`.
  - Pruebas nuevas `tests/unit/test_ecr_scan_wait.py` y `tests/security/test_ecr_scan_wait_workflow.py`.

- **Lifecycle de ECR compatible con rollback: conservar 100 imágenes** (H3.2-ECR-LIFECYCLE)
  - La política de lifecycle de ECR de AWS DEV (`deployment/ecr/lifecycle-policy.json`) pasa la regla de retención de `imageCountMoreThan: 20` a `imageCountMoreThan: 100`, para que el LKG y los candidatos de rollback no se expiren al acumularse publicaciones. La regla 1 (capas sin etiqueta a los 7 días) no cambia.
  - Nuevo test sin AWS (`tests/unit/test_ecr_lifecycle_policy.py`) que lee la política y rompe CI si no hay reglas, hay prioridades repetidas, una regla expira por antigüedad imágenes con etiqueta o el conteo de retención baja de 100.
  - Nuevo `docs/ECR_LIFECYCLE_POLICY.md` con el procedimiento de aplicación (put/get-lifecycle-policy y vista previa), verificación, reversa y las comprobaciones de digests del LKG que se mantienen. La aplicación en AWS DEV la ejecuta el humano.

- **Ventana de validación abierta con aviso de valores referenciales** (SIM-RV-V1-VENTANA)
  - Por decisión del humano (2026-10-14) la ventana validada del simulador queda abierta: se eliminan el estado «bloqueado», el corte de 90 días y el 422 por vencimiento, y la simulación se genera para cualquier fecha de simulación (la fecha actual de `America/Santiago`).
  - El formulario muestra siempre un aviso de que los resultados son valores referenciales (no vinculantes) y el PDF lo indica de forma explícita en la sección «Supuestos y advertencias»; desaparece el aviso condicional de ventana de validación vencida en pantalla y en el PDF.
  - El motor `app/simulador_pension/**` no cambia: conserva `VENTANA_VALIDADA` y su `warnings.warn` informativo (no llega a pantalla ni al PDF).

- **Ajustes de uso del CRM y del simulador** (SIM-UX-AJUSTES)
  - Los errores de validación del formulario del simulador (p. ej. edad fuera de rango) se muestran en la misma pantalla, en un aviso arriba del formulario, conservando lo ingresado, con HTTP 422 y mensaje claro en español; ya no se responde con una pantalla de texto aparte.
  - En el detalle del lead se elimina el botón antiguo «Abrir simulación» y queda solo «Abrir simulador» del panel nuevo (visible para `executive`, `ceo` y `cto`).
  - Cabecera del CRM: «Volver al sitio» pasa a «Home» y «Salir» pasa a «Cerrar sesión».
  - El CRM deja de llamarse «CRM Lite»: ahora se muestra «CRM» en títulos de página, cabecera, insignia, kickers, login y la app Streamlit.

- **Ficha PDF «Estudio de pensión»** (SIM-FICHA-PDF)
  - El PDF del simulador pasa a carta apaisada (792 × 612 pt) con el formato de la ficha «Estudio de pensión» de TPI: banda azul marino `#0f243e` con tratamiento y nombre del cliente, título «ESTUDIO DE PENSIÓN» y fecha; fila de datos (fecha de nacimiento, cónyuge, tasa de venta y valor UF); tablas de «OPCIÓN I» (Renta Vitalicia Inmediata + Rescate Total) y «OPCIÓN II» (Aumento Temporal de Pensión + Inflación Futura 4% + Rescate Total) cuando hay aumento temporal; pie con el nombre del ejecutivo y el contacto corporativo en texto plano; y banda inferior azul marino con el logo oficial (`official-logo-on-dark.png`).
  - Cálculos derivados verificados con datos sintéticos: Rescate Total = pensión × meses garantizados; `$` Valor Actual = pensión × valor UF; Valor Futuro = Valor Actual × 1,04^años del aumento; Rescate Total de la Opción II = pensión aumentada × meses del aumento + pensión base × (meses garantizados − meses del aumento).
  - Se conservan la leyenda «Estimación referencial no vinculante», la versión del modelo, el código de verificación, el escape de marcado, los metadatos genéricos sin PII y la ausencia de RUT, correo y teléfono del lead; la renta temporal con RVD conserva su sección con la nueva apariencia.

### 🔧 Corregido

- **Línea de tiempo del lead: no fallar con simulaciones registradas antes de guardar sus entradas** (SIM-HISTORIAL-EVENTOS-ANTIGUOS)
  - Las simulaciones registradas antes de `SIM-EVIDENCIA-ENTRADAS` (2026-10-16) solo conservan el escenario, la versión del modelo y el código de verificación (la vista devuelve `entradas` y `resultado` en `NULL`). El detalle del lead dejaba de renderizar con un 500 porque la plantilla encadenaba atributos de la evidencia (`item.entradas.causante.sexo`) sobre un valor indefinido.
  - La presentación (`app/web/presentation.py`) ahora normaliza las entradas y el resultado a una forma segura (cada campo con clave fija y fallback `None`) y marca los eventos antiguos con `es_legacy`. La plantilla muestra para ellos «Simulación generada» con ejecutivo, escenario, versión del modelo y código, más la nota «Registro anterior al guardado de entradas: solo se conservan escenario, version y codigo», sin detalle desplegable de entradas.
  - La presentación y la plantilla toleran cualquier dato faltante o nulo de la evidencia (entradas o resultado ausentes, causante ausente, beneficiarios vacíos, beneficiarios con campos faltantes y fechas nulas) sin producir un 500; los eventos con evidencia completa se muestran como hasta ahora (entradas, causante, beneficiarios y resultado).

---

## [0.2.0] - 2026-10-12

### ✅ Agregado

- **Logo oficial de CRM Lite** (#64)
  - Reemplaza el logo temporal por el logo oficial de Tu Pensión Inteligente.
  - Se renderiza en la cabecera y en la pantalla de acceso de CRM Lite.
  - Servido como recurso estático local (`app/web/static/img/official-logo-on-light.png` y `app/web/static/img/official-logo-on-dark.png`), sin cargas desde orígenes externos.
  - Variante para tema oscuro (`official-logo-on-dark.png`) seleccionada vía CSS.
  - Texto alternativo accesible en ambas instancias.

### 🔒 Seguridad

- **Mitigación de CVE-2026-85091 (zlib)** (#65)
  - Se fija `zlib=1.3.2-r1` en la imagen de la aplicación (`Dockerfile`).
  - Se actualiza `zlib` en la imagen de Caddy (`deployment/caddy/Dockerfile`).
  - Se actualizan los contratos de supply chain y el test de imagen de la aplicación.

## [0.1.0] - 2026-07-31

### ✅ Agregado

- **Validación Completa MVP1**
  - Validación de conexión a PostgreSQL
  - Validación de catálogos (género, estado civil, AFP)
  - Flujo completo de registro (persona → lead → consentimientos)
  - Documentación de validación detallada

- **Documentación Actualizada**
  - README.md mejorado con estado de validación
  - Nuevo documento: [docs/MVP1_VALIDACION.md](docs/MVP1_VALIDACION.md)
  - Nuevo documento: [docs/PROJECT_STATUS.md](docs/PROJECT_STATUS.md)
  - Nuevo documento: CHANGELOG.md (este archivo)

- **Herramientas de Validación**
  - Script: `test_connection.py` - Validar conexión a BD
  - Script: `test_solicitud_flow.py` - Validar flujo de registro
  - Script: `explore_schema.py` - Explorar estructura de tablas
  - Script: `generar_informe.py` - Generar reporte de validación
  - Script: `check_postgres.py` - Verificar usuarios de BD
  - Script: `check_streamlit.py` - Verificar importación de Streamlit
  - Script: `list_tables.py` - Listar tablas del esquema

- **GitHub Actions CI/CD**
  - Workflow `.github/workflows/ci.yml` para:
    - Linting (ruff, black)
    - Type checking (mypy)
    - Pruebas unitarias
    - Cobertura de código
    - Auditoría de seguridad

### 🔧 Corregido

- **Problema 1:** Credenciales incorrectas en `.env`
  - Usuario `tpi_app` no existe
  - Solución: Usar usuario `postgres` con contraseña correcta

- **Problema 2:** Módulo `psycopg.pool` no disponible
  - psycopg v3 separó pool en paquete independiente
  - Solución: Instalar `psycopg-pool` y actualizar imports

- **Problema 3:** URL de conexión con prefijo SQLAlchemy
  - `ConnectionPool` requiere formato `postgresql://` no `postgresql+psycopg://`
  - Solución: Actualizar `get_database_url()` en `app/config/settings.py`

- **Problema 4:** Parámetro `row_factory` inválido en constructor
  - `psycopg_pool.ConnectionPool` no acepta `row_factory` en constructor
  - Solución: Aplicar `row_factory` en `get_connection()` después de obtener conexión

- **Problema 5:** Columnas faltantes en INSERT de `leads`
  - Query no incluía columnas requeridas: `fecha_ingreso`, `origen_lead`, `fuente_actual`
  - Solución: Agregar columnas y parámetros correspondientes

- **Problema 6:** Columna `id_persona` faltante en INSERT de `consentimientos`
  - Tabla requiere `id_persona` pero no se insertaba
  - Solución: Incluir `id_persona` en parámetros de INSERT

### 📋 Cambios

- Actualizar archivo `.env` con credenciales correctas
- Actualizar `app/config/settings.py` para URL de conexión correcta
- Actualizar `app/database/connection.py` para psycopg_pool compatible
- Actualizar `app/repositories/solicitud_repository.py` con INSERT correcto
- README.md completamente reescrito con información de validación
- Agregar documentación de seguridad en SECURITY.md

### 📚 Documentación

- [x] Documento de validación MVP1 completo
- [x] Estado del proyecto documentado
- [x] Roadmap detallado
- [x] Métricas y cobertura
- [x] Pasos siguiente claros

---

## [0.0.1] - 2026-07-30 (Initial Release - Anterior a esta validación)

### ✅ Agregado

- Estructura base Streamlit con 3 páginas
- Conexión a PostgreSQL con pool
- Modelo de datos completo
- Validadores (RUT, email, teléfono)
- Catálogos dinámicos
- Suite de pruebas unitarias
- GitHub Actions workflow
- Documentación arquitectura
- Docker y docker-compose
- License MIT
- Contributing guide
- Security policy

### 📋 Conocidos

- Sin autenticación (es MVP)
- Sin rate limiting (es MVP)
- Validadores secundarios necesitan revisión

---

## Cómo Contribuir

Para contribuir cambios a este changelog:

1. Crea una rama: `git checkout -b feature/description`
2. Haz tus cambios
3. Actualiza este CHANGELOG.md con:
   - Sección `[Unreleased]` si aún no existe
   - Categorías: Added, Changed, Deprecated, Removed, Fixed, Security
4. Commit con mensaje descriptivo
5. Push y abre Pull Request

---

## Versionado

Este proyecto sigue [Semantic Versioning](https://semver.org/):

- MAJOR: Cambios incompatibles
- MINOR: Funcionalidades nuevas compatibles
- PATCH: Correcciones de bugs

**Versión Actual:** 0.2.0  
**Próxima Versión:** 0.3.0 (por definir)

---

## Histórico de Versiones

| Versión | Fecha | Estado | Hito |
|---------|-------|--------|------|
| 0.2.0 | 12 Oct 2026 | 🚀 RELEASE DEV | Logo oficial de CRM Lite + mitigación zlib |
| 0.1.0 | 31 Jul 2026 | ✅ VALIDADO | MVP1 Completado |
| 0.0.1 | 30 Jul 2026 | ✅ INICIAL | Estructura Base |

---

**Última actualización:** 12 Octubre 2026  
**Responsable:** Equipo TPI Back-office  
**Contacto:** dev@tupensioninteligente.cl
