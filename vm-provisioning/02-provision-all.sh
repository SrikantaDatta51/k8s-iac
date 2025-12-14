#!/bin/bash
set -e

# Setup Network first
./00-setup-host-net.sh

# Function to wait for SSH
wait_for_ssh() {
    local ip=$1
    echo "Waiting for SSH on $ip..."
    while ! nc -z $ip 22; do
        sleep 2
    done
    echo "SSH is up on $ip"
}

# --- Command Cluster (1 Master, 2 Workers) ---
echo "Provisioning Command Cluster..."
./01-create-vm.sh cmd-master 2 4096 20 10
./01-create-vm.sh cmd-worker-1 2 4096 20 11
./01-create-vm.sh cmd-worker-2 2 4096 20 12

# --- GPU Cluster (1 Master, 1 GPU Worker, 1 CPU Worker) ---
echo "Provisioning GPU Cluster..."
# Note: GPU Worker will need manual PCI passthrough config later or modified virt-install args
./01-create-vm.sh gpu-master 2 4096 20 20
./01-create-vm.sh gpu-worker-gpu 4 8192 40 21
./01-create-vm.sh gpu-worker-cpu 2 4096 20 22

# --- CPU Cluster (1 Master, 2 Workers) ---
echo "Provisioning CPU Cluster..."
./01-create-vm.sh cpu-master 2 4096 20 30
./01-create-vm.sh cpu-worker-1 2 4096 20 31
./01-create-vm.sh cpu-worker-2 2 4096 20 32

echo "All VMs Provisioned."
