#!/bin/bash
set -e

# Tool Installation Script - ArgoCD-Only Version (No Karmada)
# Assumes kubeconfigs are at ~/.kube/config-command-cluster, etc.

# Resolve Kubconfig Path (Handle sudo/root mismatch)
if [ -f "$HOME/.kube/config-command-cluster" ]; then
    KUBE_ROOT="$HOME/.kube"
elif [ -f "/home/ubuntu/.kube/config-command-cluster" ]; then
    KUBE_ROOT="/home/ubuntu/.kube"
elif [ -f "/home/$SUDO_USER/.kube/config-command-cluster" ]; then
    KUBE_ROOT="/home/$SUDO_USER/.kube"
else
    echo "Error: Cannot find kubeconfig files in $HOME, /home/ubuntu, or /home/$SUDO_USER"
    exit 1
fi

echo "Using Kubeconfigs from: $KUBE_ROOT"
KUBECONFIG_CMD="$KUBE_ROOT/config-command-cluster"
KUBECONFIG_GPU="$KUBE_ROOT/config-gpu-cluster"
KUBECONFIG_CPU="$KUBE_ROOT/config-cpu-cluster"

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
CALICO_MANIFEST="$SCRIPT_DIR/calico-v3.30.0.yaml"
ARGOCD_MANIFEST="$SCRIPT_DIR/command-cluster/argocd-install.yaml"

echo "=== Installing Tools (ArgoCD-Only) ==="

# 1. Install Calico v3.30+ on All Clusters
echo "--- Installing Calico v3.30.0 (Supports Whisker) ---"
for KC in "$KUBECONFIG_CMD" "$KUBECONFIG_GPU" "$KUBECONFIG_CPU"; do
    CLUSTER_NAME=$(basename "$KC" | sed 's/config-//')
    echo "  Applying Calico to $CLUSTER_NAME..."
    kubectl --kubeconfig "$KC" apply -f "$CALICO_MANIFEST"
done

# 2. Install ArgoCD on Command Cluster
echo "--- Installing/Verifying ArgoCD on Command Cluster ---"
if kubectl --kubeconfig "$KUBECONFIG_CMD" get ns argocd &> /dev/null; then
    echo "  ArgoCD namespace exists. Updating resources..."
else
    kubectl --kubeconfig "$KUBECONFIG_CMD" create namespace argocd
fi
kubectl --kubeconfig "$KUBECONFIG_CMD" apply -n argocd -f "$ARGOCD_MANIFEST"

# Patch ArgoCD Server to NodePort for easy access
echo "  Patching ArgoCD Server to NodePort..."
kubectl --kubeconfig "$KUBECONFIG_CMD" patch svc argocd-server -n argocd -p '{"spec": {"type": "NodePort"}}' --type merge || true

# 3. Register Member Clusters to ArgoCD
# We enable ArgoCD to deploy to 'gpu-cluster' and 'cpu-cluster' by creating Secrets in the argocd namespace.
echo "--- Registering GPU and CPU Clusters to ArgoCD ---"

create_argocd_cluster_secret() {
    local cluster_name=$1
    local kubeconfig_path=$2
    local server_ip=$3
    
    # Check if already registered
    if kubectl --kubeconfig "$KUBECONFIG_CMD" -n argocd get secret "$cluster_name-secret" &>/dev/null; then
        echo "  $cluster_name already registered."
        return
    fi

    echo "  Registering $cluster_name ($server_ip)..."
    # Extract CA, Cert, Key from kubeconfig
    local ca=$(grep 'certificate-authority-data' "$kubeconfig_path" | awk '{print $2}' | head -n 1)
    local cert=$(grep 'client-certificate-data' "$kubeconfig_path" | awk '{print $2}' | head -n 1)
    local key=$(grep 'client-key-data' "$kubeconfig_path" | awk '{print $2}' | head -n 1)

    # Create Secret Manifest
    cat <<EOF | kubectl --kubeconfig "$KUBECONFIG_CMD" apply -f -
apiVersion: v1
kind: Secret
metadata:
  name: $cluster_name-secret
  namespace: argocd
  labels:
    argocd.argoproj.io/secret-type: cluster
type: Opaque
stringData:
  name: $cluster_name
  server: $server_ip
  config: |
    {
      "tlsClientConfig": {
        "insecure": false,
        "caData": "$ca",
        "certData": "$cert",
        "keyData": "$key"
      }
    }
EOF
}

