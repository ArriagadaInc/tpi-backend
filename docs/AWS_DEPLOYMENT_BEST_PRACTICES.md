# Mejores prácticas de deployment en AWS — Tu Pensión Inteligente

Estado: v5 — reestructurado en tres documentos a pedido del jefe de proyecto (ver historial de revisión e "Cómo usar estos documentos"). Este archivo contiene el razonamiento de ingeniería, las lecciones aprendidas y el golden path operativo. Las reglas obligatorias (DEBE/DEBERÍA/PUEDE), las condiciones de STOP, las responsabilidades y la gestión de excepciones viven en `docs/AWS_DEPLOYMENT_POLICY.md`. El estado operativo fechado, el checklist de la próxima promoción y el backlog viven en `docs/AWS_DEPLOYMENT_STATUS.md`.
Ambiente: AWS DEV (`821656895812`, `us-east-2`), aplicable a QA/PROD cuando se creen
Última consolidación: 2026-09-07 (v1) — revisado 2026-09-07 (v2, v3, v4, v5) tras comentarios de desarrollador y jefe de proyecto
Fuente: `Lecciones_Aprendidas_Deployment_AWS_TPI_H3.2.docx`, `Lecciones_Aprendidas_Deploy_AWS_TPI_H3.3.docx`, `TPI_Lecciones_Aprendidas_Deploy_AWS_H3_3.pdf`, auditoría del repo al 2026-09-07, y revisión técnica del equipo (desarrollador + jefe de proyecto)

## Historial de revisión

- **v1 (2026-09-07):** primera consolidación de los tres documentos de lecciones aprendidas + auditoría del repo.
- **v2 (2026-09-07):** corrige, tras revisión del equipo: (a) el orden del checklist IAM (inspección física antes de aplicar, no después); (b) distingue explícitamente estado OBSERVADO EN AWS vs. VERSIONADO EN MAIN vs. PROPUESTO EN PR sin mergear; (c) identifica un gap concreto en `wait_for_codepipeline_execution.py` (no distingue un `NotFound` inicial de uno posterior a haber visto la ejecución `InProgress`); (d) suaviza la regla de "reemplazar Green" para exigir diagnóstico y autorización separada; (e) aclara la nomenclatura Green/Blue/baseline; (f) distingue el candidate congelado de H3.3 (medida deliberada) del antipatrón de hardcodeo permanente; (g) atribuye el hallazgo de CRLF a la workstation específica desde la que se auditó, no al repositorio en general. **Esta versión contenía un error factual, corregido en v3.**
- **v3 (2026-09-07):** corrige, tras segunda revisión del desarrollador (verificado directamente contra `origin/main` con un fetch limpio): (a) `deployment/iam/tpi-codepipeline-dev-eb.json` y el mecanismo base de CodePipeline **sí están en `main`**; el PR #33 está solo 2 commits adelante de `main` (no 20 como decía la v2, error causado por comparar contra una copia local de `main` desactualizada 18 commits por un fetch fallido); (b) precisa exactamente qué agrega el PR #33 sobre `main`: el statement IAM de CloudFormation, el archivo nuevo `wait_for_codepipeline_execution.py`, el inspector `inspect_dev_eb_control_plane_readonly.sh`, y actualizaciones a runbook/arquitectura/tests; (c) documenta que el runbook en `main` dice "preparado, no aprovisionado ni ejecutado" — toda la narrativa de aprovisionamiento y del fallo de promoción vive solo en el PR sin mergear; (d) exige corregir el gap del waiter (estado `has_been_visible`) **dentro del PR #33, antes del merge**, y agrega el test faltante que debe existir; (e) reemplaza "gana el runbook" por una jerarquía de precedencia con STOP obligatorio ante contradicciones; (f) corrige la fila de antipatrones que todavía usaba lenguaje Blue/Green después de que el glosario aclarara que no existe esa separación física hoy.
- **v4 (2026-09-07):** corrige, tras tercera revisión del desarrollador: (a) la metadata del encabezado seguía diciendo "v2" pese a que el contenido ya era v3 — corregido; (b) el checklist y el backlog afirmaban que `inspect_dev_eb_control_plane_readonly.sh` ya cubre `ServiceRole`, `IamInstanceProfile` efectivo, detalle de Auto Scaling Group, Launch Template y Load Balancer/Target Groups — verificado leyendo el script: hoy solo obtiene datos básicos del environment, `RoleARN` y estado del stack, la lista de recursos físicos vía `ListStackResources` (tipo + physical ID, sin detalle de configuración) y los tipos declarados vía `GetTemplate`. No consulta explícitamente `ServiceRole`/`IamInstanceProfile` desde `describe-configuration-settings`, ni el detalle de ASG/Launch Template/Load Balancer/listeners/Target Groups. Se adopta la opción preferida por el desarrollador: ampliar el inspector en vez de reducir la afirmación del documento, para que la evidencia sea reproducible por script y no dependa de comandos manuales sueltos — queda como ítem de backlog con las llamadas AWS exactas que faltan agregar. El análisis del waiter (punto 3 de esa revisión) ya estaba correctamente reflejado desde la v3 y no requirió cambios adicionales.
- **v5 (2026-09-07):** reestructuración completa a pedido del jefe de proyecto, quien evaluó el documento como sólido en su núcleo técnico (8,5/10 como documento de ingeniería) pero no listo como política oficial (7/10) por mezclar cuatro cosas distintas: política, estándar técnico, estado operativo y backlog. Se separa en tres documentos: `AWS_DEPLOYMENT_POLICY.md` (reglas obligatorias en lenguaje DEBE/DEBERÍA/PUEDE, condiciones de STOP, responsabilidades, excepciones y ciclo de revisión — marcada como política **provisional**, no vigente, hasta aprobación formal), este documento (razonamiento, lecciones aprendidas, antipatrones y golden path), y `AWS_DEPLOYMENT_STATUS.md` (snapshot fechado, checklist de la próxima promoción y backlog). También se incorpora, en la Política, un principio nuevo sobre minimización de datos en diagnósticos read-only ("read-only no es sinónimo de safe-to-log"), motivado por un hallazgo real: el `PhysicalId` de un `WaitConditionHandle` expuso una URL prefirmada en la salida del inspector. Y se corrige, con evidencia física nueva reportada por el equipo, que el stack no tiene Load Balancer ni Target Groups hoy (`RoleARN = null`, y los resource types reales son ASG/Launch Template/EIP/WaitCondition/WaitConditionHandle) — el detalle actualizado de esa evidencia y sus consecuencias sobre el alcance IAM vive en `AWS_DEPLOYMENT_STATUS.md`.

