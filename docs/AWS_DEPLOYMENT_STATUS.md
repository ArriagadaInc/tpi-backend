# Estado operativo del deployment en AWS — Tu Pensión Inteligente

Estado: snapshot fechado, no política. Este documento caduca rápido a propósito y debe revisarse antes de cada promoción — no es una verdad permanente. Las reglas obligatorias que sí son permanentes están en `docs/AWS_DEPLOYMENT_POLICY.md`; el razonamiento y las lecciones aprendidas están en `docs/AWS_DEPLOYMENT_BEST_PRACTICES.md`.
Ambiente: AWS DEV (`821656895812`, `us-east-2`).
Última actualización: 2026-09-07 (v1 de este documento, separado de `AWS_DEPLOYMENT_BEST_PRACTICES.md` v4 a pedido del jefe de proyecto; incorpora evidencia física reportada por el equipo el mismo día).

## Historial de revisión

- **v1 (2026-09-07):** extraído de la sección "Dónde estamos realmente hoy", el checklist y el backlog de `AWS_DEPLOYMENT_BEST_PRACTICES.md` v4, para separar estado circunstancial de política permanente. Incorpora evidencia física nueva reportada por el equipo: `RoleARN = null` en el stack, y los resource types físicamente presentes (`AWS::AutoScaling::AutoScalingGroup`, `AWS::EC2::LaunchTemplate`, `AWS::EC2::EIP`, `AWS::CloudFormation::WaitCondition`, `AWS::CloudFormation::WaitConditionHandle` — **sin** Load Balancer ni Target Groups hoy). Esta evidencia es reportada por el equipo (jefe de proyecto) sobre una ejecución real del inspector actual; no fue reverificada de forma independiente en esta sesión por no tener acceso directo a AWS. También registra un hallazgo de seguridad: el `PhysicalId` de un `WaitConditionHandle` expuso una URL prefirmada en la salida read-only del inspector — ver backlog y `AWS_DEPLOYMENT_POLICY.md` principio 11.

## Convenciones de evidencia

- **OBSERVADO EN AWS** — confirmado contra el estado físico real de la cuenta.
- **VERSIONADO EN MAIN** — existe en la rama `main`, mergeado.
- **PROPUESTO EN PR SIN MERGEAR** — existe solo en una rama de feature/fix, todavía no en `main`.
- **PENDIENTE DE APLICAR** — el cambio existe en código pero no hay confirmación de que esté aplicado en AWS.

## Snapshot: dónde estamos hoy

Lo bueno primero: el repo ya implementa la gran mayoría de los principios de la Política, no como intención sino como código y tests — CI separa lint/test/security/docker-build de la fabricación del release, `publish-dev-ecr-images.yml` resuelve el digest desde ECR después del push, los roles IAM están separados por responsabilidad, `promote_eb_candidate.py` es idempotente y verifica checksums, y hay tests de seguridad que corren en cada CI. Eso es **VERSIONADO EN MAIN** en su mayor parte.

