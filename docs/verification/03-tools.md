# Layer 3: Tools Verification (ArgoCD, Calico, Gitea)

**Goal:** Ensure management tools and network plugins are functional.

## 1. Network Plugin (Calico)
Run for EACH cluster (Command, GPU, CPU):
```bash
export KUBECONFIG=~/.kube/config-command-cluster
# Check Calico Nodes
kubectl get pods -n calico-system -l k8s-app=calico-node
# Check Typha (if deployed) or Kube-Controllers
kubectl get pods -n calico-system
```
**Whisker/Goldmane**:
```bash
kubectl get svc -n calico-system
# Look for 'goldmane' or 'whisker' -> NodePort
```

## 2. ArgoCD (Command Cluster)
```bash
# Check Pods
kubectl -n argocd get pods
# Check Service Reachability
curl -k https://192.168.100.10:<NodePort>
```
**Login Check**:
```bash
# Get Pass
PASS=$(kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d)
# Login (requires argocd cli, optional)
# argocd login 192.168.100.10:<NodePort> --username admin --password $PASS --insecure
```

## 3. Gitea (Local Git)
```bash
# Check Pod
kubectl -n gitea get pods
# Test URL
curl -I http://192.168.100.10:30300
```
