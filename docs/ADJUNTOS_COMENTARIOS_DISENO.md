# Adjuntos en las notas de seguimiento del lead: diseño y resguardos

Estado: **decisiones del humano del 2026-10-21; sin implementar**. Este documento fija las decisiones y los
resguardos antes de escribir código. Las tareas que lo implementan están en `tasks/backlog.yaml` (prefijo
`CRM-ADJUNTOS-`). Si una decisión cambia, se cambia aquí primero.

## 1. Qué se quiere

Que quien escribe una nota de seguimiento en el detalle de un lead pueda adjuntarle imágenes y PDF, y que los demás
usuarios con acceso a ese lead los vean en la línea de tiempo.

## 2. Decisiones del humano

| # | Decisión | Valor |
|---|---|---|
| 1 | Tipos permitidos | PDF, PNG y JPEG, verificados por su **contenido** (no por la extensión ni por el tipo que declara el cliente). Nada de SVG, HTML, TIFF, GIF, EPS ni PPM. |
| 2 | Límites | 10 MB por archivo, 5 archivos por nota y 25 MB por petición. |
| 3 | Vista | **En línea**: las imágenes se ven dentro del detalle del lead y los PDF se abren en una pestaña nueva con el visor del navegador. También hay descarga. |
| 4 | Retención | El adjunto vive mientras exista el lead. Se borra a solicitud del titular (Ley 21.719), junto con su objeto en S3. Sin expiración automática en la primera versión. |
| 5 | Auditoría | Cada subida, vista o descarga, rechazo y borrado queda en `tpi.auditoria` (append-only). |
| 6 | Quién los ve | **Todos los usuarios que tienen acceso al lead** (un asesor solo ve los de su cartera; quien no ve el lead recibe 404). |

Supuestos míos, sin objeción del humano: los valores de los puntos 1, 2, 4 y 5 son los propuestos el 2026-10-21 y se
aceptaron al no ser objetados; el plazo definitivo de retención lo fija el humano (ver sección 8).

## 3. Lo que el código actual impone

- **Las notas no son una entidad.** Cada nota se agrega a la columna de texto `tpi.leads.comentarios` (máximo 1000
  caracteres por nota, con un encabezado de fecha y autor que otras consultas interpretan con una expresión regular). No hay tabla
  de comentarios ni identificador de nota.
- **La visibilidad ya existe:** un asesor solo escribe y ve en leads de su asignación activa; el resto de la lógica
  devuelve 404 sin revelar que el lead existe (`SolicitudService._advisor_mutation_scope`).
- **La app ya usa el SDK de AWS** (`app/notifications/sns.py`), así que usar S3 no agrega una dependencia nueva.
- **El PDF del simulador usa Pillow 13** (ya sin excepciones de `pip-audit`).

**Decisión de diseño (mía, a confirmar con la primera tarea):** los adjuntos son una entidad propia ligada al lead
(`tpi.lead_adjuntos`) que se sube **junto con la nota, en la misma transacción y con la misma marca de tiempo**, y se
muestra como evento en la línea de tiempo al lado de la nota. No se migran las notas a una tabla: sería un cambio grande
que no hace falta para esta función.

## 4. Resguardos obligatorios

1. **Validar por contenido.** Firma del archivo (PNG, JPEG, `%PDF-`) y estructura mínima válida. El tipo que se
   guarda y se sirve es el verificado, nunca el declarado por el cliente. Se rechaza todo lo demás.
2. **PDF sin partes activas.** Se rechazan los PDF con JavaScript, acciones de lanzamiento (`/Launch`), archivos
   incrustados (`/EmbeddedFile`) o cifrados (`/Encrypt`).
3. **Imágenes re-codificadas al subir**, en un proceso aislado con límites de memoria, tiempo y píxeles, con Pillow 13.
   Quita EXIF y GPS y neutraliza archivos que son válidos como imagen y como otra cosa (políglotas). Nunca se decodifica
   un archivo de usuario dentro de la petición web.
4. **Almacenamiento privado.** Bucket S3 con acceso público bloqueado, cifrado en reposo, solo TLS y versionado; claves
   aleatorias (UUID), nunca el nombre del usuario. El nombre original se guarda como metadato saneado y solo se
   muestra escapado.
