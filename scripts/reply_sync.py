"""Consent-gated, read-only Gmail reply matching. No mail sending or AI calls."""
import base64
import urllib.parse
import google_mail
import email
from email import policy
from email.parser import BytesParser
from email.utils import getaddresses, parsedate_to_datetime
import hashlib
import imaplib
import json
import os
import re
import ssl
import threading
import time

import outreach as o
import workspace as w
import engagement as e
import reply_content

CONSENT_VERSION = 1
STATE_LOCK = threading.RLock()
SYNC_LOCK = threading.Lock()
RUNNING = False
MAX_MESSAGE_BYTES = 1_000_000


def credentials():
    cfg = o.load_config()
    account = cfg.get('sender', '').strip().lower()
    if cfg.get('mail_transport') == 'google':
        return account, google_mail.load().get('connection_id', '') if google_mail.connected(google_mail.READ) else ''
    if cfg.get('mail_transport') == 'disconnected': return account, ''
    password = os.environ.get('GMAIL_APP_PASSWORD') or cfg.get('gmail_app_password', '')
    return account, password.replace(' ', '')


def identity():
    account, password = credentials()
    return hashlib.sha256((account+'|'+password).encode()).hexdigest()


def load():
    path = o.ROOT/'reply-sync.json'
    return json.loads(path.read_text()) if path.exists() else {}


def authorized(state=None):
    state = state if state is not None else load()
    account, password = credentials()
    return bool(account and password and state.get('enabled') and state.get('identity') == identity()
                and state.get('consent_version') == CONSENT_VERSION)


def status():
    with STATE_LOCK:
        state = load()
        account, password = credentials()
        current = state.get('identity') == identity()
        allowed = authorized(state)
        return {'account': account, 'configured': bool(account and password), 'authorized': allowed,
                'consent_version': CONSENT_VERSION, 'prompt_needed': bool(account and password and not current),
                'syncing': bool(RUNNING and allowed), 'last_checked': state.get('last_checked') if current else None,
                'last_error': state.get('last_error', '') if current else '',
                'last_result': state.get('last_result') if current else None}


def consent(data):
    if type(data.get('allow')) is not bool:
        raise ValueError('Choose whether to allow reply tracking')
    if data.get('allow') and data.get('consent_version') != CONSENT_VERSION:
        raise ValueError('Review the current reply tracking permission first')
    account, password = credentials()
    if data['allow'] and not (account and password):
        raise ValueError('Connect Google with reply access, or configure a Gmail app password in Account Setup first')
    with STATE_LOCK:
        state = load()
        if state.get('identity') != identity(): state = {}
        state.update(enabled=data['allow'], identity=identity(), account=account,
                     consent_version=CONSENT_VERSION, consented_at=time.time())
        state['last_error'] = ''
        o.save_json(o.ROOT/'reply-sync.json', state)
    return status()


def require_consent(expected=None):
    if not authorized() or (expected and identity() != expected):
        raise ValueError('Reply tracking permission is required for the current Gmail account')


def sent_messages():
    account, _ = credentials()
    if not (o.ROOT/'outreach.sqlite').exists(): return [], 0
    with o.db_open() as db:
        rows = db.execute("SELECT campaign,email,message_id,updated FROM deliveries WHERE status IN ('accepted_by_smtp','accepted_by_gmail_api','sent_browser') ORDER BY updated DESC").fetchall()
    result, missing = [], 0
    for cid, recipient, mid, stamp in rows:
        path = w.location('campaigns', cid+'.json')
        if not path.exists(): continue
        campaign = w.read_json(path)
        if campaign.get('sender', '').lower() != account: continue
        if not re.fullmatch(r'<[^<>\s]{1,450}>', mid or ''):
            missing += 1; continue
        result.append({'campaign_id':cid, 'email':recipient.lower(), 'message_id':mid,
                       'run_id':campaign.get('source_run_id'), 'sent_at':stamp})
    return result, missing


def literal(data):
    return next((part[1] for part in data or [] if isinstance(part, tuple) and isinstance(part[1], bytes)), b'')


