# Local workflow additions

The original six sidebar entries, including User Instruction, remain unchanged. Card wall and Table remain available in Contacts. Original colors, provider integrations, email generation and sending are unchanged.

## Where to find the additions

- Contacts: choose a brand brief for AI-generated matching reasons and filter-based matching and sort by fit or priority. Click a creator name or View details to open the right-hand detail panel.
- Creator details: inspect available list data and matching reasons, view automatically generated English fit explanations, set a manual priority and collaboration stage, and save private notes. The AI reads available EasyKOL search data or retrieves the profile automatically; no creator content notes are required.
- Outreach email: save, edit and reuse briefs in Brand library. Apply a brief to the existing personalized-opening fields and the active contact list.
- Contacts: expand Collaboration progress board. Change stages using each card's dropdown. State is saved separately for each contact list.
- Creator details / Replies: paste a reply from your inbox. English keyword rules suggest a category; select a category to override the suggestion before saving. This is manual recording, not live inbox synchronization.
- Delivery log: Replies & next steps collects manually recorded replies and saved to-dos across lists.
- Creator details / Follow-up: create and edit a template-based draft, choose a local reminder date, and save. Reminders are shown when the workspace is open; there are no background notifications or automatic sends.
- Follow-ups pause after a recorded human reply, a provider reply event, suppression, or closing/partnering a collaboration. An explicitly recorded Do not contact reply also adds the address to the existing suppression list.

All new information is saved in engagement.json in the existing local workspace data directory. Existing search data, settings and credentials are not migrated or replaced. No demonstration contacts are added to your real workspace.

## Validation

74 Python tests passed, including the original workflow tests, local HTTP authorization checks, persistence, matching with incomplete information, reply classification, follow-up pausing and suppression. JavaScript syntax checks passed. Browser checks covered both contact views, details, draft save, reply classification and pausing, brand reuse, board changes, and User Instruction navigation. No real provider calls or email sends were made.

## Restore the original

The original code is archived in outreach-v3-original-before-enhancements.zip. Close the dashboard launch terminal before restoring. Extract the archive, then replace the application folder with its tiktok-outreach-V3 folder. Open Open Dashboard.command (macOS) or Open Dashboard.bat (Windows) again.

Your workspace data is stored separately, so restoring the application folder does not erase contacts, credentials, or newly saved notes. The original version ignores engagement.json. A private snapshot of the pre-change local data is also retained in this chat's work directory, outside these shareable archives.

## AI creator-fit correction

Opening a creator automatically generates Why this creator fits from EasyKOL profile facts and the selected brand brief. If no brand is selected, a saved EasyKOL search goal can be used. Private notes and old user-entered content notes are not model evidence. The old content-notes form is removed.

The existing AI key and model in Account Setup are required. Missing AI configuration, provider failures and insufficient profile facts are explicitly reported. Cached valid results are reused for up to 24 hours; changed briefs or source list data invalidate the result. Regenerate AI fit explicitly requests a new model response. Results include grounded reasons, a suggested collaboration angle and missing information. The local cache is creator-fit.json.

The current real workspace has no AI key or model configured, so live AI output could not be verified. Provider request/response handling was tested with mocks; automatic UI generation was verified using clearly labeled sample data and a simulated model response. No sample AI output or fake key was copied to the real workspace.

## Brand form simplification

Brand library is now the single place to create and edit brand details. The duplicate Brand brief for personalized openings form was removed. Applying a saved brief keeps the existing email context and per-list matching behavior, with an applied-context summary in Brand library. Existing draft context is retained across reloads.

The contact upload control is labeled Upload contact list and explains how to import a hand-picked list using name/email columns. SMTP sending and the Do not contact list now include plain-English explanations. Sending logic and provider credentials are unchanged. JavaScript syntax checks passed; browser verification confirmed a single brand-name editor, preserved saved briefs and email context, and removal of the duplicate form. No email was sent or AI request made during this change.

## Manual contact entry

Contacts now has an Add contact by email form. Email is required; name is optional. The owner can save to My contacts or any existing list. Successful saves open the destination list and select the contact for outreach. Existing selections are retained when adding to the same list. Duplicate email addresses within a list are reused without overwriting their details. The form does not call EasyKOL or AI, or send email. Missing profile statistics appear as unknown.

80 Python tests passed, including manual-contact persistence, single-email validation, duplicates, preserving existing list rows/metadata, background-job conflicts, authorization and drafting. JavaScript syntax checks passed. An isolated browser workspace verified save, reload, duplicate handling and an unsent email preview. Test contacts were not added to the real workspace.

## Visible SMTP sending feedback

The SMTP send control now shows inline setup errors, live progress with the button disabled, and distinct success/failure/unconfirmed/skipped results. Recipient outcomes are listed beside the button. Gmail acceptance is labeled as successful submission, without claiming inbox delivery or reading. Failed and unknown outcomes are not automatically retried. The latest sending task is saved with its campaign ID and can be recovered through an authenticated read-only status endpoint after reloading. Request-submission or polling failures explicitly tell the owner when an outcome is unknown.

81 Python tests and 9 sending-status JavaScript tests passed. Browser verification used pre-recorded successful, failed and uncertain outcomes in a separate read-only fixture; page reload preserved the result. No real email was sent during implementation or verification. The actual owner workspace had no sending job or delivery record for the attempted send, and showed SMTP not configured.

## Consent-based Gmail reply tracking

The local demo now asks for permission before reusing the saved sending-account Gmail app password for reply syncing. No real mailbox access occurs before the owner clicks Allow & sync replies. Permission is bound to the sender, credential and consent version, and can be stopped through Delivery log. A different sender or credential requires new consent. New users still need a valid Gmail connection; this is a local permission flow, not Google OAuth sign-in.

