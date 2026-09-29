# Política de deployment en AWS — Tu Pensión Inteligente

Estado: POLÍTICA PROVISIONAL — adoptada como norma de trabajo del equipo, pendiente de aprobación formal antes de marcarse como `POLÍTICA VIGENTE` (ver sección 7).
Owner: (pendiente de asignar — propuesto: CTO / Release Approver)
Aprobada: (pendiente)
Última revisión: 2026-09-07 (v1)
Próxima revisión: (ver sección 7 — condiciones de revisión)
Ámbito: DEV → QA → PROD; Elastic Beanstalk; CodePipeline; GitHub Actions; ECR; S3 de artefactos de release; IAM asociado al deployment.

## Historial de revisión

- **v1 (2026-09-07):** primera versión de la política, separada de `docs/AWS_DEPLOYMENT_BEST_PRACTICES.md` (v4) a pedido del jefe de proyecto, quien evaluó ese documento como sólido en su núcleo técnico (8,5/10 como documento de ingeniería) pero no apto todavía como política oficial (7/10) por mezclar política, estándar técnico, estado operativo y backlog en un solo archivo. Esta v1 extrae el núcleo normativo (principios, controles obligatorios, condiciones de STOP), lo redacta en lenguaje DEBE/DEBERÍA/PUEDE, y agrega responsabilidades, gestión de excepciones, revisión periódica, y un principio nuevo sobre minimización de datos en diagnósticos read-only, motivado por un hallazgo real de esta semana (ver principio 11).

## 1. Propósito y alcance

Esta política establece las reglas obligatorias para promover cualquier release del backoffice de TPI a un ambiente de AWS, desde DEV hasta QA y PROD. Aplica a:

- Elastic Beanstalk (o el mecanismo de cómputo que lo reemplace).
- CodePipeline y cualquier orquestador de despliegue equivalente.
- GitHub Actions como publicador/orquestador externo.
- Amazon ECR (imágenes de contenedor).
- S3 como almacén de artefactos de release.
- El IAM asociado a todo lo anterior.

Esta política es de mayor jerarquía normativa que `docs/AWS_DEPLOYMENT_BEST_PRACTICES.md`, `docs/DEV_EB_CODEPIPELINE_ARCHITECTURE.md` y `docs/DEV_EB_DEPLOYMENT_RUNBOOK.md`. Esos documentos **implementan** esta política — describen el porqué, la arquitectura y los pasos exactos, respectivamente — pero **no pueden contradecirla**. Si un runbook exige un paso que viola una regla DEBE/NO DEBE de esta política, el runbook está mal y debe corregirse; no se ejecuta el paso mientras tanto.

**Jerarquía de evidencia (distinta de la jerarquía normativa anterior):** cuando dos fuentes no coinciden sobre *qué está pasando* en AWS hoy (no sobre qué regla aplica, sino sobre el estado de los hechos), el orden de precedencia es:

1. Evidencia física observada directamente en AWS.
2. Contrato aprobado y versionado en `main` (IAM, pipeline, arquitectura).
3. Runbook operacional.
4. `docs/AWS_DEPLOYMENT_STATUS.md` y `docs/AWS_DEPLOYMENT_BEST_PRACTICES.md`.

Ante cualquier contradicción relevante entre niveles, la acción correcta no es "usar el de mayor precedencia y seguir" — es **detenerse y reconciliar la documentación** antes de continuar. Una contradicción entre fuentes es, en sí misma, evidencia insuficiente para proceder. (Esta regla nace de un error real: una versión anterior del documento de mejores prácticas afirmó que cierto mecanismo no existía en `main` por comparar contra una copia local desactualizada del repositorio.)

## 2. Principios obligatorios

Convención: **DEBE** = obligatorio; **DEBERÍA** = norma salvo excepción documentada (ver sección 6); **PUEDE** = permitido explícitamente.

1. **Identidad del release.** Toda promoción DEBE poder demostrar, en cualquier momento, qué commit, qué imagen (por digest), qué bundle, qué Application Version de Elastic Beanstalk y qué ejecución de pipeline produjeron lo que corre en AWS. Si alguna respuesta depende de memoria humana o de documentación desactualizada, la promoción no se considera suficientemente reproducible.

2. **IAM como contrato completo.** Todo cambio de IAM asociado al deployment DEBE derivarse de documentación oficial del servicio más evidencia física del stack real (como mínimo: `RoleARN` del stack de CloudFormation, los recursos físicos que efectivamente existen en él, y el service role/instance profile efectivos de Elastic Beanstalt). NO DEBE ampliarse una policy agregando únicamente el permiso puntual que arrojó el último `AccessDenied`.

