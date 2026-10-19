"""Local brand briefs and creator relationship tools. No network or email sending."""
import hashlib
import json
import math
import re
import threading
import time
import uuid

import outreach as o
import workspace as w
import reply_content

LOCK = threading.RLock()
STAGES = ('shortlisted', 'contacted', 'replied', 'negotiating', 'partnered', 'closed')
CATEGORIES = ('interested', 'pricing', 'question', 'declined', 'unsubscribe', 'automatic', 'other')
PRIORITIES = ('auto', 'high', 'normal', 'low')


def text(data, key, limit=2000, required=False):
    value = data.get(key, '')
    if not isinstance(value, str) or len(value) > limit:
        raise ValueError(f'{key.replace("_", " ").capitalize()} must be text, up to {limit} characters')
    value = value.strip()
    if required and not value:
        raise ValueError(f'{key.replace("_", " ").capitalize()} is required')
    return value


def load():
    path = o.ROOT / 'engagement.json'
    if not path.exists():
        return {'brands': [], 'contexts': {}, 'records': {}}
    with path.open(encoding='utf-8') as f:
        return json.load(f)


def write(state):
    o.save_json(o.ROOT / 'engagement.json', state)


def key_for(run_id, creator):
    identity = creator.get('email') or creator.get('profile_url') or creator.get('username') or creator.get('name')
    return hashlib.sha256((run_id + '|' + str(identity).lower()).encode()).hexdigest()[:24]


def resolve(data):
    run = w.get_run(data.get('run_id'))
    key = text(data, 'creator_key', 24, True)
    for creator in run['contacts']:
        if key_for(run['id'], creator) == key:
            return run, creator, key
    raise ValueError('This creator does not belong to the selected list')


def blank_record(run, creator, key):
    return {'key': key, 'run_id': run['id'], 'run_title': run['title'],
            'name': creator.get('name') or creator.get('username') or 'Unnamed creator',
            'email': creator.get('email', ''), 'profile_url': creator.get('profile_url', ''),
            'stage': 'shortlisted', 'priority': 'auto', 'notes': '', 'content_notes': '',
            'replies': [], 'todos': [], 'updated': time.time()}


def save_brand(data):
    brand = {field: text(data, field, limit, field in ('name', 'product')) for field, limit in
             [('name', 100), ('product', 1000), ('goal', 2000), ('offer', 1000),
              ('language', 100), ('regions', 100), ('content_keywords', 500), ('signature', 500)]}
    brand['content_keywords'] = brand['content_keywords'].lower()
    for field in ('min_followers', 'max_followers'):
        raw = data.get(field, '')
        if raw in ('', None):
            brand[field] = None
        else:
            try:
                number = int(raw)
                if str(raw).strip() != str(number) or number < 0 or number > 10**12:
                    raise ValueError
                brand[field] = number
            except (ValueError, TypeError, OverflowError):
                raise ValueError('Follower limits must be whole, non-negative numbers') from None
    if brand['min_followers'] is not None and brand['max_followers'] is not None and brand['max_followers'] < brand['min_followers']:
        raise ValueError('Maximum followers must be at least the minimum')
    if brand['regions'] and any(not re.fullmatch('[A-Za-z]{2}', r.strip()) for r in brand['regions'].split(',')):
        raise ValueError('Use two-letter target region codes, such as US,GB')
    brand['regions'] = brand['regions'].upper()
    brand['updated'] = time.time()
    with LOCK:
        state = load()
        bid = data.get('id') or 'brand-' + uuid.uuid4().hex[:12]
        w.identifier(bid)
        if data.get('id') and not any(b['id'] == bid for b in state['brands']):
            raise ValueError('The brand brief does not exist')
        brand['id'] = bid
        state['brands'] = [b for b in state['brands'] if b['id'] != bid] + [brand]
        write(state)
    return brand


def set_context(data):
    run = w.get_run(data.get('run_id'))
    bid = text(data, 'brand_id', 100)
    with LOCK:
        state = load()
        if bid and not any(b['id'] == bid for b in state['brands']):
            raise ValueError('The brand brief does not exist')
        state['contexts'][run['id']] = bid
        write(state)
    return {'brand_id': bid}


