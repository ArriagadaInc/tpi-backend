# H3.3 DEV Domain Cutover

## 1. Contexto

El objetivo de este trabajo fue migrar el dominio DEV publico desde el uso temporal de `dev.genialabs.cl` hacia el dominio oficial `dev.tupensioninteligente.cl`, preservando HTTPS valido, manteniendo rollback y evitando impacto sobre produccion.

La estrategia se ejecuto en AWS DEV y se mantuvo el environment anterior disponible como respaldo durante todo el proceso.

## 2. Arquitectura Final

Flujo final:

```text
dev.tupensioninteligente.cl
-> DataTecno
-> NS delegados de Route 53
-> AWS Route 53 Hosted Zone
-> Alias A
-> tpi-backoffice-dev-green
-> Caddy
-> aplicacion
```

Recursos finales relevantes:

| Elemento | Valor |
|---|---|
| Hosted Zone del nuevo dominio | `Z07053592LX0W8GJXNI1C` |
| Environment activo | `tpi-backoffice-dev-green` |
| CNAME del environment | `tpi-backoffice-dev-ecr.us-east-2.elasticbeanstalk.com` |
| VersionLabel | `h2-5d-ecr-47fa0c9` |

## 3. Delegacion DNS

La delegacion de `dev.tupensioninteligente.cl` ya estaba creada en DataTecno hacia los 4 NS públicos de AWS Route 53:

- `ns-1081.awsdns-07.org`
- `ns-1594.awsdns-07.co.uk`
- `ns-607.awsdns-11.net`
- `ns-461.awsdns-57.com`

El dominio principal `tupensioninteligente.cl` no fue migrado ni alterado.

## 4. Problema TLS Inicial

Los sintomas iniciales fueron:

- DNS resolvia correctamente.
- `http://dev.tupensioninteligente.cl` llegaba a Caddy.
- HTTP respondia `308 Permanent Redirect` hacia HTTPS.
- `https://dev.tupensioninteligente.cl` fallaba durante el handshake TLS.

Esto permitio descartar un problema basico de DNS y conectividad.

## 5. Diagnostico ACME

La investigacion mostro que:

- Caddy si reconocia el nuevo hostname en su config efectiva.
- Caddy si intentaba emitir certificado.
- El challenge usado era DNS-01 con Route 53.
- Primero aparecieron errores IAM sobre Route 53.
- Luego se identifico que el provider estaba intentando operar sobre la hosted zone incorrecta.

## 6. Causa Raiz Final de TLS

La causa raiz quedo en `deployment/caddy/Caddyfile`.

Existia un `hosted_zone_id Z0562050FYDQE12LRGMA` hardcodeado para `dev.genialabs.cl`.

Como el snippet DNS-01 era compartido por:

- `dev.genialabs.cl`
- `dev.tupensioninteligente.cl`

Caddy intentaba crear:

```text
_acme-challenge.dev.tupensioninteligente.cl
```

dentro de la hosted zone de `dev.genialabs.cl`, lo que producia:

```text
InvalidChangeBatch
```

La solucion fue separar la configuracion DNS-01 por hosted zone.

## 7. Configuracion Caddy Final

Quedo separada asi:

| Hostname | Hosted Zone |
|---|---|
| `dev.genialabs.cl` | `Z0562050FYDQE12LRGMA` |
| `dev.tupensioninteligente.cl` | `Z07053592LX0W8GJXNI1C` |
| `backoffice.dev.genialabs.cl` | Configuracion anterior asociada a `dev.genialabs.cl` |

La evidencia runtime en `/config/caddy/autosave.json` confirmo esa separacion.

## 8. IAM

Rol involucrado:

- `tpi-backoffice-dev-ec2-role`

Policy ajustada:

- `CaddyRoute53AcmeDev`

La policy quedo restringida para permitir `route53:ChangeResourceRecordSets` solo sobre la hosted zone correcta del nuevo dominio y solo para el challenge TXT requerido.

No se expusieron secretos ni credenciales en ningun momento.

## 9. Problema de Deployment del Environment Antiguo

Al intentar actualizar `tpi-backoffice-dev` con Elastic Beanstalk, aparecio:

```text
Service role is required. It can't be removed.
```

La evidencia recolectada indico que:

- ambos environments tenian configuraciones de alto nivel equivalentes;
- incluso un `UpdateEnvironment` limpio con solo `VersionLabel` fallaba;
- el problema estaba asociado al estado historico del environment activo antiguo;
- se detuvo el intento de seguir forzando ese environment para no bloquear el avance.

