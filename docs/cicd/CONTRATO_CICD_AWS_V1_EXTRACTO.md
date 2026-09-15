---
document: Contrato CI/CD AWS v1 - extracto de tecnicas reutilizables
authority: historical
original_file: TPI_Contrato_CICD_AWS_v1.pdf
original_date: 2026-09-10
original_status: Propuesta de implementacion
original_sha256: 5b07ddaad5655fe277233218ab36a5d6df96d8923e39c6f7da433570e72b0a35
superseded_by: docs/cicd/TPI_Contrato_CICD_AWS_v2.md
imported_at: 2026-09-14
---

# Contrato CI/CD AWS v1 — extracto historico

El v1 fue una propuesta reemplazada por el v2 (2026-09-12). El v2 abandono el enfoque de preflights
extensos y de CodePipeline como centro del release. Este extracto conserva solo tecnicas que siguen
siendo validas como conocimiento. **No usar** su baseline (rollback, candidate, roles, hashes de
policies, Launch Template) ni su arquitectura CodePipeline como camino obligatorio.

## Tecnicas vigentes como conocimiento

1. **Separar Pipeline A (aplicacion) de Pipeline B (infraestructura/plataforma).** Coincide con las
   clases A-E del v2. Eventos que invalidan el contrato del environment y convierten un cambio en
   clase C: cambio de platform branch/version de EB; cambio de stack fisico, ASG o Launch Template;
   cambio de service role o instance profile; habilitar/deshabilitar streaming de logs o health;
   cambio de buckets/control plane; cambio de estrategia de deployment EB; cambio de cuenta o region.
2. **CloudWatch Logs es parte del contrato caller-side de EB.** Se observaron `DescribeLogGroups`,
   `CreateLogGroup` y `PutRetentionPolicy` bajo el actor que inicio la operacion, sobre varios log
   groups del environment.
3. **Read-only no significa seguro para ocultar errores.** Un postflight debe fallar si no puede
   recopilar evidencia. No usar `|| true` en observabilidad critica.
4. **Los resumenes de CodePipeline no siempre entregan la causa raiz.** EB Events y CloudTrail fueron
   las fuentes autoritativas para identificar el caller y la accion denegada.
5. **Orden de fuentes de diagnostico:** estado fisico EB -> EB Events -> CloudTrail del actor -> logs
   del stage/pipeline -> resumen de CodePipeline. No invertir este orden.
6. **Clasificacion de fallos:** application defect / contract drift / AWS service behavior /
   observability. Solo un contract drift real habilita un cambio de infraestructura/IAM.
7. **Politica de rollback por situacion:**

| Situacion | Accion |
| --- | --- |
| UpdateEnvironment rechazado antes de modificar runtime | Detener; no rollback innecesario. |
| Environment degrada y runtime queda inconsistente | Rollback explicito a last-known-good. |
| Pipeline falla pero environment sigue target/Green | Postflight y diagnostico; no rollback ciego. |
| Smoke funcional critico falla | Rollback segun impacto; preservar evidencia. |
| Observabilidad falla pero estado no puede verificarse | Fail closed; no declarar exito. |

8. **Ideas de diseno para H3.2 (no requisitos del fast path):** contrato declarativo por ambiente con
   schema; verificacion IAM repo == AWS por hash canonico; evidence record por release; DoD de 3-5
   releases consecutivas sin tocar IAM ni consola; promover el mismo artefacto entre ambientes sin
   rebuild.
