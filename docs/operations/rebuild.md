# Raincheck — Rebuild and Reproducibility Runbook

## Purpose

This runbook describes how Raincheck can be redeployed from its
Infrastructure as Code, Ansible, Helm, and GitOps configuration.

The existing environment has been validated, but a complete
destroy-and-rebuild cycle has not been performed.

This is a documented rebuild procedure, not a guarantee of
zero-touch disaster recovery.

## 1. Prerequisites

Required tools:

- AWS CLI with an authorized AWS profile
- Terraform >= 1.10.0 and < 2.0.0
- Ansible with the required collections and Python dependencies
- kubectl compatible with K3s v1.29
- Helm 3
- Git and SSH
- Python 3

The original deployment used:

- AWS region: eu-north-1
- AWS CLI profile: raincheck
- Three EC2 instances
- K3s v1.29.5+k3s1
- ArgoCD Helm chart argo-cd 7.1.1 (application v2.11.2)
- kube-prometheus-stack chart 92.17.0

AWS resources incur charges.

## 2. Terraform backend

Terraform uses an S3 backend:

- Bucket: raincheck-tfstate-161072922899-eu-north-1
- Key: environments/dev/terraform.tfstate
- Region: eu-north-1
- Native S3 state locking enabled

The S3 backend bucket must exist before Terraform initialization.

For deployment in another AWS account, configure an appropriate
backend bucket and AWS credentials.

Do not copy or commit Terraform state files, credentials, private
SSH keys, or secret variable files.

Review the Terraform bootstrap configuration under terraform/bootstrap.

## 3. Provision AWS infrastructure

From the repository root:

    cd terraform
    terraform init
    terraform validate
    terraform plan

Review the plan and expected AWS costs.

Only after reviewing and approving the plan:

    terraform apply

Terraform defines the following private IP addresses:

- Master: 10.0.1.10
- Worker 1: 10.0.1.11
- Worker 2: 10.0.1.12

These addresses are specific to the configured VPC topology.

A different network topology may require updating the Ansible
playbook and Kubernetes scheduling configuration.

## 4. Generate Ansible inventory

Return to the repository root:

    cd ..

Ensure AWS CLI authentication works and the required SSH private
key is available at:

    ~/.ssh/raincheck.pem

Generate inventory:

    ./scripts/update-inventory.sh

This script discovers running EC2 instances using their AWS tags
and writes inventory/hosts.ini.

Review the generated inventory before proceeding.

## 5. Install K3s

The Ansible playbook is:

    ansible/playbooks/install-k3s.yml

It performs the following operations:

1. Waits for SSH connectivity.
2. Installs the pinned K3s master version.
3. Reads the master join token securely.
4. Joins both K3s workers.
5. Generates a secure local kubeconfig.
6. Verifies node readiness.
7. Applies workload scheduling labels.

The Ansible roles are located under:

    ansible/roles/k3s_master
    ansible/roles/k3s_worker

Install the pinned Python dependencies in a dedicated virtual
environment before running Ansible:

    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r ansible/requirements.txt

From the repository root, run:

    cd ansible
    ansible-playbook playbooks/install-k3s.yml
    cd ..

Before running, ensure the required Ansible dependencies are
installed and SSH host keys have been verified.

The playbook generates:

    ~/.kube/raincheck-config

## 6. Secure Kubernetes access

Use the SSH tunnel described by the Ansible playbook.

The Kubernetes API is accessed locally through:

    https://127.0.0.1:16443

Set:

    export KUBECONFIG="$HOME/.kube/raincheck-config"

Verify:

    kubectl get nodes

Do not expose the Kubernetes API publicly or commit kubeconfig
files to Git.

## 7. Kubernetes Secrets

The application requires a Secret named:

    raincheck-rabbitmq

Namespace:

    raincheck

Required keys:

    username
    password

The monitoring deployment uses:

    monitoring-grafana

Namespace:

    monitoring

Required credential keys:

    admin-user
    admin-password

Create the namespaces and supply the Secrets securely before
deploying the dependent workloads.

Use credentials from an approved secure source. Never store
plaintext credentials in Git or terminal command history.

On a completely new RabbitMQ data volume, fresh credentials
may be generated. When restoring existing RabbitMQ data,
credentials must remain consistent with the broker's stored state.

The Grafana chart must have a valid existing Secret before
the Grafana workload is deployed.

## 8. Install ArgoCD

ArgoCD is deployed using Helm configuration stored at:

    helm/argocd/values.yaml

The existing deployment uses ArgoCD v2.11.2.

Install the pinned ArgoCD Helm chart after the Kubernetes
cluster is operational:

    helm repo add argo https://argoproj.github.io/argo-helm
    helm repo update
    helm upgrade --install argocd argo/argo-cd \
      --version 7.1.1 \
      --namespace argocd \
      --create-namespace \
      -f helm/argocd/values.yaml

