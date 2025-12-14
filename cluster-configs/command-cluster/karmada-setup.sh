#!/bin/bash
set -e

# Install Karmada CLI
echo "Installing Karmadactl..."
curl -s https://raw.githubusercontent.com/karmada-io/karmada/master/hack/install-cli.sh | sudo bash

# Init Karmada
echo "Initializing Karmada Control Plane..."
# This requires a running K8s cluster and kubectl context set to it
# We assume this script is run on the command-cluster master or with proper kubeconfig
sudo karmadactl init
