# H2.2 - AWS DEV Deployment

## Scope

This document records the first real DEV deployment of the current Streamlit
backoffice. It deploys the existing Dockerfile to Elastic Beanstalk and keeps
the existing RDS instance external to the environment. It does not introduce
business features, authentication, HTTPS, or H2.3 work.

## Architecture

```text
Authorized browser IP
        |
        v
Elastic Beanstalk: tpi-backoffice-dev (SingleInstance)
        |
        v
EC2 / Docker / Streamlit :8501
        |
        v
Services -> Repositories -> PostgreSQL RDS
```

The Elastic Beanstalk proxy receives HTTP on port 80 and forwards traffic to
the Docker container. Streamlit listens only inside the instance on port 8501.
The container runs as `appuser`, and its Docker healthcheck runs
`python -m scripts.healthcheck_runtime`.

## AWS Resources

Region: `us-east-2`

| Resource | Name or identifier | Purpose |
| --- | --- | --- |
| Elastic Beanstalk application | `tpi-backoffice` | Application versions and DEV environment |
| Elastic Beanstalk environment | `tpi-backoffice-dev` | Docker, Single Instance DEV runtime |
| Platform | Docker on 64bit Amazon Linux 2023 4.13.6 | Managed host platform |
| EC2 instance | Elastic Beanstalk managed `t3.micro` | Runs the Docker container |
| Application SG | `tpi-backoffice-dev-sg` / `sg-0eef93dbf801489b2` | Restricted web ingress and RDS source |
| RDS SG | `tpi-postgres-admin-sg` / `sg-022326409c27878b6` | Existing RDS security group |
| RDS | `tpi-postgres-dev` | Existing external PostgreSQL DEV database |
| Secret | `tpi/dev/database-password` | Password for `tpi_app` |
| CloudWatch Logs | `/aws/elasticbeanstalk/tpi-backoffice-dev/*` | Instance, proxy, Docker and health logs |
| S3 | `elasticbeanstalk-us-east-2-821656895812` | Elastic Beanstalk application bundles |

The active DEV URL is:

`http://tpi-backoffice-dev-821656895812.us-east-2.elasticbeanstalk.com`

## Network Security

- VPC: `vpc-0f86145db5a906b73`.
- Instance subnet: `subnet-0c91f8646aff84d47` in `us-east-2a`.
- The environment is Single Instance in a public subnet, with an Elastic IP
  managed by Elastic Beanstalk.
- `tpi-backoffice-dev-sg` allows TCP/80 only from the authorized tester public
  IP `/32`. It has no inbound TCP/22, TCP/8501, or TCP/5432 rule.
- `DisableDefaultEC2SecurityGroup=true` prevents Elastic Beanstalk from adding
  its default public HTTP security group. The EC2 instance has only the
  application SG attached.
- RDS keeps its existing DBeaver administrative rule. H2.2 adds TCP/5432 with
  source `sg-0eef93dbf801489b2`, never a public CIDR.
- No rule created by H2.2 allows `0.0.0.0/0` inbound traffic.

RDS remains `PubliclyAccessible=true` by the explicit H2.2 constraint. Its
effective PostgreSQL protection is the restricted RDS security group. Changing
that setting is a later hardening task and is not part of this deployment.

## IAM And Secrets

The environment has no AWS access keys in code, Docker, or environment files.

| Principal | Permissions |
| --- | --- |
| `tpi-backoffice-dev-ec2-role` | `AWSElasticBeanstalkWebTier`, `AmazonSSMManagedInstanceCore`, and inline read access only to the DEV database secret |
| `tpi-backoffice-dev-eb-service-role` | `AWSElasticBeanstalkEnhancedHealth` |
| `tpi-backoffice-dev-ec2-profile` | Instance profile containing the EC2 role |

The inline policy in `deployment/iam/tpi-backoffice-dev-read-database-secret.json`
allows only `secretsmanager:GetSecretValue` and `secretsmanager:DescribeSecret`
for this ARN:

`arn:aws:secretsmanager:us-east-2:821656895812:secret:tpi/dev/database-password-Zu4Lk2`

The secret uses the AWS managed Secrets Manager key, so no customer managed KMS
decrypt permission is required. The secret value is never documented or read by
deployment commands.

Elastic Beanstalk injects it natively through the
`aws:elasticbeanstalk:application:environmentsecrets` namespace as
`DATABASE_PASSWORD`. Application code does not call Secrets Manager.

## Runtime Configuration

The versioned configuration is `.ebextensions/01-h2-2-aws-dev.config`.

