---
document: TPI Contrato de Entrega Continua en AWS
version: "2"
authority: canonical
date: 2026-09-12
original_file: TPI_Contrato_CICD_AWS_v2.pdf
original_pages: 13
original_sha256: 1d1d027a35eb1e1025ee7fdf82cbe6af55dd1c578746c58815aba363d065a7a6
imported_at: 2026-09-14
import_method: >-
  pdftotext (modos layout y raw). Texto trasladado sin cambios de contenido;
  las tablas se reconstruyeron desde el orden raw y la numeracion de listas se normalizo.
supersedes: TPI_Contrato_CICD_AWS_v1 (ver docs/cicd/CONTRATO_CICD_AWS_V1_EXTRACTO.md)
summary: docs/TPI_Contrato_CICD_AWS_v2.md
---

# TU PENSION INTELIGENTE — Contrato de Entrega Continua en AWS

**v2 - Golden Path agil, seguro, reproducible y auditable.**
Actualizado con las lecciones reales del cierre de H3.3. 12 de septiembre de 2026.

> Nota de importacion: la seccion 15 es un **snapshot historico al 2026-09-12**.
> No representa estado actual; el estado se verifica con la skill `aws-read-preflight`.

| Campo | Valor al 2026-09-12 |
| --- | --- |
| Ambiente actual | AWS DEV - account 821656895812 - us-east-2 |
| Runtime desplegado | h3-3-crm-web-43101be-domainlocked-r1 - Ready / Green / Ok |
| Estado H3.3 | CLOSED WITH DEFERRED ACCEPTANCE ITEMS |
| Proximo foco | H3.3.1 funcional + H3.2 industrializacion del deployment |

## Resumen ejecutivo

Esta version reemplaza el enfoque anterior de "perfeccionar el pipeline antes de validar el
producto" por un modelo de entrega en dos velocidades: un fast path version-only para cambios de
aplicacion/proxy que no requieren modificar infraestructura, y un infrastructure path separado
para cambios de Elastic Beanstalk, IAM, red, secretos o base de datos. El objetivo es reducir el
tiempo de entrega sin sacrificar trazabilidad, seguridad ni rollback.

### Leccion central

La principal leccion de H3.3 es que Elastic Beanstalk puede convertir un UpdateEnvironment con
cambios de configuracion en una operacion compuesta que atraviesa EC2, CloudFormation y S3.
Intentar descubrir ese contrato IAM permiso por permiso genera ciclos lentos y poco predecibles.
En cambio, el cutover version-only con una Application Version inmutable llego a
Ready / Green / Ok sin tocar option settings ni reabrir el stack de configuracion.

### Regla operativa nueva

```text
CAMBIO DE APP / CADDY SIN INFRA   -> VERSION-ONLY FAST PATH
CAMBIO DE CONFIG EB / IAM / RED / DB -> CAMBIO SEPARADO, DISENADO Y PROBADO COMO INFRAESTRUCTURA
NO MEZCLAR AMBOS EN EL MISMO RELEASE
```

### Resultado esperado

- Deploy DEV normal: minutos, no horas de investigacion IAM.
- Artefactos inmutables y trazables desde commit hasta VersionLabel.
- Rollback de una sola accion: volver a una VersionLabel conocida.
- Smoke funcional inmediatamente despues de runtime green, antes de invertir en hardening adicional.
- Produccion: mismo principio, pero con infraestructura versionada y service roles explicitos; no
  depender de credenciales del caller.

### Que cambio respecto de v1

| Antes | Ahora v2 |
| --- | --- |
| El pipeline era el centro del release. | El artefacto y la identidad del runtime son el centro; el mecanismo de promocion puede variar por ambiente. |
| Se intentaba resolver UpdateEnvironment con option settings desde el caller. | En DEV, cambios normales usan version-only. Configuracion de infraestructura se trata como cambio separado. |
| Preflights extensos antes de ver funcionalidad. | Preflight minimo + deploy + smoke funcional temprano. |
| IAM caller-side se iba completando por AccessDenied. | Prohibido. Se disena el contrato completo o se usa service role/IaC. |
| CodePipeline Commands podia esperar hasta 30 min. | El job de promocion debe ser corto; la espera larga vive fuera del token de Commands o usa un mecanismo nativo. |
| Cierre tecnico podia avanzar sin acceptance funcional temprano. | Acceptance funcional es gate de release; defectos se detectan inmediatamente tras runtime green. |

