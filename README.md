# Outreach V4

A local workspace for finding TikTok creators with EasyKOL, reviewing contacts, preparing editable outreach emails, and tracking Gmail replies.

## Simplified connections

For teammates pulling this repository, see [团队安装与部署步骤](docs/TEAM_QUICKSTART_CN.md). A private member connection file is required for the shared AI service; Git pull does not copy the administrator's credentials.

Google OAuth sending/reply access and an optional team AI gateway are now supported. Team administrators must configure these services before members can connect. See [connection setup](docs/CONNECTION_SETUP_CN.md). SMTP and personal AI keys remain available as fallbacks.

## Download and open

Select **Code → Download ZIP** on this private repository page, then extract the complete folder. Each teammate must first have access to the repository.

**Requirement:** Python 3.10 or newer. No additional Python packages or Codex installation are required to open and use the workspace. If Python is not installed, install it once from [python.org](https://www.python.org/downloads/). On Windows, select **Add python.exe to PATH** during installation.

| Computer | Open after extracting |
| --- | --- |
| macOS | Double-click **Open Dashboard.command** |
| Windows | Double-click **Open Dashboard.bat** |
| Linux | Run `python3 scripts/dashboard.py --reuse` from the project folder |

Keep the launcher window open while using the workspace. It opens a private local browser page automatically. Closing that window stops the local service. Do not open `assets/index.html` directly.

If macOS reports that the `.command` file is not executable, open Terminal in the extracted folder and run:

```bash
bash "Open Dashboard.command"
```

## First use

1. **Account Setup:** add your own accounts for any live services you want to use. Account setup is not needed to browse the interface, import contacts, or prepare manual drafts.
2. **Find Creators:** enter your criteria, result count, and credit budget. **Start search** submits an EasyKOL search and opens **Contacts**, with live task status.
3. **Contacts:** review the card wall or table, open creator details, import CSV / Excel files, or expand **Add contact by email**. Select recipients and click **Outreach**.
4. **Outreach email:** edit the subject and message, then click **Generate and preview draft**. Review each recipient's email before sending. Preparing a draft does not send it.
5. **Delivery log:** review sending results and enable Gmail reply tracking if needed.

The sidebar and **Previous / Next** switch between separate pages and preserve your current inputs and recipient selection. Navigation itself does not run a search or send email.

## Which accounts are needed?

| Feature | Setup |
| --- | --- |
| View the interface, import/add contacts, edit manual email drafts | None |
| Real creator search | Your EasyKOL account email, API key, and sufficient credits |
| AI creator-fit analysis and personalized opening options | Team AI service URL and access code, or your personal AI API key and model; manual editing remains available |
| Send directly using Gmail SMTP | Connect Google, or use your sending Gmail and a Gmail app password for SMTP |
| Automatically sync matching Gmail replies | Google connection with reply access (or SMTP setup), followed by explicit permission in **Delivery log** |
| Gmail browser sending instructions | An agent capable of following the copied instruction in your signed-in Gmail; copying does not send email |

Your own connected services bill their usage to your own accounts. This download contains no shared EasyKOL credits, AI key, Gmail password, or sender mailbox.

## Reply and open tracking

Gmail reply tracking matches incoming replies against messages sent from this workspace. It reads relevant messages without deleting mail or marking it read. The app checks periodically while its page is open and visible; **Sync now** is also available after permission. Received replies appear as a creator list with expandable details.

An SMTP success means Gmail accepted the message for sending; it does not guarantee inbox delivery. Open/click tracking is separate and requires a reachable public HTTPS tracking endpoint. It is not enabled merely by downloading or running this local demo, and image blocking or privacy features can affect open tracking.

## Local data and team sharing

This is a **local application**, not a shared cloud workspace. Each teammate has separate contacts, drafts, settings, delivery records, and mailbox permissions. The dashboard listens only on `127.0.0.1`.

Data is stored outside the downloaded source in `~/.config/tiktok-outreach-v3` on macOS/Linux, or the corresponding user-profile location on Windows. The existing `v3` storage name is kept for compatibility with earlier installations. Updating the source does not delete existing local data.

The repository is private. The owner must grant teammates repository access before they can open it or download the project. Do not upload personal settings, contact exports, mail contents, or API keys to this repository.

## Development checks

```bash
python3 -m unittest discover -s tests -q
node --test tests/test_send_feedback.cjs
```

Node is optional and is used only for the JavaScript tests. It is not needed to run the application.

See [QUICKSTART.md](QUICKSTART.md) for a short walkthrough and [WORKFLOW_ADDITIONS.md](WORKFLOW_ADDITIONS.md) for implementation and restoration notes. Instruction has four switchable empty sections: User journey, How it works, Risks & Where It Breaks, and Status & Next Steps.
