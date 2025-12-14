#!/bin/bash
set -e

NET_NAME="k8s-net"
NET_XML="./${NET_NAME}.xml"

# Root check removed for user-mode libvirt access attempt
# if [ "$EUID" -ne 0 ]; then ... fi

echo "Creating Network XML definition..."
cat > "$NET_XML" <<EOF
<network>
  <name>$NET_NAME</name>
  <forward mode='bridge'/>
  <bridge name='virbr-k8s'/>
</network>
EOF

if virsh net-info "$NET_NAME" > /dev/null 2>&1; then
    echo "Network $NET_NAME already exists."
else
    echo "Defining network $NET_NAME..."
    virsh net-define "$NET_XML"
    virsh net-start "$NET_NAME"
    virsh net-autostart "$NET_NAME"
fi

echo "Network $NET_NAME is ready."
virsh net-list --all