## 1. Principios no negociables

1. **Artefacto inmutable primero.** Cada release se identifica por commit, digest ECR, bundle
   SHA256, S3 key y Application Version. Nunca se reconstruye para hacer rollback.
2. **Runtime observado > intencion.** Ready/Green/Ok prueba salud, no identidad. El postflight debe
   comprobar VersionLabel y endpoints esperados.
3. **Version-only por defecto.** Si el cambio no requiere infraestructura, no modificar option
   settings, red, IAM ni stack CloudFormation durante la promocion.
4. **Infraestructura es otro producto.** IAM, EB configuration, Route53, service roles, red y DB se
   cambian en PRs separados, con rollback y evidencia propia.
5. **No AccessDenied-driven development.** Nunca: error -> permiso -> retry. Si aparece una
   dependencia nueva, detenerse y revisar el contrato completo antes de tocar IAM.
6. **Smoke funcional temprano.** Apenas el runtime este verde: login, flujo critico y persistencia.
   No esperar a terminar hardening del pipeline para descubrir que el feature no aparece.
7. **Secretos fuera de observabilidad.** Logs, comandos y handoffs nunca imprimen secretos. Los smoke
   usan sesion humana o credenciales de prueba gestionadas, no lectura indiscriminada de Secrets
   Manager.
8. **Un release, una promocion.** No retries ciegos. Cada intento tiene execution ID/registro; un
   segundo intento requiere causa entendida y estado limpio.
9. **Rollback simple y probado.** El rollback preferido es volver a una VersionLabel conocida, sin
   reconstruccion ni reconfiguracion.
10. **Main debe converger con runtime.** Una vez validado el candidate, el codigo desplegado debe
    quedar mergeado en main y CI verde; no mantener divergencia prolongada.

## 2. Clasificacion de cambios: decidir la ruta antes de desplegar

| Clase | Ejemplos | Ruta | Regla |
| --- | --- | --- | --- |
| A - Aplicacion | FastAPI, templates, reglas de negocio, tests, Caddy sin cambio infra | FAST PATH version-only | No option settings. No IAM. No Route53. No DB migrations. |
| B - Config no secreta del runtime | Dominios, toggles o parametros que pueden vivir en bundle/config de aplicacion | DEV: bundle especifico por ambiente. PROD: IaC/config gestionada | No mezclar con un cambio funcional si puede evitarse. |
| C - Infraestructura | IAM, EB option settings, service role, VPC, SG, ALB, Route53, buckets | INFRA PATH | PR separado + plan/inspeccion + change window + rollback. |
| D - Base de datos | DDL, grants, indices, migraciones | DB PATH | Aplicar una sola vez, versionada, con verificacion y rollback/documentacion. |
| E - Secretos | Passwords, auth users, HMAC, session secret | SECRET PATH | Rotacion/versionado fuera del artefacto; nunca en repo ni logs. |

### Decision de 30 segundos

```text
¿Puedo desplegar el nuevo runtime sin cambiar option settings/infra?
  SI -> FAST PATH VERSION-ONLY
  NO -> NO INTENTAR "ARREGLAR" IAM DURANTE EL RELEASE. ABRIR CAMBIO DE INFRA SEPARADO.
```

## 3. Golden Path DEV - version-only fast path

Este es el camino operativo recomendado para releases normales de aplicacion en DEV. Fue el
mecanismo que finalmente permitio completar el cutover H3.3 de forma estable.

1. **Congelar candidate.** CI verde. Registrar commit exacto. Construir imagen una vez y fijarla por
   digest.
2. **Construir bundle determinista.** Solo archivos necesarios. Sin `build:` en runtime. Imagenes por
   digest. Config DEV no secreta resuelta sin tocar EB option settings.
3. **Calcular y registrar SHA256.** El nombre/key del release debe incorporar identidad estable.
   Descargar y verificar despues del upload.
