#!/usr/bin/env bash
#=============================================================================
# K8s Node Storage & Ephemeral Storage Audit Script
# Run FROM INSIDE the Kubernetes node (SSH into the node first)
# Requires: root or sudo
#
# What this audits:
#   1. Block devices & drives — all physical/virtual disks and partitions
#   2. Mount points — what is mounted where, with sizes
#   3. Kubelet configuration — root-dir, ephemeral storage backing
#   4. Containerd configuration — root/state directories, snapshotter
#   5. Ephemeral storage allocatable — what K8s offers to pods
#   6. Per-pod ephemeral usage — what each pod is consuming
#   7. Drive capacity certification — verify full drive is offered
#   8. /var breakdown — what is using /var space
#
# Usage:
#   sudo bash node-storage-audit.sh                    # full audit
#   sudo bash node-storage-audit.sh --json             # JSON output
#   sudo bash node-storage-audit.sh --section drives   # specific section
#=============================================================================

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

SEPARATOR="$(printf '=%.0s' {1..80})"
SUB_SEP="$(printf '-%.0s' {1..60})"

header() {
    echo ""
    echo -e "${BLUE}${SEPARATOR}${NC}"
    echo -e "${BOLD}${CYAN}  $1${NC}"
    echo -e "${BLUE}${SEPARATOR}${NC}"
}

subheader() {
    echo ""
    echo -e "  ${YELLOW}${SUB_SEP}${NC}"
    echo -e "  ${BOLD}$1${NC}"
    echo -e "  ${YELLOW}${SUB_SEP}${NC}"
}

ok()   { echo -e "  ${GREEN}✓${NC} $1"; }
warn() { echo -e "  ${YELLOW}⚠${NC} $1"; }
fail() { echo -e "  ${RED}✗${NC} $1"; }
info() { echo -e "  ${BLUE}ℹ${NC} $1"; }

bytes_to_human() {
    local bytes=$1
    if   (( bytes >= 1099511627776 )); then echo "$(echo "scale=2; $bytes / 1099511627776" | bc) TB"
    elif (( bytes >= 1073741824 ));    then echo "$(echo "scale=2; $bytes / 1073741824" | bc) GB"
    elif (( bytes >= 1048576 ));       then echo "$(echo "scale=2; $bytes / 1048576" | bc) MB"
    else echo "$bytes B"
    fi
}

# ============================================================================
# SECTION 1: BLOCK DEVICES & DRIVES
# ============================================================================
audit_drives() {
    header "1. BLOCK DEVICES & DRIVES"

    subheader "All Block Devices (lsblk)"
    lsblk -o NAME,TYPE,SIZE,FSTYPE,MOUNTPOINT,MODEL,SERIAL,ROTA,TRAN 2>/dev/null || lsblk -o NAME,SIZE,TYPE,MOUNTPOINT
    echo ""

    subheader "Physical Disks Only"
    lsblk -d -o NAME,TYPE,SIZE,MODEL,SERIAL,ROTA,TRAN 2>/dev/null || lsblk -d -o NAME,SIZE,TYPE
    echo ""

    subheader "Disk Sizes (fdisk)"
    fdisk -l 2>/dev/null | grep "^Disk /dev/" | grep -v "loop\|ram" || true
    echo ""

    subheader "RAID / LVM / MD Devices"
    if command -v pvs &>/dev/null; then
        echo "  Physical Volumes (PVs):"
        pvs 2>/dev/null || echo "    (none)"
        echo ""
        echo "  Volume Groups (VGs):"
        vgs 2>/dev/null || echo "    (none)"
        echo ""
        echo "  Logical Volumes (LVs):"
        lvs 2>/dev/null || echo "    (none)"
    else
        info "LVM tools not installed"
    fi
    if [ -f /proc/mdstat ]; then
        echo ""
        echo "  MD RAID:"
        cat /proc/mdstat
    fi
    echo ""

    subheader "NVMe Devices"
    if command -v nvme &>/dev/null; then
        nvme list 2>/dev/null || info "nvme list failed"
    elif ls /dev/nvme* &>/dev/null; then
        ls -la /dev/nvme* 2>/dev/null
    else
        info "No NVMe devices found"
    fi
}

