# Pre-Submission Checklist

Project: **TikTok Outreach V2**

Verification date: **2026-09-28**

## Automated verification completed

- [x] All Python files compile successfully.
- [x] JavaScript syntax check passes for `assets/app.js`.
- [x] All 41 automated tests pass.
- [x] The latest local interface opens successfully in a browser.
- [x] The single-user and team-meeting illustrations are served locally.
- [x] The interface contains no visible Chinese text.

## Privacy and security checks completed

- [x] No `config.json`, database, log, dashboard-session, run, campaign, job, or template data is included in the project folder.
- [x] No live EasyKOL, OpenAI, Gmail, or GitHub key pattern was found in the project files.
- [x] `.gitignore` excludes local configuration, secrets, databases, logs, sessions, generated runs, campaigns, jobs, templates, and ZIP files.
- [x] No email was sent and no EasyKOL credit was used during this verification.
- [x] Sending safeguards, duplicate prevention, and suppression checks remain covered by automated tests.

## Manual checks required before the first push

- [ ] Confirm the exact GitHub repository URL and repository owner.
- [ ] Confirm whether the repository should be public or private.
- [ ] Set the Git commit author name and email.
- [ ] Review the final staged file list before committing.
- [ ] Confirm that the target repository does not contain work that would be overwritten.

## Recommended commands

```bash
python3 -m unittest discover -s tests -v
node --check assets/app.js
python3 -m py_compile scripts/*.py
git diff --check
git status --short --ignored
```

## Files that must never be uploaded

- API keys or access tokens
- Gmail app passwords
- Local configuration files
- Creator contact lists or private campaign data
- Delivery databases and logs
- Browser access tokens and dashboard session files

This checklist documents the verified project snapshot. It does not guarantee that third-party APIs, email addresses, email delivery, or AI-generated content will remain available or accurate.