4. **Publicar en bucket de releases/EB.** Key nueva. Nunca sobrescribir una key de release aprobada.
5. **Crear Application Version nueva.** VersionLabel unica y descriptiva. No borrar/recrear una AV
   existente.
6. **Preflight minimo.** Cuenta/region correctas, environment sano, source esperado, target AV
   existe, no hay update en curso.
7. **Cutover version-only.**
   `aws elasticbeanstalk update-environment --environment-name ... --version-label ...`.
   Sin `--option-settings`.
8. **Esperar Ready / Green / Ok.** Observar VersionLabel exacta y eventos EB. No confundir verde con
   acceptance funcional.
9. **Smoke funcional inmediato.** Endpoint publico, login, feature critico, persistencia y
   autorizacion. Si falla, clasificar como defecto funcional, no seguir endureciendo deployment.
10. **Validacion de datos cuando aplique.** SELECT read-only sobre efectos del flujo. No rerun de
    migraciones.
11. **Merge a main y CI.** Verificar que el commit probado es el que se mergea. Main CI verde.
12. **Bitacora.** Registrar evidencia, deuda, rollback y siguiente paso.

## 4. Comando de promocion preferido en DEV

La llamada de promocion debe ser deliberadamente pequena. El deploy de aplicacion no debe cargar
tambien configuracion de infraestructura.

```bash
AWS_PROFILE=tpi-dev
AWS_REGION=us-east-2
aws sts get-caller-identity --profile "$AWS_PROFILE"
aws elasticbeanstalk update-environment \
   --profile "$AWS_PROFILE" \
   --region "$AWS_REGION" \
   --environment-name tpi-backoffice-dev-green \
   --version-label <VERSION_LABEL_APROBADA>
```

### Prohibido en el fast path

- `--option-settings`
- Cambios IAM o trust policy durante el release
- Cambios Route53 manuales salvo cutover expresamente aprobado
- Rebuild del candidate para arreglar deployment
- Rerun de migraciones que ya fueron aplicadas
- Borrar/recrear Application Versions para reutilizar un nombre

### Rollback operativo

```bash
aws elasticbeanstalk update-environment \
    --profile tpi-dev \
    --region us-east-2 \
    --environment-name tpi-backoffice-dev-green \
    --version-label <LAST_KNOWN_GOOD>
```

El rollback no debe depender de un build nuevo ni de reconstruir metadata historica. Por eso la
VersionLabel anterior se conserva intacta.

## 5. Fast path no significa atajo de seguridad

| Gate | Evidencia minima |
| --- | --- |
| Identidad AWS | Account y region exactas; nunca usar profile default si puede apuntar a otra cuenta. |
| Supply chain | Commit, digest app, digest Caddy, bundle SHA256, S3 key, AV. |
| Seguridad | CI + security tests + escaneo de imagen sin findings HIGH/CRITICAL segun politica. |
| Runtime | VersionLabel exacta + Ready/Green/Ok. |
| Producto | Smoke del flujo critico y autorizacion. |
| Persistencia | SELECT read-only de efectos cuando el feature escribe BD. |
| Rollback | VersionLabel anterior conocida y conservada. |
| Trazabilidad | Bitacora y PR/issue actualizados. |

## 6. Infra path - cambios que NO deben viajar con un release normal

Si hay que modificar option settings de Elastic Beanstalk, IAM, CloudFormation, red, service roles o
buckets, el cambio deja de ser un deploy de aplicacion. Se convierte en una operacion de
infraestructura y debe seguir otra ruta.

### Contrato minimo del infra path

1. Definir el objetivo exacto y el rollback antes de escribir.
2. Inspeccionar estado fisico real: stack, RoleARN, service role de EB, instance profile y recursos
   administrados.
3. Disenar el contrato IAM completo. No derivarlo de la secuencia de AccessDenied.
4. Versionar el cambio en IaC/policy y cubrirlo con tests de seguridad.
5. Aplicar en una ventana separada del deploy funcional.
6. Leer de vuelta el estado fisico y comparar repo == AWS.
7. Solo despues habilitar el fast path de aplicacion.

### Objetivo de Produccion

