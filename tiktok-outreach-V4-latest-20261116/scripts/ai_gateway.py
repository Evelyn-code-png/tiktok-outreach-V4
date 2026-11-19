"""Small team gateway. Deploy behind HTTPS; never distribute its OpenAI key."""
import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import sqlite3
import time
import urllib.error
import urllib.request


def reserve(token):
    path = Path(os.environ.get('AI_GATEWAY_DB', '~/.config/outreach-ai/usage.sqlite')).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with sqlite3.connect(path, timeout=10) as db:
        db.execute('CREATE TABLE IF NOT EXISTS usage (user TEXT, day INTEGER, count INTEGER, PRIMARY KEY(user,day))')
        db.execute('BEGIN IMMEDIATE')
        user, day = hashlib.sha256(token.encode()).hexdigest(), int(time.time()//86400)
        count = db.execute('SELECT count FROM usage WHERE user=? AND day=?',(user,day)).fetchone()
        if count and count[0] >= int(os.environ.get('AI_DAILY_REQUEST_LIMIT','50')): return False
        db.execute('INSERT INTO usage VALUES (?,?,1) ON CONFLICT(user,day) DO UPDATE SET count=count+1',(user,day))
    return True


def payload(data):
    if not isinstance(data,dict) or set(data)-{'model','instructions','input','text'}:
        raise ValueError('Unsupported request')
    if not isinstance(data.get('input'),str) or not isinstance(data.get('instructions'),str) or not isinstance(data.get('text'),dict):
        raise ValueError('Text and structured output are required')
    return {**data, 'model':os.environ['OPENAI_MODEL'], 'store':False, 'max_output_tokens':2000}


class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def setup(self):
        super().setup(); self.connection.settimeout(15)
    def respond(self,code,data):
        body=json.dumps(data).encode(); self.send_response(code)
        self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(body)))
        self.send_header('Cache-Control','no-store'); self.end_headers(); self.wfile.write(body)
    def do_GET(self):
        return self.respond(200, {'status':'ok'}) if self.path == '/healthz' else self.respond(404, {'error':'Not found'})
    def do_POST(self):
        if self.path != '/v1/responses': return self.respond(404,{'error':'Not found'})
        supplied=self.headers.get('Authorization','').removeprefix('Bearer ')
        allowed=[t.strip() for t in os.environ.get('AI_GATEWAY_TOKENS','').split(',') if t.strip()]
        if not supplied or not any(secrets.compare_digest(supplied,t) for t in allowed):
            return self.respond(401,{'error':'Invalid team access code'})
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=100000: return self.respond(413,{'error':'Request too large or empty'})
            data=payload(json.loads(self.rfile.read(length)))
        except (ValueError,TypeError): return self.respond(400,{'error':'Invalid request'})
        if not reserve(supplied): return self.respond(429,{'error':'Daily team allowance reached'})
        request=urllib.request.Request('https://api.openai.com/v1/responses',data=json.dumps(data).encode(),
            headers={'Authorization':'Bearer '+os.environ['OPENAI_API_KEY'],'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(request,timeout=60) as response: result=json.load(response)
        except urllib.error.HTTPError as error:
            return self.respond(429 if error.code==429 else 502,{'error':'AI provider unavailable; contact the team administrator'})
        except (OSError,ValueError): return self.respond(502,{'error':'AI provider unavailable'})
        return self.respond(200,result)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--local',action='store_true',help='Connect this computer using its saved personal AI credentials; loopback only')
    parser.add_argument('--host', choices=['127.0.0.1','0.0.0.0'], default='127.0.0.1', help='Use 0.0.0.0 only behind a hosting platform HTTPS proxy')
    args=parser.parse_args()
    if args.local:
        import outreach as o
        cfg=o.load_config()
        for env,field in [('OPENAI_API_KEY','openai_key'),('OPENAI_MODEL','openai_model')]:
            if not os.environ.get(env): os.environ[env]=cfg.get(field,'')
        if not os.environ.get('OPENAI_API_KEY') or not os.environ.get('OPENAI_MODEL'):
            raise SystemExit('Save a personal AI key and model in Account Setup before starting local AI.')
        token=secrets.token_urlsafe(32)
        os.environ['AI_GATEWAY_TOKENS']=token
        os.environ['AI_GATEWAY_DB']=str(o.ROOT/'local-ai-usage.sqlite')
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        cfg['ai_gateway_url']='http://127.0.0.1:'+str(server.server_port)
        cfg['ai_gateway_token']=token
        o.save_json(o.ROOT/'config.json',cfg)
        print('Local AI gateway ready at '+cfg['ai_gateway_url']+'. Keep this window open, then open or refresh the dashboard. No AI request has been made.',flush=True)
    else:
        if not all(os.environ.get(k) for k in ('OPENAI_API_KEY','OPENAI_MODEL','AI_GATEWAY_TOKENS')):
            raise SystemExit('Set OPENAI_API_KEY, OPENAI_MODEL and AI_GATEWAY_TOKENS on the server first.')
        server=ThreadingHTTPServer((args.host,int(os.environ.get('PORT') or os.environ.get('AI_GATEWAY_PORT','8766'))),Handler)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()


if __name__=='__main__': main()