# ============================================================================
# SECTION 2: MOUNT POINTS & FILESYSTEM USAGE
# ============================================================================
audit_mounts() {
    header "2. MOUNT POINTS & FILESYSTEM USAGE"

    subheader "All Mounted Filesystems (real, no tmpfs/overlay)"
    df -hT | head -1
    df -hT | grep -v "tmpfs\|overlay\|squashfs\|devtmpfs\|udev" | tail -n +2 | sort -k7
    echo ""

    subheader "All Mounted Filesystems (including overlay — full view)"
    df -hT | head -1
    df -hT | tail -n +2 | sort -k7
    echo ""

    subheader "Key Mount Points (raw bytes)"
    echo "  Mount Point               | Size (bytes)         | Used (bytes)         | Avail (bytes)        | Use%"
    echo "  $SUB_SEP"
    for mp in / /var /var/lib /var/lib/kubelet /var/lib/containerd /var/log /tmp /home; do
        if mountpoint -q "$mp" 2>/dev/null || [ -d "$mp" ]; then
            read -r size used avail pct < <(df --output=size,used,avail,pcent "$mp" 2>/dev/null | tail -1 | tr -s ' ')
            size_b=$((size * 1024))
            used_b=$((used * 1024))
            avail_b=$((avail * 1024))
            printf "  %-25s | %-20s | %-20s | %-20s | %s\n" \
                "$mp" "$(bytes_to_human $size_b)" "$(bytes_to_human $used_b)" "$(bytes_to_human $avail_b)" "$pct"
        fi
    done
    echo ""

    subheader "Which drive backs each key directory"
    for mp in / /var /var/lib/kubelet /var/lib/containerd /var/log; do
        if [ -d "$mp" ]; then
            dev=$(df "$mp" 2>/dev/null | tail -1 | awk '{print $1}')
            echo "  $mp → $dev"
        fi
    done
}