5. **IAM mínimo** en el rol de la instancia: leer, escribir y borrar objetos del prefijo de adjuntos; sin listar el bucket.
6. **Todo pasa por la app.** Nada de URLs firmadas ni de acceso directo a S3. La ruta de vista y de descarga aplica la
   misma regla de visibilidad que el lead (404 si no es visible).
7. **Cabeceras de respuesta de los adjuntos:** `Content-Type` fijado por el tipo verificado, `X-Content-Type-Options: nosniff`,
   `Content-Disposition` con nombre saneado (en línea para vista, `attachment` para descarga), `Cache-Control: private,
   no-store` y una política `Content-Security-Policy` restrictiva (`default-src 'none'`, con `sandbox` en las imágenes). El
   visor de PDF de algunos navegadores no funciona con `sandbox`; se prueba y se documenta la excepción.
8. **Antivirus antes de servir.** El adjunto nace `pendiente`; solo se sirve cuando pasa a `limpio`. `infectado` o
   `error` se bloquea y se audita.
9. **CSRF, límite de tasa por usuario y tamaño de petición acotado** en la subida.
10. **Interruptor apagado.** Todo el código nace detrás de un interruptor de configuración (`ATTACHMENTS_ENABLED`,
    falso por defecto). Solo se enciende cuando el escaneo está desplegado y verificado.
11. **Sin contenido en los logs:** ni bytes, ni nombres de archivo, ni texto extraído.

## 5. Riesgo aceptado por la decisión 6 (todos los que ven el lead ven los adjuntos)

La interfaz enmascara los datos personales para todos salvo `ceo` y `cto`, pero **un archivo no se puede enmascarar**:
una foto de una cédula la vería cualquier usuario con acceso al lead, aunque la pantalla le oculte el RUT. El humano lo
aceptó el 2026-10-21. Compensaciones:

- aviso visible al subir («no subas documentos de identidad completos salvo que sea necesario»);
- cada vista y descarga queda auditada (quién y cuándo);
- borrado a solicitud del titular, con su objeto y sus versiones en S3;
- revisión de esta decisión tras el primer mes de uso real.

Al implementar, se deja constancia en `docs/SEGURIDAD.md`.

## 6. Retención y borrado

- Los adjuntos pertenecen al lead. La limpieza de leads de prueba en DEV borra también sus objetos.
- La eliminación a solicitud del titular borra la fila y el objeto (todas sus versiones) y deja un registro de
  auditoría sin contenido.
- Sin expiración automática en la primera versión. El plazo definitivo (y si corresponde una expiración) lo
  decide el humano con asesoría legal.

## 7. Pasos de implementación

| Paso | Qué es | Clase | Quién | Depende de |
|---|---|---|---|---|
| 1. `CRM-ADJUNTOS-1-INFRA-S3` | Bucket S3 privado y permisos del rol de la instancia, con plantilla revisable y script de aplicación que simula por defecto | C | El humano aplica, con Claude interactivo | — |
| 2. `CRM-ADJUNTOS-2-TABLA` | Tabla `tpi.lead_adjuntos`, permisos y vista de auditoría; migración `010` con su script de retroceso | D | El Developer escribe SQL y pruebas; el humano aplica | — |
| 3. `CRM-ADJUNTOS-3-CODIGO` | Subida, vista en línea y descarga, validación, re-codificación, borrado y línea de tiempo; todo con el interruptor apagado | A (con configuración de clase B) | Developer | 1 y 2 |
| 4. `CRM-ADJUNTOS-4-ESCANEO` | Antivirus (ClamAV o la protección contra malware de S3, a decidir al empezar), estados del adjunto y habilitación | C y A | Developer y humano | 3 |

Los pasos 1 y 2 son independientes y pueden avanzar en paralelo.

## 8. Preguntas abiertas

- Plazo definitivo de retención y si se agrega una expiración automática.
- Antivirus: ClamAV en un contenedor propio o la protección contra malware de S3 (se decide en el paso 4 con costos y operación).
- Si en el futuro se migran las notas a una tabla (hoy no hace falta).
- Si se permite subir adjuntos solo a algunos roles (hoy: todos los que pueden escribir notas).

## 9. Criterios para encender el interruptor

Pruebas de seguridad en verde (extensión falsa, tipo declarado distinto del real, políglotas, PDF con partes
activas, archivo sobre el límite, nombre malicioso, acceso cruzado entre asesores → 404), `pip-audit` sin excepciones,
escaneo desplegado y verificado, smoke humano en DEV y la constancia en `docs/SEGURIDAD.md`.