def matching(creator, record, brand):
    reasons, gaps, matches = [], [], 0
    criteria = 0
    if not brand:
        return {'label': 'Choose a brand brief', 'rank': 0, 'reasons': [],
                'gaps': ['Select a saved brand brief to compare creator data.'], 'suggested_priority': 'normal'}
    regions = [r.strip().upper() for r in brand.get('regions', '').split(',') if r.strip()]
    if regions:
        criteria += 1
        region = creator.get('region', '').upper()
        if region in regions:
            matches += 1; reasons.append('Region matches your target: ' + region)
        else:
            gaps.append('Region is unavailable.' if not region else 'Region is outside your target: ' + region)
    language = brand.get('language', '').strip().lower()
    lang_alias = {'english': 'en', 'spanish': 'es', 'french': 'fr', 'german': 'de', 'chinese': 'zh', 'japanese': 'ja', 'korean': 'ko', 'portuguese': 'pt'}
    if language:
        criteria += 1
        wanted = lang_alias.get(language, language)
        actual = str(creator.get('language', '')).lower()
        actuals = [lang_alias.get(v.strip(), v.strip()) for v in re.split('[,;/]', actual)]
        if wanted in actuals:
            matches += 1; reasons.append('Language matches your brief: ' + brand['language'])
        else:
            gaps.append('Language is unavailable.' if not actual else 'Language differs from your brief: ' + actual)
    low, high = brand.get('min_followers'), brand.get('max_followers')
    if low is not None or high is not None:
        criteria += 1
        try:
            n = float(creator.get('followers', ''))
            if not math.isfinite(n) or n < 0: raise ValueError
            if (low is None or n >= low) and (high is None or n <= high):
                matches += 1; reasons.append('Follower count is within your selected range.')
            else:
                gaps.append('Follower count is outside your selected range.')
        except (ValueError, TypeError):
            gaps.append('Follower count is unavailable.')
    gaps.append('Content alignment is evaluated by AI from EasyKOL profile data.')
    rank = matches / criteria if criteria else 0
    return {'label': 'Strong filter fit' if criteria and matches == criteria else 'Partial filter fit' if matches else 'Needs review',
            'rank': rank, 'reasons': reasons, 'gaps': gaps,
            'suggested_priority': 'high' if criteria >= 2 and matches == criteria else 'normal'}


def saved_delivery_data():
    """Read existing outcomes without triggering provider work or creating a database."""
    if not (o.ROOT / 'outreach.sqlite').exists():
        return {}, set(), set()
    with o.db_open() as db:
        rows = db.execute("SELECT email,status,updated FROM deliveries ORDER BY updated").fetchall()
        replied = {r[0] for r in db.execute("SELECT DISTINCT email FROM tracking_events WHERE event='reply'")}
        suppressed = {r[0] for r in db.execute('SELECT email FROM suppressed')}
    latest = {}
    for email, status, updated in rows:
        latest[email.lower()] = {'status': status, 'updated': updated}
    return latest, replied, suppressed


def stop_reason(record, replied, suppressed):
    if record.get('email', '').lower() in {x.lower() for x in suppressed}:
        return 'Recipient is on the suppression list.'
    if record.get('stage') in ('closed', 'partnered'):
        return 'Collaboration is closed or already partnered.'
    if any(r['category'] != 'automatic' for r in record['replies']):
        return 'A reply was recorded. Review it before any follow-up.'
    if record.get('email', '').lower() in {x.lower() for x in replied}:
        return 'A reply event was recorded. Review the conversation first.'
    return ''


def displayed_reply(reply):
    body=reply_content.clean_reply_text(reply['body']) or 'Reply received. Open Gmail to view the message.'
    result={**reply,'body':body}
    if reply.get('source')=='Gmail sync' and reply.get('category')!='automatic' and body!=reply['body']:
        result['category']=classify_reply(body)
    return result


def snapshot(run_id=None):
    with LOCK:
        state = load()
    latest, replied, suppressed = saved_delivery_data()
    replied |= {r.get('email', '').lower() for r in state['records'].values() if any(x['category'] != 'automatic' for x in r['replies'])}
    records = []
    for saved in state['records'].values():
        record = {**saved, 'todos': [dict(t) for t in saved['todos']]}
        record['replies']=[displayed_reply(reply) for reply in saved['replies']]
        record['followup_blocked'] = stop_reason(record, replied, suppressed)
        record['delivery'] = latest.get(record.get('email', '').lower())
        for todo in record['todos']:
            if todo['kind'] == 'followup' and todo['status'] == 'pending' and record['followup_blocked']:
                todo['status'] = 'paused'; todo['pause_reason'] = record['followup_blocked']
        records.append(record)
    result = {'brands': state['brands'], 'contexts': state['contexts'], 'records': records}
    if run_id:
        run = w.get_run(run_id)
        brand_id = state['contexts'].get(run_id, '')
        brand = next((b for b in state['brands'] if b['id'] == brand_id), None)
        result['creators'] = []
        import creator_fit
        fit_brief = creator_fit.resolve_brief(run, state)
        fit_results = creator_fit.summaries(run, fit_brief)
        for index, creator in enumerate(run['contacts']):
            key = key_for(run_id, creator)
            record = next((r for r in records if r['key'] == key), None) or blank_record(run, creator, key)
            record = dict(record)
            record['delivery'] = latest.get(record.get('email', '').lower())
            record['followup_blocked'] = stop_reason(record, replied, suppressed)
            # Existing delivery history informs the suggested stage, never invents a sent event.
            if key not in state['records'] and record['delivery'] and record['delivery']['status'] in ('accepted_by_smtp', 'accepted_by_gmail_api', 'sent_browser'):
                record['stage'] = 'contacted'
            if key not in state['records'] and record.get('email', '').lower() in replied:
                record['stage'] = 'replied'
            result['creators'].append({'key': key, 'record': record, 'match': matching(creator, record, fit_brief), 'ai_fit': fit_results[index]})
    return result


