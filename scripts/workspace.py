"""Durable local jobs and contact/campaign operations for the dashboard."""
import csv
import base64
import hashlib
import io
import json
from pathlib import Path
import re
import threading
import time
from types import SimpleNamespace as NS
import uuid
import zipfile
import xml.etree.ElementTree as ET

import outreach as o

JOB_LOCK = threading.RLock()
WORK_LOCK = threading.Lock()

def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,100}', value):
        raise ValueError('The record ID is invalid')
    return value

def location(kind, value):
    if not isinstance(value, str): raise ValueError('The record path is invalid')
    stem = value.rsplit('.', 1)[0] if value.endswith(('.json', '.txt')) else value
    identifier(stem)
    return o.ROOT / kind / value

def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))

def summarize_run(path):
    rows = o.csv_read(path / 'creators.csv') if (path / 'creators.csv').exists() else []
    meta = read_json(path / 'meta.json') if (path / 'meta.json').exists() else {}
    return {'id': path.name, 'title': meta.get('title', path.name), 'rows': len(rows),
            'emails': len({r['email'].lower() for r in rows if r.get('email')}),
            'created': meta.get('created', path.stat().st_mtime),
            'source': meta.get('source', 'EasyKOL'), 'csv_path': str(path / 'creators.csv')}

def list_runs():
    root = o.ROOT / 'runs'
    rows = [summarize_run(p) for p in root.iterdir() if p.is_dir() and (p / 'creators.csv').exists()] if root.exists() else []
    return sorted(rows, key=lambda x: x['created'], reverse=True)

def get_run(run_id):
    p = location('runs', run_id)
    if not (p / 'creators.csv').exists(): raise ValueError('The contact list does not exist')
    result = summarize_run(p)
    result['contacts'] = o.csv_read(p / 'creators.csv')
    import creator_photos
    creator_photos.enrich(result['contacts'], p)
    return result

def add_contact(data):
    for key in ('email', 'name', 'run_id'):
        if key in data and not isinstance(data[key], str):
            raise ValueError('Contact fields must be text')
    email = o.valid_email(data.get('email'))
    name = data.get('name', '').strip()
    if len(name) > 120 or any(c in name for c in '\r\n\x00'):
        raise ValueError('Use a contact name of up to 120 characters on one line')
    run_id = data.get('run_id', '').strip() or 'manual-contacts'
    identifier(run_id)
    # Avoid overwriting a list while a search/enrichment job is replacing it.
    if not WORK_LOCK.acquire(blocking=False):
        raise ValueError('A background task is running. Wait for it to finish, then add the contact.')
    try:
        path = location('runs', run_id)
        exists = (path / 'creators.csv').exists()
        if not exists and run_id != 'manual-contacts':
            raise ValueError('The contact list does not exist')
        rows = o.csv_read(path / 'creators.csv') if exists else []
        if any(row.get('email', '').lower() == email for row in rows):
            return {'run': get_run(run_id), 'added': False, 'email': email}
        if len(rows) >= 5000:
            raise ValueError('This list already has 5,000 contacts. Choose another list.')
        rows.append({'name': name or email.split('@')[0], 'email': email,
                     'username': '', 'profile_url': '', 'followers': '',
                     'region': '', 'language': '', 'source': 'Manual'})
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
        o.csv_write(path / 'creators.csv', rows)
        if not exists:
            o.save_json(path / 'meta.json', {'title': 'My contacts', 'source': 'Manual', 'created': time.time()})
        return {'run': get_run(run_id), 'added': True, 'email': email}
    finally:
        WORK_LOCK.release()

ALIASES = {'nickname': 'name', 'displayName': 'name', '昵称': 'name', '姓名': 'name',
           'profileUrl': 'profile_url', '主页': 'profile_url', '主页链接': 'profile_url',
           '邮箱': 'email', 'Email': 'email', 'followerCount': 'followers', '粉丝数': 'followers',
           'URL': 'profile_url', '@username': 'username', 'Region': 'region', 'Language': 'language', 'Followers': 'followers',
           '国家': 'region', '地区': 'region', '语言': 'language', '来源': 'source', '用户名': 'username'}

