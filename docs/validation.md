# Raincheck submission validation and evidence

This document separates **previously observed results** from checks that should be repeated only if convenient and safe. Do not expose secrets, tokens, private keys, kubeconfigs or identifiable public IPs in screenshots.

## Previously reported during development

- Three K3s nodes Ready.
- Raincheck and monitoring Argo CD Applications Synced / Healthy.
- End-to-end weather request successfully processed and result retrieved from Redis.
- RabbitMQ queues `weather_tasks`, `weather_tasks.retry` and `weather_tasks.dlq` verified empty after cleanup; one active consumer on the main queue.
- Eight worker unit tests passed in CI; CI run for commit `0153bc5` succeeded.
- Prometheus reported 22/22 healthy scrape targets.
- Kubernetes API reached through SSH tunnel without public port 6443 exposure.

These are historical observations, not assertions that the live environment is currently running.

## Evidence to capture before submission

| File name suggestion | Evidence | How to capture |
| --- | --- | --- |
| `01-weather-ui.png` | Weather result displayed | Open frontend and request a city |
| `02-k3s-nodes.png` | Three Ready nodes | `kubectl get nodes -o wide` (redact IPs) |
| `03-raincheck-pods.png` | Application pods healthy | `kubectl get pods -n raincheck` |
| `04-argocd.png` | Raincheck and monitoring Synced/Healthy | Argo CD UI or `kubectl get applications -n argocd` |
| `05-github-actions.png` | Successful build/test/scan/push | GitHub Actions successful run |
| `06-prometheus.png` | Healthy targets | Prometheus Targets page |
| `07-grafana.png` | Metrics dashboard | Grafana dashboard with visible panels |
| `08-rabbitmq.png` | Queue and consumer status | RabbitMQ management UI or `rabbitmqctl list_queues` |

Save screenshots in `docs/screenshots/` and reference them from the README once captured. Never fabricate evidence or present historical results as live current checks.

## Safe read-only verification

```bash
kubectl get nodes
kubectl get applications -n argocd
kubectl get pods -n raincheck
kubectl get pods -n monitoring
kubectl -n raincheck get services
kubectl -n raincheck exec raincheck-rabbitmq-0 -- rabbitmqctl list_queues name messages consumers --timeout 15
```

If the instances are stopped, do not restart them solely to collect screenshots without first considering time and AWS charges. Screenshots of previous validated sessions can be used if accurately labeled.

## Final repository checks

```bash
git diff --check
git status --short --branch
git ls-files | grep -E '(^|/)(kubeconfig|\.env|terraform\.tfstate|terraform\.tfvars|id_rsa|id_ed25519)$|\.(pem|p12|pfx|tfplan)$' || true
```

Inspect any matches manually. Verify Markdown links and Mermaid rendering on GitHub before submitting.