Antes de PROD, el stack debe dejar de depender de que el caller de UpdateEnvironment tenga permisos
amplios sobre EC2/S3/CloudFormation. La direccion recomendada es un service role explicito para la
operacion administrada y control plane versionado con CloudFormation/CDK (o equivalente), de modo
que GitHub/CodePipeline solo promueva artefactos y no administre infraestructura de forma incidental.

## 7. IAM: regla aprendida de H3.3

Durante H3.3 se observaron dependencias sucesivas de UpdateEnvironment sobre DescribeSubnets,
DescribeSecurityGroups, DescribeVpcs, DescribeImages y finalmente S3/CloudFormation. Esto demuestra
que UpdateEnvironment con configuracion no es una llamada aislada. Por lo tanto:

```text
NUNCA:   AccessDenied -> agregar 1 permiso -> retry
SIEMPRE: clasificar el cambio -> inspeccionar la operacion compuesta -> disenar el contrato completo -> aplicar una vez
```

El rol de promocion debe conservar permisos de escritura estrictamente scoped. Las lecturas amplias
solo se justifican si son parte documentada del contrato y, preferentemente, quedan encapsuladas en
service roles del servicio administrado.

## 8. CodePipeline y GitHub Actions - papel recomendado

La automatizacion sigue siendo deseable, pero no debe convertirse en requisito para desplegar un
release DEV si el propio pipeline aun esta en proceso de industrializacion. H3.3 demostro que un
camino manual version-only, trazable y pequeno es mas seguro que forzar un pipeline incompleto.

### Estado recomendado de responsabilidades

| Componente | Responsabilidad |
| --- | --- |
| GitHub Actions | CI, tests, seguridad, build de imagen, digest, candidate manifest. No administrar EB directamente en PROD. |
| ECR | Repositorio inmutable de imagenes aprobadas. |
| S3 release/EB bucket | Bundles inmutables, content-addressed o key unica por release. |
| CodePipeline | Orquestacion de promocion cuando el contrato este estabilizado. No almacenar logica privilegiada mutable. |
| Elastic Beanstalk | Ejecutar una Application Version exacta. |
| IaC | IAM, roles, EB config, red, Route53 y demas infraestructura. |
| Operador/Human gate | Acceptance funcional y autorizacion de promociones sensibles. |

### Commands y timeouts

No volver a ejecutar un promotor que mantenga un proceso vivo 30 minutos dentro de una accion
Commands si el token de la accion puede expirar. El command debe iniciar/verificar rapidamente y
salir; la observacion larga debe quedar en un waiter externo o mecanismo nativo con credenciales
renovables.

## 9. Smoke funcional: nuevo gate prioritario

La validacion funcional debe ocurrir inmediatamente despues de que el runtime queda sano. H3.3 habria
detectado antes que CEO/CTO seguia con PII enmascarada y que la accion de asignacion no aparecia.
Esos defectos no eran problemas de AWS; eran acceptance de producto.

### Smoke minimo H3.3/H3.3.1

- Public site responde por HTTPS.
- Backoffice autentica y abre la bandeja.
- CEO/CTO ve PII completa; roles restringidos reciben masking server-side y el HTML no filtra PII.
- Control de asignacion manual visible y utilizable cuando corresponde.
- Asignacion cambia estado a asignado, persiste en tpi.asignaciones y registra tpi.auditoria.
- Refresh conserva el estado y una sola asignacion activa.

Si el smoke falla, el release puede mantenerse desplegado en DEV para diagnostico, pero el hito no
debe declararse plenamente aceptado. La deuda se registra en issue con alcance concreto.

## 10. Base de datos y migraciones

Las migraciones no son parte automatica de cada deploy. Para TPI, 005/006 ya estaban aplicadas en
DEV y no debian reejecutarse durante los intentos de promocion.

Reglas:

- Migracion versionada, idempotente o con precondiciones claras.
- Aplicacion una sola vez y evidencia de version/efecto.
- Deploy de aplicacion nunca "arregla" una falla reejecutando DDL.
- Smoke posterior usa SELECT read-only para verificar invariantes.
- Produccion: separar migration job del application cutover y definir compatibilidad hacia atras.

## 11. Secretos y pruebas autenticadas

