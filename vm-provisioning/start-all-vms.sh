#!/bin/bash

# List of all VMs
VMS=(
    "cmd-master" "cmd-worker-1" "cmd-worker-2"
    "gpu-master" "gpu-worker-gpu" "gpu-worker-cpu"
    "cpu-master" "cpu-worker-1" "cpu-worker-2"
)

echo "Starting K8s Cluster VMs..."

for vm in "${VMS[@]}"; do
    state=$(virsh domstate "$vm" 2>/dev/null || echo "not_found")
    if [[ "$state" == "running" ]]; then
        echo "✅ $vm is already running."
    elif [[ "$state" == "shut off" ]]; then
        echo "🚀 Starting $vm..."
        virsh start "$vm"
    elif [[ "$state" == "not_found" ]]; then
        echo "⚠️  VM $vm not found. Did you provision it?"
    else
        echo "ℹ️  VM $vm is in state: $state"
    fi
done

echo "Waiting a few seconds for networking..."
sleep 5

echo "Current Status:"
./03-check-status.sh
