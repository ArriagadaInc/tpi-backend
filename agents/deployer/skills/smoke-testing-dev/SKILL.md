---
name: smoke-testing-dev
role: deployer
load_when: "VERIFYING, despues de postflight de infraestructura PASS"
sources: [release_contract_v2, aws_lessons_extracts, handoff_h33]
---

# smoke-testing-dev

## 1. Cuando se carga
VERIFYING, solo cuando la identidad de runtime y el estado del environment ya estan verificados.

## 2. Puede
- Ejecutar el smoke no autenticado de `environments/dev.yaml` con un cliente independiente (Python).
- Preparar la lista de criterios humanos para `approve.py accept`.

## 3. No puede
- Leer `AUTH_USERS_JSON`, ingresar credenciales o pedir contrasenas en chat.
- Escribir datos en BD o ejecutar SELECT con credenciales de aplicacion.
- Declarar DONE con criterios humanos sin aceptacion registrada.

## 4. Precondiciones
- `deployment-*.json` con `result: success` y runtime_identity completa.

## 5. Comandos y herramientas
- `python -c "import urllib.request as u; r=u.urlopen('https://dev.tupensioninteligente.cl/api/v1/catalogs', timeout=30); print(r.status)"`
  y equivalentes para cada check (sin seguir redirects a dominios legacy; verificar TLS por defecto).
- Si el cliente local falla por TLS, repetir con un segundo cliente antes de diagnosticar AWS (LL-15).
- Criterios humanos: el Deployer deja en `progress/current.md` la lista y el humano ejecuta
  `python scripts/harness/approve.py accept --decision accept --criteria AC-x,AC-y`.

## 6. Evidencia obligatoria
`verification-*.json`: approved_commit, deployed_commit, result, smoke (PASS/FAIL por check),
acceptance_criteria (met / not_met / pending_human, con method), pii_log_scan, failure_class.

## 7. STOP
- Defecto de autorizacion, PII o persistencia: `verify_failed` con `failure_class: functional`
  (sin rollback automatico; el release puede quedar en DEV para diagnostico).
- Endpoints caidos con environment degradado: `failure_class: infrastructure`.

## 8. Fuentes
- `docs/cicd/TPI_Contrato_CICD_AWS_v2.md` secciones 9 y 11.
- `docs/cicd/LECCIONES_DEPLOY_AWS_H3_2_H3_3.md` LL-12, LL-15; backlog `AUTOMATED_AUTHENTICATED_SMOKE`.
