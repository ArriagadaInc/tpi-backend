# Adjuntos de notas: revisión previa a producción

**Qué es este informe.** Prepara la decisión del humano sobre los seis puntos que se aceptaron el
2026-10-21 para los adjuntos de las notas del lead, antes de llevarlos a producción. Describe **cómo
funciona el código hoy** (comprobado leyendo el repositorio, no de memoria), el riesgo concreto, las
opciones con su esfuerzo y costo, una recomendación y la pregunta exacta que debe decidir el humano.

**Qué NO es.** No decide por el humano, no cambia el comportamiento de la aplicación, no da opinión
jurídica y no inventa cifras, tarifas ni plazos. Todo hecho externo que no esté en el repositorio o en
su documentación local queda marcado como **«a confirmar»** y dice quién debe confirmarlo.

**Cómo se leyó el código.** Las referencias a archivos y funciones son las reales al commit de
`origin/main` de esta tarea. Los seis puntos vienen de `docs/ADJUNTOS_COMENTARIOS_DISENO.md` (secciones
5, 6 y 8) y de `docs/SEGURIDAD.md` (sección «Adjuntos de notas»).

## Resumen

| # | Punto | Riesgo | Recomendación (una línea) | Quién decide |
|---|-------|--------|---------------------------|--------------|
| 1 | PDF con archivos incrustados | Medio | Mantenerlos permitidos hoy, pero dejar documentado el ajuste para volver al rechazo y revisarlo de nuevo cuando haya uso real. | Humano (producto/seguridad) |
| 2 | Visibilidad de los adjuntos para todo usuario con acceso al lead | Alto | Mantener la visibilidad por ahora, pero agregar el aviso al subir y dejar la re-codificación/enmascarado como tarea futura. | Humano (privacidad) |
| 3 | EXIF y GPS de las imágenes | Medio | Mantener sin re-codificar en esta versión y agendar la eliminación de metadatos para la segunda versión. | Humano (privacidad) |
| 4 | Retención y borrado a solicitud del titular | Alto | Mantener el borrado actual (objeto + marca) y resolver con el asesor legal el plazo y la expiración automática. | Humano + asesor legal |
| 5 | Costo de GuardDuty Malware Protection for S3 | Bajo | Dejar la fórmula del costo y medir el uso real con el script; confirmar tarifas antes de producción. | Humano (presupuesto) |
| 6 | Validación de PDF con streams comprimidos | Medio | Mantener la validación actual (no descomprime streams) y apoyarse en GuardDuty y el visor; documentar como límite conocido. | Humano (seguridad) |

Los niveles de riesgo son una **valoración del autor de este informe** para ordenar la lectura; no son
un hecho medido.

---

## 1. PDF con archivos incrustados

### (a) Cómo funciona HOY

Un PDF con el nombre exacto `/EmbeddedFile` se **acepta** y se marca como `pdfe` cuando
`ATTACHMENTS_ALLOW_PDF_EMBEDDED_FILES` es verdadero (es el valor por defecto). Con ese ajuste en falso,
se rechaza con el código `pdf_embedded_files`.

Referencias reales:

- `app/attachments/validation.py` — `validate_attachment_content` llama a `_pdf_has_embedded_files`
  (`allow_embedded_files=allow_pdf_embedded_files`); si encuentra `/EmbeddedFile` y está permitido,
  devuelve `True` y el tipo pasa a `pdfe`.
- `app/attachments/validation.py` — `_pdf_has_embedded_files` rechaza siempre los nombres `/JS`,
  `/JavaScript`, `/Launch` y `/Encrypt` (con sus escapes `#xx` y respetando dónde termina cada nombre);
  `_PDF_EMBEDDED_FILE_NAME = "EmbeddedFile"`.
