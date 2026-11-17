# Validation Record

Validated on September 26, 2026 (America/Los_Angeles).

## Live integrations

- EasyKOL API quota and creator search were verified with the configured account.
- Email enrichment created a provider task, resumed it, downloaded the XLSX export, and matched addresses by profile URL.
- The signed-in Gmail account and compose flow were verified. No real test email was sent.
- SMTP behavior was tested with a mock server only.

## Automated checks

The test suite uses temporary directories, mock API responses, and mock SMTP. It does not read the real configuration or send email. Coverage includes search validation, quota limits, CSV/XLSX import, personalization, duplicate and suppression handling, durable jobs, cancellation, recovery after interruption, browser/SMTP deduplication, templates, and tracking metrics.

Run:

```bash
python3 -m unittest discover -s tests -v
```

## Safety and packaging

The plugin manifest and skill format validate successfully. The real API key is outside the plugin source and share package. Local credential files are permission-restricted and are never included in the plugin archive.

Browser sending still requires a valid Gmail login session. SMTP acceptance does not guarantee inbox delivery or that a message was read.
