# Raincheck — reviewed configuration

## Scope and safety

This review covers the Terraform, Ansible, Argo CD, Helm, application, and CI configuration included in the supplied archive. It does **not** apply changes to AWS or the live Kubernetes cluster. No Terraform destroy/apply is required for the fixes in this review.

The archive contained a `kubeconfig` file. It is deliberately excluded from this reviewed package. Treat that file as a cluster-admin credential: do not commit or share it, keep local permissions at `0600`, and rotate/reissue cluster access credentials because the uploaded archive contained it.

## Important configuration corrections

1. `argocd/monitoring-application.yaml` sets `helm.skipCrds: true`. The six Prometheus Operator CRDs already exist in the cluster; Argo CD should not attempt to re-apply them while they carry oversized client-side-apply annotations. This avoids deleting/recreating CRDs and preserves existing custom resources. CRD lifecycle/upgrades must be handled separately and deliberately.
2. The monitoring Application keeps `ServerSideApply=true` and adds `PruneLast=true`. This does not itself repair an already-running stale operation; terminate that operation before starting a fresh sync.
3. `monitoring/values.yaml` pins Prometheus to Worker 2 (`ip-10-0-1-12`) and its `workload=raincheck` label. This resolves the previously observed impossible combination that included the master hostname and the Raincheck workload label. Confirm the node labels before syncing.
4. The monitoring values no longer add Argo CD hook annotations to the admission webhook resources. The admission Jobs retain their chart-managed lifecycle and 300-second TTL.
5. `argocd/raincheck-application.yaml` adds `RespectIgnoreDifferences=true` so the declared StatefulSet PVC-template ignore rule is respected during sync; pruning is deferred to the end. RabbitMQ's StatefulSet already has `Prune=false,Delete=false` and PVC retention settings.
6. Ansible now applies the two workload labels after K3s workers join: Worker 1 gets `workload=argocd`; Worker 2 gets `workload=raincheck`.
7. `/kubeconfig` is explicitly ignored by Git.

## Apply the repository changes

From the repository root, inspect and commit the changed files:

```bash
git diff --check
git diff -- argocd/monitoring-application.yaml argocd/raincheck-application.yaml monitoring/values.yaml ansible/playbooks/install-k3s.yml .gitignore README.md
```

After reviewing the diff, commit and push it. Do not include `kubeconfig`, `.tfstate`, `.tfvars`, private keys, or secret values.

## Safe cluster rollout (after the commit)

1. Confirm nodes and labels:

```bash
kubectl get nodes -o wide
kubectl get nodes --show-labels
```

Worker 2 must have `kubernetes.io/hostname=ip-10-0-1-12` and `workload=raincheck`. If it does not, fix the label with the Ansible playbook or `kubectl label node ip-10-0-1-12 workload=raincheck --overwrite`.

2. Apply the updated Application definition so the live Application receives `skipCrds` and sync options:

```bash
kubectl apply -f argocd/monitoring-application.yaml
```

3. Check the current operation. Only if its phase is `Running`, terminate it using the Argo CD CLI (not a made-up `operation.terminate` field):

```bash
kubectl get application monitoring -n argocd -o jsonpath='Phase: {.status.operationState.phase}{"\n"}'
# Run this only when the phase above is Running:
argocd app terminate-op monitoring
```

If the CLI is not logged in, port-forward `argocd-server` and log in first. If the phase is `Failed` or `Succeeded`, do not run the terminate command.

4. Request a hard refresh and inspect the rendered application before syncing:

```bash
kubectl annotate application monitoring -n argocd argocd.argoproj.io/refresh=hard --overwrite
kubectl get application monitoring -n argocd -o jsonpath='Sync: {.status.sync.status}{"\n"}Health: {.status.health.status}{"\n"}Operation: {.status.operationState.phase}{"\n"}Message: {.status.operationState.message}{"\n"}'
```

5. Start one sync (CLI):

```bash
argocd app sync monitoring
argocd app wait monitoring --sync --health --timeout 600
```

6. Verify the CRDs were not part of the sync result and check the workloads:

```bash
kubectl get crd | grep monitoring.coreos.com
kubectl get pods -n monitoring -o wide
kubectl get application monitoring -n argocd
```

Do not delete or recreate the Prometheus Operator CRDs to work around annotation-size errors. Existing CRDs contain custom resource definitions used by Prometheus and Alertmanager.

## Terraform findings

The Terraform configuration uses an S3 backend with native state locking, encrypted/versioned state bucket bootstrap, private intra-cluster security-group traffic, and IMDSv2. The EC2 instances use `delete_on_termination=true` for root EBS volumes. Because the local-path RabbitMQ PVC lives on Worker 2's disk, replacing that EC2 instance can destroy RabbitMQ data. Do not run `terraform apply` as a Kubernetes troubleshooting step. Review any proposed EC2 replacement in a saved plan and protect/backup RabbitMQ data first.

The supplied Ansible inventory contains public DNS names that may be stale. Refresh them from the current Terraform outputs before running Ansible:

```bash
cd terraform
terraform output master_public_ip
terraform output worker1_public_ip
terraform output worker2_public_ip
```

Update `inventory/hosts.ini` with the current public DNS/IP values (or use a generated dynamic inventory) before running the playbook. The archive did not include Terraform state or `*.tfvars`, so the current AWS resource mapping and variable values could not be independently verified.

## Remaining operational caveats

- The app chart expects the `raincheck-rabbitmq` Kubernetes Secret to exist in namespace `raincheck`; secret contents are intentionally not stored in Git.
- The frontend and backend Services are `ClusterIP`; external access requires the existing ingress/load-balancer setup or a port-forward. No ingress resource is included in this archive.
- Redis is configured without persistence; cached weather results are ephemeral.
- `inventory/hosts.ini` must be refreshed before rerunning Ansible.