- `app/config/settings.py` — `attachments_allow_pdf_embedded_files: bool = Field(default=True, alias="ATTACHMENTS_ALLOW_PDF_EMBEDDED_FILES")`.
- `app/web/routes/leads.py` — la subida pasa `allow_pdf_embedded_files=_attachments_allow_pdf_embedded_files(request)`.
- `app/attachments/marks.py` — la marca `[adjunto:pdfe:<uuid>]` distingue estos PDF.
- `app/attachments/audit.py` — la subida guarda en `detalle` el dato `archivos_incrustados` (verdadero
  solo cuando `attachment_type == "pdfe"`).
- La nota muestra «Contiene archivos incrustados: ábrelo en el navegador» (documentado en
  `docs/SEGURIDAD.md` y `docs/ADJUNTOS_COMENTARIOS_DISENO.md`).

Qué NO hace hoy: no descomprime el PDF ni revisa el contenido de cada archivo incrustado como un archivo
independiente. JavaScript, `/Launch` y los cifrados se rechazan siempre, aunque el PDF traiga incrustados.

Prueba que fija este comportamiento (ya existente, no duplicada): `tests/unit/test_attachments_validation.py`
→ `test_pdf_with_embedded_file_is_allowed_by_default_and_marked_pdfe` (aceptado con la marca `pdfe`) y
`test_pdf_with_embedded_file_rejected_when_disallowed` (rechazado con el código `pdf_embedded_files`
cuando `ATTACHMENTS_ALLOW_PDF_EMBEDDED_FILES` es falso).

### (b) Riesgo concreto y peor caso

Un archivo incrustado puede ser un ejecutable, un documento con macros o un HTML. **Para hacer daño,
alguien tiene que abrirlo a mano** desde un lector de escritorio: los visores de PDF de los navegadores
no lo ejecutan solos, y la app sirve el PDF con `Content-Security-Policy: default-src 'none'`.

Peor caso: un usuario sube un PDF con un archivo incrustado que es malware y otro usuario lo descarga y
lo abre con su lector de escritorio. La capa que lo mitiga es GuardDuty (ver punto 5) y que la política
del bucket **no entrega nada que no esté `NO_THREATS_FOUND`**. GuardDuty **no garantiza** revisar el
contenido incrustado como un archivo independiente (riesgo ya documentado en `docs/SEGURIDAD.md`).

### (c) Opciones

- **Opción A — Dejarlo como está.** Permite PDF con incrustados (marca `pdfe`, aviso en la nota, dato en
  auditoría, ajuste para volver al rechazo). Esfuerzo: ninguno. Costo: ninguno directo. Efecto: los
  usuarios pueden adjuntar PDF con incrustados; el riesgo se acepta con las mitigaciones actuales.
- **Opción B — Volver al rechazo.** Poner `ATTACHMENTS_ALLOW_PDF_EMBEDDED_FILES=false`. Esfuerzo:
  cambiar una variable de configuración (el código ya soporta el rechazo). Costo: ninguno directo.
  Efecto: algunos PDF legítimos (p. ej. con documentos adjuntos) dejan de subir y se rechazan con un
  mensaje claro.
- **Opción C — Permitir, pero advertir más.** Mantener A y reforzar el aviso de la nota o el aviso al
  subir. Esfuerzo: pequeño (texto). Costo: ninguno. Efecto: mismo comportamiento, más contexto al usuario.

### (d) Recomendación (propuesta)

Mantener la **Opción A** hoy (ya aceptada el 2026-10-21), con el ajuste `ATTACHMENTS_ALLOW_PDF_EMBEDDED_FILES`
documentado como botón de emergencia, y volver a revisar este punto cuando el script del punto 5 muestre
cuántos PDF con incrustados hay en uso real.

### (e) Pregunta para el humano

¿Se mantiene la decisión de permitir PDF con archivos incrustados (marca `pdfe`) en producción, con el
ajuste `ATTACHMENTS_ALLOW_PDF_EMBEDDED_FILES` listo para volver al rechazo, o se prefiere rechazarlos
desde el primer día?

---

## 2. Visibilidad de los adjuntos para todos los usuarios con acceso al lead

### (a) Cómo funciona HOY

La vista y la descarga de un adjunto aplican **la misma regla de visibilidad que el detalle del lead** y
sirven el archivo **sin enmascarar**.