**1. El contrato IAM caller-side de Elastic Beanstalk tiene su base VERSIONADA EN MAIN; el permiso de CloudFormation está PROPUESTO EN PR SIN MERGEAR (PR #33, rama `fix/eb-update-control-plane`, 2 commits por delante de `main`), y todavía no está confirmado como aplicado físicamente.** El mecanismo de CodePipeline en sí — el pipeline, `deploy-dev-eb.yml`, la policy base de `tpi-codepipeline-dev-eb.json` — ya está en `main`. Lo que agrega el PR #33 es puntual: el statement `OrchestrateOnlyPhysicalDevEnvironmentStack` (los permisos de CloudFormation que corrigen el `cloudformation:GetTemplate` que bloqueó la promoción real), el archivo `deployment/aws/wait_for_codepipeline_execution.py`, el inspector `scripts/release/inspect_dev_eb_control_plane_readonly.sh`, y actualizaciones a runbook/arquitectura/tests. El runbook en `main` todavía dice "preparado, no aprovisionado ni ejecutado" — la narrativa completa de aprovisionamiento y del fallo de promoción vive solo en el PR #33 sin mergear.

   **Evidencia física ya obtenida (OBSERVADO EN AWS, con el inspector actual sin ampliar):** `RoleARN` del stack `awseb-e-sd5gmkxr5r-stack` es **`null`** — la actualización del stack corre con las credenciales del caller, no con un service role propio. Los recursos físicos presentes en el stack (vía `ListStackResources`/`GetTemplate`) son: `AWS::AutoScaling::AutoScalingGroup`, `AWS::EC2::LaunchTemplate`, `AWS::EC2::EIP`, `AWS::CloudFormation::WaitCondition` y `AWS::CloudFormation::WaitConditionHandle`. **No hay Load Balancer ni Target Groups en este stack hoy** — la formulación de versiones anteriores de este checklist que los daba por hecho era incorrecta; corresponde tratarlos como condicionales ("si existen"), no como parte fija de la inspección.

   **Evidencia física que sigue faltando** (bloqueada por la ampliación pendiente del inspector, ver backlog): `ServiceRole` configurado del environment e `IamInstanceProfile` efectivo (vía `describe-configuration-settings`), y el detalle de configuración del Auto Scaling Group y del Launch Template (vía `describe-auto-scaling-groups` / `describe-launch-template-versions` — hoy solo se sabe que existen como resource type, no su configuración).

   Con `RoleARN = null` confirmado, la pregunta relevante para decidir el alcance final del permiso deja de ser solo "¿falta `cloudformation:GetTemplate`?": como CloudFormation actualiza el stack usando las credenciales del caller (no un service role propio), el alcance final debe considerar también si hacen falta permisos downstream de Auto Scaling/EC2 para que esas credenciales puedan actualizar el ASG y el Launch Template — no debe prejuzgarse que el único cambio necesario sea el permiso de CloudFormation ya propuesto en el PR #33. Corregir solo lo que pidió el último `AccessDenied` sin cerrar esta evidencia repetiría el antipatrón "AccessDenied → permiso puntual → reintento" a un nivel más sutil. Este es el ítem P0.

**2. El estado de la transición `Promote` de CodePipeline no está confirmado — es PENDIENTE DE VERIFICAR, no un hecho observado.** El runbook (en el PR sin mergear) documenta la *intención* de mantenerla deshabilitada tras el fallo, pero no hay confirmación posterior de que se haya vuelto a deshabilitar. Debe verificarse con una consulta read-only (`get-pipeline-state` o equivalente) antes de asumir nada.

**3. El observador GitHub → CodePipeline (parte del PR #33, no existe todavía en `main`) tiene un gap concreto de diseño que debe corregirse *dentro de ese mismo PR, antes de mergear*.** `wait_for_codepipeline_execution.py`: el contador de reintentos por `PipelineExecutionNotFoundException` no distingue si la ejecución ya fue observada como `InProgress` en algún momento anterior. Falta un estado explícito `has_been_visible`, con esta regla: `NotFound` antes de la primera observación válida → retry/backoff acotado; primera respuesta válida (`InProgress`, `Succeeded`, etc.) → `has_been_visible = True`; `NotFound` posterior → falla inmediata. `tests/unit/test_codepipeline_execution_waiter.py` tiene 4 tests y ninguno cubre la secuencia `NotFound → InProgress → NotFound`; ese test falta y debe agregarse junto con el fix, en el mismo PR.

**4. El diseño actual del mecanismo de promoción es de un solo uso, no reutilizable.** `deploy-dev-eb.yml`, `tpi-github-actions-dev-release.json`, `tpi-codepipeline-dev-eb.json` y `tpi-dev-eb-pipeline.json` tienen hardcodeada la identidad exacta del candidate H3.3. Congelar ese candidate fue la decisión correcta para esta promoción puntual; falta un camino para que la próxima release no repita la misma edición manual de varios archivos. Diseño detallado conversado aparte (rutas S3 estables + inputs de workflow derivados del manifest).

**5. Higiene de línea de comandos: CRLF en el working tree de esta workstation específica (Windows, sesión `note-alvaro`).** Confirmado que es CRLF local vs. LF en lo commiteado (el blob real en `HEAD` está limpio); no es un defecto del repositorio.

**6. Herramientas de diagnóstico desactualizadas.** `deployment/aws/check_eb_iam_isolation.py` sigue usando los nombres de environment de una etapa anterior (`tpi-backoffice-dev` / `tpi-backoffice-dev-ecr`) en vez de `tpi-backoffice-dev-green`, el nombre vigente hoy.

**7. La bitácora del proyecto no refleja el trabajo más complejo que se hizo.** `docs/BITACORA.md` no tiene entradas desde el 7 de agosto.

**8. Los tres documentos de este conjunto (Policy / Best Practices / Status) están sin versionar.** Ninguno de los tres aparece todavía en el control de versiones del repo.

**9. Hallazgo de seguridad de esta semana: read-only no fue safe-to-log.** La ejecución del inspector fue técnicamente de solo lectura, pero el `PhysicalId` de un recurso `AWS::CloudFormation::WaitConditionHandle` expuso una URL prefirmada en su salida. Ver `AWS_DEPLOYMENT_POLICY.md` principio 11 (minimización de datos en diagnósticos) y el ítem de backlog correspondiente más abajo.

## Checklist accionable antes de la próxima promoción

Orden: el waiter se corrige primero, el inspector se amplía y se completa la inspección física antes de tocar IAM, y recién después viene el merge.

1. **Corregir el waiter** (`wait_for_codepipeline_execution.py`) dentro del PR #33: agregar el estado `has_been_visible` y el test `NotFound → InProgress → NotFound → falla inmediata`. No mergear el PR sin esto.
2. **Ampliar el inspector** (`scripts/release/inspect_dev_eb_control_plane_readonly.sh`) antes de tratarlo como evidencia completa: agregar `describe-configuration-settings` (ServiceRole e IamInstanceProfile efectivos), `describe-auto-scaling-groups` y `describe-launch-template-versions`, y `describe-load-balancers`/`describe-listeners`/`describe-target-groups` **si el stack llegara a tener alguno** (hoy confirmado que no tiene). Al ampliarlo, aplicar minimización de datos: no volcar sin redactar el `PhysicalId` de recursos que puedan ser URLs prefirmadas (p. ej. `WaitConditionHandle`) — ver Política, principio 11.
3. **Completar la inspección física read-only** del environment y el stack con el inspector ya ampliado. Ya se obtuvo `RoleARN = null` y el listado de resource types (sin LB/TG); falta ServiceRole/IamInstanceProfile efectivos y el detalle de ASG/Launch Template.
4. **Validar** el alcance IAM final contra toda la evidencia del paso 3 — incluyendo si, dado `RoleARN = null`, hacen falta permisos downstream de Auto Scaling/EC2 además del permiso de CloudFormation ya propuesto en PR #33.
5. **Mergear** el PR solo después de corregir el waiter, ampliar el inspector y validar el alcance IAM.
6. **Aplicar la policy caller-side final aprobada y validada contra el stack físico** (no necesariamente limitada al permiso de CloudFormation ya propuesto — ver punto 4).
7. **Leer de nuevo** la policy desde IAM (`get-role-policy`) y comparar explícitamente repo == AWS.
8. **Dry-run** (`execute_promotion=false`) y confirmar que preflight, artifact y rol read-only pasan sin escrituras.
9. **Recién entonces**, promoción real (`execute_promotion=true`), siguiendo el golden path de `AWS_DEPLOYMENT_BEST_PRACTICES.md`.
10. Postflight completo antes de dar el release por cerrado.
11. Agregar la entrada correspondiente en `docs/BITACORA.md` con los IDs de esta promoción, y versionar los tres documentos de este conjunto si todavía siguen `untracked`.

## Backlog de acciones derivadas

| Prioridad | Acción | Criterio de cierre | Estado |
| --- | --- | --- | --- |
| P0 | Corregir el observador GitHub → CodePipeline para distinguir `NotFound` inicial de `NotFound` posterior a `InProgress`, dentro del PR #33, antes de mergear | `wait_for_codepipeline_execution.py` mantiene un estado `has_been_visible`; agregado el test `NotFound → InProgress → NotFound → falla inmediata` | Gap confirmado leyendo el código y los tests actuales; bloquea el merge |
| P0 | Ampliar el inspector read-only para cubrir ServiceRole/IamInstanceProfile efectivo, detalle de ASG, Launch Template/versiones, y LB/listeners/Target Groups condicionalmente | El script produce esa evidencia por comando; no vuelca `PhysicalId` sensible sin redactar | Gap confirmado leyendo el script; bloquea completar la inspección física |
| P0 | Minimizar datos sensibles en la salida del inspector (hallazgo de esta semana) | El inspector redacta u omite el `PhysicalId` de recursos tipo `WaitConditionHandle` (y cualquier otro que pueda contener URLs prefirmadas/tokens) salvo necesidad explícita; cualquier salida ya generada que contenga la URL expuesta se elimina o se regenera redactada | Hallazgo confirmado: un `PhysicalId` de `WaitConditionHandle` expuso una URL prefirmada en una ejecución real del inspector; elevado a principio de política (ver `AWS_DEPLOYMENT_POLICY.md` #11) |
| P0 | Completar la inspección física del stack con el inspector ya ampliado | ServiceRole/IamInstanceProfile efectivos y detalle de ASG/Launch Template obtenidos y comparados contra el alcance IAM propuesto | Parcial: `RoleARN=null` y resource types ya obtenidos (sin LB/TG); falta el resto, depende de ampliar el inspector |
| P0 | Aplicar la policy caller-side final de Elastic Beanstalk, validada contra el stack físico completo | Policy leída de vuelta desde IAM (`get-role-policy`) y confirmada idéntica a la versionada, incluyendo cualquier permiso downstream que exija `RoleARN=null` | No aplicado en AWS; alcance final todavía sujeto a la inspección completa |
| P0 | Verificar el estado real de la transición `Promote` antes de cualquier acción | Confirmado por consulta read-only a CodePipeline, no por inferencia del runbook | No verificado en esta auditoría (solo acceso a repo, no a AWS en vivo) |
| P1 | Tests de semántica y cuotas de AWS | Cobertura de cuotas de servicio, campos opcionales, estados transitorios y errores no transitorios | Parcial: ya existe test para la cuota de `environmentVariables` de CodePipeline Commands |
| P1 | Generalizar el pipeline para no requerir edición manual de 4 archivos por release | Rutas S3 estables + inputs de workflow derivados del manifest, según el diseño propuesto por separado | Pendiente |
| P1 | Agregar `.gitattributes` con normalización LF | `git status` deja de mostrar el repo como modificado por CRLF en checkouts de Windows | Pendiente |
| P2 | Actualizar o retirar `check_eb_iam_isolation.py` | El script usa los nombres de environment vigentes o se elimina si ya no aplica | Pendiente |
| P2 | Retomar `docs/BITACORA.md` | La bitácora refleja el trabajo de CodePipeline/IAM de esta semana y queda al día hacia adelante | Pendiente |
| P2 | Versionar `AWS_DEPLOYMENT_POLICY.md`, `AWS_DEPLOYMENT_BEST_PRACTICES.md` y este documento | Los tres dejan de aparecer como `untracked` | Pendiente |
| P2 | Convertir el mecanismo de promoción en un componente reutilizable para QA/PROD | Extraer los patrones de DEV sin copiar permisos ni scripts ad hoc | Pendiente, depende de cerrar P0/P1 primero |
