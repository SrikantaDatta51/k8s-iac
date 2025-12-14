#!/bin/bash
set -e

# SSH Wrapper to avoid checking host keys and dealing with know_hosts for ephemeral VMs
SSH_OPTS="-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i $HOME/.ssh/id_rsa"
SSH_USER="ubuntu"
NET_PREFIX="192.168.100"

# Define Clusters
# Format: "MASTER_IP_SUFFIX:WORKER_SUFFIXES_COMMA_SEP"
# Worker suffixes are comma separated
CLUSTERS=(
    "10:11,12"  # Command Cluster: Master .10, Workers .11, .12
    "20:21,22"  # GPU Cluster: Master .20, Workers .21, .22
    "30:31,32"  # CPU Cluster: Master .30, Workers .31, .32
)

CLUSTER_NAMES=(
    "command-cluster"
    "gpu-cluster"
    "cpu-cluster"
)

SCRIPTS_DIR="$(dirname "$0")"

install_prereqs() {
    local ip=$1
    echo "  [Node $ip] Installing prerequisites..."
    scp $SSH_OPTS "$SCRIPTS_DIR/install-prereqs.sh" "$SSH_USER@$ip:~/"
    ssh $SSH_OPTS "$SSH_USER@$ip" "sudo ./install-prereqs.sh"
}

init_master() {
    local ip=$1
    echo "  [Master $ip] Initializing Control Plane..."
    scp $SSH_OPTS "$SCRIPTS_DIR/manage-cluster.sh" "$SSH_USER@$ip:~/"
    # We use a standard CIDR for simplicity, or we could customize per cluster
    ssh $SSH_OPTS "$SSH_USER@$ip" "sudo ./manage-cluster.sh init 10.244.0.0/16"
}

join_worker() {
    local master_ip=$1
    local worker_ip=$2
    echo "  [Worker $worker_ip] Joining cluster via Master $master_ip..."
    
    # Fetch join command from master
    ssh $SSH_OPTS "$SSH_USER@$master_ip" "cat ~/join-command.sh" > /tmp/join_cmd_${master_ip}.sh
    
    # Send to worker
    scp $SSH_OPTS /tmp/join_cmd_${master_ip}.sh "$SSH_USER@$worker_ip:~/join-command.sh"
    
    # Run join
    ssh $SSH_OPTS "$SSH_USER@$worker_ip" "sudo chmod +x ~/join-command.sh && sudo ./join-command.sh"
}

fetch_kubeconfig() {
    local master_ip=$1
    local cluster_name=$2
    echo "  [Master $ip] Fetching Kubeconfig..."
    mkdir -p ~/.kube
    scp $SSH_OPTS "$SSH_USER@$master_ip:~/.kube/config" ~/.kube/config-${cluster_name}
    echo "  Kubeconfig saved to ~/.kube/config-${cluster_name}"
}

# Main Loop
for i in "${!CLUSTERS[@]}"; do
    CLUSTER_INFO="${CLUSTERS[$i]}"
    CLUSTER_NAME="${CLUSTER_NAMES[$i]}"
    
    IFS=':' read -r MASTER_SUFFIX WORKER_SUFFIXES <<< "$CLUSTER_INFO"
    MASTER_IP="${NET_PREFIX}.${MASTER_SUFFIX}"
    
    echo "=== Processing $CLUSTER_NAME (Master: $MASTER_IP) ==="
    
    # 1. Install Prereqs on Master
    install_prereqs "$MASTER_IP"
    
    # 2. Init Master
    init_master "$MASTER_IP"
    
    # 3. Fetch Kubeconfig
    fetch_kubeconfig "$MASTER_IP" "$CLUSTER_NAME"
    
    # 4. Process Workers
    IFS=',' read -ra WORKERS <<< "$WORKER_SUFFIXES"
    for WORKER_SUFFIX in "${WORKERS[@]}"; do
        WORKER_IP="${NET_PREFIX}.${WORKER_SUFFIX}"
        echo "  --- Processing Worker $WORKER_IP ---"
        
        # Install Prereqs
        install_prereqs "$WORKER_IP"
        
        # Join Cluster
        join_worker "$MASTER_IP" "$WORKER_IP"
    done
    
    echo "=== $CLUSTER_NAME Setup Complete ==="
    echo ""
done

echo "All clusters bootstrapped!"