def select_mailbox(client):
    # Gmail's special-use flag is independent of the user's folder language.
    response, lines = client.list()
    if response == 'OK':
        for line in lines or []:
            if not isinstance(line, bytes): continue
            match = re.match(rb'\(([^)]*)\)\s+(?:"[^"]*"|NIL)\s+(.+)$', line)
            if match and set(match[1].upper().split()) & {b'\\ALL', b'\\ALLMAIL'}:
                folder = match[2].decode('ascii')
                if client.select(folder, readonly=True)[0] == 'OK': return 'Inbox and archived mail'
    if client.select('INBOX', readonly=True)[0] != 'OK':
        raise ValueError('Gmail could not open a read-only mailbox')
    return 'Inbox only'


def match_reply(message, index):
    senders = {address.lower() for _, address in getaddresses(message.get_all('From', []))}
    refs = re.findall(r'<[^<>\s]+>', str(message.get('In-Reply-To', '')))
    refs += list(reversed(re.findall(r'<[^<>\s]+>', str(message.get('References', '')))))
    for mid in refs:
        original = index.get(mid)
        if original and original['email'] in senders:
            return original
    return None



def reply_text(message):
    part = message.get_body(preferencelist=('plain','html'))
    if part is None: return 'Reply received. Open Gmail to view the message.'
    try: body = part.get_content()
    except (LookupError, UnicodeError): body = (part.get_payload(decode=True) or b'').decode('utf-8','replace')
    if not isinstance(body, str): return 'Reply received. Open Gmail to view the message.'
    if part.get_content_type() == 'text/html':
        parser=reply_content.ReplyHTML();parser.feed(body);body=parser.result()
    return reply_content.clean_reply_text(body)[:20000] or 'Reply received. Open Gmail to view the message.'


def is_automatic(message):
    auto = str(message.get('Auto-Submitted','')).strip().lower()
    return bool((auto and auto != 'no') or str(message.get('Precedence','')).lower() in ('bulk','list','junk')
                or message.get_content_type() == 'multipart/report')


def import_reply(original, message, body):
    mid = str(message.get('Message-ID', '')).strip()
    if not mid or len(mid)>500: return False, False
    external_id = hashlib.sha256((credentials()[0]+'|'+mid).encode()).hexdigest()
    auto = is_automatic(message)
    category = 'automatic' if auto else e.classify_reply(body)
    human = category != 'automatic'
    try: created = parsedate_to_datetime(str(message.get('Date'))).timestamp()
    except (ValueError, TypeError, OverflowError): created=time.time()
    if not 0 < created <= time.time()+86400: created=time.time()
    added = False
    with e.LOCK:
        state = e.load()
        run_id = original.get('run_id')
        try:
            run = w.get_run(run_id)
            creator = next(c for c in run['contacts'] if c.get('email','').lower()==original['email'])
        except (ValueError, OSError, StopIteration):
            run = {'id':original['campaign_id'],'title':'Sent campaign'}
            creator = {'name':original['email'],'email':original['email']}
        key = e.key_for(run['id'],creator)
        record = state['records'].get(key) or e.blank_record(run,creator,key)
        if not any(r.get('external_id')==external_id for r in record['replies']):
            record['replies'].append({'id':external_id[:32], 'external_id':external_id, 'body':body,
                'category':category,'source':'Gmail sync','created':created,'subject':str(message.get('Subject',''))[:500]})
            if category in ('declined','unsubscribe'): record['stage']='closed'
            elif human and record['stage'] not in ('closed','partnered','negotiating'): record['stage']='replied'
            if category=='unsubscribe':
                with o.db_open() as db: db.execute('INSERT OR IGNORE INTO suppressed VALUES (?)',(original['email'],))
            if human:
                for todo in record['todos']:
                    if todo['kind']=='followup' and todo['status']=='pending':todo.update(status='paused',pause_reason='A Gmail reply was received. Review the conversation first.')
                if category not in ('declined','unsubscribe'):
                    record['todos'].append({'id':external_id[:32], 'kind':'reply','title':'Review the Gmail reply',
                        'status':'pending','due_at':time.time()+86400,'created':time.time(),'subject':'','body':''})
            record['updated']=time.time();state['records'][key]=record;e.write(state);added=True
    # This is idempotent even if an earlier sync stopped after saving the reply text.
    if human: o.record_tracking(original['campaign_id'], original['email'], 'reply')
    return added, human