Referencias reales:

- `app/web/routes/leads.py` — `attachment_view_or_download` llama a `service.get_attachment(...)` y
  devuelve el contenido con `Response(content=stored.content, ...)`.
- `app/services/solicitud_service.py` — `get_attachment` comprueba en orden: usuario autenticado,
  visibilidad del lead (`get_solicitud_detalle_masked`), que la marca de ese `uuid` esté en la nota de
  ese lead, y que el tipo coincida. Si algo falla, devuelve `None` (404 genérico).
- `app/services/solicitud_service.py` — `get_solicitud_detalle_masked`: `ceo`/`cto`
  (`can_view_full_pii`) ven el lead completo; un `advisor` solo ve su propio lead (y con PII completa);
  el resto (`executive`, `operations`, `readonly`, `tester`, `admin`) ve el lead **enmascarado**
  (`rut`, `email`, `telefono`). La máscara se aplica con `mask_row_for_display` en
  `app/security/masking.py`.
- `app/auth/models.py` — `SUPERUSER_ROLES = {"ceo", "cto"}`; `is_superuser`.

Qué significa en la práctica: **un archivo no se puede enmascarar**. Una foto de una cédula la vería
cualquier usuario que tenga acceso al lead, aunque la pantalla le oculte el RUT. Esto ya está aceptado
como riesgo en `docs/SEGURIDAD.md` y en `docs/ADJUNTOS_COMENTARIOS_DISENO.md` (sección 5).

### (b) Riesgo concreto y peor caso

El enmascarado protege los campos de texto, pero no el contenido de una imagen o un PDF. Peor caso: un
asesor o un rol de solo lectura con acceso al lead abre una foto de una cédula adjunta y ve el RUT
completo de una persona, aun cuando la pantalla se lo ocultaría.

### (c) Opciones

- **Opción A — Dejarlo como está.** Esfuerzo: ninguno. Costo: ninguno. Efecto: quien tiene acceso al
  lead ve el archivo completo.
- **Opción B — Re-codificar imágenes en la subida** (quitar EXIF/GPS y, si se quiere, redimensionar o
  eliminar metadatos; no resuelve el texto dentro de la propia imagen). Esfuerzo: medio (procesamiento
  de imágenes con Pillow, ya presente en el proyecto). Costo: CPU/memoria al subir. Efecto: reduce
  metadatos, pero una foto de una cédula sigue mostrando el RUT como imagen.
- **Opción C — Restringir quién ve adjuntos** (p. ej. solo `ceo`/`cto` o el asesor dueño). Esfuerzo:
  pequeño (cambiar la comprobación de visibilidad). Costo: ninguno directo. Efecto: menos personas ven
  los archivos, pero se pierde la utilidad de compartir el adjunto con el equipo que atiende el lead.

### (d) Recomendación (propuesta)

Mantener la **Opción A** por ahora (ya aceptada), asegurar que el aviso visible al subir («no subas
documentos de identidad completos salvo que sea necesario») esté activo, y agendar la re-codificación
(Opción B) como segunda versión. La Opción C es una decisión de producto que conviene tener sobre la
mesa si el riesgo se materializa.

### (e) Pregunta para el humano

¿Se acepta que cualquier usuario con acceso al lead vea el adjunto **sin enmascarar** (sabiendo que una
foto de una cédula muestra el RUT completo), o se quiere restringir la vista/descarga a un subconjunto
de roles desde el primer día?

---

## 3. EXIF y GPS de las imágenes

### (a) Cómo funciona HOY

Las imágenes **no se re-codifican**: se valida la firma y las dimensiones leyendo solo el encabezado, y
los bytes se guardan y se sirven tal cual. Por lo tanto, los metadatos EXIF y la ubicación GPS que
traiga la foto quedan visibles para quien vea el adjunto.

Referencias reales:

- `app/attachments/validation.py` — `_png_dimensions` y `_jpeg_dimensions` leen ancho/alto del
  encabezado sin decodificar píxeles; `validate_attachment_content` devuelve `ValidatedAttachment`
  con `content` igual a los bytes originales (no los modifica).