def import_csv(data):
    content = data.get('csv_text', '')
    if not isinstance(content, str) or len(content.encode()) > 2_000_000:
        raise ValueError('CSV files must be 2 MB or smaller')
    reader = csv.DictReader(io.StringIO(content.lstrip('\ufeff')))
    if not reader.fieldnames: raise ValueError('The CSV file is missing a header')
    headers = [ALIASES.get(h.strip(), h.strip()) for h in reader.fieldnames]
    if len(headers) != len(set(headers)): raise ValueError('The CSV file contains duplicate or equivalent columns; merge them before importing')
    if 'email' not in headers and 'profile_url' not in headers:
        raise ValueError('The CSV file must contain an email or profile_url column')
    source = str(data.get('title') or 'CSV import')[:200]
    rows = []
    for r in reader:
        if None in r: raise ValueError('A CSV row has more values than the header; check commas and quotation marks')
        row = {ALIASES.get(k.strip(), k.strip()): v or '' for k, v in r.items()}
        row['source'] = row.get('source') or source
        rows.append(row)
        if len(rows) > 5000: raise ValueError('A single import can contain up to 5,000 rows')
    rows = o.normalize(rows)
    if not rows: raise ValueError('The CSV file contains no contacts')
    run_id = 'import-' + uuid.uuid4().hex[:12]
    p = location('runs', run_id); p.mkdir(parents=True, mode=0o700)
    o.csv_write(p / 'creators.csv', rows)
    o.save_json(p / 'meta.json', {'title': source, 'created': time.time(), 'source': 'CSV'})
    return get_run(run_id)

def import_xlsx(data):
    from email_results import xlsx_rows
    try:
        raw = base64.b64decode(data.get('xlsx_base64', ''), validate=True)
    except (ValueError, TypeError): raise ValueError('The Excel file encoding is invalid') from None
    if len(raw) > 1_400_000: raise ValueError('Excel imports must be 1.4 MB or smaller; convert larger files to CSV')
    try: rows = xlsx_rows(raw)
    except (OSError, ValueError, KeyError, IndexError, zipfile.BadZipFile, ET.ParseError): raise ValueError('This Excel format is not supported; use a standard XLSX file or export it as CSV') from None
    if not rows: raise ValueError('The Excel file contains no contacts')
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    return import_csv({'csv_text': buf.getvalue(), 'title': data.get('title', 'Excel import')})

def search_args(data, out):
    queries = [str(x).strip() for x in data.get('queries', []) if str(x).strip()]
    if not 1 <= len(queries) <= 20 or any(len(q) > 500 for q in queries):
        raise ValueError('Enter 1-20 search requests, with no more than 500 characters each')
    limit, budget = int(data.get('limit', 20)), int(data.get('budget', 20))
    if not 1 <= limit <= 50 or budget < len(queries) * limit:
        raise ValueError('Results per request must be 1-50, and the total budget must cover requests multiplied by results per request')
    low = int(data.get('min_followers', 0)); high = data.get('max_followers')
    high = int(high) if high not in (None, '') else None
    avg = int(data.get('avg_min', 0))
    if low < 0 or avg < 0 or (high is not None and high < low):
        raise ValueError('The follower or view-count range is invalid')
    regions = str(data.get('regions', '')).upper()
    if not regions or any(not re.fullmatch(r'[A-Z]{2}', x.strip()) for x in regions.split(',')):
        raise ValueError('Use two-letter country codes, such as US,GB')
    return queries, NS(query=queries[0] if len(queries) == 1 else None, queries_file=None,
        regions=regions, languages=str(data.get('languages', '')).strip(), min_followers=low,
        max_followers=high, avg_min=avg, limit=limit, budget=budget, has_email=bool(data.get('has_email', True)), out=str(out))

def job_file(job_id): return location('jobs', identifier(job_id) + '.json')

def save_job(job):
    with JOB_LOCK:
        path = job_file(job['id'])
        if path.exists() and read_json(path).get('cancel_requested'):
            job['cancel_requested'] = True
        o.save_json(path, job)

def cancel_job(job_id):
    with JOB_LOCK:
        job = get_job(job_id)
        if job['status'] not in ('queued', 'running'):
            raise ValueError('The task has already ended')
        job['cancel_requested'] = True
        if job['status'] == 'queued':
            job['status'] = 'cancelled'
            job['finished'] = time.time()
        save_job(job)
    return {'id': job_id, 'message': 'The stop request was recorded. An operation already submitted may still finish, but later steps will not run.'}

