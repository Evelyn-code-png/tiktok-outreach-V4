"""Desktop Google OAuth with PKCE; tokens never enter browser API responses."""
import base64
import hashlib
import json
import os
from pathlib import Path
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

import outreach as o

SEND = 'https://www.googleapis.com/auth/gmail.send'
READ = 'https://www.googleapis.com/auth/gmail.readonly'
EMAIL = 'https://www.googleapis.com/auth/userinfo.email'
LOCK = threading.RLock()
PENDING = {}


def client():
    path = os.environ.get('GOOGLE_OAUTH_CLIENT_FILE')
    local = o.ROOT / 'google-client.json'
    path = Path(path).expanduser() if path else local if local.exists() else Path(__file__).resolve().parents[1] / 'google-client.json'
    if not path.exists():
        raise ValueError('The team must install google-client.json (Google Desktop OAuth client) before Google connection is available.')
    cfg = json.loads(path.read_text()).get('installed', {})
    if not cfg.get('client_id'):
        raise ValueError('Use a Google Desktop app OAuth client JSON file.')
    return cfg


def load():
    path = o.ROOT / 'google-token.json'
    return json.loads(path.read_text()) if path.exists() else {}


def connected(scope=SEND):
    token = load()
    return bool(o.load_config().get('mail_transport') == 'google' and token.get('refresh_token') and scope in token.get('scope', '').split()
                and token.get('email') == o.load_config().get('sender', '').lower())


def status():
    try:
        client(); ready = True
    except (ValueError, OSError):
        ready = False
    token = load()
    return {'available': ready, 'has_connection': bool(token.get('refresh_token')), 'connected': connected(), 'read_connected': connected(READ),
            'account': token.get('email', '') if connected() else ''}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def request(url, *, token=None, form=None, body=None):
    headers = {}
    data = None
    if token: headers['Authorization'] = 'Bearer ' + token
    if form is not None:
        data = urllib.parse.urlencode(form).encode(); headers['Content-Type'] = 'application/x-www-form-urlencoded'
    if body is not None:
        data = json.dumps(body).encode(); headers['Content-Type'] = 'application/json'
    with urllib.request.build_opener(NoRedirect()).open(urllib.request.Request(url, data=data, headers=headers), timeout=40) as response:
        return json.load(response)


def begin(port, read=False):
    cfg = client()
    with LOCK:
        PENDING.clear()
        state = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(64)
        redirect = f'http://127.0.0.1:{port}/oauth/google/callback'
        scopes = [EMAIL, SEND] + ([READ] if read else [])
        PENDING[state] = {'expires': time.time()+600, 'verifier': verifier, 'redirect': redirect,
                          'scopes': scopes, 'client': cfg}
    params = {'client_id': cfg['client_id'], 'redirect_uri': redirect, 'response_type': 'code',
              'scope': ' '.join(scopes), 'state': state, 'access_type': 'offline', 'prompt': 'consent',
              'code_challenge_method': 'S256',
              'code_challenge': base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')}
    return {'url': 'https://accounts.google.com/o/oauth2/v2/auth?' + urllib.parse.urlencode(params)}


def finish(query):
    state = query.get('state', [''])[0]
    with LOCK:
        pending = PENDING.pop(state, None)
        if not pending or pending['expires'] < time.time():
            raise ValueError('Google connection expired or is invalid. Start again in Account Setup.')
        if query.get('error') or not query.get('code'):
            raise ValueError('Google connection was not approved. Your previous connection is unchanged.')
        cfg = pending['client']
        try:
            token = request('https://oauth2.googleapis.com/token', form={
                'client_id': cfg['client_id'], 'client_secret': cfg.get('client_secret', ''),
                'code': query['code'][0], 'code_verifier': pending['verifier'],
                'redirect_uri': pending['redirect'], 'grant_type': 'authorization_code'})
            if not set(pending['scopes']).issubset(set(token.get('scope', '').split())) or not token.get('refresh_token'):
                raise ValueError('Required Google permissions were not granted. Reconnect and approve the requested permissions.')
            profile = request('https://www.googleapis.com/oauth2/v2/userinfo', token=token['access_token'])
            if not profile.get('verified_email'):
                raise ValueError('Google did not return a verified email address.')
            token['email'] = o.valid_email(profile['email']).lower()
            token['expires_at'] = time.time()+int(token['expires_in'])
            token['connection_id'] = secrets.token_hex(16)
            token['client_id'] = cfg['client_id']
            o.private_dir()
            o.save_json(o.ROOT/'google-token.json', token)
            config = o.load_config(); config['sender'] = token['email']; config['mail_transport'] = 'google'; o.save_json(o.ROOT/'config.json', config)
        except (urllib.error.URLError, OSError, KeyError, TypeError):
            raise ValueError('Could not complete Google connection. Check the team OAuth configuration and try again.') from None
    return token['email']


def access(scope=SEND):
    with LOCK:
        if not connected(scope): raise ValueError('Connect Google with the required permission in Account Setup.')
        token = load()
        if token.get('expires_at', 0) > time.time()+60: return token['access_token']
        cfg = client()
        if token.get('client_id') != cfg['client_id']:
            raise ValueError('The Google app configuration changed. Reconnect Google.')
        try:
            fresh = request('https://oauth2.googleapis.com/token', form={
                'client_id': cfg['client_id'], 'client_secret': cfg.get('client_secret', ''),
                'refresh_token': token['refresh_token'], 'grant_type': 'refresh_token'})
            token.update(fresh); token['expires_at'] = time.time()+int(fresh['expires_in'])
            o.save_json(o.ROOT/'google-token.json', token)
        except (urllib.error.URLError, OSError, KeyError, TypeError):
            raise ValueError('Google access expired or was revoked. Reconnect Google in Account Setup.') from None
        return token['access_token']


def api(path, scope=READ, body=None):
    try:
        return request('https://gmail.googleapis.com/gmail/v1/users/me/' + path, token=access(scope), body=body)
    except urllib.error.HTTPError as error:
        if error.code in (401, 403): raise ValueError('Google mailbox access is unavailable. Reconnect with reply access in Account Setup.') from None
        if error.code == 429: raise ValueError('Google is rate-limiting mailbox checks. Try syncing later.') from None
        raise ValueError('Google could not complete the mailbox check. Try again later.') from None
    except (OSError, ValueError) as error:
        if isinstance(error, ValueError): raise
        raise ValueError('Could not connect to Google. Try syncing later.') from None


def disconnect():
    # A local disconnect never silently falls back to a saved SMTP password.
    with LOCK:
        PENDING.clear()
        path = o.ROOT/'google-token.json'
        if path.exists(): path.unlink()
        cfg = o.load_config(); cfg['mail_transport'] = 'disconnected'; o.save_json(o.ROOT/'config.json', cfg)
    return status()