- `app/attachments/storage.py` — `S3AttachmentStorage.put` sube `body` tal cual.
- `app/web/routes/leads.py` — `attachment_view_or_download` sirve `stored.content` sin re-codificar.

Prueba que fija este comportamiento: `tests/unit/test_attachments_known_limitations.py` →
`test_current_behavior_jpeg_with_exif_gps_is_accepted_and_bytes_preserved` (un JPEG con EXIF que
incluye coordenadas GPS se acepta y sus bytes no se modifican).

### (b) Riesgo concreto y peor caso

Una foto tomada con el teléfono suele traer EXIF con la ubicación GPS. Peor caso: un lead incluye una
foto tomada en el domicilio o el trabajo de una persona; quien vea el adjunto puede extraer esa
ubicación aunque el lead no la declare.

### (c) Opciones

- **Opción A — Dejarlo como está.** Esfuerzo: ninguno. Costo: ninguno. Efecto: los metadatos (incluido
  GPS) quedan visibles.
- **Opción B — Quitar metadatos al subir** (re-codificar/limpiar EXIF con Pillow, ya presente en el
  proyecto). Esfuerzo: medio. Costo: CPU/memoria al subir. Efecto: desaparece el GPS y demás EXIF, pero
  el contenido de la imagen no cambia.

### (d) Recomendación (propuesta)

Mantener la **Opción A** en esta primera versión (ya aceptada) y agendar la **Opción B** (limpieza de
metadatos) como segunda versión.

### (e) Pregunta para el humano

¿Se acepta que las imágenes conserven EXIF y GPS visibles en esta primera versión, o se quiere quitar
los metadatos al subir antes de producción?

---

## 4. Retención y borrado a solicitud del titular

### (a) Cómo funciona HOY (qué hace el sistema)

- **Qué se guarda y dónde.** El archivo vive en un objeto S3 con clave `leads/<id_lead>/<uuid>`; sus
  metadatos (tipo verificado, tamaño, SHA-256, quién subió y cuándo) van en los metadatos del objeto.
  La relación con la nota es una marca `[adjunto:<tipo>:<uuid>]` al final de `tpi.leads.comentarios`.
  El diseño está en `docs/ADJUNTOS_COMENTARIOS_DISENO.md` (sección 3).
- **Cuánto vive.** El adjunto vive mientras exista el lead. **No hay expiración automática** en esta
  versión.
- **Cómo se borra.** `app/services/solicitud_service.py` → `delete_attachment` (solo `ceo`/`cto`):
  (1) borra el objeto de S3 primero; (2) reemplaza la marca exacta por
  `[adjunto-eliminado:<tipo>:<uuid>]` con un UPDATE parametrizado acotado al lead; (3) escribe el
  evento `adjunto_eliminado` en `tpi.auditoria`. Si el borrado de S3 falla, la nota no se toca.
- **Qué queda después del borrado.** El objeto de S3 se elimina (el bucket **no tiene versionado**, así
  que el borrado es real, ver `docs/ADJUNTOS_INFRA_S3.md`). Queda en la nota la marca
  `[adjunto-eliminado:...]`, que se muestra como «Archivo eliminado» sin imagen ni enlaces. Quedan en
  `tpi.auditoria` los eventos previos (`adjunto_subido`, `adjunto_visto`, `adjunto_descargado`,
  `adjunto_eliminado`), que son append-only y **no se borran**: registran quién, qué `uuid`, tipo,
  tamaño y SHA-256, pero **nunca** el contenido ni el nombre del archivo.
- **Copias.** Si alguien descargó o abrió el adjunto antes del borrado, puede quedar una copia local en
  su equipo; el sistema no controla eso. Los logs de la aplicación **no** contienen bytes, texto
  extraído ni nombres de archivo (`docs/SEGURIDAD.md`).
- **Limpieza de leads de prueba en DEV.** `delete_test_lead` borra también los objetos de los adjuntos
  del lead (por las marcas), con mejor esfuerzo.

