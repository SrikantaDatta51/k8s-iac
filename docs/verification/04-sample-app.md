# Layer 4: Sample App & GitOps Verification

**Goal:** Ensure the NGINX sample app deploys via ArgoCD to the target clusters.

## 1. Git Repository
Ensure Gitea has the repo:
```bash
# Clone to verify content
git clone http://192.168.100.10:30300/gitea_admin/gitops-repo.git /tmp/verify-repo
ls /tmp/verify-repo/apps/whisker-demo
```

## 2. ArgoCD Applications
Check if Applications are synced.
```bash
export KUBECONFIG=~/.kube/config-command-cluster
kubectl -n argocd get applications
# Expected: nginx-gpu, nginx-cpu (if using App-of-Apps or multiple Apps)
```

## 3. Target Cluster Deployment
Verify the app actually landed on the GPU/CPU clusters.
```bash
# Check GPU Cluster for NGINX
kubectl --kubeconfig ~/.kube/config-gpu-cluster -n quickstart get pods

# Check CPU Cluster for NGINX
kubectl --kubeconfig ~/.kube/config-cpu-cluster -n quickstart get pods
```

## 4. Connectivity (Service Access)
```bash
# Port forward to test NGINX on GPU cluster
kubectl --kubeconfig ~/.kube/config-gpu-cluster -n quickstart port-forward svc/nginx 8888:80 &
curl localhost:8888
kill %1
```
