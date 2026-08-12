# GreaterWMS Test 3 Deployment

This repository is the source for the GreaterWMS test deployment. The release
target is deliberately explicit so the unrelated `wms-quickstart` project
cannot be used by mistake.

| Setting | Required value |
| --- | --- |
| Git repository | `https://github.com/maxwu1978/GreaterWMS.git` |
| Git branch | `codex/sn-receiving` |
| Render service | `greaterwms-v2-test3-sn` |
| Render service ID | `srv-d9r3c41t0dsc73b94l2g` |
| Public URL | `https://greaterwms-v2-test3-sn.onrender.com` |
| Database | `greaterwms-v2-test3-db` |

Use the guarded release command from this repository:

```bash
bash scripts/deploy_greaterwms_test3.sh
```

The script refuses any repository or branch other than the values above. The
Render service is configured to deploy from `codex/sn-receiving`; after the
push, verify the service URL and Render deployment before reporting success.
