# Advanced Deployment Guide

## Overview

ai-decision-council can be deployed in multiple ways:

- Single-machine reference implementation
- Cloud-native (Kubernetes)
- Serverless (AWS Lambda, Google Cloud Functions)
- Embedded in existing services

---

## Reference Deployment (Development/Testing)

### Single Machine

```bash
# Install
pip install "ai-decision-council[api]"

# Configure
export LLM_COUNCIL_API_KEY="sk-..."
export LLM_COUNCIL_REFERENCE_API_TOKEN="your-secret-token"

# Run
ai-decision-council api serve --host localhost --port 8001
```

**Limitations:**

- Single process, no clustering
- File-based storage (JSON)
- No horizontal scaling
- Authentication is static token

**Good for:** Local development, demos, small teams

---

## Kubernetes Deployment

A complete production-ready Kubernetes manifest is provided in the repository (`k8s-deployment.yaml`). This includes:

- Deployment with 3 replicas
- HorizontalPodAutoscaler (3-10 replicas based on CPU/memory)
- Service and LoadBalancer
- ConfigMap and Secrets for configuration
- PodDisruptionBudget for reliability
- RBAC roles and ServiceAccount
- Liveness and readiness probes

### Deploy to Kubernetes

```bash
# Configure your image registry
kubectl set image deployment/ai-council \
  ai-council=your-registry/ai-council:1.4.0 \
  -n production

# Apply manifests
kubectl apply -f k8s-deployment.yaml

# Verify
kubectl get pods -n ai-council
kubectl logs -n ai-council -l app=ai-council
```

### Configuration

Use ConfigMap and Secrets in the manifest to set environment variables:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: council-config
data:
  LLM_COUNCIL_MODELS: "openai/gpt-5.1,anthropic/claude-sonnet-4.5,google/gemini-3-pro-preview"
  LLM_COUNCIL_MODEL_COUNT: "3"
  LLM_COUNCIL_API_URL: "https://openrouter.ai/api/v1/chat/completions"
  LLM_COUNCIL_CORS_ORIGINS: "https://app.example.com,https://dashboard.example.com"
  LLM_COUNCIL_DATA_DIR: "/data/conversations"

---
apiVersion: v1
kind: Secret
metadata:
  name: council-secrets
type: Opaque
data:
  LLM_COUNCIL_API_KEY: <base64-encoded-key>
  LLM_COUNCIL_REFERENCE_API_TOKEN: <base64-encoded-token>

---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ai-council
  labels:
    app: ai-council
spec:
  replicas: 3 # High availability
  selector:
    matchLabels:
      app: ai-council
  template:
    metadata:
      labels:
        app: ai-council
    spec:
      containers:
        - name: council
          image: mycompany/ai-council:1.1.0
          imagePullPolicy: Always
          ports:
            - containerPort: 8001
              name: http

          # Environment from config
          envFrom:
            - configMapRef:
                name: council-config
            - secretRef:
                name: council-secrets

          # Health checks
          livenessProbe:
            httpGet:
              path: /v1/health # Assumes you add this endpoint
              port: 8001
            initialDelaySeconds: 30
            periodSeconds: 10
            timeoutSeconds: 5

          readinessProbe:
            httpGet:
              path: /v1/ready
              port: 8001
            initialDelaySeconds: 10
            periodSeconds: 5

          # Resource limits
          resources:
            requests:
              cpu: "500m"
              memory: "512Mi"
            limits:
              cpu: "2000m"
              memory: "2Gi"

          # Graceful shutdown
          lifecycle:
            preStop:
              exec:
                command: ["/bin/sh", "-c", "sleep 10"]

          # Persistent volume for storage
          volumeMounts:
            - name: data
              mountPath: /data

      # Init container for DB migration (if using DB backend)
      initContainers:
        - name: migrate
          image: mycompany/ai-council:1.1.0
          command: ["python", "-m", "ai_decision_council", "db", "migrate"]
          envFrom:
            - secretRef:
                name: council-secrets

      volumes:
        - name: data
          persistentVolumeClaim:
            claimName: council-data

---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: council-data
spec:
  accessModes:
    - ReadWriteMany # Multiple pods can read/write
  resources:
    requests:
      storage: 100Gi
  storageClassName: fast-ssd # Use appropriate storage class

---
apiVersion: v1
kind: Service
metadata:
  name: ai-council
spec:
  type: LoadBalancer
  ports:
    - port: 80
      targetPort: 8001
      protocol: TCP
      name: http
  selector:
    app: ai-council

---
apiVersion: autoscaling.k8s.io/v2
kind: HorizontalPodAutoscaler
metadata:
  name: ai-council-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: ai-council
  minReplicas: 2
  maxReplicas: 10
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
    - type: Resource
      resource:
        name: memory
        target:
          type: Utilization
          averageUtilization: 80