## Cómo usar estos documentos

El conjunto de documentación de deployment de TPI tiene cuatro capas, cada una con un rol distinto:

```text
AWS_DEPLOYMENT_POLICY.md              → qué jamás violamos (DEBE/DEBERÍA/PUEDE)
AWS_DEPLOYMENT_BEST_PRACTICES.md      → por qué, y qué hemos aprendido (este documento)
DEV_EB_CODEPIPELINE_ARCHITECTURE.md   → cómo están separadas las responsabilidades y los permisos
DEV_EB_DEPLOYMENT_RUNBOOK.md          → exactamente qué comando/paso ejecutar hoy
```

Más `AWS_DEPLOYMENT_STATUS.md` (snapshot fechado del estado operativo, checklist de la próxima promoción y backlog — deliberadamente fuera de este documento para que este pueda ser estable) y `BITACORA.md` (evidencia histórica de lo ya ejecutado).

La Política es la capa normativa: sus reglas DEBE/DEBERÍA/PUEDE tienen mayor jerarquía que cualquier cosa escrita acá. El runbook implementa la política pero no puede contradecirla. Este documento responde:

1. ¿Por qué llegamos a cada regla de la Política? (los 10 principios de abajo, con su razonamiento completo)
2. ¿Cuál es el camino estándar (golden path) para promover un release, paso a paso, siempre?
3. ¿Qué antipatrones ya nos costaron caro y no deben repetirse?

Este documento debe revisarse después de cada release real (exitosa o fallida) y actualizarse si aparece una lección nueva. La jerarquía de precedencia para resolver contradicciones entre fuentes (evidencia física en AWS → contrato versionado en `main` → runbook → documentos generales), y la regla de detenerse ante cualquier contradicción relevante, están definidas formalmente en `AWS_DEPLOYMENT_POLICY.md` §1.

## Principio rector

> Un deploy profesional no es "hacer que AWS acepte el cambio". Es promover un artefacto inmutable por un camino único y autorizado, poder demostrar cada eslabón de la cadena, y detenerse de forma segura cuando el estado no es demostrable.

Corolario operativo: **NO EVIDENCE = NO RELEASE**. Si no podemos demostrar qué commit, qué imagen, qué digest, qué bundle, qué Application Version y qué pipeline produjeron lo que está corriendo en AWS, el deployment no se considera válido, sin importar que Elastic Beanstalk diga `Ready / Green / Ok`.

