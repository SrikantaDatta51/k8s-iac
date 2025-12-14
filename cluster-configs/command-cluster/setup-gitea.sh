#!/bin/bash
set -e

# Setup Gitea User and Repo automatically
KUBECONFIG="$HOME/.kube/config-command-cluster"
POD=$(kubectl --kubeconfig "$KUBECONFIG" -n gitea get pod -l app=gitea -o jsonpath="{.items[0].metadata.name}")

echo "Found Gitea Pod: $POD"

# 1. Create Admin User
echo "Creating Admin User..."
kubectl --kubeconfig "$KUBECONFIG" -n gitea exec "$POD" -- su git -c "gitea admin user create --username gitea_admin --password gitea_admin_password --email admin@example.com --admin" || echo "User likely already exists"

# 2. Create Repository (using curl against API)
echo "Creating GitOps Repository..."
TOKEN=$(curl -s -X POST "http://192.168.100.10:30300/api/v1/users/gitea_admin/tokens" \
    -H "Content-Type: application/json" \
    -u gitea_admin:gitea_admin_password \
    -d '{"name":"setup-script-token", "scopes": ["repo"]}' | grep -o '"sha1":"[^"]*"' | cut -d'"' -f4)

if [ -z "$TOKEN" ]; then
    echo "Could not generate token (or already exists). Trying basic auth..."
    curl -X POST "http://192.168.100.10:30300/api/v1/user/repos" \
        -H "Content-Type: application/json" \
        -u gitea_admin:gitea_admin_password \
        -d '{"name":"gitops-repo", "private": false}'
else
    echo "Token generated. Creating repo..."
    curl -X POST "http://192.168.100.10:30300/api/v1/user/repos" \
        -H "Content-Type: application/json" \
        -H "Authorization: token $TOKEN" \
        -d '{"name":"gitops-repo", "private": false}'
fi

echo ""
echo "=== Gitea Setup Complete ==="
echo "User: gitea_admin"
echo "Pass: gitea_admin_password"
echo "Repo: http://192.168.100.10:30300/gitea_admin/gitops-repo.git"
