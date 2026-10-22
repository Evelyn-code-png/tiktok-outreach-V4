#!/usr/bin/env python3
"""EasyKOL + Gmail outreach. Python 3.10+, standard library only."""
import argparse
import base64
import google_mail
from contextlib import contextmanager
import csv
import getpass
import hashlib
import json
import os
from pathlib import Path
import re
import smtplib
import sqlite3
import ssl
import sys
import time
import tempfile
import html
import urllib.error
import urllib.parse
import urllib.request
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from string import Template

ROOT = Path(os.environ.get('TIKTOK_OUTREACH_HOME', '~/.config/tiktok-outreach-v3')).expanduser()
EMAIL = re.compile(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)+")
FIELDS = ['name', 'username', 'profile_url', 'email', 'followers', 'region', 'language', 'source', 'avatar_url']

class OperationCancelled(ValueError):
    pass

def check_cancel(args):
    callback = getattr(args, 'should_stop', None)
    if callback and callback():
        raise OperationCancelled('The task was stopped. Completed data and delivery records were preserved, but an in-flight provider request cannot be withdrawn.')

def report_progress(args, **values):
    callback = getattr(args, 'progress', None)
    if callback:
        callback(values)

def private_dir():
    ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)

def load_config():
    p = ROOT / 'config.json'
    return json.loads(p.read_text()) if p.exists() else {}

def save_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix='.' + path.name + '-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp): os.unlink(temp)

def valid_email(value):
    value = str(value or '').strip()
    if len(value) > 254 or not EMAIL.fullmatch(value):
        raise ValueError('Enter one valid email address')
    return value.lower()

def setup(_):
    if not sys.stdin.isatty():
        raise ValueError('Run setup in a local terminal; secret input will remain hidden')
    private_dir()
    cfg = load_config()
    cfg['sender'] = valid_email(input('Gmail sender address [' + cfg.get('sender', '') + ']: ').strip() or cfg.get('sender', ''))
    cfg['easykol_email'] = valid_email(input('EasyKOL account email [' + cfg.get('easykol_email', cfg['sender']) + ']: ').strip() or cfg.get('easykol_email', cfg['sender']))
    for key, label in [('easykol_key', 'EasyKOL API key'), ('gmail_app_password', 'Gmail app password (not your sign-in password)')]:
        value = getpass.getpass(label + '; leave blank to keep the saved value: ').strip()
        if value:
            cfg[key] = value.replace(' ', '') if key == 'gmail_app_password' else value
    save_json(ROOT / 'config.json', cfg)
    return {'saved': str(ROOT / 'config.json')}

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None

def easykol_http_error(path, error, key, email):
    """Show a bounded provider reason, never credentials or a raw error page."""
    stage = {'/quota': 'balance check', '/intelligent-search': 'creator search'}.get(path, 'request')
    message = f'EasyKOL {stage} returned HTTP {error.code}.'
    try:
        raw = error.read(8193)
        body = raw[:8192].decode('utf-8', 'replace')
        edge = re.search(r'\berror code\s*:\s*(1\d{3,4})\b', body, re.I)
        if edge and edge[1] == '1010':
            message += ' The provider edge rejected the client signature (1010).'
        else:
            try:
                payload = json.loads(body) if len(raw) <= 8192 else {}
            except ValueError:
                payload = {}
            if isinstance(payload, dict):
                reason = payload.get('message')
                if not isinstance(reason, str):
                    reason = payload.get('error') if isinstance(payload.get('error'), str) else ''
                # Redact the known credentials before truncation, including encoded forms.
                for secret in (key, email):
                    if secret:
                        for form in (secret, urllib.parse.quote(secret, safe=''), json.dumps(secret)[1:-1]):
                            reason = reason.replace(form, '[redacted]')
                reason = re.sub(r'[\x00-\x1f\x7f]', ' ', reason).strip()
                if reason:
                    message += ' Provider reason: ' + reason[:320]
                code = payload.get('statusCode', payload.get('code'))
                if isinstance(code, int) or (isinstance(code, str) and re.fullmatch(r'[A-Za-z0-9_-]{1,40}', code)):
                    message += f' (provider code {code}).'
    except (OSError, ValueError, AttributeError):
        pass
    message += ' No automatic retry was made. A failed search has not produced a usable creator list.'
    return ValueError(message)

