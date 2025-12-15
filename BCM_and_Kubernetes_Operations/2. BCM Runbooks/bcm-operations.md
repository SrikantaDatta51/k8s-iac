# Legacy BCM Operations Manual
## Principal Engineer's Guide to "Old World" Operations

> **Disclaimer**: These operations represent the **Imperative** and **Manual** management style of the legacy BCM (Business Configuration Manager) system. Our goal is to deprecate these in favor of Kubernetes GitOps.

---

## Part 1: Top 15 Day-0 Operations (Provisioning & Setup)

These tasks are performed *once* per server/rack to bring it into the BCM inventory.

1.  **Rack & Stack**:
    *   **Action**: Physically mount server in 42U rack. Connect Power (A/B feeds) and TOR (Top of Rack) Switch.
    *   **Validation**: Verify Green LEDs on PSU and NIC.
2.  **BIOS/RAID Configuration**:
    *   **Action**: Boot into BIOS (F2). Enable VT-x/AMD-V. Set Hardware RAID-10.
    *   **Command**: Manual interaction via IPMI/iDRAC console.
3.  **OS Installation (PXE)**:
    *   **Action**: Trigger PXE boot from BCM Provisioning VLAN.
    *   **Command**: `ipmitool chassis bootdev pxe && ipmitool chassis power cycle`
4.  **Static IP Assignment**:
    *   **Action**: Edit interface files manually to assign Host IP.
    *   **File**: `/etc/netplan/01-netcfg.yaml` or `/etc/sysconfig/network-scripts/ifcfg-eth0`.
5.  **BCM Agent Installation**:
    *   **Action**: Download and install the proprietary BCM binary.
    *   **Command**: `curl -O http://bcm-repo/agent.rpm && rpm -ivh agent.rpm`
6.  **NTP Synchronization**:
    *   **Action**: Hardcode corporate NTP servers.
    *   **Command**: `echo "server ntp.corp.net" >> /etc/ntp.conf && service ntpd restart`
7.  **User Management (Manual)**:
    *   **Action**: Create `admin` and `ops` users locally.
    *   **Command**: `useradd -m ops -G wheel`
8.  **SSH Key Distribution**:
    *   **Action**: Copy public keys from the Jumpbox to `authorized_keys`.
    *   **Command**: `ssh-copy-id -i ~/.ssh/ops_rsa ops@<new-ip>`
9.  **Firewall Options (Iptables)**:
    *   **Action**: Open port 8080 (App) and 22 (SSH).
    *   **Command**: `iptables -A INPUT -p tcp --dport 8080 -j ACCEPT; service iptables save`
10. **Mount NFS Storage**:
    *   **Action**: Edit fstab to mount shared legacy storage.
    *   **File**: `/etc/fstab` -> `nas.corp:/data /mnt/data nfs defaults 0 0`
11. **Install Java/Runtime Dependencies**:
    *   **Action**: Install specific JDK versions required by apps.
    *   **Command**: `yum install java-1.8.0-openjdk`
12. **Log Rotation Setup**:
    *   **Action**: Configure logrotate for application logs manually.
    *   **File**: `/etc/logrotate.d/legacy-app`
13. **Register with Monitoring (Nagios/Zabbix)**:
    *   **Action**: Add host entry to central Nagios config file.
    *   **Command**: `vi /etc/nagios/objects/hosts.cfg` (on monitoring server)
14. **Security Hardening (Manual)**:
    *   **Action**: Disable Root Login, set Password Policies.
    *   **File**: `/etc/ssh/sshd_config` -> `PermitRootLogin no`
15. **Smoke Test**:
    *   **Action**: Run a simple script to verify network/disk.
    *   **Command**: `./validate_host.sh`

---

## Part 2: Top 15 Day-2 Operations (Maintenance & Recovery)

These tasks are performed *repeatedly* to keep the lights on. They are often reactive.

1.  **Restarting Stuck Services (The "Bounce")**:
    *   **Scenario**: Application memory leak.
    *   **Command**: `systemctl restart legacy-app` or `kill -9 <pid>`
2.  **Clearing Disk Space (Log Purge)**:
    *   **Scenario**: `/var/log` is 100% full.
    *   **Command**: `find /var/log -name "*.log" -mtime +30 -delete`
3.  **Patching OS Packages**:
    *   **Scenario**: Security vulnerability (CVE).
    *   **Command**: `yum update -y openssl` (Risky: requires downtime window).
4.  **Managing Config Drift**:
    *   **Scenario**: "Dev works, Prod doesn't."
    *   **Action**: SSH into both, `diff /etc/app/config.properties`, manually edit Prod to match.
5.  **Password Rotation**:
    *   **Scenario**: 90-day policy.
    *   **Command**: `chage -d 0 ops` (Forces password reset).
6.  **Analyzing Kernel Panics**:
    *   **Scenario**: Server crashed.
    *   **Action**: Read `/var/log/messages` or `/var/crash` manually via `less`.
7.  **Adding Capacity (Vertical Scaling)**:
    *   **Scenario**: App needs more RAM.
    *   **Action**: Shut down VM, increase RAM in BCM UI, Start VM.
8.  **Updating SSL Certificates**:
    *   **Scenario**: Cert expired.
    *   **Action**: SCP new `.pem` file to `/etc/pki/tls/certs/`, restart Apache/Nginx.
9.  **Database Migration (Manual)**:
    *   **Scenario**: Schema change.
    *   **Command**: `mysql -u root -p < migration_v2.sql`
10. **Network Troubleshooting (Tcpdump)**:
    *   **Scenario**: "Connectivity issues".
    *   **Command**: `tcpdump -i eth0 port 80 -w capture.pcap`
11. **Managing Cron Jobs**:
    *   **Scenario**: Backup didn't run.
    *   **Command**: `crontab -e` (Edit the user's cron file).
12. **Restoring from Tape/Snapshot**:
    *   **Scenario**: Data corruption.
    *   **Action**: Mount backup media, copy files back manually.
13. **Agent Upgrade**:
    *   **Scenario**: BCM agent version 2.0 released.
    *   **Command**: `pssh -h hosts.txt -i "rpm -Uvh agent-v2.rpm"` (Parallel SSH).
14. **User Access Revocation**:
    *   **Scenario**: Employee left company.
    *   **Command**: `usermod -L <username>`
15. **Failover (Manual DR)**:
    *   **Scenario**: Primary DC outage.
    *   **Action**: Update DNS records manually to point to secondary IP.

---
**Summary**: The BCM world is defined by *SSH loops, text editors, and human vigilance*.
