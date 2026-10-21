# Sesion archivada: CRM-ADJUNTOS-2-CODIGO-review

- Archivada: 2026-10-21T19:32:50Z
- Estado: REVIEWING

# Progreso actual

## Estado
<!-- harness:projection:begin (autogenerado desde harness/state.json por transition.py; no editar a mano) -->
- Estado del Harness: REVIEWING (rol: reviewer)
- Tarea: CRM-ADJUNTOS-2-CODIGO
- Proximo paso: Reviewer: revisar SHA exacto, CI verde, registrar review y review_approve o review_reject
- Ultima transicion: start_review (READY_FOR_REVIEW -> REVIEWING)
- Actualizado: 2026-10-21T19:30:04Z
<!-- harness:projection:end -->
- Ultima sesion archivada: progress/sessions/2026-10-21-CRM-ADJUNTOS-2-CODIGO-developer.md

## Estado reciente
- DECISION (CANDIDATE_REVIEW, SEG-DESACOPLAR-STREAMLIT, sesion claude-202610211517-reviewer-supad9892): APPROVED, cause null. Arbol del release = arbol revisado (deba86f), release en main; publish run 39622446165 success para el SHA; digests app/caddy ACTIVE con scan sin hallazgos; bundle reconstruido de forma independiente con sha256 c187fd6b... identico, solo compose por digest; S3 y AV coinciden; LKG sano con digests presentes; plan version-only y rollback unico al LKG. Sin dry-run. Evidencia: evidence/SEG-DESACOPLAR-STREAMLIT/reviewer/candidate_review-01.json.
- DECISION (DEPLOYING, SEG-DESACOPLAR-STREAMLIT, sesion claude-202610211528-deployer-supfc8c32): cutover version-only a h3-seg-desacoplar-streamlit-0c9b165-domainlocked-r1 aceptado 15:30:23Z, completado 15:31:09Z; Ready/Green/Ok; cadena VersionLabel -> AV -> S3 checksum -> digests coincide; sin reintentos ni rollback. Evidencia: evidence/SEG-DESACOPLAR-STREAMLIT/deployment/deployment-01.json. Conteos de logs y smoke en VERIFYING; AC-8 pendiente de approve.py accept.
- DECISION (VERIFYING, SEG-DESACOPLAR-STREAMLIT, sesion claude-202610211528-deployer-supfc8c32): verificacion automatizada PASS (identidad de runtime, smoke HTTP 5/5 + sin redirect legacy, conteos de logs en 0 incluido Traceback). Evidencia: evidence/SEG-DESACOPLAR-STREAMLIT/deployment/verification-01.json. AC-1..AC-7 met; AC-8 pendiente_humano.
- 2026-10-21: Tarea SEG-DESACOPLAR-STREAMLIT cerrada; resumen en tasks/completed/SEG-DESACOPLAR-STREAMLIT.yaml
- DECISION (HUMANO, 2026-10-21, con Claude interactivo): el guard bloqueo la sesion other-202610211820-developer-supde320a (blocked_guard) porque intentaste editar `.env.example`, archivo que NO esta en tu alcance (el Developer solo escribe `app/**`, `tests/**`, `front/**`, `docs/**`, `scripts/sql/**`, `scripts/*.py`, `README.md` y `CHANGELOG.md`; y por ser clase C tambien `deployment/**`, `.github/**`, `Dockerfile` y `docker-compose*.yml`). Es un bloqueo de FORMA, no de fondo. NO intentes escribir `.env.example`: documenta las variables nuevas SOLO en `docs/DEVELOPMENT_GUIDE.md` y `docs/SEGURIDAD.md` (ya lo hiciste) y, si hace falta, en `README.md`. TU TRABAJO PREVIO SE CONSERVA: el worktree ya tiene el paquete `app/attachments/`, los cambios en settings, servicio, presentacion, rutas, plantilla, CSS y compose, y 6 archivos de pruebas. Continua desde ahi, no empieces de cero: revisa primero `git status` y `git diff --stat`, corre ruff, black, mypy, bandit y la suite de pruebas, verifica cada criterio AC-1..AC-11 contra el codigo y entrega. Si el guard vuelve a bloquear, detente y reporta; no busques rodeos.
- HALLAZGO (HUMANO, 2026-10-21, con Claude interactivo, para el Reviewer de CRM-ADJUNTOS-2-CODIGO / PR 111): verifica por tu cuenta y decide si es bloqueante. (1) AC-4 pedia limitar la peticion sin Content-Length con `max_files` y `max_part_size` de Starlette, pero en el Starlette instalado `max_part_size` solo limita los campos de TEXTO: las partes de archivo se escriben sin tope (ver `MultiPartParser.on_part_data`). Una peticion con `Transfer-Encoding: chunked` y sin Content-Length esquiva el tope de 25 MiB y el de 10 MiB hasta que `validate_attachment_content` lo rechaza, despues de haber escrito todo el cuerpo a un temporal en disco (un usuario autenticado podria llenar el disco). El error de la especificacion es del humano, no del Developer; la correccion natural es rechazar con 411 o 413 las peticiones multipart de la ruta de notas que no traigan Content-Length valido cuando los adjuntos estan activos, o cortar el flujo al pasar el tope. `tests/unit/test_attachments_web.py` no prueba el caso sin Content-Length. (2) Informativo: la validacion de PDF busca los tokens prohibidos en los bytes crudos, asi que no ve JavaScript dentro de streams comprimidos (object streams con FlateDecode); `docs/SEGURIDAD.md` no lo menciona entre los riesgos aceptados. El bucket (GuardDuty) y el visor del navegador son las capas siguientes; conviene documentarlo.
- DECISION (REVIEWING, CRM-ADJUNTOS-2-CODIGO, sesion claude-202610211929-reviewer-sup6e72fc): REJECTED sobre c2cf660 (arbol 6e6dec9). CI verde y 81 pruebas de adjuntos reproducidas, pero el hallazgo del humano se confirmo contra Starlette 1.3.1: max_part_size no limita archivos, asi que AC-4 no se cumple sin Content-Length (major F-1). Pendiente para el Developer: 411/413 sin Content-Length valido o corte del flujo, prueba del caso, y documentar en SEGURIDAD.md que el escaneo de PDF no ve streams comprimidos. review-01.json (APPROVED) fue un intento previo descartado en la misma sesion; vale review-02.json. Evidencia: evidence/CRM-ADJUNTOS-2-CODIGO/reviewer/review-02.json.

## Bloqueos
- Ninguno.