La automatizacion no debe leer ni imprimir AUTH_USERS_JSON, DATABASE_PASSWORD,
API_IDEMPOTENCY_HMAC_SECRET o WEB_SESSION_SECRET para demostrar que el sistema funciona. Para smoke
autenticado existen dos opciones validas:

1. Sesion humana con usuario de prueba/rol controlado, sin compartir la contrasena en logs ni chat.
2. Cuenta sintetica de smoke administrada como secreto dedicado, con privilegios minimos, cuyo uso
   pueda automatizarse sin exponer su valor.

Para la validacion DB, preferir una identidad read-only de smoke/inspeccion separada del usuario de
aplicacion. La capacidad de auditar no debe depender de conocer el password productivo de la app.

## 12. Observabilidad y evidencia minima por release

| Dato | Debe quedar registrado |
| --- | --- |
| Git | PR, HEAD candidate, merge SHA. |
| CI | Run ID + resultado. |
| Imagenes | Repositorio + digest app/Caddy. |
| Bundle | SHA256 + S3 bucket/key + VersionId si aplica. |
| Elastic Beanstalk | Application Version + environment + estado final. |
| Smoke | Endpoints y flujo critico PASS/FAIL. |
| DB | Invariantes validadas, sin PII en documentacion. |
| Rollback | Last-known-good VersionLabel. |
| Deuda | Issue asociado y criterio de cierre. |

## 13. Antipatrones que quedan prohibidos

| Antipatron | Por que no |
| --- | --- |
| Permiso por permiso | Agregar cada Action solo porque aparecio en el ultimo error y reintentar. |
| Config + app en el mismo cutover | Cambiar VersionLabel, option settings, IAM y DNS de una sola vez. |
| Retry sin causa cerrada | Volver a ejecutar porque el environment termino sano, sin entender por que fallo. |
| Rebuild para rollback | Reconstruir una imagen antigua en lugar de reutilizar su digest/VersionLabel. |
| Green = acceptance | Dar por bueno un release solo porque EB reporta Green. |
| Smoke al final de todo | Invertir horas en infraestructura antes de probar el feature principal. |
| Secretos como herramienta de diagnostico | Leer passwords o AUTH_USERS_JSON para hacer verificaciones que pueden resolverse con identidades controladas. |
| Documentacion historica como verdad actual | Usar hostnames/version labels antiguos sin distinguir snapshot historico del contrato vigente. |

## 14. Quick runbook - release DEV normal

1. CI verde y candidate congelado
2. Confirmar digests y bundle SHA256
3. Upload a key nueva + verify download hash
4. CreateApplicationVersion nueva
5. Preflight: cuenta / region / source sano / target existe
6. update-environment SOLO --version-label
7. Esperar VersionLabel exacta + Ready/Green/Ok
8. Smoke funcional inmediato
9. SELECT read-only si el feature escribe BD
10. Si PASS: merge candidate a main + CI verde
11. Si FAIL funcional: issue + no mas cambios AWS salvo rollback necesario
12. BITACORA + evidencia + last-known-good

### STOP inmediato si

- la cuenta AWS no es 821656895812 en DEV;
- el environment no esta en el source esperado;
- el bundle/digest no coincide con lo aprobado;
- hay otro update en curso;
- se necesita --option-settings para completar el release;
- aparece un permiso de escritura nuevo no disenado;
- el smoke revela defecto de autorizacion, PII o persistencia.

## 15. Estado actual al cierre de H3.3 (SNAPSHOT HISTORICO 2026-09-12)

> No usar como estado actual. Reverificar siempre contra AWS con lecturas controladas.