def sync_once():
    expected = identity(); require_consent(expected)
    originals, missing = sent_messages()
    result = {'new_replies':0,'human_replies':0,'automatic_replies':0,'checked_messages':len(originals),
              'missing_message_ids':missing,'coverage':'No sent messages to check'}
    if not originals: return result
    # Keep scans bounded and report when older messages need another view/workspace.
    result['older_messages_not_scanned']=max(0,len(originals)-300)
    originals=originals[:300];result['checked_messages']=len(originals); index={row['message_id']:row for row in originals}
    if o.load_config().get('mail_transport') == 'google':
        return sync_google(originals, index, expected, result)
    account, password=credentials(); client=None; candidates=set()
    try:
        require_consent(expected)
        client=imaplib.IMAP4_SSL('imap.gmail.com',993,ssl_context=ssl.create_default_context(),timeout=20)
        client.login(account,password);require_consent(expected)
        result['coverage']=select_mailbox(client)
        for row in originals:
            require_consent(expected)
            # Request only messages that cite an exact outgoing Message-ID.
            typ, data=client.uid('SEARCH',None,'OR','HEADER','In-Reply-To','"'+row['message_id']+'"','HEADER','References','"'+row['message_id']+'"')
            if typ!='OK':raise ValueError('Gmail could not search for related replies. Try syncing again later.')
            for uid in (data[0] or b'').split():
                if re.fullmatch(rb'\d+',uid): candidates.add(uid)
        if len(candidates)>1000: raise ValueError('This mailbox has too many related replies for one scan. Contact support to narrow the scan.')
        with STATE_LOCK: seen=set(load().get('seen',[]))
        for uid in sorted(candidates,key=int):
            require_consent(expected)
            typ,data=client.uid('FETCH',uid,'(RFC822.SIZE BODY.PEEK[HEADER.FIELDS (FROM IN-REPLY-TO REFERENCES MESSAGE-ID DATE SUBJECT AUTO-SUBMITTED PRECEDENCE CONTENT-TYPE)])')
            if typ!='OK':raise ValueError('Gmail could not read a related message header. Try syncing again later.')
            headers=BytesParser(policy=policy.default).parsebytes(literal(data));original=match_reply(headers,index)
            if not original:continue
            mid=str(headers.get('Message-ID','')).strip()
            if not mid:continue
            dedup=hashlib.sha256((account+'|'+mid).encode()).hexdigest()
            if dedup in seen:continue
            metadata=b' '.join(p[0] for p in data if isinstance(p,tuple))
            size=re.search(rb'RFC822.SIZE (\d+)',metadata)
            if not size:raise ValueError('Gmail did not report the reply size. No message body was downloaded.')
            if int(size[1])>MAX_MESSAGE_BYTES:
                body='Reply received. This message is too large to preview; open Gmail to read it.';message=headers
            else:
                require_consent(expected)
                typ,parts=client.uid('FETCH',uid,'(BODY.PEEK[])')
                if typ!='OK':raise ValueError('Gmail could not read a matching reply. Try syncing again later.')
                raw=literal(parts)
                if len(raw)>MAX_MESSAGE_BYTES:raise ValueError('The reply is too large to preview.')
                message=BytesParser(policy=policy.default).parsebytes(raw)
                if not match_reply(message,index):continue
                body=reply_text(message)
            with STATE_LOCK:
                require_consent(expected)
                added,human=import_reply(original,message,body)
                state=load();seen.add(dedup);state['seen']=sorted(seen);o.save_json(o.ROOT/'reply-sync.json',state)
            if added:
                result['new_replies']+=1;result['human_replies' if human else 'automatic_replies']+=1
        return result
    except imaplib.IMAP4.error:
        raise ValueError('Gmail refused mailbox access. Check the saved Gmail app password or your account administrator settings.') from None
    except (OSError, TimeoutError):
        raise ValueError('Could not connect to Gmail. Check your connection and try Sync now again.') from None
    finally:
        if client:
            try:client.logout()
            except (OSError,imaplib.IMAP4.error):pass