3. **Runtime por encima de intención.** Toda promoción DEBE verificar `VersionLabel`, SHA y digest observados contra lo esperado antes de considerarse exitosa. El estado `Ready / Green / Ok` de Elastic Beanstalk es salud de infraestructura, no evidencia de identidad del software.

4. **Fail-closed.** El pipeline y cualquier observador asociado DEBEN detenerse ante un estado ambiguo o un error no reconocido explícitamente, en vez de reintentar a ciegas.

5. **Los mensajes de error no son contratos.** Las decisiones de gate DEBEN basarse en status, IDs, action executions, digests y ARNs exactos. El texto libre de diagnóstico (`errorDetails`, mensajes de excepción) NO DEBE usarse para condicionar lógica de negocio o de control.

6. **Consistencia eventual como parte del contrato.** Un observador de una ejecución de pipeline DEBE tolerar un número acotado de reintentos con backoff, exclusivamente para errores transitorios documentados antes de la primera observación válida del recurso. DEBE fallar de inmediato ante cualquier otro error, y ante cualquier anomalía posterior a haber observado el recurso por primera vez (por ejemplo, que vuelva a reportarse "no encontrado" después de haber sido visto `InProgress`).

7. **Las cuotas de servicio son requisitos.** Los límites documentados de los servicios de AWS usados en el pipeline DEBEN estar cubiertos por tests de contrato, con el mismo nivel de exigencia que la lógica de negocio.

8. **Separación de poderes.** Ningún actor DEBE tener simultáneamente permiso para alterar el artefacto de release, modificar el tooling privilegiado que lo promueve, y ejecutar el deploy. GitHub Actions NO DEBE tener permiso de escritura directa sobre Elastic Beanstalk; publica y orquesta, no ejecuta con privilegio.

9. **Persistencia de artefactos y residuos.** Los artefactos y residuos de una promoción fallida (bundles, Application Versions, datos de candidate) NO DEBEN eliminarse para reintentar "desde cero". DEBEN conservarse para permitir reanudación auditable y diagnóstico posterior.

10. **Un incidente se resuelve en su propia capa.** Un incidente de control plane (IAM, CloudFormation, Elastic Beanstalk) NO DEBE resolverse modificando DNS, base de datos, secretos o código funcional. Mezclar dominios impide encontrar la causa raíz y multiplica el radio de impacto.

11. **Read-only no es sinónimo de safe-to-log.** Los diagnósticos, inspectores y scripts read-only DEBEN aplicar minimización de datos: NO DEBEN registrar ni exponer en logs, salidas de consola, tickets o documentos, secretos, parámetros sensibles, credenciales temporales, URLs prefirmadas, tokens, ni identificadores físicos que puedan contener material sensible (por ejemplo, el `PhysicalId` de un recurso `AWS::CloudFormation::WaitConditionHandle`, que puede ser en sí mismo una URL prefirmada), salvo necesidad explícita y con tratamiento controlado (redacción, acceso restringido, expiración). *Origen: hallazgo real durante la inspección read-only de esta semana, donde el `PhysicalId` de un `WaitConditionHandle` expuso una URL prefirmada en la salida del inspector.*

## 3. Controles obligatorios del release

Cada promoción, en cualquier ambiente, DEBE satisfacer los siguientes controles antes de considerarse cerrada:

- **Release identity:** commit, imagen (por digest), bundle y Application Version identificados y congelados antes de iniciar la promoción.
- **Artifact immutability:** el candidate DEBE congelarse y permanecer inmutable durante toda la promoción. Regenerarlo para "destrabar" un problema de infraestructura está prohibido (ver principio 2 y antipatrones en Best Practices); solo se regenera por una razón funcional aprobada.
- **IAM / trust boundaries:** el contrato IAM de la operación DEBE revisarse como completo (principio 2) antes de ejecutar, no después de un `AccessDenied`.
- **Dry-run:** toda promoción DEBE ejecutar un dry-run equivalente (mismo artifact y preflight, sin publicar ni iniciar el pipeline) cuando el mecanismo lo soporte.
- **Explicit authorization:** la habilitación de cualquier transición de promoción DEBE ser un acto explícito y trazable — quién la autorizó y cuándo — nunca un estado que quede habilitado por defecto o "por costumbre".
- **Single execution:** el pipeline DEBE iniciarse una única vez por promoción, usando un mecanismo de idempotencia (client request token o equivalente), con captura inmediata del identificador de ejecución.
- **Observability:** el estado de la ejecución DEBE diagnosticarse por status, IDs y eventos exactos (ver principios 5 y 6), nunca por inferencia o por el texto de un mensaje.
- **Postflight:** toda promoción DEBE cerrar con un postflight mecánico que compare VersionLabel, health, digest/runtime, Source VersionId y eventos observados contra lo esperado.
- **Functional smoke:** el smoke funcional DEBE ejecutarse solo después de que el postflight de infraestructura haya pasado, nunca antes.
- **Rollback evidence:** antes de cualquier promoción DEBE existir y estar verificado un camino de rollback conocido (baseline) al que volver, y ese camino DEBE quedar documentado como parte del cierre del release.

