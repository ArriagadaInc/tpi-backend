# Adjuntos en las notas de seguimiento del lead: diseño y resguardos

Estado: **decisiones del humano del 2026-10-21; paso 1 (infraestructura) aplicado y verificado el 2026-10-21; paso 2 (código) implementado**. Este documento fija las decisiones y los
resguardos antes de escribir código. Las tareas que lo implementan están en `tasks/backlog.yaml` (prefijo
`CRM-ADJUNTOS-`). Si una decisión cambia, se cambia aquí primero.

Historial del diseño: la primera versión (PR #107) proponía una tabla `tpi.lead_adjuntos`, una migración y un antivirus
propio, en cuatro pasos. El mismo día se revisó y se simplificó a **dos pasos y sin tabla** (secciones 3 y 7).

## 1. Qué se quiere

Que quien escribe una nota de seguimiento en el detalle de un lead pueda adjuntarle imágenes y PDF, y que los demás
usuarios con acceso a ese lead los vean junto a la nota.

## 2. Decisiones del humano

| # | Decisión | Valor |
|---|---|---|
| 1 | Tipos permitidos | PDF, PNG y JPEG, verificados por su **contenido** (no por la extensión ni por el tipo que declara el cliente). Nada de SVG, HTML, TIFF, GIF, EPS ni PPM. |
| 2 | Límites | 10 MB por archivo, 5 archivos por nota y 25 MB por petición. |
| 3 | Vista | **En línea**: las imágenes se ven dentro del detalle del lead y los PDF se abren en una pestaña nueva con el visor del navegador. También hay descarga. |
| 4 | Retención | El adjunto vive mientras exista el lead. Se borra a solicitud del titular (Ley 21.719), junto con su objeto en S3. Sin expiración automática en la primera versión. |
| 5 | Auditoría | Cada subida, vista o descarga, rechazo y borrado queda en `tpi.auditoria` (append-only). |
| 6 | Quién los ve | **Todos los usuarios que tienen acceso al lead** (un asesor solo ve los de su cartera; quien no ve el lead recibe 404). |
| 7 | Dónde se guardan | **Sin tabla nueva**: el archivo y sus datos viven en S3, el antivirus es GuardDuty Malware Protection for S3 y la nota guarda una marca (sección 3). |
| 8 | Imágenes en la primera versión | **Sin re-codificación**: se valida la firma y las dimensiones leyendo solo el encabezado. EXIF y GPS se conservan (riesgo en la sección 5). |

Supuestos míos, sin objeción del humano: los valores de los puntos 1, 2, 4 y 5 son los propuestos el 2026-10-21 y se
aceptaron al no ser objetados; la primera versión **no guarda el nombre original del archivo** (se muestra solo el tipo,
«Imagen adjunta» o «PDF adjunto»: la página del lead no consulta S3, así que tampoco se muestra el tamaño); el plazo definitivo de retención lo fija el humano (sección 8).

## 3. Cómo se guarda cada cosa (sin tabla)

El código actual impone una restricción: **las notas no son una entidad**. Cada nota se agrega a la columna de texto
`tpi.leads.comentarios` (`TEXT`, máximo 1000 caracteres por nota que valida el servicio, con un encabezado de fecha y autor que otras
consultas interpretan con una expresión regular). No hay tabla de comentarios ni identificador de nota. Por eso:

| Qué | Dónde vive |
|---|---|
| El archivo | Objeto S3 con clave `leads/<id_lead>/<uuid>`; el `uuid` lo genera el servidor |
| Tipo verificado, tamaño, SHA-256, quién lo subió y cuándo | Metadatos del objeto S3 (sin el nombre original) |
| Si pasó el antivirus | Etiqueta `GuardDutyMalwareScanStatus` que pone GuardDuty; una política del bucket **deniega `GetObject` si la etiqueta no es `NO_THREATS_FOUND`** |
| A qué nota pertenece | Una marca que agrega el servidor al final de la nota: `[adjunto:<tipo>:<uuid>]`, con `<tipo>` = `pdf`, `png` o `jpg` |
| Quién subió, vio, descargó o borró qué | Eventos en `tpi.auditoria` (`adjunto_subido`, `adjunto_visto`, `adjunto_descargado`, `adjunto_rechazado`, `adjunto_eliminado`; `tabla_afectada` = `tpi.leads`; `detalle` con el sujeto, el `uuid`, el tipo, el tamaño y el SHA-256; nunca nombres ni contenido) |
| Borrado | Se borra el objeto; la marca queda en la nota y se muestra como «adjunto eliminado» |

Reglas de la marca:

- La agrega solo el servidor; se excluye del tope de 1000 caracteres y se permiten hasta 5 por nota. La nota con adjuntos
  sigue exigiendo texto.
- Se interpreta con una expresión regular estricta (`pdf|png|jpg` y un UUID); lo que no calza es texto normal.
- Que alguien escriba una marca a mano no da acceso a nada: la clave se arma con el lead de la ruta y el `uuid`, y la
  visibilidad del lead se comprueba primero.
- Hay que ocultar las marcas en la vista del lead, en los resúmenes del dashboard y en la exportación a Excel.

El diseño de la primera versión usaba una tabla; se descartó porque obligaba a una migración de clase D, permisos, un script de
aplicación y un antivirus propio, a cambio de datos que ya tienen hogar mejor. `tpi.auditoria` no se usa como registro de
adjuntos: su contrato dice que `detalle` no debe servir de almacén de relaciones operativas; para eventos sí sirve.

**Lo que se pierde, y se acepta:** no se puede preguntar por SQL «¿qué leads tienen adjuntos?» sin interpretar el texto; no hay
transacción entre S3 y la nota (se sube primero el objeto y, si agregar la nota falla, se borra el objeto; un fallo en ese borrado
puede dejar un objeto huérfano); el tope de 5 por nota solo lo hace el código. **Camino de vuelta:** si algún día se quiere
renombrar, describir o reportar adjuntos, se migra a una tabla con los datos de las marcas y de S3.

## 4. Resguardos obligatorios

1. **Validar por contenido.** Firma del archivo (PNG, JPEG, `%PDF-`) y estructura mínima válida. El tipo que se
   guarda y se sirve es el verificado, nunca el declarado por el cliente. Se rechaza todo lo demás.
2. **PDF sin partes activas.** Se rechazan los PDF con JavaScript, acciones de lanzamiento (`/Launch`), archivos
   incrustados (`/EmbeddedFile`) o cifrados (`/Encrypt`).
3. **Imágenes: solo el encabezado.** Se leen las dimensiones sin decodificar los píxeles, con un tope de píxeles y de
   tamaño (protege de «bombas de descompresión»). No se re-codifican en la primera versión (decisión 8). Nunca se
   decodifica una imagen completa de un usuario dentro de la petición web.
4. **Almacenamiento privado.** Bucket S3 con acceso público bloqueado, cifrado en reposo con claves de S3 (SSE-S3), solo TLS y
   **sin versionado**, para que el borrado sea real; regla que aborta subidas multiparte incompletas. Claves aleatorias (UUID),
   nunca el nombre del usuario.
5. **IAM mínimo** en el rol de la instancia: `s3:PutObject`, `s3:GetObject` y `s3:DeleteObject` sobre `leads/*` del bucket; sin
   `s3:ListBucket`. Consecuencia: S3 responde 403 tanto a un objeto inexistente como a uno denegado; la app los trata igual
   («adjunto no disponible»).
6. **Todo pasa por la app.** Nada de URLs firmadas ni de acceso directo a S3. La ruta de vista y de descarga aplica la
   misma regla de visibilidad que el lead (404 si no es visible).
7. **Cabeceras de respuesta de los adjuntos:** `Content-Type` fijado por el tipo verificado, `X-Content-Type-Options: nosniff`,
   `Content-Disposition` (en línea para vista, `attachment` para descarga) con un nombre generado por el servidor
   (`adjunto-<fecha>.<ext>`), `Cache-Control: private, no-store` y una política `Content-Security-Policy` restrictiva
   (`default-src 'none'`, con `sandbox` en las imágenes). El visor de PDF de algunos navegadores no funciona con `sandbox`; se
   prueba y se documenta la excepción.
8. **Antivirus antes de servir.** GuardDuty Malware Protection for S3 escanea cada objeto nuevo y lo etiqueta. La política del
   bucket impide leer lo que no tenga `NO_THREATS_FOUND`, así que un archivo sin escanear, con amenaza o con escaneo fallido no se
   sirve aunque la app tuviera un error. Los hallazgos los ve el humano en GuardDuty.
9. **CSRF, límite de tasa por usuario y tamaño de petición acotado** en la subida; la petición se lee por partes y se corta al
   pasar el tope.
10. **Interruptor de configuración** `ATTACHMENTS_ENABLED`, falso por defecto en el código (desarrollo local y pruebas). El
    compose de despliegue de DEV lo enciende con un valor literal, porque el paso 1 ya dejó el escaneo operando.
11. **Sin contenido en los logs:** ni bytes, ni texto extraído, ni nombres de archivo.

## 5. Riesgos aceptados

**Visibilidad (decisión 6).** La interfaz enmascara los datos personales para todos salvo `ceo` y `cto`, pero **un archivo no se
puede enmascarar**: una foto de una cédula la vería cualquier usuario con acceso al lead, aunque la pantalla le oculte el RUT.
El humano lo aceptó el 2026-10-21.

**Metadatos de las imágenes (decisión 8).** Al no re-codificarlas, EXIF y GPS (por ejemplo la ubicación de una foto tomada con el
teléfono) quedan visibles para quien vea el adjunto. Se revisa con la segunda versión.

Compensaciones:

- aviso visible al subir («no subas documentos de identidad completos salvo que sea necesario»);
- cada vista y descarga queda auditada (quién y cuándo). Abrir un lead con varias imágenes genera varias filas; se acepta
  en la primera versión;
- borrado a solicitud del titular, con su objeto en S3 (sin versionado, el borrado es real);
- revisión de estas decisiones tras el primer mes de uso real.

Al implementar, se deja constancia en `docs/SEGURIDAD.md`.

## 6. Retención y borrado

- Los adjuntos pertenecen al lead. La limpieza de leads de prueba en DEV borra también sus objetos (se encuentran por las marcas
  de la nota).
- La eliminación a solicitud del titular borra el objeto y deja un evento de auditoría sin contenido; la marca de la nota
  se muestra como «adjunto eliminado».
- Sin expiración automática en la primera versión. El plazo definitivo (y si corresponde una expiración) lo
  decide el humano con asesoría legal.

## 7. Pasos de implementación

| Paso | Qué es | Clase | Quién | Depende de |
|---|---|---|---|---|
| 1. `CRM-ADJUNTOS-1-INFRA-S3` (**aplicado y verificado el 2026-10-21**) | Bucket S3 privado, permisos mínimos del rol de la instancia, GuardDuty Malware Protection for S3 con etiquetado y la política que deniega lo no escaneado; plantilla revisable y script de aplicación que simula por defecto | C | El humano aplica, con Claude interactivo | — |
| 2. `CRM-ADJUNTOS-2-CODIGO` | Subida, vista en línea, descarga y borrado con validación; marcas en las notas; auditoría; configuración en el compose de despliegue de DEV | C (toca `deployment/**`) | Developer | 1 |

El paso 2 nace de clase C porque agrega variables al compose de despliegue (`deployment/aws/docker-compose.domainlocked.yml`);
tras el merge pasa por `BLOCKED_HUMAN` y el humano resuelve hacia `PREPARING_DEPLOYMENT`, como en `SEG-DESACOPLAR-STREAMLIT`.

**Implementación (módulos y acciones de auditoría).** La validación por contenido vive en
`app/attachments/validation.py`, las marcas en `app/attachments/marks.py`, el adaptador S3 inyectable en
`app/attachments/storage.py` (patrón de `app/notifications/sns.py`) y el escritor append-only en
`app/attachments/audit.py`. Las rutas están en `app/web/routes/leads.py` (subida en `POST /leads/{id}/comments`
multipart, vista/descarga en `GET /leads/{id}/adjuntos/{uuid}` y borrado en `POST /leads/{id}/adjuntos/{uuid}/eliminar`)
y la orquestación en `app/services/solicitud_service.py`. Las acciones de auditoría son `adjunto_subido`,
`adjunto_rechazado`, `adjunto_visto`, `adjunto_descargado` y `adjunto_eliminado` (`tabla_afectada` = `tpi.leads`).

## 8. Preguntas abiertas

- Plazo definitivo de retención y si se agrega una expiración automática.
- Costo real de GuardDuty Malware Protection for S3 (la tarifa por GB está publicada; la de por objeto en `us-east-2` hay que confirmarla).
  Resuelto el 2026-10-21: el plan se creó sin necesitar un detector de GuardDuty activo.
- Si se agrega el nombre original del archivo (hoy no se guarda).
- Si se agrega la re-codificación de imágenes (EXIF y GPS) en una segunda versión.
- Si se migra a una tabla de adjuntos cuando haga falta describir, renombrar o reportar.

## 9. Criterios para dar la función por terminada

Pruebas de seguridad en verde (extensión falsa, tipo declarado distinto del real, archivo con firma válida y contenido inválido,
PDF con partes activas, archivo sobre el límite, imagen con dimensiones excesivas, acceso cruzado entre asesores → 404, marca
escrita a mano), `pip-audit` sin excepciones, escaneo de GuardDuty comprobado con un archivo de prueba de antivirus (EICAR), smoke
humano en DEV y la constancia en `docs/SEGURIDAD.md`.