### (b) Riesgo concreto y peor caso

El sistema borra el objeto, pero la **auditoría append-only conserva el historial** (incluido el
SHA-256 y quién vio/descargó) y una copia descargada puede existir fuera del sistema. Peor caso: un
titular ejerce su derecho de supresión y el objeto se borra, pero la trazabilidad (y una copia local
previa) permanece; si eso no basta para la obligación legal, hay una brecha.

### (c) Opciones

- **Opción A — Dejarlo como está.** Sin expiración automática; borrado a solicitud del objeto + marca +
  evento de auditoría. Esfuerzo: ninguno. Costo: ninguno. Efecto: el historial de auditoría y la marca
  de eliminado permanecen.
- **Opción B — Agregar expiración automática** (borrar adjuntos pasados N días/meses, o al borrar el
  lead). Esfuerzo: medio (un proceso programado o un gancho en la limpieza). Costo: bajo. Efecto:
  reduce la retención, pero requiere decidir el plazo.
- **Opción C — Reducir lo que queda en la auditoría tras el borrado** (p. ej. no guardar SHA-256 o no
  registrar vistas/descargas). Esfuerzo: bajo-medio, pero toca el contrato de auditoría actual. Costo:
  ninguno directo. Efecto: menos trazabilidad disponible; puede afectar la capacidad de investigar.

### (d) Recomendación (propuesta)

Mantener la **Opción A** (borrado a solicitud ya implementado) y **resolver con el asesor legal** el
plazo de retención y si hace falta la **Opción B** (expiración automática). No decidir la Opción C sin
asesoría legal, porque cambia el contrato de auditoría.

### (e) Preguntas para el asesor legal (sin opinión jurídica aquí)

1. ¿El borrado actual (objeto de S3 + marca de eliminado + evento append-only que conserva `uuid`,
   tipo, tamaño, SHA-256 y quién vio/descargó) cumple la obligación de supresión de la Ley 21.719, o
   exige eliminar también esa trazabilidad?
2. ¿Hay un plazo máximo legal de retención que obligue a una expiración automática, o basta con el
   borrado a solicitud del titular?
3. ¿La existencia de copias locales descargadas por usuarios antes del borrado es responsabilidad del
   sistema o se resuelve con avisos y procedimiento interno?

**Pregunta para el humano:** ¿Se acepta la retención actual (vive mientras exista el lead, borrado a
solicitud del titular) a la espera de la respuesta del asesor legal, o se quiere fijar ya un plazo y una
expiración automática?

---

## 5. Costo de GuardDuty Malware Protection for S3

### (a) Cómo funciona HOY

GuardDuty Malware Protection for S3 escanea cada objeto nuevo que se sube al bucket de adjuntos y lo
etiqueta con `GuardDutyMalwareScanStatus`; una política del bucket **deniega `GetObject` si la etiqueta
no es `NO_THREATS_FOUND`**. La app solo lee la etiqueta (con `s3:GetObjectTagging`, solo lectura) para
mostrar «Escaneando» / «Bloqueado» / «No disponible». Referencias: `docs/ADJUNTOS_INFRA_S3.md`,
`docs/ADJUNTOS_COMENTARIOS_DISENO.md` (sección 4) y `app/services/solicitud_service.py` →
`get_attachment_scan_status`.

### (b) Riesgo concreto y peor caso

El riesgo no es de seguridad sino de **costo imprevisto**: GuardDuty Malware Protection for S3 cobra por
objeto y por GB escaneado. Peor caso: un volumen de subidas mayor al esperado produce una factura de
GuardDuty mayor a la prevista.

### (c) Costo (fórmula, a confirmar)

Este informe **no afirma tarifas** (no están en el repositorio). La fórmula del costo mensual es:

```text
costo_mensual = objetos_escaneados_por_mes × tarifa_por_objeto
              + GB_escaneados_por_mes × tarifa_por_GB
```

- `objetos_escaneados_por_mes` y los bytes subidos los mide el script de la sección «Datos de uso»
  (solo subidas; cada objeto nuevo se escanea una vez, según el diseño).