## 10. Decision Blue/Green

Se eligio `tpi-backoffice-dev-green` como environment candidato y luego activo porque:

- acepto correctamente los bundles nuevos;
- estuvo `Ready / Green / Ok`;
- permitio validar TLS y el nuevo dominio antes del cutover;
- mantuvo `tpi-backoffice-dev` disponible como rollback.

## 11. Release Desplegado

Evidencia del release:

| Item | Valor |
|---|---|
| Commit | `47fa0c92e2fb9fc916309ac219410fffb08f7cbc` |
| VersionLabel | `h2-5d-ecr-47fa0c9` |
| Bundle | `s3://elasticbeanstalk-us-east-2-821656895812/deployments/h2-5d-ecr-47fa0c9.zip` |
| SHA256 | `e62d039cdfe4e11e1c6fc1aacf13cb6182ba2480217ca5e395eaa520e2621cb7` |

## 12. Certificado TLS

Certificado emitido para `dev.tupensioninteligente.cl`:

| Campo | Valor |
|---|---|
| SAN | `dev.tupensioninteligente.cl` |
| Subject | `CN=dev.tupensioninteligente.cl` |
| Issuer | `Let's Encrypt / YE2` |
| Not Before | `Aug 25 15:42:31 2026 GMT` |
| Not After | `Nov 23 15:42:30 2026 GMT` |

Evidencia de Caddy:

- `trying to solve challenge`
- `authorization finalized`
- `certificate obtained successfully`

Luego de la emision, el TXT del challenge no quedo residual en la hosted zone.

## 13. Cutover Route 53

Cambio realizado:

| Campo | Valor |
|---|---|
| Route 53 change ID | `/change/C07728531YUZDTD2H4Z7S` |
| Estado | `INSYNC` |
| Nuevo target | `tpi-backoffice-dev-ecr.us-east-2.elasticbeanstalk.com.` |
| IP observada | `52.15.131.208` |

El DNS apunta al environment, no a una EC2 individual.

## 14. Validacion Final

Evidencia final del comportamiento publico:

| URL | Resultado |
|---|---|
| `http://dev.tupensioninteligente.cl` | `308 Permanent Redirect` |
| `https://dev.tupensioninteligente.cl/` | `200` |
| `https://dev.tupensioninteligente.cl/simulador.html` | `200` |
| `https://dev.tupensioninteligente.cl/api/v1/catalogs` | `200` |

Estado del environment:

| Campo | Valor |
|---|---|
| Environment | `tpi-backoffice-dev-green` |
| Estado | `Ready / Green / Ok` |
| VersionLabel | `h2-5d-ecr-47fa0c9` |

Los access logs de Caddy confirmaron trafico publico real llegando al environment green.

## 15. Compatibilidad Temporal

`dev.genialabs.cl` continuo operativo temporalmente como respaldo.

No se considera el dominio definitivo a futuro.

El dominio DEV oficial a futuro es:

- `dev.tupensioninteligente.cl`

## 16. Rollback

Rollback inmediato:

1. Restaurar el alias de Route 53 al target anterior.
2. No modificar Caddy, IAM ni la version green para volver al estado previo.
3. Mantener `tpi-backoffice-dev` disponible temporalmente como respaldo.

## 17. Pendientes

Pendientes controlados:

- observar estabilidad de `dev.tupensioninteligente.cl`;
- retirar posteriormente `dev.genialabs.cl`;
- simplificar configuracion Caddy/IAM asociada al dominio antiguo;
- evaluar decomisionamiento de `tpi-backoffice-dev`;
- incorporar estos aprendizajes en `H3.2 Deployment Reproducible & Runbook`.

## 18. Lecciones Aprendidas

- Un deploy exitoso no demuestra por si solo que el artefacto contenga el cambio esperado.
- Siempre validar la configuracion efectiva/runtime, no solo el repo.
- El `VersionLabel` debe poder asociarse mecanicamente con commit, bundle y hash.
- Distinguir DNS, TLS, ACME, IAM y runtime acelera el troubleshooting.
- Evitar `hosted_zone_id` globales hardcodeados cuando existen multiples zonas.
- Validar con `curl --resolve` antes de realizar un cutover publico.
- Mantener rollback independiente del cambio principal.
- Blue/green permitio avanzar sin comprometer el environment anterior.