| Elemento | Estado 2026-09-12 |
| --- | --- |
| Runtime DEV | h3-3-crm-web-43101be-domainlocked-r1 - Ready / Green / Ok |
| Dominio publico | https://dev.tupensioninteligente.cl - HTTPS OK |
| Backoffice | https://backoffice.dev.tupensioninteligente.cl - HTTPS OK |
| Candidate app | Git SHA 43101be7835088f93267bee85b0f11c8bc879867 |
| Bundle domain-locked | SHA256 007b14d4b439ea59afd13106b71edafbf902e564085581e7577770261c97282f |
| PR #49 | merge e4f63f1ba525df78ddebc8c724838978ed1f65c4 - builder/domain-locked deployment |
| PR #14 | merge 89a1c58643fc228024243d474c47986ab272257f - H3.3 code |
| Main CI cierre | 34701799998 - success |
| H3.3 | CLOSED WITH DEFERRED ACCEPTANCE ITEMS |
| H3.3.1 | Issue #50 OPEN: RBAC/PII + asignacion manual + smoke/DB |
| CodePipeline Promote | Disabled; no usar como camino obligatorio hasta cerrar H3.2 |
| Last-known-good legacy | h3-3-crm-web-28cf009-r1 conservada; no borrar hasta definir politica de retencion |

### Interpretacion

H3.3 queda cerrado administrativamente con deuda funcional explicitamente registrada. El deployment
ya no es el bloqueo principal. La prioridad funcional futura es H3.3.1. La prioridad de plataforma
es H3.2: convertir el fast path aprendido en automatizacion reusable para QA/PROD, con service roles
e IaC en lugar de permisos caller-side descubiertos durante el release.

## 16. Roadmap de industrializacion CI/CD

| Prioridad | Trabajo | Criterio de cierre |
| --- | --- | --- |
| P0 | Mantener fast path version-only documentado y reproducible | Un release DEV de aplicacion se completa sin cambios IAM/EB config y con rollback por VersionLabel. |
| P0 | Corregir deuda H3.3.1 | RBAC/PII y asignacion manual pasan smoke + DB. |
| P1 | IaC del control plane EB | Roles, policies, environment config y Route53 versionados y revisables. |
| P1 | Service role para operaciones administradas | El caller de promocion no necesita permisos amplios transversales para CloudFormation/EC2/S3. |
| P1 | Promocion automatizada version-only | CodePipeline/otro mecanismo consume manifest y AV exacta, sin long-running Commands token. |
| P1 | Smoke automatizado seguro | Usuario sintetico + DB inspector read-only sin revelar secretos. |
| P2 | Retencion/limpieza de AV y bundles | Politica basada en last-known-good y releases aprobados; nunca borrar rollback activo. |
| P2 | Replicar a QA/PROD | Mismo contrato, parametros por ambiente, sin copiar permisos ad hoc. |

## 17. Handoff para el siguiente equipo

El siguiente equipo no debe volver a reconstruir la historia del deployment desde chats o errores
antiguos. Debe partir de esta secuencia:

1. Leer docs/BITACORA.md y distinguir claramente estado actual de registros historicos.
2. Leer este contrato v2 y usar la clasificacion A-E antes de tocar AWS.
3. Para releases de aplicacion, usar version-only fast path.
4. Para H3.3.1, no modificar infraestructura salvo evidencia nueva: el runtime actual esta sano.
5. Para H3.2, industrializar el camino probado; no reactivar a ciegas el pipeline que fallo por
   dependencias caller-side.
6. Antes de PROD, cerrar service roles/IaC, smoke automatizado y politica de rollback/retencion.

### Definition of Done de una entrega profesional

```text
CODIGO:       CI verde + seguridad
ARTEFACTO:    digest + bundle SHA + S3 key
DEPLOY:       VersionLabel exacta + Ready/Green/Ok
PRODUCTO:     smoke critico PASS
DATOS:        invariantes PASS cuando aplica
ROLLBACK:     last-known-good utilizable
TRAZABILIDAD: PR/CI/AV/bitacora
DEUDA:        issue explicito, no conocimiento tribal
```

## 18. Cierre

La velocidad de delivery no proviene de eliminar controles; proviene de eliminar decisiones
innecesarias durante el release. El aprendizaje de H3.3 es que TPI debe desplegar aplicacion por una
ruta corta, inmutable y version-only, y reservar la complejidad de infraestructura para cambios de
infraestructura. Ese desacople reduce blast radius, evita ciclos de IAM reactivo y permite validar el
producto antes de gastar tiempo en el mecanismo de promocion.

Este documento v2 debe considerarse el contrato operativo de referencia para los proximos releases
AWS DEV y la base para el diseno de QA/PROD. Cualquier desviacion debe quedar justificada y
registrada en la bitacora.
