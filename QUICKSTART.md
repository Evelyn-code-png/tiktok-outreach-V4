# Outreach V4 — Quick Start

1. Download the ZIP from **Releases**, or select **Code → Download ZIP**. Extract the complete folder.
2. Install **Python 3.10+** if needed. No additional packages or Codex installation are required to open the app.
3. On Mac, open **Open Dashboard.command**. On Windows, open **Open Dashboard.bat**. Keep the launcher window open.
4. The launcher opens the local workspace in your browser. Use that opened page, not `assets/index.html`.

If the Mac launcher is not executable, open Terminal in the extracted folder and run `bash "Open Dashboard.command"`.

## Use without paid APIs

Go to **Contacts**. Import a CSV/Excel file with `name` and `email` columns, or expand **Add contact by email** and enter an address. Select your recipients, then click **Outreach**. Write the subject and message in **Outreach email**, and generate editable draft previews. Nothing is sent by importing contacts or creating previews.

## Search for creators

Add your own EasyKOL account email and API key in **Account Setup**. In **Find Creators**, complete the search criteria and budget, then click **Start search**. The app opens **Contacts** and displays search progress and the resulting saved list. Search uses your own EasyKOL credits.

## Send emails

For direct sending, configure your own Gmail address and Gmail app password in **Account Setup**. Review each draft, open **Send directly through Gmail (SMTP · optional)**, check the confirmation box and click **Send this batch via SMTP**. A result panel shows accepted, failed or uncertain outcomes. Do not repeat a send while its result is uncertain; check Gmail Sent and **Delivery log** first.

## Track replies

In **Delivery log**, click **Enable reply tracking**, review the mailbox permission and allow it if you want matching replies synced. Replies appear in a creator list; open one to read its received replies. This does not enable open/click tracking. Keep the page open for automatic reply checks, or use **Sync now**.

## Team use

The repository and releases are private, so each teammate needs repository access. Each download runs on that teammate's computer with their own credentials and separate local data. It does not use the project owner's API keys or mailbox.