# Add GPU Cluster (192.168.100.20)
create_argocd_cluster_secret "gpu-cluster" "$KUBECONFIG_GPU" "https://192.168.100.20:6443"

# Add CPU Cluster (192.168.100.30)
create_argocd_cluster_secret "cpu-cluster" "$KUBECONFIG_CPU" "https://192.168.100.30:6443"

# 4. Enable Calico Whisker & Tenant Demo
echo "--- Enabling Calico Whisker & Tenant Demo ---"
kubectl --kubeconfig "$KUBECONFIG_CMD" apply -f "$SCRIPT_DIR/command-cluster/whisker-enable.yaml" || echo "Note: Whisker CRD might not exist if using older Calico. Skipping."
kubectl --kubeconfig "$KUBECONFIG_CMD" apply -f "$SCRIPT_DIR/command-cluster/tenant-demo.yaml"

# 5. Argo Rollouts (On Workload Clusters)
echo "--- Installing Argo Rollouts (Dev & Prod) ---"
ROLLOUTS_manifest="https://github.com/argoproj/argo-rollouts/releases/latest/download/install.yaml"
# Install on GPU
kubectl --kubeconfig "$KUBECONFIG_GPU" create ns argo-rollouts || true
kubectl --kubeconfig "$KUBECONFIG_GPU" apply -n argo-rollouts -f "$ROLLOUTS_manifest"
# Install on CPU
kubectl --kubeconfig "$KUBECONFIG_CPU" create ns argo-rollouts || true
kubectl --kubeconfig "$KUBECONFIG_CPU" apply -n argo-rollouts -f "$ROLLOUTS_manifest"

# 6. Kargo (On Management Cluster)
echo "--- Installing Kargo (Management) ---"
# Prerequisite: Cert Manager (Required for Kargo Webhooks)
echo "  Installing Cert-Manager..."
kubectl --kubeconfig "$KUBECONFIG_CMD" apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.13.2/cert-manager.yaml
echo "  Waiting for Cert-Manager..."
sleep 30 # Simple wait for CRDs

# Install Kargo
echo "  Installing Kargo Controller & UI..."

# Ensure Helm is installed
if ! command -v helm &> /dev/null; then
    echo "  Helm not found. Installing..."
    curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
fi

# Install/Upgrade Kargo (OCI)
echo "  Deploying Kargo Chart (OCI)..."
kubectl --kubeconfig "$KUBECONFIG_CMD" create ns kargo || true

# Password: admin
HASH='$2b$12$juu6/PGSVlc8zWLT8GbokeqUlkT6x5HX.oVRa2v/bM44XPVW2zmsq'
# Token Signing Key (arbitrary string)
SIGN_KEY="kargo-demo-signing-key-1234567890"

# Using OCI registry
helm --kubeconfig "$KUBECONFIG_CMD" upgrade --install kargo oci://ghcr.io/akuity/kargo-charts/kargo -n kargo --create-namespace --version 0.6.0 --set dashboard.enabled=true --set api.adminAccount.passwordHash="$HASH" --set api.adminAccount.tokenSigningKey="$SIGN_KEY"

# Patch Kargo UI to NodePort (Service name depends on chart)
echo "  Patching Kargo UI to NodePort..."
# Chart usually creates 'kargo-dashboard' or 'kargo-ui'
# Let's try to detect or patch common names.
kubectl --kubeconfig "$KUBECONFIG_CMD" -n kargo patch svc kargo-dashboard -p '{"spec": {"type": "NodePort"}}' --type merge || \
kubectl --kubeconfig "$KUBECONFIG_CMD" -n kargo patch svc kargo-ui -p '{"spec": {"type": "NodePort"}}' --type merge || \
echo "Warning: Could not patch Kargo UI service."

# 7. Setup Gitea User/Repo
echo "--- Configuring Gitea ---"
chmod +x "$SCRIPT_DIR/command-cluster/setup-gitea.sh"
"$SCRIPT_DIR/command-cluster/setup-gitea.sh"

# 8. Deploy Kargo Pipeline & Apps
echo "--- Deploying Kargo Pipeline & Argo Apps ---"
# Wait for Gitea to be ready so we can push the code
sleep 10
# We need to push the new gitops-repo structure to Gitea *before* applying Kargo resources
# The setup-gitea.sh script does the push. Ensure it includes the new files.

