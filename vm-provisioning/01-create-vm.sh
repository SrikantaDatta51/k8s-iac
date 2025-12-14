#!/bin/bash
set -e

# Usage: ./01-create-vm.sh <NAME> <CPU> <RAM_MB> <DISK_GB> <IP_LAST_OCTET>
# Example: ./01-create-vm.sh k8s-master 2 2048 20 10

VM_NAME=$1
VCPUS=$2
RAM_MB=$3
DISK_GB=$4
IP_OCTET=$5

# Helper: Ensure images directory exists
IMAGES_DIR="$HOME/k8s-images"
mkdir -p "$IMAGES_DIR"

BASE_IMAGE_PATH="$IMAGES_DIR/ubuntu-22.04-server-cloudimg-amd64.img"
VM_DISK_PATH="$IMAGES_DIR/${VM_NAME}.qcow2"
CLOUD_INIT_ISO="$IMAGES_DIR/${VM_NAME}-cidata.iso"
PUB_KEY_PATH="$HOME/.ssh/id_rsa.pub"


if [ -z "$VM_NAME" ] || [ -z "$VCPUS" ] || [ -z "$RAM_MB" ] || [ -z "$DISK_GB" ] || [ -z "$IP_OCTET" ]; then
    echo "Usage: $0 <NAME> <CPU> <RAM_MB> <DISK_GB> <IP_LAST_OCTET>"
    exit 1
fi

if [ ! -f "$BASE_IMAGE_PATH" ]; then
    echo "Base image not found at $BASE_IMAGE_PATH"
    echo "Downloading Ubuntu 22.04 cloud image..."
    wget -O "$BASE_IMAGE_PATH" https://cloud-images.ubuntu.com/releases/22.04/release/ubuntu-22.04-server-cloudimg-amd64.img
fi
    wget "https://cloud-images.ubuntu.com/releases/22.04/release/ubuntu-22.04-server-cloudimg-amd64.img" -O "$BASE_IMAGE_PATH"
    if [ $? -ne 0 ]; then
        echo "Failed to download image. Please check your internet connection or URL."
        exit 1
    fi
fi

# Ensure user SSH key exists
if [ ! -f "$PUB_KEY_PATH" ]; then
    echo "SSH Public Key not found at $PUB_KEY_PATH. Generating one..."
    ssh-keygen -t rsa -b 4096 -f "$HOME/.ssh/id_rsa" -N ""
fi

SSH_KEY=$(cat "$PUB_KEY_PATH")

echo "Creating VM $VM_NAME..."

# Create Disk
if [ ! -f "$VM_DISK_PATH" ]; then
    qemu-img create -f qcow2 -F qcow2 -b "$BASE_IMAGE_PATH" "$VM_DISK_PATH" "${DISK_GB}G"
fi

# Create Cloud-Init Data
cat > meta-data <<EOF
instance-id: $VM_NAME
local-hostname: $VM_NAME
EOF

cat > user-data <<EOF
#cloud-config
users:
  - name: ubuntu
    groups: sudo
    shell: /bin/bash
    sudo: ['ALL=(ALL) NOPASSWD:ALL']
    ssh-authorized-keys:
      - $SSH_KEY
packages:
  - qemu-guest-agent
ssh_pwauth: true
chpasswd:
  list: |
    ubuntu:password
  expire: false
write_files:
  - path: /etc/netplan/99-config.yaml
    content: |
      network:
        version: 2
        ethernets:
          enp1s0:
            dhcp4: false
            addresses: [192.168.100.${IP_OCTET}/24]
            routes:
              - to: default
                via: 192.168.100.1
            nameservers:
              addresses: [8.8.8.8, 1.1.1.1]
runcmd:
  - netplan apply
EOF

# Create ISO for cloud-init
genisoimage -output "$CLOUD_INIT_ISO" -volid cidata -joliet -rock user-data meta-data
rm user-data meta-data

# Install VM
virt-install \
  --name "$VM_NAME" \
  --ram "$RAM_MB" \
  --vcpus "$VCPUS" \
  --disk path="$VM_DISK_PATH",format=qcow2 \
  --disk path="$CLOUD_INIT_ISO",device=cdrom \
  --os-variant ubuntu22.04 \
  --network network=k8s-net,model=virtio \
  --graphics none \
  --console pty,target_type=serial \
  --import \
  --channel unix,target_type=virtio,name=org.qemu.guest_agent.0 \
  --noautoconsole

echo "VM $VM_NAME started at 192.168.100.${IP_OCTET}"
