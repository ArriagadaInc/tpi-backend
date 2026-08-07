# 🚀 Guía de Deployment a Producción

**Instrucciones paso a paso para desplegar a AWS/Cloud**

---

## Índice

1. [Prerequisitos](#prerequisitos)
2. [Preparación Local](#preparación-local)
3. [AWS RDS (Base de Datos)](#aws-rds-base-de-datos)
4. [AWS ECS + Fargate (App)](#aws-ecs--fargate-app)
5. [Configuración de Seguridad](#configuración-de-seguridad)
6. [Monitoreo y Logs](#monitoreo-y-logs)
7. [Backup y Recuperación](#backup-y-recuperación)
8. [Rollback](#rollback)

---

## Prerequisitos

### Requerimientos

- AWS Account activa
- AWS CLI instalado y configurado
- Docker instalado localmente
- Git para versionamiento
- Domain name (ej: api.tupensioninteligente.cl)

### Instalar AWS CLI

```bash
# Windows
msiexec.exe /i https://awscli.amazonaws.com/AWSCLIV2.msi

# Linux/Mac
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
sudo ./aws/install

# Verificar
aws --version
```

### Configurar AWS CLI

```bash
aws configure
# Ingresar:
# AWS Access Key ID: [tu-key-id]
# AWS Secret Access Key: [tu-secret-key]
# Default region: us-east-1
# Default output format: json
```

---

## Preparación Local

### 1. Actualizar Versión

```bash
# En pyproject.toml:
# version = "1.0.0"  →  version = "1.0.1"

# En código:
# st.caption("Version: 0.1.0 MVP")  →  "Version: 1.0.1"
```

### 2. Crear Dockerfile

```dockerfile
# Dockerfile
FROM python:3.12-slim

WORKDIR /app

# Instalar dependencias del sistema
RUN apt-get update && apt-get install -y \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copiar requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código
COPY . .

# Exponer puerto Streamlit
EXPOSE 8501

# Health check
HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health || exit 1

# Ejecutar Streamlit
CMD ["streamlit", "run", "app/streamlit_app.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0"]
```

### 3. Crear .dockerignore

```
# .dockerignore
.env
.venv
__pycache__
.pytest_cache
.git
.gitignore
README.md
QUICKSTART.md
*.pyc
logs/
htmlcov/
```

### 4. Extraer dependencias

```bash
# Generar requirements.txt
pip freeze > requirements.txt

# O usar poetry
poetry export -f requirements.txt --output requirements.txt
```

### 5. Hacer commit

```bash
git add .
git commit -m "chore: prepare v1.0.1 for production"
git push origin main
```

---

## AWS RDS (Base de Datos)

### Crear Instancia RDS

```bash
# Variables
REGION="us-east-1"
DB_INSTANCE_ID="tpi-backoffice-prod"
DB_NAME="tpi_prod"
DB_USER="tpi_prod_user"
DB_PASSWORD="<inject-at-runtime>"

# Crear instancia
aws rds create-db-instance \
    --db-instance-identifier "$DB_INSTANCE_ID" \
    --db-instance-class "db.t3.micro" \
    --engine "postgres" \
    --engine-version "15.4" \
    --master-username "$DB_USER" \
    --master-user-password "$DB_PASSWORD" \
    --allocated-storage 20 \
    --storage-type "gp3" \
    --storage-encrypted \
    --vpc-security-group-ids "sg-xxxxxx" \
    --db-subnet-group-name "default" \
    --no-publicly-accessible \
    --backup-retention-period 30 \
    --preferred-backup-window "03:00-04:00" \
    --preferred-maintenance-window "mon:04:00-mon:05:00" \
    --multi-az \
    --region "$REGION"

# Esperar a que se cree (puede tardar 10-15 minutos)
aws rds wait db-instance-available \
    --db-instance-identifier "$DB_INSTANCE_ID" \
    --region "$REGION"
```

### Configurar Endpoint

```bash
# Obtener endpoint
aws rds describe-db-instances \
    --db-instance-identifier tpi-backoffice-prod \
    --query 'DBInstances[0].Endpoint.Address' \
    --output text

# Resultado: tpi-backoffice-prod.xxxxx.us-east-1.rds.amazonaws.com
```

### Restaurar Base de Datos

```bash
# 1. Exportar esquema desde local
pg_dump -h localhost \
        -U tpi_app \
        -d tpi_local \
        --schema-only > schema.sql

# 2. Conectarse a RDS y restaurar
psql -h tpi-backoffice-prod.xxxxx.us-east-1.rds.amazonaws.com \
     -U tpi_prod_user \
     -d tpi_prod \
     -f schema.sql

# 3. Verificar
psql -h tpi-backoffice-prod.xxxxx.us-east-1.rds.amazonaws.com \
     -U tpi_prod_user \
     -d tpi_prod \
     -c "SELECT COUNT(*) FROM tpi.personas"
```

### Crear Credenciales Seguras

```bash
# Guardar en AWS Secrets Manager
aws secretsmanager create-secret \
    --name tpi/prod/database-password \
    --description "PostgreSQL RDS password for TPI backoffice" \
    --secret-string "{\"password\": \"$DB_PASSWORD\"}" \
    --region us-east-1

# Recuperar después (en aplicación)
aws secretsmanager get-secret-value \
    --secret-id tpi/prod/database-password \
    --region us-east-1
```

---

## AWS ECS + Fargate (App)

### 1. Crear repositorio ECR

```bash
# Crear ECR repository
aws ecr create-repository \
    --repository-name tpi-backoffice \
    --region us-east-1 \
    --image-scan-on-push \
    --encryption-configuration encryptionType=AES256

# Resultado:
# "repositoryUri": "123456789.dkr.ecr.us-east-1.amazonaws.com/tpi-backoffice"
```

### 2. Login a ECR

```bash
# Obtener token
aws ecr get-login-password --region us-east-1 | \
    docker login --username AWS --password-stdin \
    123456789.dkr.ecr.us-east-1.amazonaws.com
```

### 3. Build y Push Docker

```bash
# Build
docker build -t 123456789.dkr.ecr.us-east-1.amazonaws.com/tpi-backoffice:1.0.1 .

# Push
docker push 123456789.dkr.ecr.us-east-1.amazonaws.com/tpi-backoffice:1.0.1

# Verificar
aws ecr describe-images \
    --repository-name tpi-backoffice \
    --region us-east-1
```

### 4. Crear Cluster ECS

```bash
# Crear cluster Fargate
aws ecs create-cluster \
    --cluster-name tpi-backoffice-prod \
    --capacity-providers FARGATE FARGATE_SPOT \
    --default-capacity-provider-strategy capacityProvider=FARGATE,weight=1,base=1 \
    --region us-east-1
```

### 5. Crear Task Definition

```bash
# Crear archivo task-definition.json
cat > task-definition.json << 'EOF'
{
  "family": "tpi-backoffice-prod",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "512",
  "memory": "1024",
  "containerDefinitions": [
    {
      "name": "tpi-backoffice",
      "image": "123456789.dkr.ecr.us-east-1.amazonaws.com/tpi-backoffice:1.0.1",
      "portMappings": [
        {
          "containerPort": 8501,
          "protocol": "tcp"
        }
      ],
      "environment": [
        {
          "name": "ENVIRONMENT",
          "value": "production"
        }
      ],
      "secrets": [
        {
          "name": "DATABASE_HOST",
          "valueFrom": "arn:aws:secretsmanager:us-east-1:123456789:secret:tpi/prod/database-host"
        },
        {
          "name": "DATABASE_PASSWORD",
          "valueFrom": "arn:aws:secretsmanager:us-east-1:123456789:secret:tpi/prod/database-password"
        }
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/tpi-backoffice",
          "awslogs-region": "us-east-1",
          "awslogs-stream-prefix": "ecs"
        }
      },
      "healthCheck": {
        "command": ["CMD-SHELL", "curl -f http://localhost:8501/_stcore/health || exit 1"],
        "interval": 30,
        "timeout": 5,
        "retries": 3,
        "startPeriod": 60
      }
    }
  ],
  "executionRoleArn": "arn:aws:iam::123456789:role/ecsTaskExecutionRole",
  "taskRoleArn": "arn:aws:iam::123456789:role/ecsTaskRole"
}
EOF

# Registrar
aws ecs register-task-definition \
    --cli-input-json file://task-definition.json \
    --region us-east-1
```

### 6. Crear Servicio ECS

```bash
# Crear servicio
aws ecs create-service \
    --cluster tpi-backoffice-prod \
    --service-name tpi-backoffice-service \
    --task-definition tpi-backoffice-prod:1 \
    --desired-count 2 \
    --launch-type FARGATE \
    --network-configuration "awsvpcConfiguration={subnets=[subnet-xxxxx,subnet-yyyyy],securityGroups=[sg-zzzzz],assignPublicIp=ENABLED}" \
    --load-balancers targetGroupArn=arn:aws:elasticloadbalancing:us-east-1:123456789:targetgroup/tpi-backoffice/xxxxx,containerName=tpi-backoffice,containerPort=8501 \
    --region us-east-1
```

### 7. Configurar Auto-Scaling

```bash
# Registrar target group
aws application-autoscaling register-scalable-target \
    --service-namespace ecs \
    --resource-id service/tpi-backoffice-prod/tpi-backoffice-service \
    --scalable-dimension ecs:service:DesiredCount \
    --min-capacity 2 \
    --max-capacity 10 \
    --region us-east-1

# Crear política de auto-scaling
aws application-autoscaling put-scaling-policy \
    --policy-name tpi-backoffice-scaling \
    --service-namespace ecs \
    --resource-id service/tpi-backoffice-prod/tpi-backoffice-service \
    --scalable-dimension ecs:service:DesiredCount \
    --policy-type TargetTrackingScaling \
    --target-tracking-scaling-policy-configuration "TargetValue=70,PredefinedMetricSpecification={PredefinedMetricType=ECSServiceAverageCPUUtilization},ScaleOutCooldown=60,ScaleInCooldown=300" \
    --region us-east-1
```

---

## Configuración de Seguridad

### 1. HTTPS/SSL

```bash
# Crear certificado en AWS Certificate Manager
aws acm request-certificate \
    --domain-name api.tupensioninteligente.cl \
    --domain-name "*.tupensioninteligente.cl" \
    --validation-method DNS \
    --region us-east-1

# Crear Application Load Balancer con HTTPS
aws elbv2 create-listener \
    --load-balancer-arn arn:aws:elasticloadbalancing:us-east-1:123456789:loadbalancer/app/tpi-backoffice/xxxxx \
    --protocol HTTPS \
    --port 443 \
    --certificate-arn arn:aws:acm:us-east-1:123456789:certificate/xxxxx \
    --default-actions Type=forward,TargetGroupArn=arn:aws:elasticloadbalancing:us-east-1:123456789:targetgroup/tpi-backoffice/xxxxx
```

### 2. WAF (Web Application Firewall)

```bash
# Crear Web ACL
aws wafv2 create-web-acl \
    --name tpi-backoffice-waf \
    --region us-east-1 \
    --scope REGIONAL \
    --default-action Block={} \
    --rules 'Name=AWSManagedRulesCommonRuleSet,Priority=1,OverrideAction={None={}},VisibilityConfig={SampledRequestsEnabled=true,CloudWatchMetricsEnabled=true,MetricName=CommonRuleSetMetric},Statement={ManagedRuleGroupStatement={VendorName=AWS,Name=AWSManagedRulesCommonRuleSet}}' \
    --visibility-config SampledRequestsEnabled=true,CloudWatchMetricsEnabled=true,MetricName=tpi-backoffice-waf

# Asociar a ALB
aws wafv2 associate-web-acl \
    --web-acl-arn arn:aws:wafv2:us-east-1:123456789:regional/webacl/tpi-backoffice-waf/xxxxx \
    --resource-arn arn:aws:elasticloadbalancing:us-east-1:123456789:loadbalancer/app/tpi-backoffice/xxxxx \
    --region us-east-1
```

### 3. Security Groups

```bash
# Crear SG para aplicación (solo puerto 8501)
aws ec2 create-security-group \
    --group-name tpi-backoffice-app-sg \
    --description "Security group for TPI backoffice app" \
    --vpc-id vpc-xxxxx \
    --region us-east-1

# Permitir puerto 8501 desde ALB
aws ec2 authorize-security-group-ingress \
    --group-id sg-app-xxxxx \
    --protocol tcp \
    --port 8501 \
    --source-security-group-id sg-alb-yyyyy \
    --region us-east-1

# Crear SG para BD (solo puerto 5432)
aws ec2 create-security-group \
    --group-name tpi-backoffice-db-sg \
    --description "Security group for TPI backoffice database" \
    --vpc-id vpc-xxxxx \
    --region us-east-1

# Permitir puerto 5432 desde app SG
aws ec2 authorize-security-group-ingress \
    --group-id sg-db-yyyyy \
    --protocol tcp \
    --port 5432 \
    --source-security-group-id sg-app-xxxxx \
    --region us-east-1
```

---

## Monitoreo y Logs

### 1. CloudWatch Logs

```bash
# Crear log group
aws logs create-log-group \
    --log-group-name /ecs/tpi-backoffice \
    --region us-east-1

# Ver logs
aws logs tail /ecs/tpi-backoffice --follow --region us-east-1
```

### 2. CloudWatch Alarms

```bash
# Alarma para CPU alta
aws cloudwatch put-metric-alarm \
    --alarm-name tpi-backoffice-cpu-high \
    --alarm-description "Alert when CPU > 80%" \
    --metric-name CPUUtilization \
    --namespace AWS/ECS \
    --statistic Average \
    --period 300 \
    --threshold 80 \
    --comparison-operator GreaterThanThreshold \
    --evaluation-periods 2 \
    --alarm-actions arn:aws:sns:us-east-1:123456789:alerts \
    --region us-east-1

# Alarma para Memory
aws cloudwatch put-metric-alarm \
    --alarm-name tpi-backoffice-memory-high \
    --alarm-description "Alert when Memory > 80%" \
    --metric-name MemoryUtilization \
    --namespace AWS/ECS \
    --statistic Average \
    --period 300 \
    --threshold 80 \
    --comparison-operator GreaterThanThreshold \
    --evaluation-periods 2 \
    --alarm-actions arn:aws:sns:us-east-1:123456789:alerts \
    --region us-east-1
```

---

## Backup y Recuperación

### Backup Automático de BD

```bash
# Ya configurado con:
# --backup-retention-period 30
# --preferred-backup-window "03:00-04:00"
```

### Backup Manual

```bash
# Crear snapshot
aws rds create-db-snapshot \
    --db-instance-identifier tpi-backoffice-prod \
    --db-snapshot-identifier tpi-backoffice-backup-2024-01-15 \
    --region us-east-1

# Listar snapshots
aws rds describe-db-snapshots \
    --region us-east-1
```

### Restaurar desde Snapshot

```bash
# Crear nueva instancia desde snapshot
aws rds restore-db-instance-from-db-snapshot \
    --db-instance-identifier tpi-backoffice-restored \
    --db-snapshot-identifier tpi-backoffice-backup-2024-01-15 \
    --region us-east-1

# Esperar a que esté disponible
aws rds wait db-instance-available \
    --db-instance-identifier tpi-backoffice-restored \
    --region us-east-1
```

---

## Rollback

### Rollback de Código

```bash
# Ver historial de deployments
aws ecs describe-services \
    --cluster tpi-backoffice-prod \
    --services tpi-backoffice-service \
    --region us-east-1

# Cambiar a versión anterior
aws ecs update-service \
    --cluster tpi-backoffice-prod \
    --service tpi-backoffice-service \
    --task-definition tpi-backoffice-prod:1 \
    --region us-east-1

# Esperar update
aws ecs wait services-stable \
    --cluster tpi-backoffice-prod \
    --services tpi-backoffice-service \
    --region us-east-1
```

### Rollback de BD

```bash
# Restaurar desde snapshot
aws rds restore-db-instance-from-db-snapshot \
    --db-instance-identifier tpi-backoffice-restored \
    --db-snapshot-identifier tpi-backoffice-backup-2024-01-15 \
    --region us-east-1

# Cambiar application a nuevo endpoint
# Actualizar en Secrets Manager:
aws secretsmanager update-secret \
    --secret-id tpi/prod/database-host \
    --secret-string "{\"host\": \"tpi-backoffice-restored.xxxxx.us-east-1.rds.amazonaws.com\"}" \
    --region us-east-1

# Redeploy applicación
aws ecs update-service \
    --cluster tpi-backoffice-prod \
    --service tpi-backoffice-service \
    --force-new-deployment \
    --region us-east-1
```

---

## Checklist de Deployment

- [ ] Versión actualizada en código
- [ ] Dockerfile creado y testeado
- [ ] ECR repository creado
- [ ] Docker image built y pushed
- [ ] RDS instance creada y funcional
- [ ] Base de datos restaurada
- [ ] Credenciales guardadas en Secrets Manager
- [ ] ECS cluster creado
- [ ] Task definition registrada
- [ ] ECS service creado
- [ ] Load balancer configurado
- [ ] HTTPS/SSL configurado
- [ ] WAF configurado
- [ ] Security groups configurados
- [ ] CloudWatch logs habilitados
- [ ] Alarms configuradas
- [ ] Tests en producción pasando
- [ ] Usuarios pueden acceder
- [ ] Backup configurado
- [ ] Runbook de rollback listo

---

**Deployment Ready** ✅
