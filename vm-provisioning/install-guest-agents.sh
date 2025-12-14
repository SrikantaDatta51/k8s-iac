#!/bin/bash
set -e

# List of all VMs and their IPs (based on known mapping)
# cmd-master: 10, cmd-worker-1: 11, cmd-worker-2: 12
# gpu-master: 20, gpu-worker-gpu: 21, gpu-worker-cpu: 22
# cpu-master: 30, cpu-worker-1: 31, cpu-worker-2: 32

declare -A VM_IPS
VM_IPS=(
    ["cmd-master"]="192.168.100.10"
    ["cmd-worker-1"]="192.168.100.11"
    ["cmd-worker-2"]="192.168.100.12"
    ["gpu-master"]="192.168.100.20"
    ["gpu-worker-gpu"]="192.168.100.21"
    ["gpu-worker-cpu"]="192.168.100.22"
    ["cpu-master"]="192.168.100.30"
    ["cpu-worker-1"]="192.168.100.31"
    ["cpu-worker-2"]="192.168.100.32"
)

echo "Installing qemu-guest-agent on all VMs..."

for vm in "${!VM_IPS[@]}"; do
    ip="${VM_IPS[$vm]}"
    echo "Processing $vm ($ip)..."
    
    # Check if reachable
    if ! ping -c 1 -W 1 "$ip" &> /dev/null; then
        echo "⚠️  $vm ($ip) is not reachable. Skipping."
        continue
    fi

    # Install agent
    ssh -o StrictHostKeyChecking=no "ubuntu@$ip" "sudo apt-get update && sudo apt-get install -y qemu-guest-agent && sudo systemctl start qemu-guest-agent"
    
    echo "✅ Agent installed on $vm"
done

echo "All agents installed. Giving them a moment to sync..."
sleep 5
./03-check-status.sh
