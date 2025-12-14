# Layer 2: Kubernetes Cluster Verification

**Goal:** Ensure all 3 clusters are healthy, nodes are Ready, and API servers are reachable.

## 1. Kubeconfig Existence
Checks if the install script generated configs correctly.
```bash
ls -l ~/.kube/config-command-cluster
ls -l ~/.kube/config-gpu-cluster
ls -l ~/.kube/config-cpu-cluster
```

## 2. Command Cluster Health
```bash
export KUBECONFIG=~/.kube/config-command-cluster
kubectl get nodes -o wide
# Expected: 1 master, 2 workers. Status: Ready.
kubectl get pods -A
# Expected: CoreDNS, Kube-Proxy running.
```

## 3. GPU/CPU Cluster Health
```bash
# GPU Cluster
kubectl --kubeconfig ~/.kube/config-gpu-cluster get nodes
# Verify GPU Node labels (if applied specific labels)

# CPU Cluster
kubectl --kubeconfig ~/.kube/config-cpu-cluster get nodes
```

## 4. API Reachability
```bash
# Curl the API server from the host
curl -k https://192.168.100.10:6443/version
curl -k https://192.168.100.20:6443/version
```
