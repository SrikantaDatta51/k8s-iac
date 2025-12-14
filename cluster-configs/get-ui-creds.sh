#!/bin/bash
set -e

KUBECONFIG="$HOME/.kube/config-command-cluster"

echo "=== Access Credentials & Endpoints ==="
echo ""

# ArgoCD
echo ">> ArgoCD"
ARGO_PWD=$(kubectl --kubeconfig $KUBECONFIG -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" 2>/dev/null | base64 -d || echo "Not Found")
ARGO_PORT=$(kubectl --kubeconfig $KUBECONFIG -n argocd get svc argocd-server -o jsonpath='{.spec.ports[?(@.name=="https")].nodePort}')
echo "  URL: https://192.168.100.10:$ARGO_PORT"
echo "  User: admin"
echo "  Pass: $ARGO_PWD"
echo ""

# Karmada
echo ">> Karmada Dashboard"
#KARMADA_PORT=$(kubectl --kubeconfig $KUBECONFIG -n karmada-system get svc karmada-dashboard -o jsonpath='{.spec.ports[0].nodePort}')
#echo "  URL: http://192.168.100.10:$KARMADA_PORT"
echo "  Auth: (No Auth / Token)"
echo ""

# Gitea
echo ">> Gitea"
GITEA_PORT=$(kubectl --kubeconfig $KUBECONFIG -n gitea get svc gitea-http -o jsonpath='{.spec.ports[0].nodePort}')
echo "  URL: http://192.168.100.10:$GITEA_PORT"
echo "  User: gitea_admin"
echo "  Pass: r8sA84!L^s" # Hardcoded from installation if secret missing, strictly for dev
echo ""

# ChartMuseum
echo ">> ChartMuseum"
CM_PORT=$(kubectl --kubeconfig $KUBECONFIG -n chartmuseum get svc chartmuseum -o jsonpath='{.spec.ports[0].nodePort}')
echo "  URL: http://192.168.100.10:$CM_PORT"
echo "  Api: http://192.168.100.10:$CM_PORT/api/charts"
echo ""

echo "Done."
