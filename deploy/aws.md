# AWS resources (personal account, us-west-2), created 2026-09-21

All tagged `Project=livs`. Use `aws --profile personal --region us-west-2`.

| Resource | Id |
| --- | --- |
| Instance (t3.small, Ubuntu 24.04) | i-08abcfdd9fcc099ba |
| Media volume (100 GB gp3, /dev/sdf, kept on termination) | vol-024e6756399fd0880 |
| Elastic IP | 52.25.167.188 (eipalloc-0ea74bf127f0a4716) |
| Security group | sg-0079ff5d47e33803a |
| Key pair | livs (`~/.ssh/livs.pem`) |
| DNS | livs.greggarber.net → 52.25.167.188 (zone Z00403141EP9QQ5HQP78K) |

ssh: `ssh -i ~/.ssh/livs.pem ubuntu@livs.greggarber.net`. Port 22 is open only to Greg's IP at creation time; update the security group when it changes.

Tear down: terminate the instance, delete the media volume, release the address, delete the security group, delete the DNS record.
