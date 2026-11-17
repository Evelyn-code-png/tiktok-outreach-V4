"""Outbound-only tracking client. Accesses only the application's own data directory.

The cloud receives opaque random IDs and HTTPS destinations, never recipients,
mail bodies, mailbox credentials, local paths, or an address for this computer.
"""
import html
import json
import os
import re
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

import outreach as o

LOCK = threading.RLock()
ID = re.compile(r'[A-Za-z0-9_-]{43}')
ORIGIN = re.compile(r'https://(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.workers\.dev|[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.pages\.dev)')
LINK = re.compile(r'https://[^\s<>"\x00-\x1f]+')


def origin(value):
    value = str(value or '').strip().rstrip('/')
    if not ORIGIN.fullmatch(value):
        raise ValueError('Use the exact HTTPS workers.dev or pages.dev address of your dedicated tracking service')
    return value


def load():
    path = o.ROOT / 'cloud-tracking.json'
    return json.loads(path.read_text()) if path.exists() else {}


def save(data):
    o.save_json(o.ROOT / 'cloud-tracking.json', data)
    os.chmod(o.ROOT / 'cloud-tracking.json', 0o600)


def configured():
    cfg = load()
    return bool(cfg.get('enabled') and cfg.get('verified') and
                ORIGIN.fullmatch(str(cfg.get('origin', ''))) and ID.fullmatch(str(cfg.get('token', ''))))


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def request(path, data=None, cfg=None):
    cfg = cfg or load()
    base = origin(cfg.get('origin'))
    token = cfg.get('token', '')
    if not ID.fullmatch(token):
        raise ValueError('A valid dedicated tracking access token is required')
    if path not in ('/v1/health', '/v1/register', '/v1/events'):
        raise ValueError('Unsupported tracking request')
    req = urllib.request.Request(base + path,
        data=None if data is None else json.dumps(data).encode(),
        headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json',
                 'User-Agent': 'OutreachV4-Tracking/1.0'})
    try:
        with urllib.request.build_opener(NoRedirect).open(req, timeout=15) as response:
            raw = response.read(65537)
            if len(raw) > 65536:
                raise ValueError('Tracking response is too large')
            result = json.loads(raw)
        if not isinstance(result, dict):
            raise ValueError('Invalid tracking response')
        return result
    except (OSError, ValueError, urllib.error.URLError):
        # Never include URLs, response bodies, or access tokens in a visible error.
        raise ValueError('Tracking service could not be reached or verified. No email was sent by this check.') from None


def status():
    cfg = load()
    return {'enabled': configured(), 'origin': cfg.get('origin', ''),
            'last_checked': cfg.get('last_checked'), 'error': cfg.get('error', '')}


def configure(data):
    if set(data) - {'origin', 'token', 'enabled'}:
        raise ValueError('Unsupported tracking setting')
    with LOCK:
        old = load()
        if data.get('enabled') is False:
            old['enabled'] = False
            save(old)
            return status()
        base = origin(data.get('origin'))
        token = str(data.get('token') or (old.get('token') if base == old.get('origin') else '') or '').strip()
        candidate = {'origin': base, 'token': token}
        result = request('/v1/health', cfg=candidate)
        if result.get('service') != 'outreach-tracking' or result.get('version') != 1:
            raise ValueError('This address is not the dedicated Outreach tracking service')
        save({**candidate, 'enabled': True, 'verified': True, 'last_checked': time.time(), 'error': ''})
        return status()


def public_destination(value):
    parsed = urllib.parse.urlsplit(value)
    host = (parsed.hostname or '').lower()
    if (parsed.scheme != 'https' or parsed.username or parsed.password or parsed.port or
            len(value) > 2048 or not host or '.' not in host or ':' in host or
            re.fullmatch(r'[\d.]+', host) or
            any(host == suffix or host.endswith(suffix) for suffix in
                ('localhost', '.localhost', '.local', '.internal', '.test', '.invalid'))):
        raise ValueError('Only public HTTPS destinations can be tracked')
    return value


