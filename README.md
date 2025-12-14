# K8s Infrastructure as Code (KVM & GitOps)

This project contains scripts to provision KVM-based Kubernetes clusters and standard GitOps configurations.

## Directory Structure

- `vm-provisioning/`: Scripts to create VMs on the host.
- `cluster-bootstrap/`: Scripts to run inside VMs to install K8s.
- `cluster-configs/`: Manifests for ArgoCD, Calico, Nvidia, etc.
- `gitops-repo/`: Template for your GitOps repository.

## Quick Start Configuration

### 1. Provision VMs (On Host)
Run the orchestration script to check prerequisites and create all 9 VMs.
```bash
cd vm-provisioning
sudo ./02-provision-all.sh
```

### 2. Bootstrap Clusters (Inside VMs)
SSH into each node (default user `ubuntu`, key `~/.ssh/id_rsa`).
#### On All Nodes:
```bash
# Copy install-prereqs.sh to the node
scp cluster-bootstrap/install-prereqs.sh ubuntu@<VM_IP>:~
ssh ubuntu@<VM_IP> "sudo chmod +x install-prereqs.sh && sudo ./install-prereqs.sh"
```
#### On Master Nodes:
```bash
scp cluster-bootstrap/manage-cluster.sh ubuntu@<MASTER_IP>:~
ssh ubuntu@<MASTER_IP> "sudo chmod +x manage-cluster.sh && sudo ./manage-cluster.sh init"
```
*Save the join command output!*

#### On Worker Nodes:
Run the join command provided by the `init` step.

#### On GPU Nodes:
Run the GPU setup script.
```bash
scp cluster-bootstrap/install-gpu.sh ubuntu@<GPU_NODE_IP>:~
ssh ubuntu@<GPU_NODE_IP> "sudo chmod +x install-gpu.sh && sudo ./install-gpu.sh"
```

### 3. Cluster Configuration (Post-Install)
Apply manifests using `kubectl`.

#### Command Cluster
```bash
# Apply Calico
kubectl apply -f cluster-configs/calico.yaml

# Install ArgoCD
kubectl create namespace argocd
kubectl apply -n argocd -f cluster-configs/command-cluster/argocd-install.yaml

# Install Karmada (Run script)
./cluster-configs/command-cluster/karmada-setup.sh
```

#### GPU Cluster
```bash
# Apply Calico
kubectl apply -f cluster-configs/calico.yaml

# Apply Nvidia Device Plugin
kubectl apply -f cluster-configs/gpu-cluster/nvidia-device-plugin.yaml
```

#### CPU Cluster
```bash
# Apply Calico
kubectl apply -f cluster-configs/calico.yaml
```

## GitOps Workflow
See `gitops-repo/workflow-docs.md` for details on how to use the GitOps structure to promote changes from CPU to GPU clusters.

## Observability Checks
- **Calico Whisker**: Requires Calico v3.30+. The included `calico.yaml` is v3.29.1. You may need to upgrade Calico to enable Whisker/Flowlogs UI fully.
- **PCI Passthrough**: Ensure your host IOMMU is enabled and you assign the GPU PCI device to `gpu-worker-gpu` in `virt-install` (manual step specific to hardware).