def get_job(job_id):
    p = job_file(job_id)
    if not p.exists(): raise ValueError('The task does not exist')
    return read_json(p)

def recent_jobs():
    p = o.ROOT / 'jobs'
    return sorted([read_json(x) for x in p.glob('*.json')], key=lambda x: x['created'], reverse=True)[:50]

def latest_send_job(campaign_id):
    identifier(campaign_id)
    o.load_campaign(location('campaigns', campaign_id + '.json'))
    jobs = []
    for path in (o.ROOT / 'jobs').glob('*.json'):
        job = read_json(path)
        if job.get('kind') == 'send' and (job.get('campaign_id') or job.get('result', {}).get('campaign_id')) == campaign_id:
            jobs.append(job)
    return max(jobs, key=lambda job: job['created']) if jobs else None

def recover_jobs():
    for path in (o.ROOT / 'jobs').glob('*.json'):
        job = read_json(path)
        if job['status'] in ('queued', 'running'):
            job['status'] = 'interrupted'
            job['error'] = 'The previous workspace session was interrupted. The operation may have run; review the raw result or delivery history before retrying.'
            save_job(job)

def start_job(kind, data):
    request_id = identifier(data.get('request_id'))
    if kind not in ('search', 'send', 'emails', 'emails-resume'): raise ValueError('Unknown task type')
    # Validate before creating a durable job or starting any paid request.
    if kind == 'search': search_args(data, o.ROOT / 'runs' / request_id)
    if kind == 'send':
        cid = identifier(data.get('campaign_id'))
        campaign = o.load_campaign(location('campaigns', cid + '.json'))
        if data.get('execute') is not True: raise ValueError('Sending requires explicit confirmation')
        if not 1 <= int(data.get('max_messages', 20)) <= 500: raise ValueError('The batch size must be 1-500 messages')
        if not o.doctor(NS(online=False))['gmail_configured']: raise ValueError('Connect Google or configure SMTP in Account Setup first')
    if kind == 'emails': get_run(data.get('run_id'))
    if kind == 'emails-resume':
        old = get_job(data.get('source_job_id'))
        if old['status'] in ('queued', 'running', 'completed'):
            raise ValueError('The original task is still running or has already finished; review that task directly')
        if not old.get('provider_task_id') or not old.get('source_run_id'):
            raise ValueError('The original task has no provider task ID to resume')
        get_run(old['source_run_id'])
    # Request IDs survive reconnects so a lost HTTP response cannot duplicate work.
    fingerprint = hashlib.sha256(json.dumps({'kind': kind, 'data': data}, sort_keys=True).encode()).hexdigest()
    with JOB_LOCK:
        path = job_file(request_id)
        if path.exists():
            old = read_json(path)
            if old.get('fingerprint') != fingerprint: raise ValueError('The same request ID was used with different parameters')
            return old
        job = {'id': request_id, 'kind': kind, 'status': 'queued', 'created': time.time(), 'fingerprint': fingerprint}
        if kind == 'send': job['campaign_id'] = cid
        save_job(job)
    threading.Thread(target=run_job, args=(job, data), daemon=True).start()
    return job

