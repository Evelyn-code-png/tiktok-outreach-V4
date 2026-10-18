#!/usr/bin/env python3
"""Private, loopback-only dashboard for the outreach plugin."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import socketserver
import threading
from types import SimpleNamespace as NS
from urllib.parse import urlparse, parse_qs
import webbrowser
import urllib.request
import base64

import outreach as o
import workspace as w
import engagement as engagement
import creator_fit
import reply_sync

ASSETS = Path(__file__).resolve().parents[1] / 'assets'
LOCK = threading.Lock()

class LocalServer(ThreadingHTTPServer):
    def server_bind(self):
        # Avoid reverse DNS for a strictly loopback service (can stall on macOS).
        socketserver.TCPServer.server_bind(self)
        self.server_name = '127.0.0.1'
        self.server_port = self.server_address[1]

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # Never put request bodies, credentials or browser tokens in logs.

    def respond(self, status, body, content_type='application/json; charset=utf-8'):
        payload = json.dumps(body, ensure_ascii=False).encode() if isinstance(body, (dict, list)) else body
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        self.end_headers()
        self.wfile.write(payload)

    def authorized(self):
        host = f'127.0.0.1:{self.server.server_port}'
        if self.headers.get('Host') != host:
            return False
        origin = self.headers.get('Origin')
        if origin and origin != 'http://' + host:
            return False
        try: return secrets.compare_digest(self.headers.get('X-Outreach-Token', ''), self.server.token)
        except TypeError: return False

    def do_GET(self):
        host = f'127.0.0.1:{self.server.server_port}'
        if self.headers.get('Host') != host:
            return self.respond(403, {'error': 'Invalid host'})
        path = urlparse(self.path).path
        if path.startswith('/t/open/') and path.endswith('.gif'):
            parts=path.removeprefix('/t/open/').removesuffix('.gif').split('/',1)
            if len(parts)==2:
                cid,token=parts
                try:
                    c=o.load_campaign(w.location('campaigns',cid+'.json'))
                    for m in c['messages']:
                        if o.tracking_token(cid,m['to'])==token:o.record_tracking(cid,m['to'],'open');break
                except Exception: pass
            pixel=base64.b64decode('R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==')
            return self.respond(200,pixel,'image/gif')
        if path.startswith('/t/click/'):
            parts=path.removeprefix('/t/click/').split('/',1); query=parse_qs(urlparse(self.path).query)
            if len(parts)==2 and query.get('url'):
                cid,token=parts
                try:
                    c=o.load_campaign(w.location('campaigns',cid+'.json'))
                    for m in c['messages']:
                        if o.tracking_token(cid,m['to'])==token:
                            target=query['url'][0]; parsed=urlparse(target)
                            if parsed.scheme not in ('http','https'): raise ValueError
                            o.record_tracking(cid,m['to'],'click'); self.send_response(302);self.send_header('Location',target);self.end_headers();return
                except Exception: pass
            return self.respond(404,{'error':'tracking link invalid'})
        if path in ('/engagement.js', '/engagement.css', '/send-feedback.js', '/reply-sync.js'):
            mime = 'text/javascript; charset=utf-8' if path.endswith('.js') else 'text/css; charset=utf-8'
            return self.respond(200, (ASSETS / path[1:]).read_bytes(), mime)
        if path in ('/', '/app.js', '/app.css', '/after-state.js', '/team-meeting-collaboration.svg', '/single-user-workspace.png',
                    '/fragmented-to-connected.png', '/target-users.png', '/business-impact.png'):
            name = {'/': 'index.html', '/app.js': 'app.js', '/after-state.js': 'after-state.js', '/app.css': 'app.css',
                    '/team-meeting-collaboration.svg': 'team-meeting-collaboration.svg',
                    '/single-user-workspace.png': 'single-user-workspace.png',
                    '/fragmented-to-connected.png': 'fragmented-to-connected.png',
                    '/target-users.png': 'target-users.png',
                    '/business-impact.png': 'business-impact.png'}[path]
            mime = {'/': 'text/html; charset=utf-8', '/app.js': 'text/javascript; charset=utf-8', '/after-state.js': 'text/javascript; charset=utf-8',
                    '/app.css': 'text/css; charset=utf-8',
                    '/team-meeting-collaboration.svg': 'image/svg+xml',
                    '/single-user-workspace.png': 'image/png',
                    '/fragmented-to-connected.png': 'image/png',
                    '/target-users.png': 'image/png',
                    '/business-impact.png': 'image/png'}[path]
            return self.respond(200, (ASSETS / name).read_bytes(), mime)
        if not self.authorized():
            return self.respond(403, {'error': 'Open the workspace through the local launcher'})
        if path == '/api/status':
            result = o.doctor(NS(online=False))
            result['easykol_email'] = o.load_config().get('easykol_email', '')
            result['tracking_configured'] = bool(o.load_config().get('tracking_base_url'))
            result['ai_configured'] = bool((o.load_config().get('openai_key') or os.environ.get('OPENAI_API_KEY'))
                                           and (o.load_config().get('openai_model') or os.environ.get('OPENAI_MODEL')))
            return self.respond(200, result)
        if path == '/api/history':
            query = parse_qs(urlparse(self.path).query)
            try:
                args = NS(limit=int(query.get('limit', ['100'])[0]), offset=int(query.get('offset', ['0'])[0]),
                          campaign_id=query.get('campaign_id', [None])[0], email=query.get('email', [None])[0])
                return self.respond(200, o.history(args))
            except ValueError as e: return self.respond(400, {'error': str(e)})
        if path == '/api/mail/status': return self.respond(200, reply_sync.status())
        if path == '/api/send-status':
            try: return self.respond(200, {'job': w.latest_send_job(parse_qs(urlparse(self.path).query).get('campaign_id', [''])[0])})
            except (ValueError, OSError): return self.respond(400, {'error': 'Choose a valid saved campaign'})
        if path == '/api/runs': return self.respond(200, {'runs': w.list_runs()})
        if path == '/api/jobs': return self.respond(200, {'jobs': w.recent_jobs()})
        if path == '/api/campaigns': return self.respond(200, {'campaigns': w.list_campaigns()})
        if path == '/api/templates': return self.respond(200, {'templates': w.list_templates()})
        if path == '/api/metrics':
            query=parse_qs(urlparse(self.path).query); result=o.metrics(query.get('campaign_id',[None])[0]); result['reply_tracking_enabled']=reply_sync.status()['authorized'] or result['replied']>0; return self.respond(200, result)
        try:
            if path == '/api/engagement':
                query = parse_qs(urlparse(self.path).query)
                return self.respond(200, engagement.snapshot(query.get('run_id', [None])[0]))
            if path.startswith('/api/run/'):
                return self.respond(200, w.get_run(path.removeprefix('/api/run/')))
            if path.startswith('/api/job/'):
                return self.respond(200, w.get_job(path.removeprefix('/api/job/')))
            if path.startswith('/api/campaign/'):
                return self.respond(200, o.load_campaign(w.location('campaigns', path.removeprefix('/api/campaign/') + '.json')))
            if path.startswith('/api/csv/'):
                run_id = path.removeprefix('/api/csv/')
                w.get_run(run_id)
                return self.respond(200, (w.location('runs', run_id) / 'creators.csv').read_bytes(), 'text/csv; charset=utf-8')
        except (ValueError, OSError):
            return self.respond(404, {'error': 'Record not found or invalid ID'})
        return self.respond(404, {'error': 'Not found'})

    def do_POST(self):
        public_path = urlparse(self.path).path
        if public_path.startswith('/t/reply/'):
            parts=public_path.removeprefix('/t/reply/').split('/',1)
            if len(parts)==2:
                cid,token=parts
                try:
                    data=json.loads(self.rfile.read(min(int(self.headers.get('Content-Length','0')),10000)))
                    c=o.load_campaign(w.location('campaigns',cid+'.json'))
                    for m in c['messages']:
                        if o.tracking_token(cid,m['to'])==token:o.record_tracking(cid,m['to'],'reply');return self.respond(204,b'')
                except Exception: pass
            return self.respond(404, {'error':'tracking token invalid'})
        if not self.authorized():
            return self.respond(403, {'error': 'Invalid request origin or access token'})
        if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
            return self.respond(415, {'error': 'JSON request required'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 2_000_000:
                return self.respond(413, {'error': 'Request is empty or exceeds 2 MB'})
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError('Invalid request format')
            path = urlparse(self.path).path
            if path == '/api/mail/consent': return self.respond(200, reply_sync.consent(data))
            if path == '/api/mail/sync': return self.respond(202, reply_sync.start_sync())
            if path == '/api/config':
                if any(k in data and not isinstance(data[k], str) for k in ('sender', 'easykol_email', 'easykol_key', 'gmail_app_password','tracking_base_url','openai_key','openai_model')):
                    raise ValueError('Configuration fields must be text')
                with LOCK:
                    cfg = o.load_config()
                    for key in ('sender', 'easykol_email'):
                        if data.get(key): cfg[key] = o.valid_email(data[key])
                    key = data.get('easykol_key', '').strip()
                    if key:
                        if not key.startswith('ek_') or any(c.isspace() for c in key):
                            raise ValueError('Invalid EasyKOL key format')
                        cfg['easykol_key'] = key
                    password = data.get('gmail_app_password', '').replace(' ', '').strip()
                    if password: cfg['gmail_app_password'] = password
                    ai_key = data.get('openai_key', '').strip()
                    if ai_key:
                        if any(c.isspace() for c in ai_key) or len(ai_key) > 500:
                            raise ValueError('Invalid AI API key format')
                        cfg['openai_key'] = ai_key
                    ai_model = data.get('openai_model', '').strip()
                    if ai_model:
                        if not re.fullmatch(r'[A-Za-z0-9._-]{1,100}', ai_model):
                            raise ValueError('Invalid AI model name')
                        cfg['openai_model'] = ai_model
                    base_url=data.get('tracking_base_url','').strip()
                    if base_url:
                        if not base_url.startswith('https://') or len(base_url)>500: raise ValueError('Tracking URL must use HTTPS')
                        cfg['tracking_base_url']=base_url.rstrip('/')
                    o.private_dir()
                    o.save_json(o.ROOT / 'config.json', cfg)
                return self.respond(200, {'message': 'Settings saved locally; keys are never returned to the page'})
            if path == '/api/creator-fit': return self.respond(200, creator_fit.generate(data))
            if path == '/api/brand-brief': return self.respond(200, engagement.save_brand(data))
            if path == '/api/brand-context': return self.respond(200, engagement.set_context(data))
            if path == '/api/engagement': return self.respond(200, engagement.mutate(data))
            if path == '/api/quota':
                return self.respond(200, o.api('/quota'))
            if path == '/api/suppress':
                return self.respond(200, o.suppress(NS(email=data.get('email'))))
            if path == '/api/contact': return self.respond(200, w.add_contact(data))
            if path == '/api/import': return self.respond(200, w.import_csv(data))
            if path == '/api/import-xlsx': return self.respond(200, w.import_xlsx(data))
            if path == '/api/template': return self.respond(200, w.save_template(data))
            if path == '/api/draft': return self.respond(200, w.create_campaign(data))
            if path == '/api/campaign-message': return self.respond(200, w.update_campaign_message(data))
            if path == '/api/personalize': return self.respond(200, w.personalize_contact(data))
            if path == '/api/cancel': return self.respond(200, w.cancel_job(data.get('job_id')))
            if path in ('/api/search', '/api/send', '/api/emails', '/api/emails-resume'):
                return self.respond(202, w.start_job(path.removeprefix('/api/'), data))
            return self.respond(404, {'error': 'Not found'})
        except (ValueError, KeyError, TypeError, OSError) as e:
            # Domain errors deliberately avoid provider raw responses and secrets.
            self.respond(400, {'error': str(e) if isinstance(e, ValueError) else 'Operation failed; check the input and local file permissions'})

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port', type=int, default=8768)
    p.add_argument('--no-open', action='store_true')
    p.add_argument('--reuse', action='store_true', help='Open a healthy existing dashboard instead of starting a duplicate')
    args = p.parse_args()
    if args.reuse:
        session_path = o.ROOT / 'dashboard-session.json'
        if session_path.exists():
            session = json.loads(session_path.read_text())
            parsed = urlparse(session.get('url', ''))
            if parsed.scheme == 'http' and parsed.hostname == '127.0.0.1' and parsed.port:
                token = parsed.fragment.removeprefix('token=')
                req = urllib.request.Request(f'http://127.0.0.1:{parsed.port}/api/status', headers={'X-Outreach-Token': token})
                try:
                    with urllib.request.urlopen(req, timeout=2) as response: json.load(response)
                    if not args.no_open: webbrowser.open(session['url'])
                    print('The workspace is already running.', flush=True)
                    return
                except (OSError, ValueError): pass
    server = LocalServer(('127.0.0.1', args.port), Handler)
    server.token = secrets.token_urlsafe(32)
    w.recover_jobs()
    url = f'http://127.0.0.1:{server.server_port}/#token={server.token}'
    o.private_dir()
    o.save_json(o.ROOT / 'dashboard-session.json', {'url': url, 'port': server.server_port, 'pid': __import__('os').getpid()})
    print(f'Workspace started http://127.0.0.1:{server.server_port}/ （The access link is saved locally in dashboard-session.json）', flush=True)
    if not args.no_open: webbrowser.open(url)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()

if __name__ == '__main__': main()
