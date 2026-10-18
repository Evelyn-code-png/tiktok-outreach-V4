# Gmail Browser Sending

This workflow uses the connected browser's signed-in Gmail session. It does not read cookies, private APIs, or browser databases, and it does not require an SMTP password.

1. Read the full campaign file from `~/.config/tiktok-outreach/campaigns/<full-id>.json` and run `browser-plan --campaign <absolute-path>`.
2. Confirm that the user explicitly authorized this campaign and recipient count. A request to build the plugin or create a draft does not authorize sending.
3. In the current Gmail tab, verify the account and From address match the campaign sender.
4. For each message, use the freshly observed Compose controls to fill To, Subject, and Body. Do not put message text in a URL.
5. Immediately before clicking Send, run `browser-claim --campaign <absolute-path> --email <address>`. Do not click Send if it fails.
6. Click Send and wait for Gmail's visible success confirmation. Then run `browser-result --campaign <absolute-path> --email <address> --result sent_browser`.
7. If the result is unclear, record `unknown` and stop the batch. If Send was never clicked, record `failed_before_submission`.
8. Stop on Gmail limits, authentication prompts, or errors and preserve progress. Existing records are skipped automatically.

Report sent, skipped, and uncertain counts. `sent_browser` means Gmail visibly reported success; it does not prove delivery or an open.