def run_job(job, data):
    with WORK_LOCK:
        should_stop = lambda: get_job(job['id']).get('cancel_requested', False)
        def progress(values):
            job['progress'] = values
            save_job(job)
        if job_file(job['id']).exists() and should_stop():
            job['status'] = 'cancelled'; job['finished'] = time.time(); save_job(job); return
        job['status'] = 'running'; save_job(job)
        try:
            if should_stop(): raise o.OperationCancelled('The task was stopped before later steps began')
            if job['kind'] == 'search':
                run_id = 'search-' + job['id']
                p = location('runs', run_id)
                queries, args = search_args(data, p)
                args.should_stop = should_stop
                args.progress = progress
                job['run_id'] = run_id; save_job(job)
                if len(queries) > 1:
                    qfile = location('jobs', job['id'] + '-queries.txt')
                    qfile.write_text('\n'.join(queries), encoding='utf-8'); qfile.chmod(0o600)
                    args.queries_file = str(qfile)
                result = o.search(args)
                o.save_json(p / 'meta.json', {'title': ' / '.join(queries)[:200], 'created': job['created'], 'source': 'EasyKOL'})
                job['result'] = {'run_id': run_id, **result}
            elif job['kind'] == 'send':
                p = location('campaigns', data['campaign_id'] + '.json')
                job['result'] = o.send(NS(campaign=str(p), execute=True, campaign_id=data['campaign_id'],
                                         max_messages=int(data.get('max_messages', 20)), delay=2, should_stop=should_stop, progress=progress))
            elif job['kind'] in ('emails', 'emails-resume'):
                if job['kind'] == 'emails-resume':
                    original = get_job(data['source_job_id'])
                    source_run_id = original['source_run_id']
                    task_id = original['provider_task_id']
                    job['resumes_job_id'] = original['id']
                else:
                    source_run_id = data['run_id']
                    job['source_run_id'] = source_run_id; save_job(job)
                    p = location('runs', source_run_id) / 'creators.csv'
                    job['result'] = o.emails_start(NS(csv=str(p), budget=int(data.get('budget', 20))))
                    task = job['result']['task']
                    task_id = task.get('taskId') or task.get('id')
                    if not task_id: raise ValueError('The provider did not return a task ID. Do not create a duplicate; review the account task list.')
                p = location('runs', source_run_id) / 'creators.csv'
                job['source_run_id'] = source_run_id
                job['provider_task_id'] = task_id; save_job(job)
                out = location('runs', 'emails-' + job['id'])
                for _ in range(45):
                    if should_stop(): raise o.OperationCancelled('Status polling stopped, but the provider task may still be running. Keep the task ID to resume later.')
                    time.sleep(4)
                    result = o.emails_collect(NS(task_id=task_id, csv=str(p), out=str(out)))
                    if result['status'] in ('FAILED', 'CANCELLED'): raise ValueError('The provider email task did not finish successfully; the raw response was saved')
                    if result['status'] == 'COMPLETED':
                        job['result'] = {**result, 'run_id': out.name}
                        o.save_json(out / 'meta.json', {'title': 'Email enrichment · ' + source_run_id, 'created': job['created'], 'source': 'EasyKOL email lookup'})
                        break
                else:
                    raise ValueError('The provider is still processing the email task. Resume it with the saved task ID instead of paying to create another one.')
            job['status'] = 'completed'
            if job['kind'] == 'send' and job['result'].get('failed_or_unknown'):
                job['status'] = 'completed_with_errors'
                job['error'] = 'This batch stopped after a failure or uncertain result. Review the delivery history before attempting any further action.'
        except Exception as e:
            job['status'] = 'cancelled' if isinstance(e, o.OperationCancelled) else 'failed'
            job['error'] = str(e) if isinstance(e, ValueError) else 'The task failed. Review the saved results and delivery history before deciding what to do next.'
        finally:
            job['finished'] = time.time(); save_job(job)

def create_campaign(data):
    run = get_run(data.get('run_id'))
    selected = data.get('selected_emails')
    if not isinstance(selected, list) or not selected: raise ValueError('Select at least one recipient')
    selected = {o.valid_email(x) for x in selected}
    rows = [r for r in run['contacts'] if r.get('email', '').lower() in selected]
    if {r['email'].lower() for r in rows} != selected: raise ValueError('One or more selected recipients do not belong to this contact list')
    subject, body = str(data.get('subject', '')), str(data.get('body', ''))
    if len(subject) > 500 or len(body) > 100000: raise ValueError('The email subject or body is too long')
    root = o.ROOT / 'campaigns'; root.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = root / ('draft-' + uuid.uuid4().hex)
    temp.mkdir(mode=0o700)
    try:
        o.csv_write(temp / 'contacts.csv', rows)
        (temp / 'body.txt').write_text(body, encoding='utf-8'); (temp / 'body.txt').chmod(0o600)
        result = o.draft(NS(csv=str(temp / 'contacts.csv'), subject=subject, body=str(temp / 'body.txt'), out=str(temp / 'campaign.json')))
        cid = result['campaign_id']
        saved_campaign = read_json(temp / 'campaign.json')
        saved_campaign['source_run_id'] = run['id']
        o.save_json(temp / 'campaign.json', saved_campaign)
        target = root / (cid + '.json')
        if not target.exists(): (temp / 'campaign.json').replace(target)
        result['campaign_file'] = str(target)
        return result
    finally:
        for f in temp.iterdir(): f.unlink()
        temp.rmdir()