```

### 3. Deploy to K8s

```bash
kubectl apply -f council-deployment.yaml

# Monitor rollout
kubectl rollout status deployment/ai-council

# Check pods
kubectl get pods -l app=ai-council

# View logs
kubectl logs -f deployment/ai-council -c council

# Scale manually
kubectl scale deployment ai-council --replicas=5

# Check service
kubectl get svc ai-council
```

---

## Multi-Region Failover

### Active-Active Across Regions

```
┌─────────────────────┐
│   Global LB         │
│  (CloudFlare/AWS)   │
│                     │
├──────────┬──────────┤
│          │          │
▼          ▼          ▼
US-EAST   EU-WEST   ASIA-SE
K8s-1     K8s-2     K8s-3
3 pods    3 pods    3 pods
```

**Configuration:**

1. **DNS with health checks:**

```yaml
# Using Cloudflare (or similar)
apiVersion: dnsmasq/v1
kind: ServicePolicies
spec:
  failover:
    healthChecks:
      - region: us-east
        endpoint: https://api-us.example.com/health
        interval: 30s
      - region: eu-west
        endpoint: https://api-eu.example.com/health
        interval: 30s
      - region: asia-se
        endpoint: https://api-asia.example.com/health
        interval: 30s

    # If primary region fails, route to healthy regions
    failoverChain: [us-east, eu-west, asia-se]
```

2. **Shared database (PostgreSQL):**

```bash
# Each region connects to same DB or replication setup
# https://region-db.example.com:5432/council

LLM_COUNCIL_DB_URL="postgresql://user:pass@replica.postgres.instance.com/council"
```

3. **Cross-region storage replication:**

```bash
# If using object storage (S3, GCS)
# Enable cross-region replication so all regions can access conversations

aws s3api put-bucket-replication \
  --bucket council-conversations \
  --replication-configuration '...replication rules...'
```

---

## Database Backend (Production)

### PostgreSQL Storage (instead of JSON files)

```python
# core/storage.py (custom implementation)
from sqlalchemy import create_engine, Column, String, JSON
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(String(36), primary_key=True)
    owner_id = Column(String(255))
    messages = Column(JSON)
    created_at = Column(DateTime)
    updated_at = Column(DateTime)

engine = create_engine(
    f"postgresql://{user}:{password}@{host}:{port}/{db}"
)
Base.metadata.create_all(engine)
```

**Benefits:**

- ✅ ACID compliance
- ✅ Built-in replication/failover
- ✅ Query conversation history efficiently
- ✅ Multi-region consistency options

**Example setup with Cloud SQL:**

```bash
gcloud sql instances create council-db \
  --database-version=POSTGRES_15 \
  --tier=db-custom-4-16384 \
  --region=us-east \
  --replica-region=eu-west \
  --replica-region=asia-se
```

---

## Horizontal Scaling

### Challenge: API State & Session Affinity

By default, each request is independent (stateless), so scaling is straightforward:

```
Request 1 → Pod A → Query Council → Return Result
Request 2 → Pod B → Query Council → Return Result
Request 3 → Pod C → Query Council → Return Result
```

**All requests are independent** so any pod can handle any request.

### Storage Scaling

With shared database:

```
Pod A ┐
Pod B ├─→ PostgreSQL ← Load Balanced
Pod C ┘
```

**Rate limiting** becomes critical:

```python
# In-memory rate limiter (per pod) WON'T WORK across pods
# Use Redis instead:

from redis import Redis
limiter = RedisRateLimiter("redis://redis-endpoint:6379")

# Each pod checks against shared Redis
requests_remaining = limiter.check_rate(token="<api-token>")
if requests_remaining < 0:
    return 429  # Too Many Requests
```

---

## CI/CD Pipeline

### Example: GitHub Actions + K8s Deployment

Assuming your container image is already built and pushed to a registry, deploy to Kubernetes:

```yaml
name: Deploy Council to K8s

on:
  push:
    tags:
      - "v*"

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Configure kubectl
        run: |
          mkdir -p ~/.kube
          echo ${{ secrets.KUBE_CONFIG }} | base64 -d > ~/.kube/config

      - name: Deploy manifests
        run: |
          # Apply Kubernetes manifests
          kubectl apply -f k8s-deployment.yaml

          # Update image if needed
          kubectl set image deployment/ai-council \
            ai-council=your-registry/ai-council:${{ github.ref_name }} \
            -n ai-council

          # Wait for rollout
          kubectl rollout status deployment/ai-council \
            -n ai-council \
            --timeout=5m

      - name: Verify deployment
        run: |
          # Check pod health
          kubectl get pods -n ai-council
          kubectl logs -n ai-council -l app=ai-council --tail=20
