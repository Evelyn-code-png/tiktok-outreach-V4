---
name: tiktok-outreach-v3
description: Find TikTok creators and business emails with EasyKOL, edit each outreach email separately, prepare evidence-based personalized openings, and send through a signed-in Gmail browser session or SMTP. Also opens the V3 local creator workspace.
---

Use `../../scripts/outreach.py` with Python 3.10+; no extra packages are required. Resolve absolute paths before running commands and never display local secrets.

1. Run `doctor` first. V3 credentials live in `~/.config/tiktok-outreach-v3/config.json`, separate from V1. If the API key is missing, the user may authorize browser navigation to EasyKOL's API Key page; never ask the user to paste a secret into chat.
2. Search with a clear niche, country, quantity, and budget. Search consumes EasyKOL credits; do not silently broaden or repeat a billable request.
3. Use `search --query 'skincare creators' --regions US --languages en --limit 20 --budget 20 --has-email --out /absolute/run` for a single query. Use `--queries-file` for multiple lines.
4. For known profiles, use `emails-start --csv /absolute/creators.csv --budget 20`, save the task ID, then use `emails-collect --task-id ID --csv ... --out ...`. Poll at least four seconds apart and never recreate an unfinished billable task.
5. Standard CSV columns are `name,username,profile_url,email,followers,region,language,source`. Provider contact data is not a deliverability guarantee.
6. Draft with `draft --csv contacts.csv --subject 'Collaboration with $name' --body body.txt --out campaign.json`. Show the recipients, content, and count before sending.
7. For Gmail browser sending, read [browser-mail.md](browser-mail.md) and use `browser-plan`, `browser-claim`, and `browser-result` for every message. SMTP is preview-only unless the user explicitly authorizes a specific campaign and `--execute` is supplied.
8. Use `history` to review outcomes. Unknown or sending states may already have been submitted; verify Gmail Sent before retrying.
9. Use `suppress --email person@example.com` to prevent future sends to an address.

## Local dashboard

Start `scripts/dashboard.py --no-open`, keep it running, and open the local URL stored in `~/.config/tiktok-outreach-v3/dashboard-session.json`. The dashboard supports creator search, CSV/XLSX import, email enrichment, recipient selection, saved templates, per-recipient editing, grounded personalization options, campaign previews, custom sender settings, SMTP sending, Gmail instructions, delivery history, and tracking metrics.

Data is stored under `runs/`, `campaigns/`, and `jobs/` in the local configuration directory. Interrupted jobs retain completed results and provider task IDs.