- `tarifa_por_objeto` y `tarifa_por_GB` las debe **confirmar el humano** en la página de precios de AWS
  para `us-east-2`. La documentación local (`docs/ADJUNTOS_COMENTARIOS_DISENO.md`, sección 8) dice que
  «la tarifa por GB está publicada; la de por objeto en `us-east-2` hay que confirmarla» y que el plan
  se creó sin necesitar un detector de GuardDuty activo.

### (d) Opciones

- **Opción A — Dejarlo como está.** GuardDuty activo para todo objeto nuevo. Esfuerzo: ninguno. Costo:
  el de la fórmula. Efecto: máxima protección.
- **Opción B — Restringir el escaneo** (p. ej. solo ciertos tipos o tamaños). Esfuerzo: medio (cambia la
  política/infraestructura). Costo: menor, pero reduce la cobertura del antivirus. **Fuera del alcance
  de esta tarea** (toca infraestructura).

### (e) Pregunta para el humano

¿Se confirman las tarifas de GuardDuty Malware Protection for S3 (`tarifa_por_objeto` y `tarifa_por_GB`
en `us-east-2`) y se acepta el costo estimado con la fórmula y el uso medido por el script, o se quiere
restringir el escaneo?

---

## 6. Limitación de la validación de PDF con streams comprimidos

### (a) Cómo funciona HOY

La validación de PDF busca los tokens prohibidos (`/JS`, `/JavaScript`, `/Launch`, `/Encrypt`) en los
**bytes crudos** del archivo, decodificando los escapes `#xx` de los nombres, pero **no descomprime los
streams** (`FlateDecode`). Por eso, JavaScript que esté dentro de un *object stream* comprimido **no se
ve** y el PDF pasa la validación.

Referencias reales:

- `app/attachments/validation.py` — `_pdf_names` recorre los bytes y extrae nombres; no llama a ningún
  descompresor. `_pdf_has_embedded_files` solo rechaza los tokens que aparecen en crudo.
- `app/attachments/validation.py` — `_pdf_has_embedded_files` sí detecta `/EmbeddedFile` de forma
  fiable, porque va en el diccionario del propio stream, que nunca queda comprimido.

Prueba que fija este comportamiento: `tests/unit/test_attachments_known_limitations.py` →
`test_known_limitation_javascript_inside_flate_object_stream_passes` (un PDF cuyo `/JavaScript` está
dentro de un object stream comprimido con FlateDecode pasa hoy la validación).

### (b) Riesgo concreto y peor caso

Un PDF puede esconder JavaScript dentro de un stream comprimido y pasar la validación de la app. Las
capas siguientes son **GuardDuty** (que escanea el archivo completo) y el **visor del navegador** (que
no ejecuta JavaScript del PDF). Peor caso: un PDF con JavaScript malicioso comprimido pasa la
validación; la mitigación depende de que GuardDuty lo marque y de que el usuario no lo abra en un lector
de escritorio.

### (c) Opciones

- **Opción A — Dejarlo como está.** Esfuerzo: ninguno. Costo: ninguno. Efecto: el límite queda
  documentado y cubierto por GuardDuty y el visor.
- **Opción B — Descomprimir y revisar los streams en la validación.** Esfuerzo: medio-alto (parsear
  object streams y filtros FlateDecode de forma segura, con límites para no inflar memoria). Costo:
  CPU/memoria al subir. Efecto: reduce este hueco, pero agrega complejidad y riesgo de parseo.
- **Opción C — Aceptar solo PDF sin streams comprimidos** (rechazar `FlateDecode` en object streams).
  Esfuerzo: medio. Costo: ninguno directo. Efecto: algunos PDF legítimos (la mayoría usa compresión) se
  rechazarían.

### (d) Recomendación (propuesta)

Mantener la **Opción A** en esta versión, con el límite claramente documentado (este informe y la prueba
de caracterización), y evaluar la **Opción B** como mejora futura si se quiere endurecer sin depender
solo de GuardDuty.