def api(path, body=None):
    cfg = load_config()
    key = os.environ.get('EASYKOL_API_KEY') or cfg.get('easykol_key')
    email = os.environ.get('EASYKOL_API_EMAIL') or cfg.get('easykol_email')
    if not key or not email:
        raise ValueError('The EasyKOL API key or account email is missing; run setup first')
    req = urllib.request.Request('https://app.easykol.com/external/v1' + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={'ek-api-key': key, 'ek-api-email': email, 'Content-Type': 'application/json'})
    try:
        with urllib.request.build_opener(NoRedirect).open(req, timeout=45) as r:
            result = json.load(r)
    except urllib.error.HTTPError as e:
        raise easykol_http_error(path, e, key, email) from None
    except (urllib.error.URLError, TimeoutError):
        raise ValueError('The EasyKOL network request failed. It may still have been submitted; check the task and credit balance before retrying.') from None
    if not isinstance(result, dict) or result.get('statusCode', 1000) != 1000 or result.get('error'):
        raise ValueError('EasyKOL returned an application error; check permissions, credits, and request details')
    return result.get('data', result)

def avatar_url(row):
    """Preserve only HTTPS image references; never interpret HTML or inline data."""
    for key in ('avatar_url', 'avatarUrl', 'avatar', 'avatarThumb', 'avatarMedium', 'avatarLarger', 'profileImageUrl', 'profilePictureUrl'):
        value = row.get(key)
        if isinstance(value, dict):
            value = value.get('url') or next(iter(value.get('url_list') or []), '')
        if not isinstance(value, str) or len(value) > 4096: continue
        try:
            parsed = urllib.parse.urlparse(value)
            if parsed.scheme == 'https' and parsed.hostname and not parsed.username and not parsed.password:
                return value
        except ValueError: pass
    return ''


def normalize(rows):
    out, seen = [], set()
    for row in rows:
        profile = str(row.get('profile_url') or row.get('profileUrl') or '')
        raw_email = str(row.get('email') or '').strip()
        emails = sorted(set(x.lower() for x in EMAIL.findall(raw_email)))
        # Only parse explicit email fields, never creator bios or unrelated metadata.
        for email in emails or ['']:
            item = dict(name=row.get('name') or row.get('nickname') or row.get('username') or '',
                username=row.get('username') or '', profile_url=profile, email=email,
                followers=row.get('followers', row.get('followerCount', '')),
                region=row.get('region') or '', language=row.get('language') or '',
                source=row.get('source') or 'EasyKOL', avatar_url=avatar_url(row))
            key = (profile or item['username'] or item['name'], email)
            if key not in seen:
                seen.add(key)
                out.append(item)
    return out

def needs_csv_quote(value):
    text = str(value)
    return text.startswith(('\t', '\r', '\n')) or text.lstrip().startswith(('=', '+', '-', '@'))

def csv_write(path, rows):
    path = Path(path)
    fd, temp = tempfile.mkstemp(prefix='.' + path.name + '-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS)
            writer.writeheader()
            for row in rows:
                # Protect spreadsheet viewers against formula injection.
                writer.writerow({k: "'" + str(v) if needs_csv_quote(v) else v for k, v in row.items() if k in FIELDS})
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp): os.unlink(temp)

