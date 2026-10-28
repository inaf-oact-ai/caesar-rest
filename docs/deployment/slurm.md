# Slurm deployment

> **Primary deployment backend:** Slurm is currently the actively developed mode. This page retains historical setup text for subsequent review.

> **Documentation migration (stage 1):** The section below is reproduced from the original `devel` README (lines 252–284). Its commands, versions, paths and examples have **not yet been modernized or revalidated**. See [archived original](../archive/ORIGINAL_README.md).

### **Run Slurm services (OPTIONAL)**   
If you want to manage jobs with Slurm, you must run the following services:    

```systemctl start munge.service```    
```systemctl start slurmd.service```   
```systemctl start slurmdbd.service```    
```systemctl start slurmctld.service```   
```systemctl start slurmrestd.service```    

Below, we report a sample configuration file (`/usr/lib/systemd/system/slurmrestd.service`) for the Slurm REST service:    

```
[Unit]
Description=Slurm REST daemon
After=network.target munge.service slurmctld.service
ConditionPathExists=/etc/slurm/slurm.conf

[Service]
Type=simple
User=caesar
Group=caesar
EnvironmentFile=-/etc/sysconfig/slurmrestd
# Default to local auth via socket
ExecStart=/usr/sbin/slurmrestd -f /etc/slurm/slurmrestd.conf -a rest_auth/jwt -s openapi/v0.0.36 -vvvv 0.0.0.0:6820
ExecReload=/bin/kill -HUP $MAINPID

[Install]
WantedBy=multi-user.target
```

**NB: Slurm is currently the suggested job management option for caesar-rest application.**