Verify the ArgoCD namespace and controller workloads.

The Raincheck application manifest is:

    argocd/raincheck-application.yaml

The monitoring application manifest is:

    argocd/monitoring-application.yaml

Register both applications after their prerequisites exist.

The Raincheck Application has automated synchronization and
self-healing enabled.

The monitoring Application does not have automated synchronization
enabled and requires an explicit initial sync.

## 9. Prometheus Operator CRDs

The monitoring Application references kube-prometheus-stack
chart version 92.17.0.

The existing cluster contains 10 monitoring.coreos.com CRDs.

Its Helm source uses:

    skipCrds: true

Therefore, on a completely new cluster, the Prometheus Operator
CRDs must be installed separately before monitoring synchronization.

On a fresh cluster, install the CRDs from the exact pinned
chart version before deploying the monitoring Application.

From the repository root:

    helm repo add prometheus-community \
      https://prometheus-community.github.io/helm-charts

    helm repo update prometheus-community

    CHART_DIR="$(mktemp -d)"

    helm pull prometheus-community/kube-prometheus-stack \
      --version 92.17.0 \
      --untar \
      --untardir "$CHART_DIR"

    CRD_DIR="$CHART_DIR/kube-prometheus-stack/charts/crds/crds"

    find "$CRD_DIR" -maxdepth 1 -name '*.yaml' -type f | wc -l

The expected count is 10.

On a newly created cluster only, install these CRDs:

    kubectl apply --server-side -f "$CRD_DIR"

Wait for CRD establishment:

    for file in "$CRD_DIR"/*.yaml; do
      crd_name="$(basename "$file" .yaml)"
      crd_name="${crd_name#crd-}"
      kubectl wait --for=condition=Established \
        "crd/${crd_name}.monitoring.coreos.com" --timeout=120s
    done

Verify the installed CRDs:

    kubectl get crd | grep monitoring.coreos.com

Remove the temporary chart directory:

    rm -rf "$CHART_DIR"

Do not use this installation procedure as an automatic
upgrade mechanism on an existing monitoring deployment.

Do not delete existing CRDs or monitoring custom resources as
a troubleshooting shortcut.

CRD installation and upgrades require separate lifecycle
management.

## 10. Deploy Raincheck and monitoring

Apply the ArgoCD Application manifests:

    kubectl apply -f argocd/raincheck-application.yaml
    kubectl apply -f argocd/monitoring-application.yaml

Ensure the required Secrets and monitoring CRDs exist first.

Verify the Raincheck application reaches Synced and Healthy.

Perform an explicit initial synchronization of monitoring
and verify it reaches Synced and Healthy.

## 11. Validate the deployment

Verify Kubernetes nodes:

    kubectl get nodes

Verify application workloads:

    kubectl get pods -n raincheck

Verify monitoring workloads:

    kubectl get pods -n monitoring

Verify ArgoCD Applications:

    kubectl get applications -n argocd

Verify the frontend using a local port-forward:

    kubectl port-forward -n raincheck svc/raincheck-frontend 8080:80

Open:

    http://localhost:8080

Submit a weather request and confirm the complete asynchronous
processing path works.

Check RabbitMQ processing, Redis results, Prometheus targets,
and Grafana access.

Additional validation evidence is documented in:

    docs/validation.md

## 12. Grafana dashboard restoration

The exported Grafana dashboard is stored at:

    docs/monitoring/raincheck-dashboard.json

The dashboard is backed up in Git.

It is not currently automatically provisioned by the Helm chart.

After a complete rebuild, import the dashboard manually into
Grafana and verify its Prometheus data source and panels.

Grafana uses ephemeral storage in the current configuration,
so dashboards and database-backed settings can be lost when
the Grafana pod is replaced.

## 13. Persistence and recovery limitations

RabbitMQ uses a local-path persistent volume tied to Worker 2.

Destroying or replacing the underlying EC2 instance can result
in permanent RabbitMQ data loss.

Redis stores temporary weather results without persistence.

Prometheus historical metrics are not guaranteed to survive
infrastructure destruction.

Grafana uses ephemeral storage.

Kubernetes Secrets are intentionally not stored in Git and
must be recreated securely.

Terraform state is stored separately in S3 and must be
managed carefully during infrastructure destruction or
recreation.

This runbook supports fresh deployment of application services,
not restoration of all historical runtime data.

## 14. Reproducibility statement

Raincheck uses Terraform, Ansible, Helm, GitHub Actions, and
ArgoCD to provide a repeatable infrastructure and application
deployment process.

The existing environment has been validated successfully.

A complete clean-room rebuild has not been executed, and
some bootstrap tasks require manual preparation.

Full disaster recovery, automated Secret restoration,
durable observability storage, and automatic Grafana dashboard
provisioning are potential future improvements.
