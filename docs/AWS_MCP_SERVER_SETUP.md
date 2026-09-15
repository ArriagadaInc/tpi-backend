# AWS MCP Server (Agent Toolkit) — Setup

> Estado: configurado y verificado (2026). Cuenta `821656895812` · perfil `tpi-dev` · región del servicio MCP `us-east-1`.

## Resumen

Se conectó el servidor **AWS MCP Server (Agent Toolkit)** al agente DSH (DeepSeek Harness) mediante el plugin `@deepseek-ai/dsh-mcp-client` y el proxy local [`mcp-proxy-for-aws`](https://github.com/aws/mcp-proxy-for-aws).

El endpoint administrado de AWS MCP usa autenticación **SigV4 (IAM)**, que los clientes MCP estándar no implementan. Por eso se interpone un proxy local (`mcp-proxy-for-aws-cli`) que firma las peticiones con las credenciales locales del perfil `tpi-dev`.

## Arquitectura

```
DSH (dsh-mcp-client)  ──stdio──▶  uvx mcp-proxy-for-aws-cli  ──SigV4──▶  https://aws-mcp.us-east-1.api.aws/mcp
```

- Transporte: `stdio` (el proxy corre como proceso local).
- Las tools aparecen en DSH con nombre `mcp__aws__<rawName>`.

## Configuración

Archivo: `C:\Users\Usuario\.dsh\cordis.patch.yml` (capa de parche de nivel `$DSH_HOME`, aplica a todos los perfiles).

```yaml
- id: mcp-aws
  name: '@deepseek-ai/dsh-mcp-client'
  config:
    serverName: aws
    transport: stdio
    command: uvx
    args:
      - 'mcp-proxy-for-aws-cli@latest'
      - 'https://aws-mcp.us-east-1.api.aws/mcp'
      - '--region'
      - 'us-east-1'
    env:
      AWS_MCP_PROXY_PROFILES: tpi-dev
```

- `AWS_MCP_PROXY_PROFILES` (no `AWS_PROFILE`) es lo que usa el proxy para localizar el perfil; admite varios perfiles separados por espacio para cambio de cuenta por llamada.
- El perfil se lee del disco en cada petición; no pasan secretos por el entorno del proceso.

## Tools disponibles (8)

| Tool | readOnly | destructive | Descripción |
|---|---|---|---|
| `aws___search_documentation` | ✅ | — | Búsqueda en docs AWS (chunks literales de página) |
| `aws___read_documentation` | ✅ | — | Leer página completa de docs como markdown |
| `aws___retrieve_skill` | ✅ | — | Recuperar una skill AWS (SKILL.md o archivo) |
| `aws___get_regional_availability` | ✅ | — | Disponibilidad de recursos por región |
| `aws___list_regions` | ✅ | — | Listar regiones AWS |
| `aws___get_tasks` | ✅ | — | Estado de tareas largas (polling) |
| `aws___get_presigned_url` | ❌ | — | Generar URL prefirmada |
| `aws___run_script` | ❌ | ⚠️ **sí** | Ejecutar script (capacidad destructiva) |

## Modo solo-lectura vs completo

- **Solo-lectura**: agregar `--read-only` a `args` oculta `aws___get_presigned_url` y `aws___run_script`, dejando 6 tools de consulta. Es el modo recomendado durante diagnósticos (ver `AGENTS.md`).
- **Completo**: sin `--read-only` se exponen las 8 tools, incluida `aws___run_script` (destructiva).

```yaml
    args:
      - 'mcp-proxy-for-aws-cli@latest'
      - 'https://aws-mcp.us-east-1.api.aws/mcp'
      - '--region'
      - 'us-east-1'
      - '--read-only'          # ← quitar para modo completo
```

## Prerrequisitos

- AWS CLI v2 instalado.
- `uv`/`uvx` instalado (el proxy se descarga bajo demanda la primera vez).
- Sesión AWS activa: `aws login --profile tpi-dev` (credenciales válidas ~12 h, renovables 90 días).
- Perfil `tpi-dev` apuntando a la cuenta `821656895812`.

## Verificación

Listar las tools reales del endpoint (handshake MCP):

```powershell
# credenciales
aws sts get-caller-identity --profile tpi-dev   # → Account: 821656895812

# proxy instalable/ejecutable
uvx mcp-proxy-for-aws-cli@latest --help         # → MCP Proxy for AWS vX.Y.Z
```

Tras recargar/reiniciar la sesión DSH, las tools deben aparecer como `mcp__aws__*`.

## Notas

- La extensión CLI `aws agent-toolkit` no es necesaria para MCP (el proxy va directo al endpoint). Se instala opcionalmente con `aws configure agent-toolkit --yes --region us-east-1 --profile tpi-dev`.
- El catálogo completo capturado queda en `aws-mcp-tools-full.json` (raíz del repo).
- El endpoint solo existe en `us-east-1`; los recursos TPI se operan en `us-east-2` (ver `AGENTS.md`).

## Referencias

- [mcp-proxy-for-aws (GitHub)](https://github.com/aws/mcp-proxy-for-aws)
- [Agent Toolkit for AWS — setup](https://github.com/aws/agent-toolkit-for-aws/blob/main/setup-instructions/setup.md)