| Variable | DEV value |
| --- | --- |
| `APP_ENV` | `aws-dev` |
| `APP_NAME` | `TPI Backoffice DEV` |
| `APP_DEBUG` | `false` |
| `DATABASE_HOST` | RDS DEV endpoint |
| `DATABASE_PORT` | `5432` |
| `DATABASE_NAME` / `DATABASE_SCHEMA` | `tpi` / `tpi` |
| `DATABASE_USER` | `tpi_app` |
| `DATABASE_SSLMODE` | `require` |
| `DATABASE_CONNECT_TIMEOUT` | `10` |
| `DATABASE_POOL_MIN_SIZE` / `DATABASE_POOL_MAX_SIZE` | `1` / `5` |
| `DATABASE_POOL_TIMEOUT` | `30` |
| `LOG_LEVEL` | `INFO` |
| `DATABASE_PASSWORD` | Secrets Manager ARN injection only |

## Deployment Procedure

Use the dedicated profile and never use the default AWS profile for TPI:

```powershell
aws sts get-caller-identity --profile tpi-dev
aws configure get region --profile tpi-dev
```

The expected account is `821656895812` and region is `us-east-2`.

1. Run the project tests and quality gates.
2. Build the runtime image locally:

```powershell
docker build --tag tpi-backoffice-h22:<git-sha> .
```

3. Create a source bundle from the reviewed commit:

```powershell
git archive --format=zip --output <git-sha>.zip <git-sha>
```

4. Upload the bundle to the Elastic Beanstalk bucket, create an application
   version, then update `tpi-backoffice-dev` to that version.
5. Wait for `Status=Ready` and `Health=Green` before testing the URL.

`.gitattributes` marks `docker-compose.yml` as `export-ignore`. Compose is for
local development only; excluding it ensures the Elastic Beanstalk Docker
platform uses the repository Dockerfile rather than trying to launch local
PostgreSQL services.

## Health Checks And Smoke Test

The completed deployment validated:

```powershell
Invoke-WebRequest http://tpi-backoffice-dev-821656895812.us-east-2.elasticbeanstalk.com/_stcore/health
Invoke-WebRequest http://tpi-backoffice-dev-821656895812.us-east-2.elasticbeanstalk.com/
```

Expected results are HTTP 200 and `ok` for `/_stcore/health`, and HTTP 200 for
the main page. The endpoint is reachable only from the temporarily authorized
public IP.

For a managed, non-SSH diagnostic, use SSM with the existing instance role to
inspect Docker and run the existing readiness command. The successful check
must report:

- Docker container state `healthy`.
- Container user `appuser`.
- `all_ready=True`, `connected=True`, `schema_accessible=True`, and
  `leads_accessible=True`.

Those checks exercise PostgreSQL SSL connectivity, the `tpi` schema,
`tpi.leads`, and required catalogs. They are read-only and do not create leads.

## Logging And Observability

Application logging writes to stdout, and Elastic Beanstalk streams Docker,
nginx, engine, hook, and environment-health logs to CloudWatch Logs. Retention
is seven days and groups are retained if the environment is terminated.

Never log passwords, tokens, connection strings with credentials, RUTs, email
addresses, telephone numbers, or full lead payloads. Review application logs
after a deployment and before operational handoff. The H2.2 smoke validation
used aggregate pattern checks only; it did not print application log content.

## Costs

The following resources incur cost while retained or active:

- `t3.micro` EC2 instance and its EBS volume.
- Elastic IP while allocated, especially if not attached to a running instance.
- S3 application-version bundles.
- CloudWatch Logs storage after the free tier.
- Secrets Manager secret.
- Existing RDS DEV, which is external to Elastic Beanstalk and predates H2.2.

Single Instance has no load balancer or NAT Gateway cost. Terminating the
environment stops EC2 cost, but does not delete the external RDS, secret, S3
versions, or retained CloudWatch groups.

## Rollback

Application rollback:

1. Identify the previous Elastic Beanstalk application version.
2. Run `aws elasticbeanstalk update-environment` with that version label.
3. Wait for `Ready` and `Green`, then repeat the smoke test.

Environment rollback:

1. Terminate only `tpi-backoffice-dev` if the environment itself must be
   removed.
2. Confirm Elastic Beanstalk has released the instance and EIP.
3. Revoke only the H2.2 SG-to-SG TCP/5432 rule from the RDS SG.
4. Delete `tpi-backoffice-dev-sg` only after it is detached.
5. Remove the H2.2 IAM profile, roles, and inline policy only after the
   environment is gone.
6. Retain `tpi/dev/database-password` unless an approved credential rotation
   plan says otherwise.

Never terminate, recreate, or delete `tpi-postgres-dev` as part of rollback.
The existing DBeaver rule must remain intact.

## Limitations And Follow-up

- The environment is HTTP-only and temporarily IP restricted. HTTPS and the
  definitive access mechanism are outside H2.2.
- Single Instance has no high availability, load balancer, or automatic scale
  out. It is suitable only for low-cost DEV.
- RDS remains publicly addressable; its SG is restricted, but moving it to a
  private design belongs to a separately approved hardening effort.
- Rotate the database password through Secrets Manager and redeploy or restart
  the environment to refetch it.
- Do not begin H2.3 from this document without approval.