```

**Note:** For container builds, use your preferred container registry or CI/CD tool.

---

## Monitoring & Observability

### Prometheus Metrics

```python
# Add to your FastAPI app
from prometheus_client import Counter, Histogram, generate_latest

# Metrics
council_requests = Counter(
    'council_requests_total',
    'Total requests',
    ['stage', 'status']
)

council_duration = Histogram(
    'council_duration_seconds',
    'Request duration',
    ['stage']
)

# In Stage 1:
with council_duration.labels(stage='stage_1').time():
    results = await stage1_collect_responses(...)

council_requests.labels(stage='stage_1', status='success').inc()

@app.get('/metrics')
def metrics():
    return generate_latest()
```

**Prometheus config:**

```yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: "ai-council"
    kubernetes_sd_configs:
      - role: pod
    relabel_configs:
      - source_labels: [__meta_kubernetes_pod_label_app]
        regex: ai-council
        action: keep
```

### Alerting

```yaml
# alert.yml
groups:
  - name: council-alerts
    rules:
      - alert: HighErrorRate
        expr: |
          (increase(council_requests_total{status="error"}[5m]) 
           / increase(council_requests_total[5m])) > 0.05
        for: 5m
        annotations:
          summary: "Council error rate >5%"

      - alert: HighLatency
        expr: |
          histogram_quantile(0.99, council_duration_seconds_bucket) > 30
        for: 5m
        annotations:
          summary: "P99 latency >30s"

      - alert: APIKeyExpired
        expr: council_api_key_expires_in_days < 7
        annotations:
          summary: "API key expires in <7 days"
```

### Logging

```python
import logging

logging.basicConfig(
    format='{"timestamp": "%(asctime)s", "level": "%(levelname)s", "message": "%(message)s"}',
    level=logging.INFO
)

logger = logging.getLogger(__name__)

logger.info("Council initialized", extra={
    "council_size": len(config.models),
    "api_version": "v1"
})
```

Send logs to centralized system:

```bash
# Using ELK stack (Elasticsearch + Logstash + Kibana)
# or Google Cloud Logging, DataDog, New Relic, etc.
```

---

## Cost Optimization

### Reserved Instances (if using cloud VMs)

```bash
# Google Cloud: 3-year commitment = 60% discount
gcloud compute reservations create council-reservation \
  --machine-type=e2-standard-4 \
  --zone=us-east1-b \
  --count=5

# AWS: Same concept with Reserved Instances
```

### Spot/Preemptible Instances

```yaml
# K8s: Use preemptible nodes for non-critical workloads
nodeSelector:
  cloud.google.com/gke-preemptible: "true"

# But NOT for prod council pods (need reliability)
```

### CDN for Static Content

```bash
# Cache OpenAPI/SDK responses
CloudFront Distribution:
  - Origin: https://api.example.com/v1/openapi.json
  - TTL: 3600s
  - Cache key: request path
```

---

## Disaster Recovery

### Backup Strategy

```bash
# Daily backup of database
0 2 * * * pg_dump -h $DB_HOST $DB_NAME \
  | gzip > /backups/council-$(date +%Y%m%d).sql.gz

# Backup to S3
aws s3 cp /backups/council-$(date +%Y%m%d).sql.gz \
  s3://backup-bucket/council/
```

### Recovery Procedure

```bash
# 1. Stop current deployment
kubectl scale deployment ai-council --replicas=0

# 2. Restore from backup
zcat /backups/council-20260301.sql.gz | \
  psql -h recovered-db-instance.com council

# 3. Verify data integrity
psql -h recovered-db-instance.com council \
  -c "SELECT COUNT(*) FROM conversations;"

# 4. Restart deployment
kubectl scale deployment ai-council --replicas=3

# 5. Run health checks
kubectl exec -it deployment/ai-council -- \
  python -m pytest tests/health_checks.py
```

### RTO & RPO

| Component | RTO (Recovery Time Obj.) | RPO (Recovery Point Obj.) | Notes            |
| --------- | ------------------------ | ------------------------- | ---------------- |
| API pods  | <1 min                   | N/A                       | K8s restart      |
| Database  | 5-10 min                 | 1 day                     | Backup restore   |
| Storage   | 10-30 min                | 1 day                     | Snapshot restore |

---

## Security Checklist for Production

- [ ] **Encrypt secrets** in etcd (K8s secret encryption at rest)
- [ ] **TLS for all traffic** (kubectl apply certificate-manager)
- [ ] **API token rotation** (every 90 days)
- [ ] **Rate limiting** (prevent abuse)
- [ ] **Request signing** (HMAC-SHA256 for webhook integrity)
- [ ] **Audit logging** (track all API calls)
- [ ] **Network policies** (restrict K8s pod-to-pod communication)
- [ ] **RBAC** (Role-Based Access Control)
- [ ] **CVE scanning** (scan container images)
- [ ] **DDoS protection** (CloudFlare/AWS Shield)