def update_campaign_message(data):
    """Save one recipient's edits as a new, unsent campaign revision."""
    campaign_id = identifier(str(data.get('campaign_id', '')))
    campaign_path = location('campaigns', campaign_id + '.json')
    campaign = o.load_campaign(campaign_path)

    with o.db_open() as db:
        already_started = db.execute(
            'SELECT 1 FROM deliveries WHERE campaign=? LIMIT 1',
            (campaign_id,)
        ).fetchone()
    if already_started:
        raise ValueError('This campaign has already started sending and cannot be edited; create a new campaign instead')

    recipient = o.valid_email(data.get('email'))
    subject = str(data.get('subject', '')).strip()
    body = str(data.get('body', '')).strip()
    if not subject or not body:
        raise ValueError('The email subject and body are required')
    if '\n' in subject or '\r' in subject:
        raise ValueError('The email subject cannot contain a line break')
    if len(subject) > 500 or len(body) > 100000:
        raise ValueError('The email subject or body is too long')

    found = False
    messages = []
    for item in campaign['messages']:
        updated = dict(item)
        if o.valid_email(item['to']) == recipient:
            updated['subject'] = subject
            updated['body'] = body
            found = True
        messages.append(updated)
    if not found:
        raise ValueError('This recipient does not belong to the current campaign')

    revised = {'sender': campaign['sender'], 'messages': messages, 'replaces': campaign_id}
    if campaign.get('source_run_id'):
        revised['source_run_id'] = campaign['source_run_id']
    revised['id'] = o.campaign_hash(revised)
    revised_path = location('campaigns', revised['id'] + '.json')
    if revised['id'] != campaign_id:
        if revised_path.exists():
            existing = o.load_campaign(revised_path)
            if existing['sender'] != revised['sender'] or existing['messages'] != revised['messages']:
                raise ValueError('The new draft ID conflicts with an existing draft; try again')
        else:
            o.save_json(revised_path, revised)
        campaign['superseded_by'] = revised['id']
        o.save_json(campaign_path, campaign)
    else:
        revised_path = campaign_path
        revised = campaign

    return {'message': 'This email was saved in a new draft; nothing was sent',
            'campaign_id': revised['id'], 'campaign_file': str(revised_path),
            'campaign': revised}

def personalize_contact(data):
    """Generate three grounded opening options for one creator; never sends email."""
    from personalization import personalize
    run = get_run(data.get('run_id'))
    recipient = o.valid_email(data.get('email'))
    creator = next((row for row in run['contacts']
                    if str(row.get('email', '')).lower() == recipient), None)
    if not creator:
        raise ValueError('This creator does not belong to the current contact list')
    return personalize(creator, data)

def list_campaigns():
    root = o.ROOT / 'campaigns'
    result = []
    for p in sorted(root.glob('*.json'), key=lambda x: x.stat().st_mtime, reverse=True):
        c = read_json(p)
        if c.get('superseded_by'):
            continue
        result.append({'id': p.stem, 'subject': c['messages'][0]['subject'],
                       'recipients': len(c['messages']), 'created': p.stat().st_mtime,
                       'path': str(p)})
    return result

def template_root():
    p = o.ROOT / 'templates'; p.mkdir(parents=True, exist_ok=True, mode=0o700); return p

def list_templates():
    result=[]
    for p in sorted(template_root().glob('*.json'), key=lambda x:x.stat().st_mtime, reverse=True):
        try:
            c=read_json(p); result.append({'id':p.stem,'name':c['name'],'subject':c['subject'],'body':c['body'],'updated':p.stat().st_mtime})
        except (OSError,KeyError,TypeError): continue
    return result

def save_template(data):
    name=str(data.get('name','')).strip(); subject=str(data.get('subject','')); body=str(data.get('body',''))
    if not 1 <= len(name) <= 100 or not subject.strip() or not body.strip(): raise ValueError('The template name, subject, and body are required')
    if len(subject)>500 or len(body)>100000 or '\n' in name or '\r' in name: raise ValueError('The template is too long or its name is invalid')
    tid='tpl-'+hashlib.sha256(name.encode()).hexdigest()[:16]
    o.save_json(template_root()/(tid+'.json'),{'id':tid,'name':name,'subject':subject,'body':body,'updated':time.time()})
    return {'id':tid,'name':name,'subject':subject,'body':body}
