# Forgejo → Mattermost Webhook Setup

This guide wires The Workshop (Forgejo) events into Mattermost channels.

## 1. Create Mattermost Incoming Webhook

1. Log in to Mattermost at `https://chat.trancendos.com` (via Traefik) or `http://<host>:8065` for initial setup only
2. **Main Menu → Integrations → Incoming Webhooks → Add Incoming Webhook**
3. Title: `Forgejo / The Workshop`
4. Channel: `#ci-notifications` (or create it first)
5. Click **Save** → copy the webhook URL
6. Add to `.env.production` as `MATTERMOST_WEBHOOK_URL=<url>`
   (or store in The Void vault: `vault kv put tranc3/secret/mattermost webhook_url=<url>`)

## 2. Add Webhook in Forgejo

1. Log in to Forgejo at `https://trancendos.com/the-workshop`
2. Navigate to **Organization → Settings → Webhooks → Add Webhook → Mattermost**
   (or per-repo: **Settings → Webhooks**)
3. Target URL: paste the Mattermost incoming webhook URL
4. Trigger events: ✅ Push, ✅ Pull Request, ✅ Issues, ✅ Releases
5. Click **Add Webhook** → **Test Delivery**

## 3. Woodpecker CI Notifications

Woodpecker notifies Mattermost via the `plugins/webhook` step in `.woodpecker.yml`.

1. In Woodpecker UI (`https://ci.trancendos.com` or `http://<host>:8100`), navigate to your repo settings
2. **Secrets → Add Secret**
   - Name: `MATTERMOST_WEBHOOK_URL`
   - Value: the incoming webhook URL from Step 1
3. The `notify-mattermost` step fires on every `main` branch push (success or failure)

## 4. Channel Topology

| Channel | Purpose |
|---|---|
| `#ci-notifications` | Forgejo push events + Woodpecker CI results |
| `#deployments` | Production deploy events from Forgejo Actions |
| `#security` | Security scan failures (bandit, pip-audit) |
| `#renovate` | Renovate bot dependency update PRs |
| `#general` | Team announcements |

## 5. Verify

After setup, push a commit to any branch — within seconds you should see a message
in `#ci-notifications` showing the push author, branch, and commit message.