After permission, the page checks related replies automatically while open and visible, approximately once a minute, with a Sync now control. Gmail is opened read-only; searches use exact outgoing Message-ID references and reply sender matching. Header checks precede body reads. Only matching reply text is saved locally in engagement.json. No email is sent, deleted, or marked read. Inbox and archived mail are scanned where Gmail exposes All Mail; otherwise the UI reports Inbox only. Spam and Trash are excluded. Large messages are recorded with a notice rather than downloaded. Quoted original text is excluded from keyword classification. Automatic replies are listed separately and do not increase human reply rate. Human replies pause follow-up drafts.

SMTP-sent messages with saved Message-IDs can be matched, including replies already received before enabling sync. Browser-sent records without Message-IDs are reported as not automatically matchable. Scans cover the latest 300 sent messages and at most 1,000 matching reply candidates; the UI reports older-message coverage limits. New messages without a reply reference are not guessed into a campaign. Only successful sending records enter rate denominators. Open/click tracking remains separate and is not enabled by granting mailbox permission.

Permission and sync metadata are saved privately in reply-sync.json. The API never returns the app password or the private credential fingerprint. Credentials and reply text are never sent to an AI service.

99 Python tests and 9 JavaScript outcome tests passed. An isolated fake mailbox verified automatic import, activity display, a 100% reply rate for one test send, pause/decline behavior, and permission prompt wording. The owner granted permission through the actual demo dialog. The first real Gmail scan checked 3 sent messages, imported 1 human reply, and the browser showed Connected, one reply card and a 33.3% reply rate. No message was sent, deleted, or marked read during synchronization.

The previous version is saved in outreach-v3-before-reply-sync.zip. Restore that application folder to remove this feature. Existing saved contacts, replies and credentials are stored separately.

## Creator reply list and English interface

Replies is now a compact creator list with name/email, latest reply time, category and reply count. Rows are grouped by creator email across source lists, and duplicate imported message IDs are collapsed. Search filters by name/email; lists paginate at 20 creators per page. View replies opens a separate dialog containing only the selected creator's received replies, newest first. Existing follow-up tools remain available. All new interface labels and messages are English; original incoming mail remains in its original language.

Quoted earlier emails are removed from reply display, including Gmail/HTML blockquotes, wrapped attribution lines, Outlook header blocks and Replied Message separators. Existing saved reply records are cleaned in API responses without rewriting the original saved text. New Gmail imports are cleaned before storage. The Enrich emails in bulk control and its UI click handler were removed.

112 Python tests passed, including quote-format regressions and preserving stored reply data. Old Gmail reply categories are also recalculated for display after quoted text is removed, so the original pitch does not determine the reply category. JavaScript syntax checks passed. Browser checks used 32 isolated test creators to verify grouping, deduplication, search, 20/12-row pagination, reply-only detail dialogs, empty search, follow-up navigation and absence of the enrichment button. No test contacts were added to the actual workspace and no email was sent. The pre-change application is saved in outreach-v3-before-replies-list.zip.


## Independent workflow pages (2026-10-17)

Each of the six existing sidebar entries now shows only its own section. The sections stay mounted, so navigating with the sidebar, Previous / Next, or browser history retains form values, contact selections, drafts, and existing controls. The bottom navigation stays visible while scrolling a long page. Find Creators still contains its original search fields, quota check and task recovery tools; Contacts retains saved lists, CSV / Excel import, manual contact entry, filters, card wall, table, creator detail drawer and collaboration board. No existing control IDs were removed.

Start search validates required fields, country codes, integer ranges, follower limits and the credit budget inline in English. Invalid inputs stay on Find Creators without submitting a search. Once a search submission is accepted, the page changes to Contacts and shows running, completed, stopped or failed status beside the contact tools. Completed results open as a saved list. A failed search does not blank the previous saved-list selection. A network status failure preserves the original request ID and directs users to task recovery rather than automatically retrying a paid request.

The new Contacts Outreach button carries the selected recipients to Outreach email, with a visible recipient count. Without an email selection, it displays an English error beside that button. Previous / Next are navigation only; they never run a search or send email. The workspace header includes “Please complete Account Setup first.” with a link to that page. Form validation and operation errors appear near the relevant controls. The existing SMTP outcome panel remains unchanged.

Verification: 112 existing Python tests and 9 sending-feedback JavaScript tests passed. Browser checks used a separate private fixture with simulated EasyKOL results and sending/AI requests disabled. Checks covered empty inputs, insufficient budget, immediate search handoff with visible progress, successful results, provider failure, all six sidebar destinations, Previous / Next, browser back/forward, selected-recipient handoff, form and selection retention, draft preview, invalid email feedback, card/table views, and the creator detail drawer. Invalid searches created no jobs; the fixture recorded completed and intentionally failed search jobs, and no sending job. No live EasyKOL search or email sending was performed.

Restore point: outreach-v3-before-step-pages.zip contains the complete source before these changes. Restore its assets/app.js, assets/app.css and assets/index.html to return to the prior continuous layout. Personal data and saved credentials remain outside the source package in the existing private workspace; do not replace that private directory when restoring the UI.


## Instruction tabs reset (2026-10-17)

The sidebar, page heading, browser title and page-navigation label now say Instruction. The four previous guide sections were replaced with User journey, How it works, Risks & Where It Breaks, and Status & Next Steps. Each tab has an empty panel; no placeholder content was added. Clicks and keyboard arrows/Home/End select one panel at a time. The original #user-instruction route remains compatible. Removed the old presentation-only JavaScript initialization and script inclusion so the cleared content does not cause missing-element errors. Other workspace pages and account data are unchanged. Restore point: outreach-v3-before-instruction-reset.zip.