## Los 10 principios que se convierten en control, no en buena intención

Estos son la intersección de los tres documentos de lecciones aprendidas. Cada uno debe verificarse con una acción concreta, no solo recordarse. El enunciado normativo obligatorio (DEBE/NO DEBE) de cada uno está en `AWS_DEPLOYMENT_POLICY.md` §2, en el mismo orden; acá está el razonamiento completo detrás de cada uno. Esa política agrega además un principio 11 ("read-only no es sinónimo de safe-to-log") que nace de un hallazgo de esta semana — ver `AWS_DEPLOYMENT_STATUS.md`.

**1. El deploy es un sistema de evidencia, no un comando.** Un release debe permitir responder en cualquier momento: qué commit corre, qué imagen lo contiene, cuál es su digest, qué bundle lo representa, qué Application Version usa EB, qué pipeline la promovió y qué ejecuta realmente AWS. Si alguna respuesta depende de memoria humana o de un README desactualizado, el release no es suficientemente reproducible.

**2. IAM debe modelar la operación compuesta completa, nunca reaccionar a un `AccessDenied`.** Conceder `elasticbeanstalk:UpdateEnvironment` no implica que el caller pueda completar la operación: EB puede exigir permisos sobre S3, CloudFormation u otros servicios administrados que no están documentados como dependencia obvia. El contrato IAM se deriva de documentación oficial + evidencia física del stack real, no se descubre AccessDenied por AccessDenied.

"Completo" tiene un criterio concreto, no es una sensación: antes de dar por cerrado un contrato IAM caller-side hay que poder mostrar evidencia física de, como mínimo, el `RoleARN` del stack de CloudFormation (¿la actualización corre con un service role propio del stack, o con las credenciales del caller?), los tipos y recursos físicos reales del stack (Auto Scaling Group, Launch Template, Load Balancer/Target Groups), y el service role e instance profile efectivos de EB. Corregir solo el permiso puntual que arrojó el último `AccessDenied` (por ejemplo, agregar `cloudformation:GetTemplate` porque fue lo que falló) sin esa evidencia es el mismo antipatrón de "AccessDenied → agrego el permiso → reintento", aplicado un nivel más abajo.

**3. Runtime > intención.** No importa qué se quiso desplegar; importa qué ejecuta realmente AWS. `Ready / Green / Ok` es salud de infraestructura, no prueba de identidad del software. Después de cada promoción hay que comparar VersionLabel, SHA y digest observados contra los esperados.

**4. Fail-closed es una inversión, no una molestia.** Cada vez que el pipeline se detuvo en lugar de reintentar a ciegas, se evitaron reintentos destructivos, rollbacks innecesarios, recreación del candidate o cambios de DNS fuera de contexto. El costo es más iteración manual; el beneficio es que el baseline nunca se rompió.

**5. Los mensajes de error no son contratos.** AWS puede omitir `errorDetails` o `externalExecutionSummary`, o devolverlos con formato variable. Las decisiones de gate se toman por estado, IDs, action executions, digests y ARNs exactos — el texto de diagnóstico es para leer, no para condicionar código.

**6. La consistencia eventual es parte del contrato operativo, no un bug.** `StartPipelineExecution` puede devolver un execution ID que `GetPipelineExecution` todavía no reconoce (`PipelineExecutionNotFoundException`). El observador debe tolerar ese estado transitorio con reintentos acotados y backoff — y fallar de inmediato ante cualquier otro error.

**7. Las cuotas del servicio son requisitos, no detalles de implementación.** El límite de `environmentVariables` en una acción `Commands` de CodePipeline no aparece validando solo sintaxis JSON o corriendo tests locales. Los límites documentados de los servicios administrados deben estar cubiertos por tests de contrato, igual que la lógica de negocio.

**8. Separación de poderes: ningún actor puede alterar el artefacto, cambiar el tooling privilegiado y ejecutar el deploy al mismo tiempo.** GitHub publica y orquesta; no tiene permiso de escritura directa sobre Elastic Beanstalk. CodePipeline ejecuta con un service role propio, usando tooling descargado desde un prefijo que GitHub no puede modificar y verificado por SHA-256 antes de ejecutarse.

**9. Los artefactos y residuos sobreviven a un fallo; no se limpian para "empezar de cero".** No borrar `candidate-data`, bundles o Application Versions para reintentar más rápido. Conservarlos es lo que permite reanudar de forma verificable y auditar exactamente qué pasó. Después de cualquier escritura fallida, corresponde un postflight de solo lectura antes de decidir el siguiente paso.

