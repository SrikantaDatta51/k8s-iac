#!/bin/bash
set -e

# Usage: 
#   Identify as Master: sudo ./manage-cluster.sh init <POD_CIDR>
#   Join Cluster:       sudo ./manage-cluster.sh join <TOKEN> <HASH> <MASTER_IP>

MODE=$1

if [ "$MODE" == "init" ]; then
    POD_CIDR=${2:-"10.244.0.0/16"}
    echo "Initializing Control Plane with Pod CIDR $POD_CIDR..."
    kubeadm init --pod-network-cidr=$POD_CIDR --upload-certs | tee kubeadm-init.out
    
    # Extract join command
    kubeadm token create --print-join-command > join-command.sh
    chmod +x join-command.sh
    
    # Configure for root
    mkdir -p $HOME/.kube
    cp -i /etc/kubernetes/admin.conf $HOME/.kube/config
    chown $(id -u):$(id -g) $HOME/.kube/config

    # Configure for ubuntu user (required for SCP retrieval)
    mkdir -p /home/ubuntu/.kube
    cp -i /etc/kubernetes/admin.conf /home/ubuntu/.kube/config
    chown -R ubuntu:ubuntu /home/ubuntu/.kube

    echo "Cluster initialized."
    echo "To join workers, run the command printed above."

elif [ "$MODE" == "join" ]; then
    # In a real automation scenario, you'd pass the full join command or discovery token
    # For simplicity, we assume the user puts the join command in a file or passes args.
    # Here we just expect the user to run the specific kubeadm join command provided by 'init'
    echo "Please run the 'kubeadm join' command provided by the master node."
    
    # Or purely automated way if arguments were perfect:
    # kubeadm join $2:6443 --token $3 --discovery-token-ca-cert-hash $4
else
    echo "Usage: $0 [init|join]"
fi