def _worker():
    global RUNNING
    expected=identity()
    try:
        result=sync_once()
        with STATE_LOCK:
            if authorized() and identity()==expected:
                state=load();state.update(last_result=result,last_checked=time.time(),last_error='');o.save_json(o.ROOT/'reply-sync.json',state)
    except Exception as error:
        with STATE_LOCK:
            if authorized() and identity()==expected:
                state=load();state['last_error']=str(error) if isinstance(error,ValueError) else 'Reply sync could not finish. Try again later.';o.save_json(o.ROOT/'reply-sync.json',state)
    finally:
        with STATE_LOCK:RUNNING=False
        SYNC_LOCK.release()


def start_sync():
    global RUNNING
    with STATE_LOCK:
        require_consent()
        if SYNC_LOCK.acquire(blocking=False):
            RUNNING=True
            state=load();state['last_error']='';o.save_json(o.ROOT/'reply-sync.json',state)
            threading.Thread(target=_worker,daemon=True).start()
    return status()


def sync_google(originals, index, expected, result):
    """Search by correspondent/date; verify exact RFC Message-ID before reading body."""
    candidates = set()
    for row in originals:
        page = None
        while True:
            require_consent(expected)
            params = {'q': 'from:'+row['email']+' after:'+str(max(0,int(row['sent_at'])-86400)),
                      'maxResults': 100, 'includeSpamTrash': 'true'}
            if page: params['pageToken'] = page
            response = google_mail.api('messages?'+urllib.parse.urlencode(params))
            candidates.update(item['id'] for item in response.get('messages', []))
            if len(candidates)>1000: raise ValueError('Too many related messages for one scan. Narrow the campaign before syncing.')
            page = response.get('nextPageToken')
            if not page: break
    result['coverage'] = 'Gmail including spam and trash; exact reply references only'
    for mid in candidates:
        require_consent(expected)
        path = 'messages/'+urllib.parse.quote(mid, safe='')
        meta = google_mail.api(path+'?format=metadata')
        message = email.message.EmailMessage(policy=policy.default)
        for header in meta.get('payload', {}).get('headers', []):
            if header['name'].lower() in ('from','in-reply-to','references','message-id','date','subject','auto-submitted','precedence','content-type'):
                message[header['name']] = header['value']
        original = match_reply(message, index)
        if not original: continue
        dedup = hashlib.sha256((credentials()[0]+'|'+str(message.get('Message-ID','')).strip()).encode()).hexdigest()
        with STATE_LOCK:
            if dedup in load().get('seen', []): continue
        if meta.get('sizeEstimate', MAX_MESSAGE_BYTES+1)>MAX_MESSAGE_BYTES:
            body = 'Reply received. This message is too large to preview; open Gmail to read it.'
        else:
            require_consent(expected)
            raw = google_mail.api(path+'?format=raw').get('raw', '')
            if len(raw)>MAX_MESSAGE_BYTES*2: raise ValueError('The reply is too large to preview.')
            decoded = base64.urlsafe_b64decode(raw+'='*(-len(raw)%4))
            if len(decoded)>MAX_MESSAGE_BYTES: raise ValueError('The reply is too large to preview.')
            message = BytesParser(policy=policy.default).parsebytes(decoded)
            if not match_reply(message,index): continue
            body = reply_text(message)
        with STATE_LOCK:
            require_consent(expected)
            added,human = import_reply(original,message,body)
            state = load(); state['seen'] = sorted(set(state.get('seen', [])) | {dedup}); o.save_json(o.ROOT/'reply-sync.json',state)
        if added:
            result['new_replies'] += 1
            result['human_replies' if human else 'automatic_replies'] += 1
    return result