## 4. Condiciones de STOP

Detenerse no es un fallo del proceso — es el proceso funcionando como se diseñó. Ante cualquiera de estas condiciones, el pipeline y las personas operando DEBEN detenerse en vez de continuar o reintentar:

- **Estado de AWS ambiguo:** no reintentar hasta demostrar si la ejecución anterior sigue activa, falló o completó.
- **Source inesperado:** si el objeto exacto ya existe cuando debería estar ausente, no se borra automáticamente.
- **Application Version discrepante:** no eliminar ni recrear; comparar `SourceBundle` y contenido/hash antes de decidir.
- **`AccessDenied` nuevo:** no agregar el permiso puntual en caliente. Revisar el contrato IAM completo de la operación (principio 2).
- **Transición de promoción habilitada o ejecutada sin que correspondiera:** detener todo y auditar la cadena de autorización.
- **Environment que no está en estado saludable conocido:** no lanzar una promoción nueva encima de un cambio que ya está en curso.
- **Necesidad percibida de tocar DNS, base de datos o secretos para "resolver" un fallo de deploy:** es la señal de que el problema se está atacando en la capa equivocada (principio 10). Detenerse y volver a la causa raíz real.
- **El mismo error de infraestructura se repite dos veces:** prohibido un tercer reintento sin abrir un diagnóstico formal de causa raíz. Reemplazar un environment es una intervención mayor, no una consecuencia automática — solo se hace si la evidencia demuestra corrupción o deriva, y con autorización separada de quien esté a cargo (ver responsabilidades).

## 5. Responsabilidades

- **Developer:** prepara el candidate (congelado e inmutable), abre el PR correspondiente, corre y mantiene los tests, y produce la evidencia técnica que exige el contrato IAM y el resto de los controles obligatorios de la sección 3.
- **CTO / Release Approver:** autoriza cambios de IAM, autoriza explícitamente cada transición de promoción, autoriza la ejecución real de la promoción, y autoriza cualquier rollback o reemplazo de environment.
- **GitHub (Actions):** publicador y orquestador. No tiene ni debe tener permiso de escritura directa sobre Elastic Beanstalk (principio 8).
- **CodePipeline:** ejecutor privilegiado de la promoción, con su propio service role, separado del rol usado por GitHub.

Esta separación de responsabilidades por rol humano/de sistema es la contraparte operativa de la separación de poderes técnica del principio 8: ningún rol, humano o de sistema, debe poder saltarse esta cadena.

## 6. Gestión de excepciones

Cualquier excepción a esta política DEBE quedar documentada **antes** del cambio que la motiva, incluyendo: motivo, riesgo asumido, alcance temporal (cuándo deja de aplicar la excepción), responsable que la autoriza, y plan de reversión.

Una emergencia operativa NO DEBE usarse para modificar retrospectivamente la evidencia de un release ya cerrado. Una emergencia puede justificar una excepción documentada hacia adelante; nunca reescribir lo que ya ocurrió.

## 7. Revisión de esta política

Esta política DEBE revisarse, como mínimo:

- Después de cualquier incidente de deployment relevante.
- Al crear los ambientes de QA o PROD.
- Al cambiar de plataforma o mecanismo de deployment.
- Cada 6 meses como máximo, aunque no haya ocurrido ninguno de los eventos anteriores.

Mientras el owner formal (CTO / Release Approver) no la apruebe explícitamente con fecha, esta política se adopta igualmente como **norma de trabajo provisional** del equipo — los principios, controles y condiciones de STOP de las secciones 2 a 4 ya rigen las promociones actuales — pero el documento no debe marcarse `Estado: POLÍTICA VIGENTE` hasta que exista esa aprobación formal.