def csv_read(path):
    with open(path, encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise ValueError('The CSV header is missing or contains duplicate columns')
        rows = list(reader)
    for row in rows:
        if None in row: raise ValueError('A CSV row contains more values than the header')
        for k, v in row.items():
            if v and v.startswith("'") and needs_csv_quote(v[1:]):
                row[k] = v[1:]
    return rows

def search(args):
    check_cancel(args)
    sentences = [args.query] if args.query else [x.strip() for x in Path(args.queries_file).read_text().splitlines() if x.strip()]
    if not sentences or any(not 1 <= len(x) <= 500 for x in sentences):
        raise ValueError('Each search request must contain 1-500 characters')
    if not 1 <= args.limit <= 50 or args.min_followers < 0 or args.avg_min < 0:
        raise ValueError('The result limit must be 1-50, and follower and view counts cannot be negative')
    regions = [x.strip().upper() for x in args.regions.split(',') if x.strip()]
    if not regions or any(not re.fullmatch('[A-Z]{2}', r) for r in regions):
        raise ValueError('Use two-letter country codes, such as US,GB')
    planned = len(sentences) * args.limit
    if planned > args.budget:
        raise ValueError(f'This search can use up to {planned} credits, which exceeds the budget of {args.budget}')
    quota = api('/quota')
    if quota.get('remaining', planned) < planned:
        raise ValueError('The EasyKOL balance is too low for this search limit')
    out = Path(args.out)
    if out.exists():
        raise ValueError('The output folder already exists; use a different name to preserve the earlier search')
    out.mkdir(parents=True, mode=0o700)
    all_rows = []
    report_progress(args, completed=0, total=len(sentences), unit='searches', rows=0)
    for index, sentence in enumerate(sentences):
        check_cancel(args)
        body = dict(sentence=sentence, platform='TIKTOK', regions=regions,
                    minSubscribers=args.min_followers, avgMin=args.avg_min,
                    limit=args.limit, dedupDays=3)
        if args.max_followers is not None:
            if args.max_followers < args.min_followers:
                raise ValueError('The maximum follower count cannot be lower than the minimum')
            body['maxSubscribers'] = args.max_followers
        if args.languages:
            body['languages'] = [x.strip() for x in args.languages.split(',')]
        if args.has_email:
            body['hasContactInfo'] = True
        result = api('/intelligent-search', body)
        save_json(out / f'raw-{index + 1}.json', result)
        rows = result.get('data') if isinstance(result, dict) else result
        if not isinstance(rows, list) or any(not isinstance(x, dict) for x in rows):
            raise ValueError('The search response format changed. The raw response was saved, and processing stopped to prevent mismatched contacts.')
        all_rows.extend(rows)
        csv_write(out / 'creators.csv', normalize(all_rows))
        report_progress(args, completed=index + 1, total=len(sentences), unit='searches', rows=len(normalize(all_rows)))
        if index < len(sentences) - 1:
            time.sleep(6.1)
    return {'csv': str(out / 'creators.csv'), 'rows': len(normalize(all_rows)), 'maximum_search_credits': planned}

def emails_start(args):
    urls = list(dict.fromkeys(r['profile_url'] for r in csv_read(args.csv) if r.get('profile_url')))
    if not urls or len(urls) > 100:
        raise ValueError('Each batch requires 1-100 creator profile URLs')
    for url in urls:
        p = urllib.parse.urlparse(url)
        if p.scheme != 'https' or p.hostname not in ('www.tiktok.com', 'tiktok.com') or not re.fullmatch(r'/@[A-Za-z0-9_.]+/?', p.path):
            raise ValueError('Only HTTPS TikTok creator profile URLs are accepted')
    cost = (len(urls) + 4) // 5
    if cost > args.budget:
        raise ValueError(f'The email lookup requires an estimated {cost} credits, which exceeds the budget')
    task = api('/kol-emails', {'ttUrls': urls, 'ytbUrls': [], 'insUrls': []})
    private_dir()
    save_json(ROOT / ('email-task-' + str(time.time_ns()) + '.json'), task)
    return {'task': task, 'estimated_credits': cost, 'next': 'Check the task with emails-status --task-id; do not create a duplicate task'}

def emails_status(args):
    if not re.fullmatch(r'[A-Za-z0-9_-]+', args.task_id):
        raise ValueError('The task ID format is invalid')
    result = api('/kol-emails/' + args.task_id)
    save_json(args.out, result)
    return {'status': result.get('status'), 'raw_file': args.out,
            'note': 'Import only explicit profile-to-email associations; never infer a match from array order'}

def emails_collect(args):
    from email_results import collect
    return collect(args)

@contextmanager
def db_open():
    private_dir()
    db = sqlite3.connect(ROOT / 'outreach.sqlite', timeout=30)
    os.chmod(ROOT / 'outreach.sqlite', 0o600)
    try:
        db.execute('CREATE TABLE IF NOT EXISTS deliveries (campaign TEXT, email TEXT, status TEXT, message_id TEXT, updated REAL, PRIMARY KEY(campaign,email))')
        db.execute('CREATE TABLE IF NOT EXISTS suppressed (email TEXT PRIMARY KEY)')
        db.execute('CREATE TABLE IF NOT EXISTS tracking_events (campaign TEXT, email TEXT, event TEXT, updated REAL, PRIMARY KEY(campaign,email,event))')
        db.execute('CREATE TABLE IF NOT EXISTS cloud_tracking_messages (campaign TEXT NOT NULL, email TEXT NOT NULL, id TEXT NOT NULL UNIQUE, origin TEXT NOT NULL, PRIMARY KEY(campaign,email))')
        with db:
            yield db
    finally:
        db.close()

def campaign_hash(campaign):
    payload = {k: campaign[k] for k in ('sender', 'messages')}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

def tracking_token(campaign, email):
    secret = load_config().get('tracking_secret') or 'local-tracking-secret'
    return hashlib.sha256((campaign+'|'+email+'|'+secret).encode()).hexdigest()[:40]

def tracked_url(campaign, email, url):
    return (load_config().get('tracking_base_url','').rstrip('/') + '/t/click/' + campaign + '/' + tracking_token(campaign,email) + '?url=' + urllib.parse.quote(url, safe=''))

def record_tracking(campaign, email, event):
    valid_email(email)
    if event not in ('sent','open','click','reply'): raise ValueError('tracking event invalid')
    with db_open() as db: db.execute('INSERT OR IGNORE INTO tracking_events VALUES (?,?,?,?)',(campaign,email,event,time.time()))

def metrics(campaign_id=None):
    with db_open() as db:
        where=" WHERE status IN ('accepted_by_smtp','accepted_by_gmail_api','sent_browser')"; params=[]
        event_where=" WHERE d.status IN ('accepted_by_smtp','accepted_by_gmail_api','sent_browser')"
        if campaign_id:
            where+=' AND campaign=?'; event_where+=' AND d.campaign=?'; params=[campaign_id]
        sent=db.execute('SELECT COUNT(*) FROM deliveries'+where,params).fetchone()[0]
        rows=db.execute('SELECT t.event,COUNT(*) FROM tracking_events t JOIN deliveries d ON t.campaign=d.campaign AND t.email=d.email'+event_where+' GROUP BY t.event',params).fetchall()
    counts=dict(rows); return {'sent':sent,'opened':counts.get('open',0),'clicked':counts.get('click',0),'replied':counts.get('reply',0),
      'open_rate':round(counts.get('open',0)/sent*100,1) if sent else 0,'reply_rate':round(counts.get('reply',0)/sent*100,1) if sent else 0,
      'click_rate':round(counts.get('click',0)/sent*100,1) if sent else 0,'tracked':bool(load_config().get('tracking_base_url'))}

def load_campaign(path):
    campaign = json.loads(Path(path).read_text())
    if campaign_hash(campaign) != campaign.get('id'):
        raise ValueError('The draft was modified; generate it again')
    if campaign['sender'] != valid_email(load_config().get('sender')):
        raise ValueError('The draft sender does not match the current configuration')
    if not isinstance(campaign['messages'], list) or not campaign['messages']:
        raise ValueError('The draft contains no messages')
    seen = set()
    for item in campaign['messages']:
        email = valid_email(item['to'])
        if email in seen: raise ValueError('The draft contains a duplicate recipient')
        seen.add(email)
        if not item['subject'].strip() or '\r' in item['subject'] or '\n' in item['subject'] or not item['body'].strip():
            raise ValueError('The email subject or body is invalid')
    return campaign

def browser_plan(args):
    campaign = load_campaign(args.campaign)
    with db_open() as db:
        suppressed = {r[0] for r in db.execute('SELECT email FROM suppressed')}
        prior = dict(db.execute('SELECT email,status FROM deliveries WHERE campaign=?', (campaign['id'],)))
    pending, skipped = [], []
    for item in campaign['messages']:
        email = valid_email(item['to'])
        if email in suppressed or email in prior:
            skipped.append({'email': email, 'status': 'suppressed' if email in suppressed else prior[email]})
        else:
            pending.append(item)
    return {'campaign_id': campaign['id'], 'sender': campaign['sender'], 'pending': pending, 'skipped': skipped,
            'note': 'This command does not send email. Fill each message in the browser, run browser-claim before clicking Send, and record the visible result with browser-result.'}

def browser_claim(args):
    campaign = load_campaign(args.campaign)
    email = valid_email(args.email)
    if not any(valid_email(m['to']) == email for m in campaign['messages']):
        raise ValueError('The recipient is not part of this campaign')
    with db_open() as db:
        db.execute('BEGIN IMMEDIATE')
        if db.execute('SELECT 1 FROM suppressed WHERE email=?', (email,)).fetchone():
            raise ValueError('This address is on the suppression list')
        prior = db.execute('SELECT status FROM deliveries WHERE campaign=? AND email=?', (campaign['id'], email)).fetchone()
        if prior: raise ValueError('This recipient already has a delivery record: ' + prior[0] + '. Do not send it again.')
        db.execute('INSERT INTO deliveries VALUES (?,?,?,?,?)', (campaign['id'], email, 'sending_browser', '', time.time()))
    return {'campaign_id': campaign['id'], 'email': email, 'status': 'sending_browser'}

def browser_result(args):
    campaign = load_campaign(args.campaign)
    email = valid_email(args.email)
    allowed = ('sent_browser', 'unknown', 'failed_before_submission')
    if args.result not in allowed: raise ValueError('The browser delivery status is invalid')
    with db_open() as db:
        cursor = db.execute('UPDATE deliveries SET status=?,updated=? WHERE campaign=? AND email=? AND status=?',
                           (args.result, time.time(), campaign['id'], email, 'sending_browser'))
        if cursor.rowcount != 1: raise ValueError('No matching browser delivery claim was found')
    if args.result == 'sent_browser': record_tracking(campaign['id'], email, 'sent')
    return {'email': email, 'status': args.result}

def draft(args):
    sender = valid_email(load_config().get('sender'))
    template = Template(Path(args.body).read_text(encoding='utf-8'))
    subject = Template(args.subject)
    messages, skipped, seen = [], [], set()
    with db_open() as db:
        suppressed = {r[0] for r in db.execute('SELECT email FROM suppressed')}
    for row in normalize(csv_read(args.csv)):
        if not row['email']:
            skipped.append({'profile_url': row['profile_url'], 'reason': 'No valid email address'})
            continue
        email = valid_email(row['email'])
        if email in seen or email in suppressed:
            skipped.append({'email': email, 'reason': 'Duplicate or suppressed'})
            continue
        seen.add(email)
        title, body = subject.substitute(row), template.substitute(row)
        if not title.strip() or '\r' in title or '\n' in title or not body.strip():
            raise ValueError('The subject and body are required, and the subject cannot contain a line break')
        messages.append({'to': email, 'subject': title, 'body': body})
    if not messages:
        raise ValueError('No eligible recipients are available')
    campaign = {'sender': sender, 'messages': messages}
    campaign['id'] = campaign_hash(campaign)
    if Path(args.out).exists():
        raise ValueError('The draft file already exists; use a different name')
    save_json(args.out, campaign)
    return {'campaign_file': args.out, 'campaign_id': campaign['id'], 'recipients': len(messages), 'skipped': skipped, 'preview': messages}

def send(args):
    check_cancel(args)
    campaign = load_campaign(args.campaign)
    cfg = load_config()
    sender = valid_email(cfg.get('sender'))
    if not 1 <= args.max_messages <= 500 or args.delay < 1:
        raise ValueError('max-messages must be 1-500, and delay must be at least one second')
    if not args.execute:
        plan = browser_plan(args)
        return {'dry_run': True, 'campaign_id': campaign['id'], 'messages': plan['pending'][:args.max_messages], 'skipped': plan['skipped']}
    if args.campaign_id != campaign['id']:
        raise ValueError('The --campaign-id must match the ID shown in the preview before sending')
    password = os.environ.get('GMAIL_APP_PASSWORD') or cfg.get('gmail_app_password')
    use_google = cfg.get('mail_transport') == 'google'
    if use_google:
        google_mail.access()  # Fail before recording a submission if refresh fails.
        google_connection = google_mail.load().get('connection_id')
    elif cfg.get('mail_transport') == 'disconnected' or not password:
        raise ValueError('Connect Google in Account Setup or configure SMTP sending first')
    report = []
    planned = min(args.max_messages, len(browser_plan(args)['pending']))
    report_progress(args, completed=0, total=planned, unit='messages')
    with db_open() as db:
        # Separate SMTP connection per recipient simplifies precise outcome tracking.
        sent = 0
        for item in campaign['messages']:
            check_cancel(args)
            email = valid_email(item['to'])
            if sent >= args.max_messages:
                break
            db.execute('BEGIN IMMEDIATE')
            blocked = db.execute('SELECT 1 FROM suppressed WHERE email=?', (email,)).fetchone()
            prior = db.execute('SELECT status FROM deliveries WHERE campaign=? AND email=?', (campaign['id'], email)).fetchone()
            if blocked or prior:
                db.commit()
                report.append({'email': email, 'status': 'suppressed' if blocked else prior[0], 'skipped': True})
                continue
            msg = EmailMessage()
            msg['From'], msg['To'], msg['Subject'] = sender, email, item['subject']
            msg['Date'], msg['Message-ID'] = formatdate(localtime=True), make_msgid(domain=sender.split('@')[1])
            msg.set_content(item['body'])
            import cloud_tracking
            cloud_html = cloud_tracking.prepare(db, campaign['id'], email, item['body'])
            tracking_base = cfg.get('tracking_base_url','').rstrip('/')
            if cloud_html:
                msg.add_alternative(cloud_html, subtype='html')
            elif tracking_base:
                pixel = tracking_base + '/t/open/' + campaign['id'] + '/' + tracking_token(campaign['id'], email) + '.gif'
                safe_body = html.escape(item['body']).replace('\n','<br>')
                safe_body = re.sub(r'https?://[^\s<]+', lambda m:'<a href="'+html.escape(tracked_url(campaign['id'],email,m.group(0)),quote=True)+'">'+html.escape(m.group(0))+'</a>', safe_body)
                msg.add_alternative('<html><body>'+safe_body+'<img src="'+html.escape(pixel, quote=True)+'" width="1" height="1" alt=""></body></html>', subtype='html')
            db.execute('INSERT INTO deliveries VALUES (?,?,?,?,?)', (campaign['id'], email, 'sending', msg['Message-ID'], time.time()))
            db.commit()
            status = 'failed_before_submission'
            try:
                if use_google:
                    # Refresh before submission; never retry an ambiguous send.
                    with google_mail.LOCK:
                        connection = google_mail.load()
                        if connection.get('connection_id') != google_connection or connection.get('email') != sender.lower():
                            raise ValueError('The Google sending account changed. Review the campaign again.')
                        token = google_mail.access()
                        status = 'unknown'
                        response = google_mail.request('https://gmail.googleapis.com/gmail/v1/users/me/messages/send',
                            token=token, body={'raw': base64.urlsafe_b64encode(msg.as_bytes()).decode()})
                    if response.get('id'): status = 'accepted_by_gmail_api'
                else:
                    with smtplib.SMTP_SSL('smtp.gmail.com', 465, timeout=40, context=ssl.create_default_context()) as smtp:
                        smtp.login(sender, password.replace(' ', ''))
                        status = 'unknown'
                        refused = smtp.send_message(msg)
                        status = 'rejected' if refused else 'accepted_by_smtp'
            except (OSError, ValueError, smtplib.SMTPException):
                # A lost response after DATA may mean sent: never automatically retry.
                pass
            db.execute('UPDATE deliveries SET status=?,updated=? WHERE campaign=? AND email=?', (status, time.time(), campaign['id'], email))
            db.commit()
            if status in ('accepted_by_smtp', 'accepted_by_gmail_api'): record_tracking(campaign['id'], email, 'sent')
            report.append({'email': email, 'status': status})
            sent += 1
            report_progress(args, completed=sent, total=planned, unit='messages')
            if status not in ('accepted_by_smtp', 'accepted_by_gmail_api'):
                break
            if sent < args.max_messages:
                time.sleep(args.delay)
    attempted = [r for r in report if not r.get('skipped')]
    accepted = sum(r['status'] in ('accepted_by_smtp', 'accepted_by_gmail_api') for r in attempted)
    return {'campaign_id': campaign['id'], 'results': report, 'attempted': len(attempted), 'accepted': accepted,
            'failed_or_unknown': len(attempted) - accepted, 'skipped': len(report) - len(attempted),
            'note': 'accepted_by_smtp / accepted_by_gmail_api means the server accepted the message; it does not prove inbox delivery. Unknown or in-progress results are not retried automatically.'}

def doctor(args):
    cfg = load_config()
    result = {'config_path': str(ROOT / 'config.json'), 'sender': cfg.get('sender'),
              'easykol_configured': bool((cfg.get('easykol_key') or os.environ.get('EASYKOL_API_KEY')) and (cfg.get('easykol_email') or os.environ.get('EASYKOL_API_EMAIL'))),
              'gmail_configured': (google_mail.connected() if cfg.get('mail_transport') == 'google' else False if cfg.get('mail_transport') == 'disconnected' else bool(cfg.get('gmail_app_password') or os.environ.get('GMAIL_APP_PASSWORD')))}
    if args.online:
        result['quota'] = api('/quota')
    return result

def suppress(args):
    with db_open() as db:
        db.execute('INSERT OR IGNORE INTO suppressed VALUES (?)', (valid_email(args.email),))
    return {'suppressed': args.email}

def history(args):
    limit, offset = int(getattr(args, 'limit', 100)), int(getattr(args, 'offset', 0))
    if not 1 <= limit <= 1000 or offset < 0:
        raise ValueError('The record limit must be 1-1000, and the starting position cannot be negative')
    where, params = [], []
    if getattr(args, 'campaign_id', None):
        where.append('campaign=?'); params.append(args.campaign_id)
    if getattr(args, 'email', None):
        where.append('email=?'); params.append(valid_email(args.email))
    clause = ' WHERE ' + ' AND '.join(where) if where else ''
    with db_open() as db:
        total = db.execute('SELECT COUNT(*) FROM deliveries' + clause, params).fetchone()[0]
        rows = db.execute('SELECT campaign,email,status,message_id,updated FROM deliveries' + clause + ' ORDER BY updated DESC,campaign,email LIMIT ? OFFSET ?', params + [limit, offset]).fetchall()
    return {'deliveries': [dict(zip(['campaign', 'email', 'status', 'message_id', 'updated'], r)) for r in rows],
            'total': total, 'offset': offset, 'limit': limit}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('setup').set_defaults(fn=setup)
    p = sub.add_parser('doctor'); p.add_argument('--online', action='store_true'); p.set_defaults(fn=doctor)
    p = sub.add_parser('quota'); p.set_defaults(fn=lambda _: api('/quota'))
    p = sub.add_parser('search'); p.set_defaults(fn=search)
    q = p.add_mutually_exclusive_group(required=True); q.add_argument('--query'); q.add_argument('--queries-file')
    p.add_argument('--regions', required=True); p.add_argument('--languages')
    p.add_argument('--min-followers', type=int, default=0); p.add_argument('--max-followers', type=int)
    p.add_argument('--avg-min', type=int, default=0); p.add_argument('--limit', type=int, default=20)
    p.add_argument('--budget', type=int, default=50); p.add_argument('--has-email', action='store_true'); p.add_argument('--out', required=True)
    p = sub.add_parser('emails-start'); p.set_defaults(fn=emails_start); p.add_argument('--csv', required=True); p.add_argument('--budget', type=int, default=20)
    p = sub.add_parser('emails-status'); p.set_defaults(fn=emails_status); p.add_argument('--task-id', required=True); p.add_argument('--out', required=True)
    p = sub.add_parser('emails-collect'); p.set_defaults(fn=emails_collect); p.add_argument('--task-id', required=True); p.add_argument('--csv', required=True); p.add_argument('--out', required=True)
    p = sub.add_parser('draft'); p.set_defaults(fn=draft)
    for key in ('csv', 'subject', 'body', 'out'): p.add_argument('--' + key, required=True)
    p = sub.add_parser('send'); p.set_defaults(fn=send); p.add_argument('--campaign', required=True); p.add_argument('--execute', action='store_true'); p.add_argument('--campaign-id')
    p.add_argument('--max-messages', type=int, default=20); p.add_argument('--delay', type=float, default=2)
    p = sub.add_parser('suppress'); p.set_defaults(fn=suppress); p.add_argument('--email', required=True)
    p = sub.add_parser('history'); p.set_defaults(fn=history)
    p.add_argument('--limit', type=int, default=100); p.add_argument('--offset', type=int, default=0)
    p.add_argument('--campaign-id'); p.add_argument('--email')
    p = sub.add_parser('browser-plan'); p.set_defaults(fn=browser_plan); p.add_argument('--campaign', required=True)
    p = sub.add_parser('browser-claim'); p.set_defaults(fn=browser_claim); p.add_argument('--campaign', required=True); p.add_argument('--email', required=True)
    p = sub.add_parser('browser-result'); p.set_defaults(fn=browser_result); p.add_argument('--campaign', required=True); p.add_argument('--email', required=True); p.add_argument('--result', choices=['sent_browser', 'unknown', 'failed_before_submission'], required=True)
    args = parser.parse_args()
    try:
        print(json.dumps({'status': 'ok', 'data': args.fn(args)}, ensure_ascii=False, indent=2))
    except (ValueError, KeyError, OSError, sqlite3.Error) as e:
        print(json.dumps({'status': 'error', 'message': str(e)}, ensure_ascii=False))
        sys.exit(1)

if __name__ == '__main__':
    main()
