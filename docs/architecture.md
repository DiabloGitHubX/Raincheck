# Raincheck architecture

## Infrastructure and delivery

```mermaid
flowchart TB
  GH[GitHub repository] --> CI[GitHub Actions: lint, test, audit, scan, build]
  CI --> REG[GHCR: SHA-tagged images]
  CI --> HV[Helm image tags in Git]
  HV --> AR[Argo CD]
  TF[Terraform] --> AWS[AWS VPC / 3 EC2 nodes / EBS]
  AN[Ansible] --> K[K3s cluster]
  AWS --> K
  AR --> K
  REG --> K
  subgraph K [Three-node K3s]
    CP[Control plane]
    WK1[Worker 1: GitOps workloads]
    WK2[Worker 2: application and monitoring workloads]
  end
```

## Application request and asynchronous response

```mermaid
sequenceDiagram
  participant User as Browser/Nginx
  participant API as FastAPI
  participant Redis as Redis
  participant MQ as RabbitMQ
  participant Worker as Python worker
  participant Meteo as Open-Meteo
  User->>API: POST /weather/request {city}
  API->>Redis: Save queued status (TTL)
  API->>MQ: Publish durable weather task
  API-->>User: 202 Accepted + request_id
  MQ->>Worker: Deliver task
  Worker->>Meteo: Geocoding + weather forecast
  Meteo-->>Worker: Weather data
  Worker->>Redis: Save result/status
  Worker->>MQ: Acknowledge successful task
  loop Poll until completed/failed
    User->>API: GET /weather/result/{request_id}
    API->>Redis: Read request state
    API-->>User: Current status/result
  end
```

For failed jobs, the worker uses the RabbitMQ retry and dead-letter queues. Redis is a TTL cache, not durable long-term storage. RabbitMQ's local-path volume is node-bound. Network access to the Kubernetes API is designed to use an SSH tunnel rather than a public API endpoint.
