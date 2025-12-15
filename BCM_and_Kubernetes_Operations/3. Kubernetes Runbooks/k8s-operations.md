# Kubernetes Operations Manual
## Principal Engineer's Guide to GitOps & Modern Platform Management

---

## Part 1: Top 15 Day-0 Operations (Bootstrap & Onboarding)

These tasks establish the cluster foundation. They are declarative and automated where possible.

1.  **Cluster Bootstrap (The "Big Bang")**:
    *   **Action**: Provision Control Plane and Workers via IaC.
    *   **Command**: `./01-bootstrap-clusters.sh` (as defined in our Repo).
2.  **CNI Installation (Calico)**:
    *   **Action**: Establish Pod-to-Pod networking.
    *   **Method**: `kubectl apply -f calico.yaml` (Happens automatically during bootstrap).
3.  **GitOps Initialization (ArgoCD)**:
    *   **Action**: Install the "Controller of/for All Things".
    *   **Command**: `helm install argocd` -> Apply `root-application.yaml`.
4.  **StorageClass Provisioning**:
    *   **Action**: Define default storage (e.g., Local Path or Rook/Ceph).
    *   **Method**: `kubectl apply -f storage-class.yaml`.
5.  **Namespace Governance**:
    *   **Action**: Create standard namespaces (`monitoring`, `security`, `gateways`) with ResourceQuotas.
    *   **Method**: Git commit to `env/common/namespaces.yaml`.
6.  **Secret Management Setup (ExternalSecrets)**:
    *   **Action**: Connect K8s to Vault/AWS Secrets Manager.
    *   **Method**: Deploy `ExternalSecretStore` CRD via Helm.
7.  **Ingress Controller Deployment**:
    *   **Action**: Deploy Nginx/Traefik to handle incoming traffic.
    *   **Method**: Included in "Uber Bundle" dependency.
8.  **Observability Stack (Prometheus/Grafana)**:
    *   **Action**: Install CRDs (ServiceMonitor, AlertManager).
    *   **Method**: ArgoCD syncs `kube-prometheus-stack`.
9.  **RBAC Configuration**:
    *   **Action**: Bind AD/OIDC Groups to ClusterRoles (`view`, `edit`, `admin`).
    *   **Method**: Apply `RoleBinding` manifests.
10. **Registry Authentication**:
    *   **Action**: Create `imagePullSecrets` for private repos.
    *   **Command**: `kubectl create secret docker-registry ...` (or via ExternalSecrets).
11. **Policy Enforcement (OPA/Kyverno)**:
    *   **Action**: Deny privileged pods or root containers.
    *   **Method**: Apply `ClusterPolicy` manifests.
12. **Node Labeling & Tainting**:
    *   **Action**: Dedicate nodes for specific workloads (e.g., GPU).
    *   **Command**: `kubectl label nodes worker-gpu-1 accelerator=nvidia-a100`
13. **Backup Integration (Velero)**:
    *   **Action**: Install Velero and point to S3 Bucket.
    *   **Method**: Helm Chart + Cloud Credentials secret.
14. **Service Mesh Link (Optional)**:
    *   **Action**: Install Istio/Linkerd for mTLS.
    *   **Method**: ArgoCD Application.
15. **SSOT Sync**:
    *   **Action**: The final check.
    *   **Command**: `argocd app sync --all` to ensure the cluster matches Git completely.

---

## Part 2: Top 15 Day-2 Operations (Lifecycle & Debugging)

Tasks performed during the operational life of the platform.

1.  **Debugging `CrashLoopBackOff`**:
    *   **Action**: Investigate app startup failure.
    *   **Command**: `kubectl logs -p <pod>` (Previous logs) or `kubectl describe pod`.
2.  **Debugging Network drops (Ephemeral Containers)**:
    *   **Action**: Inspect traffic in a distroless container.
    *   **Command**: `kubectl debug -it <pod> --image=nicolaka/netshoot`
3.  **Cordon & Drain (Node Maintenance)**:
    *   **Action**: Remove a node for kernel upgrades.
    *   **Command**: `kubectl cordon <node>` -> `kubectl drain <node> --ignore-daemonsets`.
4.  **Rolling Restart**:
    *   **Action**: Force a pod rotation without downtime.
    *   **Command**: `kubectl rollout restart deployment/my-app`
5.  **Certificate Rotation (Cert-Manager)**:
    *   **Action**: Renew Ingress TLS certs.
    *   **Method**: Automated by `cert-manager`. Manual trigger: `cmctl renew <cert>`.
6.  **Scaling Applications (HPA)**:
    *   **Action**: Adjust auto-scaling thresholds.
    *   **Method**: Edit `HorizontalPodAutoscaler` yaml in Git.
7.  **Analyzing High CPU/Memory (Metrics Server)**:
    *   **Action**: Who is the noisy neighbor?
    *   **Command**: `kubectl top pods -A --sort-by=cpu`
8.  **Pvc/Volume Resizing**:
    *   **Action**: Expand a database disk.
    *   **Method**: Edit `PersistentVolumeClaim` size in Git -> `kubectl apply`.
9.  **ArgoCD Sync/Rollback**:
    *   **Action**: Bad deployment. Revert to previous hash.
    *   **Command**: `argocd app rollback <app-name>` (or `git revert`).
10. **Etcd Maintenance (Defrag)**:
    *   **Action**: Compact the K/V store.
    *   **Command**: Exec into etcd pod -> `etcdctl defrag`. (Automated by our Proactive Cron).
11. **Upgrade Kubernetes Version**:
    *   **Action**: Upgrade Control Plane then Kubelet.
    *   **Command**: `kubeadm upgrade apply v1.29` -> `apt-get install kubelet=1.29`.
12. **Prometheus Rule Tuning**:
    *   **Action**: Silence false positive alerts.
    *   **Method**: Edit `PrometheusRule` CRD in Git.
13. **Analyzing "Evicted" Pods**:
    *   **Action**: Check Node Pressure (Disk/Ram).
    *   **Command**: `kubectl get event --field-selector type=Warning`
14. **Namespace cleanup (Stuck Terminating)**:
    *   **Action**: Force delete a zombie namespace.
    *   **Command**: Remove finalizers via raw API call (carefully).
15. **Disaster Recovery Restore**:
    *   **Action**: Restore cluster state from backup.
    *   **Command**: `velero restore create --from-backup <backup-name>`

---
**Summary**: K8s Operations are *Declarative, API-driven, and Git-Centric*.