**10. Un incidente de infraestructura se resuelve en su capa.** Un fallo de control plane (IAM, CloudFormation, EB) nunca justifica tocar DNS, base de datos, secretos o código funcional para "destrabar" el deploy. Mezclar dominios impide encontrar la causa raíz y multiplica el blast radius.

## Antipatrones que quedan prohibidos

| Antipatrón | Por qué duele | Qué hacer en su lugar |
| --- | --- | --- |
| `AccessDenied` → agregar el permiso que pide → reintentar | Genera IAM por acumulación reactiva; nunca converge y puede terminar más permisivo de lo necesario | Derivar el contrato caller-side completo (documentación oficial + evidencia del stack real) antes de tocar la policy |
| Reintentar sin conocer el estado terminal de la ejecución anterior | Puede duplicar escrituras o competir con una ejecución que sigue viva | Consultar execution ID / action executions primero; ante duda, diagnóstico read-only antes de cualquier escritura |
| Validar por el texto de un mensaje de error | Los campos opcionales de las respuestas de AWS cambian o llegan vacíos | Gates basados en status, IDs, ARNs y hashes exactos; el texto es solo para el humano que lee el log |
| Regenerar el candidate para "destrabar" un problema de infraestructura | Rompe la cadena de evidencia y mezcla cambios funcionales con un problema de IAM/control-plane | Candidate congelado e inmutable; solo se regenera por una razón funcional aprobada, nunca para escapar de un error de infraestructura |
| Dar permisos de deploy directo a GitHub sobre Elastic Beanstalk | Crea un trust path alternativo fuera del pipeline controlado y auditado | Separar rol read-only, rol de release/orquestación y service role de CodePipeline; retirar roles históricos que ya no se usan |
| Usar `latest` o tags mutables como identidad de release | Rompe la trazabilidad: no hay forma de saber qué bytes hay detrás del tag en un momento dado | El digest se resuelve desde ECR después del push y se referencia por `sha256:...`, nunca por tag |
| Que hardcodear SHA/digests/bundles/`VERSION_LABEL` de un candidate congelado *se convierta en el diseño permanente* de todas las releases futuras | Congelar un candidate exacto (como se hizo para H3.3) es una medida de seguridad deliberada y correcta para *esa* promoción puntual; el problema es no tener un camino para que la próxima release no repita el mismo hardcodeo manual en 3-4 archivos | El candidate se congela por release (correcto), pero el mecanismo de promoción (workflow, IAM, pipeline) debe generalizarse para no requerir edición manual de varios archivos cada vez — ver backlog |
| Mezclar correcciones no relacionadas en un mismo cambio | Dificulta identificar la causa raíz cuando algo falla después | PRs focalizados, salvo cuando los fallos pertenecen al mismo contrato operacional (ej. IAM compuesto + observador de eventual consistency) |
| Probar reparaciones directamente sobre el environment activo de DEV | Convierte el ambiente que debería tener un rollback seguro en un laboratorio | Diagnosticar contra el environment activo solo en modo lectura; cualquier escritura de prueba pasa primero por un dry-run, y si hace falta experimentar de verdad, se hace en un environment separado y autorizado para eso — no hay hoy un par Blue/Green físico al que "volver" automáticamente (ver nomenclatura más abajo); el camino de vuelta es el baseline conocido por Application Version |

## Golden path: los 12 pasos de una promoción

Este es el orden estándar para cualquier promoción a partir de ahora, en DEV y en cualquier ambiente futuro.

1. **Congelar el candidate.** Commit, imágenes ECR por digest, bundle y manifest con hashes. Nada se regenera durante la promoción.
2. **Verificar el baseline.** Environment en `Ready / Green / Ok`, rollback disponible y saludable, candidate/source coincidiendo exactamente con lo esperado.
3. **Revisar IAM como contrato completo.** Comparar el service role contra las dependencias reales de EB (incluyendo CloudFormation y buckets administrados); cualquier cambio de IAM se revisa antes de ejecutar, no después de un `AccessDenied`.
4. **Ejecutar un dry-run.** Mismo artifact y preflight que la promoción real, pero sin publicar el source ni iniciar el pipeline (`execute_promotion=false`).
5. **Autorizar el Promote explícitamente.** Habilitar la transición solo cuando todos los gates estén cerrados, dejando evidencia de quién autorizó.
6. **Publicar el source versionado.** `candidate-data.zip` con su `VersionId` de S3; nunca depender de "el último objeto subido".
7. **Iniciar el pipeline una sola vez.** Client request token / idempotencia, y captura inmediata del execution ID.
8. **Observar con tolerancia controlada.** Retry/backoff solo para errores transitorios documentados (como `PipelineExecutionNotFoundException` justo después de iniciar); timeout y fail-closed para cualquier otro error.
9. **Diagnosticar por estados, no por suposiciones.** Source/Promote, CloudWatch log stream, eventos de EB y estado del environment.
10. **Postflight mecánico.** VersionLabel, health, digest/runtime observado, Source VersionId, action executions y eventos — todo comparado contra lo esperado.
11. **Smoke funcional, solo después del postflight de infraestructura.** PII, filtros, simulador, asignación, persistencia y auditoría.
12. **Cerrar el release.** Merge del PR funcional, actualizar el runbook con los IDs y evidencia de esta promoción, dejar clara la ruta de rollback.

