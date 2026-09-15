---
document: Lecciones de deploy AWS H3.2/H3.3 - extractos no cubiertos por BEST_PRACTICES
authority: lessons_only
imported_at: 2026-09-14
originals:
  - file: "Lecciones_Aprendidas_Deployment_AWS_TPI H3.2.docx"
    date: 2026-09-04
    sha256: 6d65d7a02ab35851fd818829cf6b8591e253b553eccf4007063ffcab78a8482b
  - file: "Lecciones_Aprendidas_Deploy_AWS_TPI H3.3.docx"
    date: 2026-09-04
    sha256: 1c80e85acb5f268c2131f579fd9ef1379ac2f37be7acc6ae35756c1b81c6bba5
  - file: TPI_Lecciones_Aprendidas_Deploy_AWS_H3_3.pdf
    date: 2026-09-07
    sha256: 10882e1ab5190aadc151ff9e05c27ab11c0a211c6b58177beea9ba4b82930701
consolidated_elsewhere: docs/AWS_DEPLOYMENT_BEST_PRACTICES.md (principios 1-10 y antipatrones)
---

# Lecciones de deploy AWS H3.2/H3.3 (extractos)

Este documento conserva **solo** conocimiento de los documentos originales que no quedo consolidado
en `docs/AWS_DEPLOYMENT_BEST_PRACTICES.md`. Los IDs de runs, SHAs, digests, version labels y
environments de los originales son **historicos** y se omitieron a proposito: no representan
estado actual ni candidatos de rollback.

La autoridad normativa vigente es `docs/cicd/TPI_Contrato_CICD_AWS_v2.md`. Estas lecciones explican
el porque de sus reglas y alimentan skills de Reviewer y Deployer.

## 1. Lecciones de control plane (origen: H3.3 docx, 2026-09-04)

- **LL-01 Data plane vs control plane.** `PutObject`/`GetObject` sobre el ZIP es acceso al artefacto.
  `CreateApplicationVersion` y `UpdateEnvironment` son control plane de EB y pueden interactuar con
  el bucket administrado y sus controles. No asumir que quien puede leer el ZIP puede operar EB.
- **LL-02 El nombre de una API no define todos sus permisos efectivos.** `UpdateEnvironment` llego a
  exigir `s3:CreateBucket`; `CreateApplicationVersion` con procesamiento exigio
  `s3:PutBucketOwnershipControls`. Una lectura como `DescribeConfigurationSettings` tambien disparo
  dependencias caller-side (commits #41/#43). Validar contra documentacion oficial antes del release.
- **LL-03 Los flags cambian el contrato del servicio.** `--process` activa validaciones server-side y
  dependencias extra. Con `--no-process` la Application Version queda `UNPROCESSED`, que es un estado
  **valido** para el flujo elegido; validar `SourceBundle` y `Status != FAILED`.
- **LL-04 Un paso fallido puede haber dejado efectos parciales.** El exit code del job no describe el
  estado final de AWS. Tras cualquier error de escritura: postflight read-only e inventario de
  residuos (ninguno / objeto S3 / Application Version / environment en transicion) antes de
  cualquier retry o cleanup.
- **LL-05 Reanudable e idempotente.** Reconocer un candidate existente, validar que su SourceBundle y
  digests coincidan exactamente y continuar desde un estado seguro. Nunca borrar y recrear para
  reintentar.
- **LL-06 Rollback no significa rollback automatico.** Primero determinar si el environment cambio.
  Si `UpdateEnvironment` fue rechazado, no corresponde rollback. Solo ante transicion real o estado
  degradado.
- **LL-07 Observabilidad de fallos es parte del deployment.** Eventos y estados deben recopilarse
  siempre que haya existido una tentativa de `UpdateEnvironment`, incluso si el comando fallo.
- **LL-08 Candidate inmutable reduce el espacio de diagnostico.** Nunca regenerar imagen o bundle para
  arreglar un problema de IAM/control plane salvo que la causa raiz este dentro del artefacto.
- **LL-09 Least privilege no es permiso minimo por intuicion.** Elegir primero la arquitectura de
  deployment soportada y despues derivar el rol minimo coherente con ella.
- **LL-10 Retries automaticos solo para lecturas idempotentes.** Un retry automatico de writes AWS
  puede duplicar residuos o cambiar el environment sin diagnostico.

### Checklist posterior a cualquier fallo AWS (generalizado)

1. Detener reintentos automaticos.
2. Consultar el estado real del environment.
3. Consultar si se creo o modifico la Application Version.
4. Verificar el objeto S3 y su checksum.
5. Recopilar eventos EB recientes.
6. Clasificar el residuo.
7. No hacer rollback si `UpdateEnvironment` nunca fue aceptado.
8. No limpiar hasta comprender si el residuo es reutilizable de forma segura.
9. Registrar causa y decision antes de otro intento.

## 2. Lecciones de release path (origen: H3.2 docx, 2026-09-04)

- **LL-11 El service role de EB es parte del contrato.** Un update con configuracion incompleta fue
  rechazado (`Service role is required`). Refuerza el cutover version-only sin option settings.
- **LL-12 DNS, Caddy y ACME son parte del release.** Una hosted zone fija en el Caddyfile rompio TLS
  mientras EB estaba sano. Mantener topologia explicita por dominio/zona (hoy: bundle domain-locked)
  y validar DNS, HTTP->HTTPS y certificado despues del cutover.
- **LL-13 Un patch local no implica que el bundle desplegado lo contenga.** Verificar contenido y hash
  del bundle antes y despues de subirlo y asociarlo a la Application Version.
- **LL-14 Operaciones criticas necesitan logs estructurados y buscables** (`event_name`, release,
  environment, identificador tecnico no sensible, resultado). La busqueda de eventos forma parte del
  smoke.
- **LL-15 Las herramientas locales pueden fallar sin que el servicio falle.** `curl` de Windows fue
  bloqueado por `schannel`. Ante dudas TLS/red validar desde al menos un segundo cliente
  independiente antes de diagnosticar AWS.
- **LL-16 Registro minimo de release.** Commit y tree SHA, run ID, cuenta, region, environment,
  digests app/Caddy, bundle SHA256, Application Version, runtime observado y estados CI / runtime /
  smoke. Criterio de madurez: otra persona puede tomar el SHA aprobado y demostrar sin suposiciones
  que se desplego, que corre, que pruebas pasaron y como volver atras.

**OUTDATED en el documento H3.2:** la disciplina Blue/Green con swap de CNAME, `release.yml` y "deploy
solo a Green". Hoy existe un unico environment operativo y el rollback es version-only a una
VersionLabel conocida (`AWS_DEPLOYMENT_BEST_PRACTICES.md`, seccion Nomenclatura).

## 3. Lecciones de pipeline (origen: H3.3 pdf, 2026-09-07; aplicables al infra path / H3.2)

- **LL-17 Una transicion de promocion habilitada o ejecutada sin autorizacion** exige detener todo y
  auditar la cadena de autorizacion.
- **LL-18 Validar provisioning por estados y action executions**, no por mensajes opcionales.
- **LL-19 El tooling privilegiado debe descargarse desde una ubicacion protegida y verificarse por
  SHA-256 antes de ejecutarse**; GitHub no debe poder modificarlo.
- **LL-20 Condicionar la escritura sobre EB a la Application Version autorizada**
  (`elasticbeanstalk:FromApplicationVersion`) cuando exista un rol de promocion dedicado.
