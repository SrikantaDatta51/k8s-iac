#!/bin/bash
set -e

REPO_ROOT="/home/user/.gemini/antigravity/scratch/srtumkur/2025/k8s-iac/cp-paas-iac-reference"
ADDONS_DIR="$REPO_ROOT/components/addons"
TENANTS_DIR="$REPO_ROOT/components/tenants"

# List of Addon Components
ADDONS=("cni-core" "multus-core" "nvidia-network-operator" "nvidia-gpu-operator" "cluster-observability")

create_chart() {
    local type=$1
    local name=$2
    local dir=$3
    
    echo "Creating $type component: $name..."
    mkdir -p "$dir/$name/helm/$name/templates"
    
    # Chart.yaml
    cat > "$dir/$name/helm/$name/Chart.yaml" <<EOF
apiVersion: v2
name: $name
description: Helm chart for $name
type: application
version: 0.1.0
appVersion: 0.1.0
EOF

    # values.yaml
    cat > "$dir/$name/helm/$name/values.yaml" <<EOF
# Default values for $name
enabled: true
EOF

    # Basic template
    cat > "$dir/$name/helm/$name/templates/configmap.yaml" <<EOF
apiVersion: v1
kind: ConfigMap
metadata:
  name: $name-config
  annotations:
    argocd.argoproj.io/sync-wave: "1"
data:
  info: "This is the $name component"
EOF
}

# Create Addons
for addon in "${ADDONS[@]}"; do
    create_chart "Addon" "$addon" "$ADDONS_DIR"
done

# Create Tenant Onboarding
create_chart "Tenant" "tenant-onboarding" "$TENANTS_DIR"

echo "All component charts created."
