# Layer 1: VM & Network Verification

**Goal:** Ensure KVM VMs are running, accessible, and the bridge network is routing correctly.

## 1. Host Network Check
Run on Host:
```bash
# Check Bridge exists and has IP 192.168.100.1
ip addr show virbr-k8s

# Check Libvirt Network Status
sudo virsh net-list --all
# Expected: k8s-net, active, autostart, persistent
```

## 2. VM Status
```bash
sudo virsh list --all
# Expected: cmd-master, cmd-worker-*, gpu-master, etc. all 'running'
```

## 3. Connectivity Check (Ping)
```bash
# Gateway to VMs
ping -c 2 192.168.100.10  # Command Master
ping -c 2 192.168.100.20  # GPU Master
ping -c 2 192.168.100.30  # CPU Master
```

## 4. SSH Access
```bash
# Verify passwordless SSH is working
ssh -i ~/.ssh/id_rsa ubuntu@192.168.100.10 "hostname -I"
ssh -i ~/.ssh/id_rsa ubuntu@192.168.100.20 "hostname -I"
```