# ============================================================================
# SECTION 3: KUBELET CONFIGURATION
# ============================================================================
audit_kubelet() {
    header "3. KUBELET CONFIGURATION"

    subheader "Kubelet Process & Arguments"
    local kubelet_cmd
    kubelet_cmd=$(ps aux | grep '[k]ubelet' | head -1) || true
    if [ -z "$kubelet_cmd" ]; then
        fail "kubelet process not found"
        return
    fi
    echo "  $kubelet_cmd" | fold -w 120 -s | sed 's/^/  /'
    echo ""

    subheader "Key Kubelet Settings"

    # Root dir
    local root_dir
    root_dir=$(echo "$kubelet_cmd" | grep -oP '(?<=--root-dir=)\S+' || echo "/var/lib/kubelet")
    ok "Kubelet root-dir: ${BOLD}$root_dir${NC}"
    if [ -d "$root_dir" ]; then
        dev=$(df "$root_dir" 2>/dev/null | tail -1 | awk '{print $1}')
        ok "  Backed by device: $dev"
        read -r size used avail pct < <(df --output=size,used,avail,pcent "$root_dir" 2>/dev/null | tail -1 | tr -s ' ')
        ok "  Size: $(bytes_to_human $((size*1024))), Used: $(bytes_to_human $((used*1024))), Avail: $(bytes_to_human $((avail*1024))), Use: $pct"
    fi
    echo ""

    # Image GC
    local image_gc_high image_gc_low
    image_gc_high=$(echo "$kubelet_cmd" | grep -oP '(?<=--image-gc-high-threshold=)\S+' || echo "85 (default)")
    image_gc_low=$(echo "$kubelet_cmd" | grep -oP '(?<=--image-gc-low-threshold=)\S+' || echo "80 (default)")
    info "Image GC high threshold: $image_gc_high%"
    info "Image GC low threshold: $image_gc_low%"

    # Eviction thresholds
    local eviction_hard
    eviction_hard=$(echo "$kubelet_cmd" | grep -oP '(?<=--eviction-hard=)\S+' || echo "nodefs.available<10%,imagefs.available<15% (defaults)")
    info "Eviction hard: $eviction_hard"
    echo ""

    # KubeletConfiguration file
    local config_file
    config_file=$(echo "$kubelet_cmd" | grep -oP '(?<=--config=)\S+' || echo "")
    if [ -n "$config_file" ] && [ -f "$config_file" ]; then
        subheader "KubeletConfiguration ($config_file)"
        echo "  Key storage-related fields:"
        grep -E "(rootDir|cgroupRoot|imageGC|eviction|allocatable|ephemeral|nodefs|imagefs|containerRuntimeEndpoint)" "$config_file" 2>/dev/null | sed 's/^/  /' || info "No storage fields found"
        echo ""

        # Specifically look for enforceNodeAllocatable and allocatable reserves
        echo "  Allocatable enforcement:"
        grep -A 5 "enforceNodeAllocatable\|systemReserved\|kubeReserved\|evictionHard" "$config_file" 2>/dev/null | sed 's/^/  /' || info "Not explicitly configured"
    else
        info "No kubelet config file found (using command-line args only)"
    fi
    echo ""

    subheader "Kubelet Root Directory Contents"
    if [ -d "$root_dir" ]; then
        du -sh "$root_dir"/* 2>/dev/null | sort -rh | head -20 | sed 's/^/  /'
    fi
}

# ============================================================================
# SECTION 4: CONTAINERD CONFIGURATION
# ============================================================================
audit_containerd() {
    header "4. CONTAINERD CONFIGURATION"

    subheader "Containerd Process"
    ps aux | grep '[c]ontainerd' | head -3 | sed 's/^/  /' || fail "containerd not found"
    echo ""

    subheader "Containerd Config"
    local config_file="/etc/containerd/config.toml"
    if [ ! -f "$config_file" ]; then
        config_file=$(containerd config dump 2>/dev/null | grep -m1 "config_path" | cut -d'"' -f2 || echo "")
    fi

    if [ -f "$config_file" ]; then
        echo "  Config file: $config_file"
        echo ""
        echo "  Key storage settings:"
        grep -E "(root|state|snapshotter|content_dir)" "$config_file" 2>/dev/null | head -10 | sed 's/^/  /'
    else
        info "Config file not found, dumping runtime config:"
        containerd config dump 2>/dev/null | grep -E "(root|state|snapshotter)" | head -10 | sed 's/^/  /'
    fi
    echo ""

    # Containerd root directory
    local ctr_root
    ctr_root=$(containerd config dump 2>/dev/null | grep "^root" | head -1 | awk '{print $NF}' | tr -d '"' || echo "/var/lib/containerd")
    subheader "Containerd Root: $ctr_root"
    if [ -d "$ctr_root" ]; then
        dev=$(df "$ctr_root" 2>/dev/null | tail -1 | awk '{print $1}')
        ok "Backed by device: $dev"
        read -r size used avail pct < <(df --output=size,used,avail,pcent "$ctr_root" 2>/dev/null | tail -1 | tr -s ' ')
        ok "Size: $(bytes_to_human $((size*1024))), Used: $(bytes_to_human $((used*1024))), Avail: $(bytes_to_human $((avail*1024))), Use: $pct"
        echo ""
        echo "  Directory breakdown:"
        du -sh "$ctr_root"/* 2>/dev/null | sort -rh | head -10 | sed 's/^/  /'
    fi
}

# ============================================================================
# SECTION 5: KUBERNETES NODE ALLOCATABLE (EPHEMERAL STORAGE)
# ============================================================================
audit_allocatable() {
    header "5. KUBERNETES EPHEMERAL STORAGE ALLOCATABLE"

    subheader "Node Status (from kubelet API)"
    # Try getting allocatable from kubelet's local API
    local node_name
    node_name=$(hostname)

    if command -v kubectl &>/dev/null; then
        echo "  Node: $node_name"
        echo ""
        echo "  Capacity vs Allocatable:"
        kubectl get node "$node_name" -o json 2>/dev/null | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    cap = data['status']['capacity']
    alloc = data['status']['allocatable']
    print(f'  {\"Resource\":<25s} {\"Capacity\":<20s} {\"Allocatable\":<20s} {\"Reserved\":<20s}')
    print(f'  {\"-\"*85}')
    for r in ['cpu', 'memory', 'ephemeral-storage', 'nvidia.com/gpu', 'pods']:
        c = cap.get(r, 'N/A')
        a = alloc.get(r, 'N/A')
        # Calculate reserved
        reserved = 'N/A'
        if c != 'N/A' and a != 'N/A':
            try:
                def parse_k8s_quantity(s):
                    s = str(s)
                    if s.endswith('Ki'): return int(s[:-2]) * 1024
                    if s.endswith('Mi'): return int(s[:-2]) * 1048576
                    if s.endswith('Gi'): return int(s[:-2]) * 1073741824
                    if s.endswith('Ti'): return int(s[:-2]) * 1099511627776
                    if s.endswith('m'): return float(s[:-1]) / 1000
                    return int(s)
                cv = parse_k8s_quantity(c)
                av = parse_k8s_quantity(a)
                rv = cv - av
                if rv > 1073741824:
                    reserved = f'{rv/1073741824:.2f} Gi ({rv/cv*100:.1f}%)'
                elif rv > 0:
                    reserved = f'{rv}'
                else:
                    reserved = '0 (none reserved)'
            except:
                reserved = 'parse error'
        print(f'  {r:<25s} {c:<20s} {a:<20s} {reserved:<20s}')
except Exception as e:
    print(f'  Error: {e}')
" 2>/dev/null || warn "kubectl not available or node not accessible"
    else
        warn "kubectl not available on this node"
        info "Trying kubelet API directly..."
        curl -sSk "https://localhost:10250/configz" 2>/dev/null | python3 -c "
import json, sys
data = json.load(sys.stdin)
kc = data.get('kubeletconfig', {})
print(f'  systemReserved: {kc.get(\"systemReserved\", \"not set\")}')
print(f'  kubeReserved: {kc.get(\"kubeReserved\", \"not set\")}')
print(f'  evictionHard: {kc.get(\"evictionHard\", \"not set\")}')
" 2>/dev/null || info "Could not reach kubelet API"
    fi
    echo ""

    subheader "Ephemeral Storage Calculation"
    # The filesystem that backs ephemeral storage
    local kubelet_root
    kubelet_root=$(ps aux | grep '[k]ubelet' | grep -oP '(?<=--root-dir=)\S+' || echo "/var/lib/kubelet")
    local backing_dev
    backing_dev=$(df "$kubelet_root" 2>/dev/null | tail -1 | awk '{print $1}')
    local backing_mp
    backing_mp=$(df "$kubelet_root" 2>/dev/null | tail -1 | awk '{print $NF}')

    read -r total_kb used_kb avail_kb < <(df --output=size,used,avail "$kubelet_root" 2>/dev/null | tail -1 | tr -s ' ')
    local total_b=$((total_kb * 1024))
    local used_b=$((used_kb * 1024))
    local avail_b=$((avail_kb * 1024))

    echo "  Ephemeral storage filesystem:"
    echo "    Kubelet root-dir:  $kubelet_root"
    echo "    Backing device:    $backing_dev"
    echo "    Backing mount:     $backing_mp"
    echo "    Total capacity:    $(bytes_to_human $total_b) ($total_b bytes)"
    echo "    Currently used:    $(bytes_to_human $used_b) ($used_b bytes)"
    echo "    Currently free:    $(bytes_to_human $avail_b) ($avail_b bytes)"
    echo ""

    # Check if containerd uses same filesystem
    local ctr_root
    ctr_root=$(containerd config dump 2>/dev/null | grep "^root" | head -1 | awk '{print $NF}' | tr -d '"' || echo "/var/lib/containerd")
    local ctr_dev
    ctr_dev=$(df "$ctr_root" 2>/dev/null | tail -1 | awk '{print $1}')

    if [ "$backing_dev" = "$ctr_dev" ]; then
        ok "Kubelet ($kubelet_root) and Containerd ($ctr_root) are on the SAME drive: $backing_dev"
        info "Ephemeral storage and container images SHARE the same filesystem"
    else
        warn "Kubelet ($kubelet_root) is on $backing_dev but Containerd ($ctr_root) is on $ctr_dev"
        info "They are on DIFFERENT drives — ephemeral storage and images are separated"
    fi
}

# ============================================================================
# SECTION 6: PER-POD EPHEMERAL STORAGE USAGE
# ============================================================================
audit_pod_ephemeral() {
    header "6. PER-POD EPHEMERAL STORAGE USAGE"

    subheader "Pod Ephemeral Usage via crictl"
    if ! command -v crictl &>/dev/null; then
        warn "crictl not available, trying alternative methods"
    fi

    subheader "Pod Volumes in Kubelet Directory"
    local kubelet_root
    kubelet_root=$(ps aux | grep '[k]ubelet' | grep -oP '(?<=--root-dir=)\S+' || echo "/var/lib/kubelet")

    echo "  Ephemeral volumes per pod (writable layers + emptyDir):"
    echo ""
    if [ -d "$kubelet_root/pods" ]; then
        for pod_dir in "$kubelet_root/pods"/*/; do
            if [ -d "$pod_dir" ]; then
                pod_uid=$(basename "$pod_dir")
                total_bytes=$(du -sb "$pod_dir" 2>/dev/null | awk '{print $1}')
                volume_bytes=0
                if [ -d "${pod_dir}volumes" ]; then
                    volume_bytes=$(du -sb "${pod_dir}volumes" 2>/dev/null | awk '{print $1}' || echo 0)
                fi
                emptydir_bytes=0
                if [ -d "${pod_dir}volumes/kubernetes.io~empty-dir" ]; then
                    emptydir_bytes=$(du -sb "${pod_dir}volumes/kubernetes.io~empty-dir" 2>/dev/null | awk '{print $1}' || echo 0)
                fi
                echo "  Pod UID: $pod_uid"
                echo "    Total: $(bytes_to_human ${total_bytes:-0})"
                echo "    Volumes: $(bytes_to_human ${volume_bytes:-0})"
                echo "    EmptyDir: $(bytes_to_human ${emptydir_bytes:-0})"
                echo ""
            fi
        done | head -100
    else
        warn "No pods directory at $kubelet_root/pods"
    fi

    subheader "Container Writable Layers (containerd snapshots)"
    local ctr_root
    ctr_root=$(containerd config dump 2>/dev/null | grep "^root" | head -1 | awk '{print $NF}' | tr -d '"' || echo "/var/lib/containerd")
    if [ -d "$ctr_root/io.containerd.snapshotter.v1.overlayfs/snapshots" ]; then
        echo "  Snapshot directory: $ctr_root/io.containerd.snapshotter.v1.overlayfs/snapshots"
        echo "  Total snapshots size: $(du -sh "$ctr_root/io.containerd.snapshotter.v1.overlayfs/snapshots" 2>/dev/null | awk '{print $1}')"
        echo ""
        echo "  Top 10 largest snapshots:"
        du -sh "$ctr_root/io.containerd.snapshotter.v1.overlayfs/snapshots"/* 2>/dev/null | sort -rh | head -10 | sed 's/^/    /'
    fi
}

# ============================================================================
# SECTION 7: /var BREAKDOWN
# ============================================================================
audit_var() {
    header "7. /var DIRECTORY BREAKDOWN"

    subheader "/var Top-Level Usage"
    du -sh /var/*/ 2>/dev/null | sort -rh | sed 's/^/  /'
    echo ""

    subheader "/var/lib Breakdown"
    du -sh /var/lib/*/ 2>/dev/null | sort -rh | head -15 | sed 's/^/  /'
    echo ""

    subheader "/var/log Breakdown"
    du -sh /var/log/*/ 2>/dev/null | sort -rh | head -10 | sed 's/^/  /'
    echo ""
    echo "  Total /var/log size: $(du -sh /var/log 2>/dev/null | awk '{print $1}')"

    subheader "Container Logs (/var/log/containers)"
    if [ -d /var/log/containers ]; then
        echo "  Total: $(du -sh /var/log/containers 2>/dev/null | awk '{print $1}')"
        echo "  Top 10 largest log files:"
        ls -lhS /var/log/containers/ 2>/dev/null | head -11 | sed 's/^/    /'
    fi

    subheader "Pod Logs (/var/log/pods)"
    if [ -d /var/log/pods ]; then
        echo "  Total: $(du -sh /var/log/pods 2>/dev/null | awk '{print $1}')"
        echo "  Top 10 largest pod log directories:"
        du -sh /var/log/pods/*/ 2>/dev/null | sort -rh | head -10 | sed 's/^/    /'
    fi
}

# ============================================================================
# SECTION 8: CERTIFICATION SUMMARY
# ============================================================================
audit_certification() {
    header "8. CERTIFICATION SUMMARY"

    local kubelet_root
    kubelet_root=$(ps aux | grep '[k]ubelet' | grep -oP '(?<=--root-dir=)\S+' || echo "/var/lib/kubelet")
    local ctr_root
    ctr_root=$(containerd config dump 2>/dev/null | grep "^root" | head -1 | awk '{print $NF}' | tr -d '"' || echo "/var/lib/containerd")

    local kub_dev ctr_dev
    kub_dev=$(df "$kubelet_root" 2>/dev/null | tail -1 | awk '{print $1}')
    ctr_dev=$(df "$ctr_root" 2>/dev/null | tail -1 | awk '{print $1}')

    echo ""
    echo -e "  ${BOLD}Drive → Directory Mapping:${NC}"
    echo -e "  $SUB_SEP"

    # List all unique block devices used by K8s
    declare -A dev_dirs
    for dir in / /var /var/lib/kubelet /var/lib/containerd /var/log /tmp; do
        if [ -d "$dir" ]; then
            dev=$(df "$dir" 2>/dev/null | tail -1 | awk '{print $1}')
            size=$(df -h "$dir" 2>/dev/null | tail -1 | awk '{print $2}')
            dev_dirs["$dev"]="${dev_dirs[$dev]:-} $dir"
            echo "    $dir → $dev ($size)"
        fi
    done
    echo ""

    echo -e "  ${BOLD}Certification Checks:${NC}"
    echo -e "  $SUB_SEP"

    # Check 1: Are kubelet and containerd on same drive?
    if [ "$kub_dev" = "$ctr_dev" ]; then
        ok "CHECK 1: Kubelet and Containerd on SAME drive ($kub_dev)"
    else
        warn "CHECK 1: Kubelet ($kub_dev) and Containerd ($ctr_dev) on DIFFERENT drives"
    fi

    # Check 2: Is /var/log separate?
    local log_dev
    log_dev=$(df /var/log 2>/dev/null | tail -1 | awk '{print $1}')
    if [ "$log_dev" != "$kub_dev" ]; then
        ok "CHECK 2: /var/log is on SEPARATE drive ($log_dev) — logs don't eat ephemeral space"
    else
        warn "CHECK 2: /var/log is on SAME drive as kubelet ($kub_dev) — logs consume ephemeral space"
    fi

    # Check 3: How much of the drive is available?
    read -r total_kb used_kb avail_kb < <(df --output=size,used,avail "$kubelet_root" 2>/dev/null | tail -1 | tr -s ' ')
    local total_b=$((total_kb * 1024))
    local total_tb=$(echo "scale=2; $total_b / 1099511627776" | bc)
    echo ""
    ok "CHECK 3: Drive backing ephemeral storage: $kub_dev"
    ok "  Total capacity: $total_tb TB ($(bytes_to_human $total_b))"
    ok "  Currently used: $(bytes_to_human $((used_kb * 1024)))"
    ok "  Currently free: $(bytes_to_human $((avail_kb * 1024)))"

    # Check 4: Is the full drive offered as ephemeral?
    if command -v kubectl &>/dev/null; then
        local node_name
        node_name=$(hostname)
        local allocatable_es
        allocatable_es=$(kubectl get node "$node_name" -o jsonpath='{.status.allocatable.ephemeral-storage}' 2>/dev/null || echo "unknown")
        echo ""
        ok "CHECK 4: K8s allocatable ephemeral-storage: $allocatable_es"

        if [ "$allocatable_es" != "unknown" ]; then
            local alloc_bytes
            alloc_bytes=$(echo "$allocatable_es" | python3 -c "
import sys
s = sys.stdin.read().strip()
if s.endswith('Ki'): print(int(s[:-2]) * 1024)
elif s.endswith('Mi'): print(int(s[:-2]) * 1048576)
elif s.endswith('Gi'): print(int(s[:-2]) * 1073741824)
elif s.endswith('Ti'): print(int(s[:-2]) * 1099511627776)
else: print(int(s))
" 2>/dev/null || echo "0")
            local pct_offered
            pct_offered=$(echo "scale=1; $alloc_bytes * 100 / $total_b" | bc)
            ok "  Allocatable: $(bytes_to_human $alloc_bytes) of $(bytes_to_human $total_b) ($pct_offered%)"

            local reserved_b=$((total_b - alloc_bytes))
            info "  Reserved (system + K8s overhead): $(bytes_to_human $reserved_b)"
        fi
    fi

    # Check 5: What is consuming non-K8s space on the ephemeral drive?
    echo ""
    subheader "Non-K8s Consumers on Ephemeral Drive"
    info "Everything on $kub_dev that is NOT kubelet/containerd pods:"
    local backing_mp
    backing_mp=$(df "$kubelet_root" 2>/dev/null | tail -1 | awk '{print $NF}')
    echo ""
    echo "  Directory breakdown on $backing_mp:"
    if [ "$backing_mp" = "/" ]; then
        du -shx /* 2>/dev/null | sort -rh | head -15 | sed 's/^/    /'
    else
        du -sh "$backing_mp"/* 2>/dev/null | sort -rh | head -15 | sed 's/^/    /'
    fi

    echo ""
    echo ""
    echo -e "  ${GREEN}${BOLD}AUDIT COMPLETE${NC}"
    echo -e "  ${BLUE}$(date -u '+%Y-%m-%dT%H:%M:%SZ')${NC} on $(hostname)"
    echo ""
}

# ============================================================================
# MAIN
# ============================================================================
main() {
    echo -e "${BOLD}${CYAN}"
    echo "  ╔══════════════════════════════════════════════════════════════╗"
    echo "  ║     K8s Node Storage & Ephemeral Storage Audit             ║"
    echo "  ║     $(date -u '+%Y-%m-%dT%H:%M:%SZ')                                   ║"
    echo "  ║     Node: $(hostname | head -c 40)$(printf '%*s' $((40 - ${#HOSTNAME})) '')      ║"
    echo "  ╚══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"

    # Check root
    if [ "$(id -u)" -ne 0 ]; then
        fail "This script must be run as root (sudo)"
        exit 1
    fi

    local section="${1:-all}"

    case "$section" in
        drives|1)     audit_drives ;;
        mounts|2)     audit_mounts ;;
        kubelet|3)    audit_kubelet ;;
        containerd|4) audit_containerd ;;
        alloc*|5)     audit_allocatable ;;
        pods|6)       audit_pod_ephemeral ;;
        var|7)        audit_var ;;
        cert*|8)      audit_certification ;;
        all|*)
            audit_drives
            audit_mounts
            audit_kubelet
            audit_containerd
            audit_allocatable
            audit_pod_ephemeral
            audit_var
            audit_certification
            ;;
    esac
}

main "${1:-all}" 2>&1