## Nomenclatura: Green, Blue y "baseline" en TPI

Los documentos de lecciones aprendidas usan lenguaje de Blue/Green como disciplina general, y en una etapa anterior del proyecto existió un par real de environments (`tpi-backoffice-dev` y `tpi-backoffice-dev-ecr`, todavía visibles como valores por defecto en `deployment/aws/check_eb_iam_isolation.py`). Pero el mecanismo de promoción vigente hoy **no** opera sobre dos environments distintos: hay un único environment, `tpi-backoffice-dev-green`, y el "rollback" es volver ese mismo environment a una Application Version anterior conocida (`h2-5d-ecr-47fa0c9`), no cortar tráfico hacia un environment Blue separado. Para evitar confusión, en TPI usamos estos términos así:

- **Environment DEV actual:** `tpi-backoffice-dev-green` — el único environment sobre el que se promueve.
- **Baseline / rollback Application Version:** la versión conocida-buena a la que se vuelve si algo falla (hoy `h2-5d-ecr-47fa0c9`), dentro del mismo environment.
- **Candidate:** la Application Version nueva que se está promoviendo (hoy `h3-3-crm-web-28cf009-r1`), también dentro del mismo environment.

"Green" en el nombre del environment es histórico, no describe su rol en un patrón Blue/Green activo. Si en el futuro se implementa un Blue/Green real con dos environments y corte de tráfico, este glosario debe actualizarse para reflejarlo explícitamente.

## Cuándo detenerse (condiciones de STOP)

Las condiciones de STOP son reglas obligatorias, no una lista de sugerencias — por eso viven como norma en `AWS_DEPLOYMENT_POLICY.md` §4 (junto con responsabilidades y gestión de excepciones en §5–6). Resumen de una línea, porque vale la pena tenerlo presente al ejecutar el golden path de arriba: detenerse no es un fallo del proceso — es el proceso funcionando como se diseñó, ante estado ambiguo, `AccessDenied` nuevo, una transición de promoción habilitada sin autorización, o la tentación de tocar DNS/DB/secretos para "destrabar" un fallo de deploy.

## Dónde estamos hoy, y qué falta cerrar

El estado operativo fechado de esta semana (qué está OBSERVADO EN AWS vs. VERSIONADO EN MAIN vs. PROPUESTO EN PR SIN MERGEAR, incluyendo la evidencia física ya obtenida del stack — `RoleARN = null`, resource types reales, ausencia de Load Balancer/Target Groups hoy —, el checklist accionable antes de la próxima promoción, y el backlog priorizado) vive deliberadamente fuera de este documento, en `AWS_DEPLOYMENT_STATUS.md`. Se separó a pedido del jefe de proyecto: un documento de prácticas debería sobrevivir 2-3 años sin cambios; un snapshot de PR #33 puede quedar desactualizado mañana. Revisar ese documento antes de cualquier promoción real.

## Cierre

"Deploy profesional" para TPI significa promover un artefacto inmutable por un camino único y autorizado, poder demostrar cada eslabón de la cadena, y detenerse de forma segura cuando el estado no es demostrable — no significa desplegar más rápido. La fricción de las últimas semanas no vino de mala ingeniería: vino de estar terminando de construir, en tiempo real, exactamente el sistema de evidencia que este documento describe, y de no tener todavía separados los cuatro roles documentales (política, prácticas, arquitectura, runbook) que permiten que cada uno evolucione a su propio ritmo. Con la Política adoptada como norma provisional y el Status como snapshot vivo, cada release futura debería consumir este conjunto de documentos como checklist, no repetir su descubrimiento.
