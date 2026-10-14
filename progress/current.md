# Progreso actual

## Estado
<!-- harness:projection:begin (autogenerado desde harness/state.json por transition.py; no editar a mano) -->
- Estado del Harness: IDLE (rol: human)
- Tarea: ninguna
- Proximo paso: Humano elige tarea: python scripts/harness/approve.py activate --task <ID>
- Ultima transicion: close (DONE -> IDLE)
- Actualizado: 2026-10-14T20:51:29Z
<!-- harness:projection:end -->
- Ultima sesion archivada: progress/sessions/2026-10-14-SIM-RV-V1-closure.md

## Estado reciente
- NOTA de continuidad 2026-10-14 19:10Z (no es una decision; el BLOCKER de AWS expirada de las 18:45Z ya esta resuelto: el humano renovo `aws login` y el preflight dio ok a las 18:48Z): la sesion claude-202610141848-deployer-sup2201fe termino por un DENIED (STOP absoluto, 19:04:00Z) al crear el payload del candidate con un heredoc de Bash que contenia el texto `aws_guard.py` sin la ruta `scripts/harness/aws_guard.py`; el guard revisa el texto crudo de cada comando de Bash y esa regla se aplica tambien dentro de heredocs y cadenas. YA HECHO en PREPARING_DEPLOYMENT para SIM-RV-V1 (no repetir): publish del release 13084414558f59a7b1e30dd859199469c2a62318 (run 38618512458, conclusion success, scan gate ok); bundle domain-locked `.harness-release/h3-sim-rv-v1-1308441-domainlocked-r1.zip` (sha256 b91612eacdd0698661ceca28247199d6dd4254c1a675fbae6af969daa5431895) reproducido (check-*.zip); `s3api put-object` content-addressed y `head-object --checksum-mode ENABLED` (19:02:54Z y 19:03:09Z); `create-application-version --no-process` con la AV `h3-sim-rv-v1-1308441-domainlocked-r1` (19:03:14Z). FALTA: registrar `evidence.py write --kind candidate` y aplicar `transition.py candidate_ready`. Verifica la AV y el objeto S3 con `aws_guard.py` (describe-application-versions / head-object) en lugar de repetir escrituras; crear una AV con una etiqueta existente falla. Para el payload: crealo con la herramienta Write en `.harness-release/` (tu `write_allow`), no con un heredoc de Bash, y escribe siempre `scripts/harness/aws_guard.py` con la ruta completa.
- NOTA 2026-10-14 19:46Z (SIM-RV-V1, deployer claude-202610141943-deployer-sup7b1c1a): cutover version-only ejecutado (1 intento, sin retries) a h3-sim-rv-v1-1308441-domainlocked-r1; 19:45:04Z-19:45:56Z, VersionLabel exacta y Ready/Green/Ok, 20 eventos EB todos INFO, cadena AV->S3 checksum->digests coincide con approval-01. Evidencia: evidence/SIM-RV-V1/deployment/deployment-01.json. Pendiente en VERIFYING: smoke, conteos de logs (aws-observability), AC-18/AC-19 humanos.
- VERIFICACION 2026-10-14 19:50Z (SIM-RV-V1, VERIFYING, deployer claude-202610141943-deployer-sup7b1c1a): transicion deploy_succeeded aplicada. Postflight automatizado PASS: env h3-sim-rv-v1-1308441-domainlocked-r1 Ready/Green/Ok; AV SourceBundle y ChecksumSHA256 (uRYS6s3Q...) = candidate; smoke no autenticado 6/6 (public 200, login 200, catalogs 200, css 200, /leads 307->/login, /leads/1/simulador 307->/login); conteos de logs desde 19:45:04Z todos 0 (Authorization -REDACTED, Bearer, password, cookie, raw_payload, secret, token, hash -ACME). PENDIENTE HUMANO antes de `verified`: AC-18 (campana canaria; la ventana vencio el 2026-10-13, los PDF salen con advertencia de 90 dias) y AC-19 (smoke autenticado: ejecutivo genera PDF de 3 escenarios contrastados con el simulador de referencia; advisor/operations/readonly reciben 403; PDF sin RUT/correo/telefono; logs sin PII). Ejecutar `python scripts/harness/approve.py accept --decision accept --criteria AC-18,AC-19` en terminal humana; luego el Deployer registra verification y aplica `verified`.
- VERIFICACION FINAL 2026-10-14 20:55Z (SIM-RV-V1, deployer claude-202610142048-deployer-supd7f38e): acceptance-01 (AC-1,2,3,6,7,9,11,15,17,18,19) registrada por el humano; postflight re-observado PASS (env Ready/Green/Ok en la AV aprobada, cadena AV->S3 checksum->digests, smoke 6/6, conteos de logs desde 19:45:04Z todos 0). Evidencia: evidence/SIM-RV-V1/deployment/verification-01.json. Se aplica `verified`.
- 2026-10-14: Tarea SIM-RV-V1 cerrada; resumen en tasks/completed/SIM-RV-V1.yaml

## Bloqueos
- Ninguno.