# Apply Kargo Project/Warehouse/Stage
kubectl --kubeconfig "$KUBECONFIG_CMD" apply -f "$SCRIPT_DIR/../gitops-repo/infra/kargo/kargo-resources.yaml"

# Apply ArgoCD Apps
kubectl --kubeconfig "$KUBECONFIG_CMD" apply -f "$SCRIPT_DIR/manifests/kargo-demo-apps.yaml"

# Calico Modules (Best Effort)
# These might fail if Calico API isn't fully ready yet.
echo "--- Deploying Calico Modules (Best Effort) ---"
kubectl --kubeconfig "$KUBECONFIG_CMD" apply -f "$SCRIPT_DIR/manifests/tiers.yaml" || echo "Warning: Failed to apply Tiers"
kubectl --kubeconfig "$KUBECONFIG_CMD" apply -f "$SCRIPT_DIR/manifests/catfacts.yaml" || echo "Warning: Failed to apply Catfacts"
kubectl --kubeconfig "$KUBECONFIG_CMD" apply -f "$SCRIPT_DIR/manifests/catfacts-nwp.yaml" || echo "Warning: Failed to apply NWP"


echo "=== Collecting Access Details ==="

# Helper to get NodePort
get_nodeport() {
    local ns=$1
    local svc=$2
    kubectl --kubeconfig "$KUBECONFIG_CMD" -n "$ns" get svc "$svc" -o jsonpath='{.spec.ports[0].nodePort}'
}

# Wait for ArgoCD Password
echo "Waiting for ArgoCD secret..."
timeout 60s bash -c "until kubectl --kubeconfig '$KUBECONFIG_CMD' -n argocd get secret argocd-initial-admin-secret &>/dev/null; do sleep 2; done"

ARGO_PASS=$(kubectl --kubeconfig "$KUBECONFIG_CMD" -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d)
ARGO_PORT=$(get_nodeport "argocd" "argocd-server")
GITEA_PORT=$(get_nodeport "gitea" "gitea-http")
KARGO_PORT=$(get_nodeport "kargo" "kargo-ui" || echo "NodePort-Not-Found")

# Calico Whisker Check
WHISKER_STATUS="Not Found (OSS Version)"
if kubectl --kubeconfig "$KUBECONFIG_CMD" -n calico-system get svc whisker &>/dev/null; then
    kubectl --kubeconfig "$KUBECONFIG_CMD" -n calico-system patch svc whisker -p '{"spec": {"type": "NodePort"}}' --type merge || true
    WHISKER_PORT=$(get_nodeport "calico-system" "whisker")
    WHISKER_STATUS="http://192.168.100.10:$WHISKER_PORT"
elif kubectl --kubeconfig "$KUBECONFIG_CMD" -n calico-system get svc goldmane &>/dev/null; then
    kubectl --kubeconfig "$KUBECONFIG_CMD" -n calico-system patch svc goldmane -p '{"spec": {"type": "NodePort"}}' --type merge || true
    GOLDMANE_PORT=$(get_nodeport "calico-system" "goldmane")
    WHISKER_STATUS="Goldmane Flow Logs API: https://192.168.100.10:$GOLDMANE_PORT"
fi

echo ""
echo "=================================================="
echo "       INSTALLATION COMPLETE: ARGO-CD ONLY"
echo "=================================================="
echo "Host IP: 192.168.100.10 (Command Cluster Master)"
echo ""
echo "1. ArgoCD (Management)"
echo "   - URL:      https://192.168.100.10:$ARGO_PORT"
echo "   - User:     admin"
echo "   - Password: $ARGO_PASS"
echo "   - Clusters: gpu-cluster (Reg), cpu-cluster (Reg)"
echo ""
echo "2. Calico Whisker (Observability)"
echo "   - URL:      $WHISKER_STATUS"
echo ""
echo "3. Gitea (Local Git source)"
echo "   - URL:      http://192.168.100.10:$GITEA_PORT"
echo "   - User:     gitea_admin"
echo "   - Pass:     gitea_admin_password"
echo "   - Repo:     http://192.168.100.10:$GITEA_PORT/gitea_admin/gitops-repo.git"
echo ""
echo "4. Kargo (Release Orchestration)"
echo "   - URL:      http://192.168.100.10:$KARGO_PORT"
echo "   - Note:     Login with admin/password (default if Dex enabled) or check docs."
echo "=================================================="