def prepare(db, campaign, email, body):
    if not configured():
        return None
    cfg = load()
    base = origin(cfg['origin'])
    previous = db.execute('SELECT id,origin FROM cloud_tracking_messages WHERE campaign=? AND email=?',
                          (campaign, email)).fetchone()
    if previous and previous[1] != base:
        raise ValueError('This draft already belongs to a different tracking service. Make a new draft.')
    mid = previous[0] if previous else secrets.token_urlsafe(32)
    links, pieces, offset = [], [], 0
    for match in LINK.finditer(body):
        pieces.append(html.escape(body[offset:match.start()]))
        candidate = match.group().rstrip('.,;!?)')
        trailing = match.group()[len(candidate):]
        try:
            target = public_destination(candidate)
        except ValueError:
            pieces.append(html.escape(match.group()))
        else:
            if len(links) >= 50:
                raise ValueError('Tracking supports up to 50 links per email')
            lid = secrets.token_urlsafe(32)
            links.append({'id': lid, 'target': target})
            pieces.append('<a href="' + base + '/c/' + lid + '">' + html.escape(candidate) + '</a>' + html.escape(trailing))
        offset = match.end()
    pieces.append(html.escape(body[offset:]))
    result = request('/v1/register', {'id': mid, 'links': links}, cfg)
    if result.get('id') != mid:
        raise ValueError('Tracking registration was not confirmed; no email was sent')
    db.execute('INSERT OR IGNORE INTO cloud_tracking_messages(campaign,email,id,origin) VALUES(?,?,?,?)',
               (campaign, email, mid, base))
    return '<html><body>' + ''.join(pieces).replace('\n', '<br>') + '<img src="' + base + '/o/' + mid + '.gif" width="1" height="1" alt=""></body></html>'


def sync():
    with LOCK:
        if not configured():
            return status()
        cfg = load()
        try:
            with o.db_open() as db:
                rows = db.execute("SELECT t.id,t.campaign,t.email FROM cloud_tracking_messages t JOIN deliveries d ON t.campaign=d.campaign AND t.email=d.email WHERE t.origin=? AND d.status IN ('accepted_by_smtp','accepted_by_gmail_api')", (cfg['origin'],)).fetchall()
            count = 0
            for offset in range(0, len(rows), 100):
                selection = {r[0]: (r[1], r[2]) for r in rows[offset:offset + 100]}
                events = request('/v1/events', {'ids': list(selection)}, cfg).get('events')
                if not isinstance(events, list) or len(events) > 2 * len(selection):
                    raise ValueError('Invalid tracking events')
                checked = []
                for event in events:
                    if (not isinstance(event, dict) or set(event) != {'id', 'event', 'occurred'} or
                            event.get('id') not in selection or event.get('event') not in ('open', 'click') or
                            type(event.get('occurred')) is not int or not 0 < event['occurred'] <= time.time() + 300):
                        raise ValueError('Invalid tracking event')
                    checked.append((*selection[event['id']], event['event'], event['occurred']))
                with o.db_open() as db:
                    for row in checked:
                        db.execute('INSERT OR IGNORE INTO tracking_events VALUES(?,?,?,?)', row)
                count += len(checked)
            cfg.update(last_checked=time.time(), error='')
            save(cfg)
            return {**status(), 'events': count}
        except (OSError, ValueError):
            cfg['error'] = 'Tracking sync could not finish. Previously saved data is unchanged.'
            save(cfg)
            raise ValueError(cfg['error']) from None


def metrics(result, campaign=None):
    with o.db_open() as db:
        clause = ' AND t.campaign=?' if campaign else ''
        params = (campaign,) if campaign else ()
        joined = " FROM cloud_tracking_messages t JOIN deliveries d ON t.campaign=d.campaign AND t.email=d.email"
        accepted = " WHERE d.status IN ('accepted_by_smtp','accepted_by_gmail_api')" + clause
        sent = db.execute('SELECT COUNT(*)' + joined + accepted, params).fetchone()[0]
        counts = dict(db.execute('SELECT e.event,COUNT(*)' + joined +
            ' JOIN tracking_events e ON e.campaign=t.campaign AND e.email=t.email' +
            accepted + ' GROUP BY e.event', params).fetchall())
    result.update(tracked=configured() or sent > 0, tracked_sent=sent,
                  opened=counts.get('open', 0), clicked=counts.get('click', 0),
                  open_rate=round(counts.get('open', 0) / sent * 100, 1) if sent else None,
                  click_rate=round(counts.get('click', 0) / sent * 100, 1) if sent else None)
    return result