def classify_reply(body):
    rules = [('automatic', r'out of (?:the )?office|automatic reply|auto[- ]?reply|on vacation'),
             ('unsubscribe', r'\bunsubscribe\b|remove me|stop (?:emailing|contacting)|do not contact|don.t contact'),
             ('declined', r'not interested|no thanks|not a fit|decline|not available'),
             ('pricing', r'\brates?\b|\bpricing\b|\bbudget\b|\bfees?\b|\bquote\b|\$\s*\d'),
             ('interested', r'\binterested\b|love to|sounds good|happy to|let.s collaborate'),
             ('question', r'\?|more (?:info|details)|tell me more')]
    return next((category for category, pattern in rules if re.search(pattern, body, re.I)), 'other')


def mutate(data):
    run, creator, key = resolve(data)
    operation = text(data, 'operation', 30, True)
    with LOCK:
        state = load()
        record = state['records'].get(key) or blank_record(run, creator, key)
        if operation == 'details':
            stage = data.get('stage', record['stage'])
            priority = data.get('priority', record['priority'])
            if stage not in STAGES or priority not in PRIORITIES:
                raise ValueError('Choose a valid stage and priority')
            record.update(stage=stage, priority=priority, notes=text(data, 'notes', 5000),
                          content_notes=text(data, 'content_notes', 5000) if 'content_notes' in data else record.get('content_notes', ''))
        elif operation == 'reply':
            body = text(data, 'body', 20000, True)
            category = data.get('category') or classify_reply(body)
            if category not in CATEGORIES: raise ValueError('Choose a valid reply category')
            reply = {'id': uuid.uuid4().hex, 'body': body, 'category': category,
                     'source': 'Manually recorded', 'created': time.time()}
            record['replies'].append(reply)
            if category == 'unsubscribe':
                if record.get('email'):
                    with o.db_open() as db:
                        db.execute('INSERT OR IGNORE INTO suppressed VALUES (?)', (record['email'].lower(),))
            if category in ('declined', 'unsubscribe'):
                record['stage'] = 'closed'
            elif category != 'automatic':
                record['stage'] = 'replied'
            if category not in ('automatic', 'unsubscribe', 'declined'):
                title = {'pricing': 'Review pricing and prepare a response', 'interested': 'Discuss the next collaboration step',
                         'question': 'Answer the creator question'}.get(category, 'Review the creator reply')
                record['todos'].append({'id': uuid.uuid4().hex, 'title': title, 'kind': 'reply',
                    'status': 'pending', 'due_at': time.time() + 86400, 'created': time.time(), 'subject': '', 'body': ''})
        elif operation == 'followup':
            _, replied, suppressed = saved_delivery_data()
            replied |= {r.get('email', '').lower() for r in state['records'].values() if any(x['category'] != 'automatic' for x in r['replies'])}
            reason = stop_reason(record, replied, suppressed)
            if reason: raise ValueError(reason)
            if not creator.get('email'): raise ValueError('Add a creator contact email before planning an email follow-up')
            try:
                due = float(data.get('due_at'))
                if not math.isfinite(due) or not 0 < due < 4102444800: raise ValueError
            except (ValueError, TypeError, OverflowError):
                raise ValueError('Choose a valid reminder date') from None
            subject, body = text(data, 'subject', 500, True), text(data, 'body', 20000, True)
            if '\n' in subject or '\r' in subject: raise ValueError('The subject must be a single line')
            record['todos'].append({'id': uuid.uuid4().hex, 'title': 'Review and send follow-up draft',
                'kind': 'followup', 'status': 'pending', 'due_at': due, 'subject': subject, 'body': body,
                'created': time.time()})
        elif operation == 'complete':
            todo = next((t for t in record['todos'] if t['id'] == data.get('todo_id')), None)
            if not todo: raise ValueError('This to-do no longer exists')
            todo['status'] = 'completed'
        else:
            raise ValueError('Unknown relationship operation')
        _, replied, suppressed = saved_delivery_data()
        replied |= {r.get('email', '').lower() for r in state['records'].values() if any(x['category'] != 'automatic' for x in r['replies'])}
        reason = stop_reason(record, replied, suppressed)
        if reason:
            for todo in record['todos']:
                if todo['kind'] == 'followup' and todo['status'] == 'pending':
                    todo.update(status='paused', pause_reason=reason)
        record['updated'] = time.time()
        state['records'][key] = record
        write(state)
    return snapshot(run['id'])
