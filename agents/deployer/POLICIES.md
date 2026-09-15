# Deployer — POLICIES

Resumen legible. Fuente maquina: `harness/policies.yaml` (`roles.deployer`, `aws.state_modes`).

| Estado | AWS (via aws_guard) | Otras capacidades |
| --- | --- | --- |
| MERGING | Ninguno | `gh pr merge --squash --match-head-commit <reviewed_sha>` |
| PREPARING_DEPLOYMENT | read + `s3api put-object` content-addressed + `create-application-version --no-process` | `gh workflow run publish-dev-ecr-images.yml`, build local en `.harness-release/` |
| WAITING_HUMAN_APPROVAL | Ninguno | Ninguna (estado humano) |
| DEPLOYING | read + `update-environment` a la version aprobada (1 intento) | — |
| VERIFYING | read (logs solo conteos) | smoke HTTP sin credenciales |
| DEPLOY_FAILED / VERIFY_FAILED | read | clasificacion de fallo |
| ROLLING_BACK | read + `update-environment` al LKG aprobado (1 intento) | — |
| DONE / IDLE / BLOCKED_HUMAN | Ninguno | — |

Siempre prohibido: modificar codigo o tooling, IAM, Route53, secretos, migraciones, `--option-settings`,
borrar/recrear AV o objetos, terminar/reconstruir/swap environments, CodePipeline, `run_script`,
`get_presigned_url`, reintentar writes, operar fuera de la cuenta/region DEV, runtime distinto de Claude Code.