### (e) Pregunta para el humano

¿Se acepta el límite conocido de que la validación no descomprime los streams de los PDF (y por tanto no
ve JavaScript dentro de un object stream comprimido), apoyándose en GuardDuty y en el visor del
navegador, o se quiere endurecer la validación antes de producción?

---

## Datos de uso

> **Sección para pegar la salida del script de medición.** El Developer no tiene acceso a la base de
> datos de DEV ni a AWS, así que esta sección queda vacía a propósito. El humano ejecuta el script
> contra DEV por el túnel y pega aquí la salida (solo agregados, sin PII).

```text
(Pegar aquí la salida de: python scripts/adjuntos_revision_preprod.py --days 30)
```

### Cómo ejecutar el script contra DEV por el túnel

El script es de **solo lectura** (`scripts/adjuntos_revision_preprod.py`): solo consultas `SELECT`
parametrizadas sobre `tpi.auditoria`, sin PII, sin SHA-256 y sin identificadores de leads o personas.
Usa la conexión de la aplicación (`get_db_connection`), sin credenciales nuevas.

1. Abrir el túnel a la base de DEV (el procedimiento SSM que ya usa el proyecto para diagnóstico). **El
   túnel escucha en el puerto local `5433`**, no en `5432`: `5432` es el puerto de RDS al otro lado del
   túnel, y es además el valor por defecto de la aplicación, por eso hay que indicar `5433` expresamente.
2. Con el entorno del proyecto activado (`pip install -e .`), definir las variables de conexión en la
   misma terminal de PowerShell y ejecutar el script (ajusta usuario y base si los tuyos son otros; la
   clave se pide sin mostrarla y no se guarda en ningún archivo):

   ```powershell
   $env:APP_ENV = 'aws-dev'
   $env:DATABASE_HOST = 'localhost'
   $env:DATABASE_NAME = 'tpi'
   $env:DATABASE_USER = 'tpi_app'
   $env:DATABASE_SCHEMA = 'tpi'
   $env:DATABASE_SSLMODE = 'require'
   $clave = Read-Host 'Clave de la base' -AsSecureString
   $env:DATABASE_PASSWORD = [System.Net.NetworkCredential]::new('', $clave).Password
   python scripts/adjuntos_revision_preprod.py --days 30 --port 5433
   ```

   `--port 5433` reemplaza a `DATABASE_PORT`; si prefieres, define `$env:DATABASE_PORT = '5433'` y omite
   la opción. No aplica si usas `DATABASE_URL` (el puerto va dentro de la URL).
3. La ventana es configurable (`--days 30` por defecto). La salida muestra: conteo por acción, rechazos
   por código, subidas con y sin archivos incrustados, subidas por tipo, objetos y bytes subidos por mes,
   y la cantidad de leads distintos con adjuntos y de usuarios distintos que subieron.

Si la conexión falla, el script imprime un mensaje claro, el destino al que intentó conectarse (host,
puerto, base y usuario; nunca la clave) y termina con un código distinto de cero (no toca la base). Si
el destino es `localhost:5432`, agrega la pista de usar el puerto `5433` del túnel.

---

## Referencias

- `docs/ADJUNTOS_COMENTARIOS_DISENO.md` — decisiones y resguardos (secciones 3, 4, 5, 6 y 8).
- `docs/SEGURIDAD.md` — sección «Adjuntos de notas» (qué protege y riesgos aceptados).
- `docs/ADJUNTOS_INFRA_S3.md` — bucket, GuardDuty y política de escaneo.
- `app/attachments/` — `validation.py`, `marks.py`, `storage.py`, `audit.py`.
- `app/services/solicitud_service.py` — orquestación de subida, vista, descarga y borrado.
- `app/web/routes/leads.py` — rutas de subida, vista/descarga y borrado.
- `tests/unit/test_attachments_known_limitations.py` — pruebas que fijan los límites (puntos 3 y 6).
- `scripts/adjuntos_revision_preprod.py` — medición de uso de solo lectura.
