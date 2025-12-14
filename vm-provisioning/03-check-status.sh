#!/bin/bash
set -e

# Checks the status of the K8s VMs and Network

NET_NAME="k8s-net"

echo "=== Network Status ==="
if virsh net-list --all | grep -q "$NET_NAME"; then
    virsh net-list --all | grep "$NET_NAME"
else
    echo "Network $NET_NAME not found."
fi

echo ""
echo "=== VM Status ==="
# List all VMs matching our naming convention (cmd-*, cpu-*, gpu-*)
VMS=$(virsh list --all --name | grep -E '^(cmd|cpu|gpu)-')

if [ -z "$VMS" ]; then
    echo "No K8s VMs found."
else
    for vm in $VMS; do
        STATE=$(virsh domstate "$vm")
        IP=$(virsh domifaddr "$vm" --source agent 2>/dev/null | grep -oE "192\.168\.100\.[0-9]+" || echo "No IP")
        printf "%-20s %-15s %-15s\n" "$vm" "$STATE" "$IP"
    done
fi
