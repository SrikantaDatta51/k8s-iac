#!/bin/bash
set -e

# Usage: sudo ./install-gpu.sh
# Run this on GPU nodes

echo "Installing Nvidia Drivers..."
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/libnvidia-container/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/libnvidia-container/$distribution/libnvidia-container.list | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

apt-get update
# Install drivers (headless server)
apt-get install -y nvidia-headless-535 nvidia-utils-535

# Install container toolkit
apt-get install -y nvidia-container-toolkit

# Configure containerd
nvidia-ctk runtime configure --runtime=containerd
systemctl restart containerd

echo "GPU Setup Complete. Reboot recommended."
