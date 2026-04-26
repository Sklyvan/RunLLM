# RUNBOOK

## Rotate the Fernet key

1. Generate a new key:

   ```bash
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```

2. Wrap the old + new keys in a `MultiFernet` (one-off script). Decrypt every
   user's `garmin_credentials_encrypted` with the old key, re-encrypt with the
   new key, write back.
3. Update `FERNET_KEY` on Render and redeploy.

## Reset a user's Garmin credentials

```sql
update "user"
set garmin_credentials_encrypted = null,
    garmin_email = null,
    garmin_last_sync_at = null
where id = '<user-id>';
```

The user can re-link from the Settings page.

## Manually trigger a sync

While impersonating the user (use their JWT):

```bash
curl -X POST https://<render-host>/api/v1/garmin/sync \
     -H "Authorization: Bearer $JWT"
```

## Read logs

- Render: `Service → Logs` tab.
- Vercel: `Project → Deployments → <deployment> → Functions`.
- Local: stdout (structured one-line logs with `request_id`).

## Common issues

| Symptom | Cause | Fix |
| --- | --- | --- |
| `401` from `/api/v1/...` | Expired or wrong JWT | Sign out + sign in. |
| `409 mfa_required` on sync | Garmin invalidated cached tokens | Hit `/api/v1/garmin/credentials` then `/api/v1/garmin/mfa`. |
| `502` from `/api/v1/chat` | Anthropic API issue | Check Anthropic status page; retry. |

