#!/usr/bin/env bash
set -euo pipefail

# Raincheck - Generate Ansible inventory from current AWS EC2 addresses.
# Usage: ./scripts/update-inventory.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
INVENTORY_FILE="${PROJECT_ROOT}/inventory/hosts.ini"

AWS_REGION="${AWS_REGION:-eu-north-1}"
AWS_PROFILE="${AWS_PROFILE:-raincheck}"
ENVIRONMENT="${ENVIRONMENT:-dev}"

export AWS_REGION ENVIRONMENT INVENTORY_FILE

echo "Fetching Raincheck EC2 instances from AWS..."

AWS_JSON="$(mktemp)"
trap 'rm -f "$AWS_JSON"' EXIT

aws ec2 describe-instances \
  --profile "$AWS_PROFILE" \
  --region "$AWS_REGION" \
  --filters \
    "Name=tag:Project,Values=Raincheck" \
    "Name=tag:Environment,Values=${ENVIRONMENT}" \
    "Name=instance-state-name,Values=running" \
  --query 'Reservations[].Instances[].{
    Name:Tags[?Key==`Name`]|[0].Value,
    PublicIP:PublicIpAddress,
    PrivateIP:PrivateIpAddress
  }' \
  --output json > "$AWS_JSON"

python3 - "$AWS_JSON" <<'PY'
import ipaddress
import json
import os
import pathlib
import sys
import tempfile

with open(sys.argv[1], encoding="utf-8") as f:
    instances = json.load(f)

environment = os.environ["ENVIRONMENT"]

expected = {
    "master": f"raincheck-{environment}-master",
    "worker1": f"raincheck-{environment}-worker1",
    "worker2": f"raincheck-{environment}-worker2",
}

by_name = {}

for instance in instances:
    name = instance.get("Name")

    if name not in expected.values():
        continue

    if name in by_name:
        sys.exit(f"ERROR: Duplicate EC2 instance name: {name}")

    public_ip = instance.get("PublicIP")
    private_ip = instance.get("PrivateIP")

    if not public_ip or not private_ip:
        sys.exit(f"ERROR: Missing IP address for {name}")

    try:
        ipaddress.IPv4Address(public_ip)
        ipaddress.IPv4Address(private_ip)
    except ipaddress.AddressValueError:
        sys.exit(f"ERROR: Invalid IPv4 address for {name}")

    by_name[name] = instance

missing = set(expected.values()) - set(by_name)

if missing:
    sys.exit(
        "ERROR: Missing running EC2 instances: "
        + ", ".join(sorted(missing))
    )

master = by_name[expected["master"]]
worker1 = by_name[expected["worker1"]]
worker2 = by_name[expected["worker2"]]

content = f"""# Generated automatically by scripts/update-inventory.sh.
# Do not edit manually or commit to Git.

[k3s_master]
master ansible_host={master['PublicIP']} master_private_ip={master['PrivateIP']}

[k3s_workers]
worker1 ansible_host={worker1['PublicIP']}
worker2 ansible_host={worker2['PublicIP']}

[k3s_cluster:children]
k3s_master
k3s_workers

[k3s_cluster:vars]
ansible_user=ubuntu
ansible_ssh_private_key_file=~/.ssh/raincheck.pem
ansible_python_interpreter=/usr/bin/python3
"""

destination = pathlib.Path(os.environ["INVENTORY_FILE"])
destination.parent.mkdir(parents=True, exist_ok=True)

# Write to a temporary file first, then replace atomically.
with tempfile.NamedTemporaryFile(
    mode="w",
    encoding="utf-8",
    dir=destination.parent,
    prefix=".hosts.",
    suffix=".tmp",
    delete=False,
) as temp:
    temp.write(content)
    temporary_path = pathlib.Path(temp.name)

try:
    temporary_path.chmod(0o600)
    temporary_path.replace(destination)
except Exception:
    temporary_path.unlink(missing_ok=True)
    raise

print(f"Inventory updated: {destination}")
for role, name in expected.items():
    instance = by_name[name]
    print(
        f"  {role}: {instance['PublicIP']} "
        f"(private: {instance['PrivateIP']})"
    )
PY
