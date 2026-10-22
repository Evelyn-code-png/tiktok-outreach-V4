import base64
from email import policy
from email.parser import BytesParser
import json
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import outreach as o
import google_mail as g
import ai_connection as ai
import ai_gateway as gateway
import reply_sync as rs
import workspace as w
from test_reply_sync import message


class Connections(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        p=patch.object(o,'ROOT',self.root); p.start(); self.addCleanup(p.stop)
        p=patch.dict('os.environ', {'OPENAI_API_KEY':'','OPENAI_MODEL':'','OUTREACH_AI_URL':'','OUTREACH_AI_TOKEN':''});p.start();self.addCleanup(p.stop)
        p=patch.object(g,'client',return_value={'client_id':'test-client','client_secret':'test-secret'});p.start();self.addCleanup(p.stop)
        g.PENDING.clear()
        o.save_json(self.root/'config.json',{'sender':'sender@example.com'})
    def token(self,read=True):
        cfg=o.load_config();cfg['mail_transport']='google';o.save_json(self.root/'config.json',cfg)
        t={'refresh_token':'refresh-secret','access_token':'access-secret','scope':g.EMAIL+' '+g.SEND+(' '+g.READ if read else ''),
           'email':'sender@example.com','expires_at':time.time()+3600,'connection_id':'connection-1','client_id':'test-client'}
        o.save_json(self.root/'google-token.json',t);return t
    def callback(self,read=False):
        q=parse_qs(urlparse(g.begin(8765,read)['url']).query)
        self.assertEqual(q['code_challenge_method'],['S256']);self.assertNotIn('client_secret',q)
        return {'state':q['state'],'code':['one-time-code']}
    def test_invalid_or_expired_state_never_exchanges(self):
        q=self.callback();g.PENDING[q['state'][0]]['expires']=0
        with patch.object(g,'request') as req:
            with self.assertRaises(ValueError):g.finish(q)
            with self.assertRaises(ValueError):g.finish({'state':['bogus'],'code':['x']})
            req.assert_not_called()
    def test_success_and_callback_replay(self):
        q=self.callback(True)
        response={'access_token':'secret','refresh_token':'refresh','expires_in':3600,'scope':' '.join([g.EMAIL,g.SEND,g.READ])}
        with patch.object(g,'request',side_effect=[response,{'email':'sender@example.com','verified_email':True}]) as req:
            self.assertEqual(g.finish(q),'sender@example.com')
            self.assertIn('code_verifier',req.call_args_list[0].kwargs['form'])
            with self.assertRaises(ValueError):g.finish(q)
        self.assertTrue(g.connected(g.READ));self.assertNotIn('secret',json.dumps(g.status()))
        self.assertEqual((self.root/'google-token.json').stat().st_mode & 0o777,0o600)
    def test_partial_grant_keeps_previous_token(self):
        original=self.token();q=self.callback(True)
        with patch.object(g,'request',return_value={'scope':g.SEND,'refresh_token':'new'}):
            with self.assertRaises(ValueError):g.finish(q)
        self.assertEqual(g.load(),original)
    def test_refresh_preserves_refresh_token_and_consent_identity(self):
        t=self.token();t['expires_at']=0;o.save_json(self.root/'google-token.json',t)
        with patch.object(g,'request',return_value={'access_token':'fresh','expires_in':3600}):self.assertEqual(g.access(),'fresh')
        self.assertEqual(g.load()['refresh_token'],'refresh-secret');self.assertEqual(g.load()['connection_id'],'connection-1')
    def test_revoked_refresh_has_no_smtp_fallback(self):
        t=self.token();t['expires_at']=0;o.save_json(self.root/'google-token.json',t)
        with patch.object(g,'request',side_effect=OSError('private token error')):
            with self.assertRaisesRegex(ValueError,'Reconnect Google'):g.access()
    def test_disconnect_removes_token_and_disables_saved_smtp(self):
        self.token();cfg=o.load_config();cfg['gmail_app_password']='old';o.save_json(self.root/'config.json',cfg)
        g.disconnect();self.assertFalse(g.connected());self.assertFalse(o.doctor(NS(online=False))['gmail_configured'])
        self.assertEqual(rs.credentials()[1],'')
    def campaign(self):
        run=w.add_contact({'email':'creator@example.com','name':'Creator'})['run']
        c=w.create_campaign({'run_id':run['id'],'selected_emails':['creator@example.com'],'subject':'Collaboration','body':'Hello'})
        return NS(campaign=str(w.location('campaigns',c['campaign_id']+'.json')),execute=True,campaign_id=c['campaign_id'],max_messages=1,delay=1)
    def test_google_send_keeps_suppression_and_dedup(self):
        self.token();args=self.campaign()
        with patch.object(g,'request',return_value={'id':'gmail-id'}) as req:
            result=o.send(args);self.assertEqual(result['accepted'],1)
            self.assertEqual(result['results'][0]['status'],'accepted_by_gmail_api')
            raw=base64.urlsafe_b64decode(req.call_args.kwargs['body']['raw']);self.assertIn(b'To: creator@example.com',raw)
            o.send(args);self.assertEqual(req.call_count,1)
        self.assertEqual(o.metrics()['sent'],1)
    def test_account_reconnected_mid_batch_stops_submission(self):
        self.token();args=self.campaign()
        def progress(values):
            if values.get('completed') == 0:
                token=g.load();token['connection_id']='another-connection';o.save_json(self.root/'google-token.json',token)
        args.progress=progress
        with patch.object(g,'request') as req:
            self.assertEqual(o.send(args)['results'][0]['status'],'failed_before_submission')
            req.assert_not_called()
    def test_suppressed_google_recipient_never_submitted(self):
        self.token();args=self.campaign();o.suppress(NS(email='creator@example.com'))
        with patch.object(g,'request') as req:self.assertEqual(o.send(args)['accepted'],0);req.assert_not_called()
    def test_ambiguous_google_send_not_retried(self):
        self.token();args=self.campaign()
        with patch.object(g,'request',side_effect=OSError('connection lost')) as req:
            self.assertEqual(o.send(args)['results'][0]['status'],'unknown');o.send(args);self.assertEqual(req.call_count,1)
    def test_google_reply_requires_consent_and_exact_references(self):
        self.token();args=self.campaign()
        with o.db_open() as db:db.execute('INSERT INTO deliveries VALUES (?,?,?,?,?)',(args.campaign_id,'creator@example.com','accepted_by_gmail_api','<original@example.com>',1))
        raw=message();parsed=BytesParser(policy=policy.default).parsebytes(raw)
        meta={'sizeEstimate':len(raw),'payload':{'headers':[{'name':k,'value':str(v)} for k,v in parsed.items()]}}
        unrelated={'sizeEstimate':10,'payload':{'headers':[{'name':'From','value':'stranger@example.com'}]}}
        def api(path):
            if path.startswith('messages?'):return {'messages':[{'id':'one'},{'id':'two'}]}
            if path=='messages/two?format=metadata':return unrelated
            if path=='messages/one?format=metadata':return meta
            if path=='messages/one?format=raw':return {'raw':base64.urlsafe_b64encode(raw).decode()}
            self.fail('Unexpected mailbox read: '+path)
        with patch.object(g,'api',side_effect=api) as req:
            with self.assertRaises(ValueError):rs.sync_once()
            req.assert_not_called()
            rs.consent({'allow':True,'consent_version':1})
            self.assertEqual(rs.sync_once()['new_replies'],1);self.assertEqual(rs.sync_once()['new_replies'],0)
            self.assertEqual(sum(c.args[0].endswith('format=raw') for c in req.call_args_list),1)
    def test_sending_only_cannot_enable_reply_sync(self):
        self.token(False)
        with self.assertRaises(ValueError):rs.consent({'allow':True,'consent_version':1})
    def test_team_ai_never_uses_personal_key(self):
        o.save_json(self.root/'config.json',{'ai_gateway_url':'https://team.example','ai_gateway_token':'team-code','openai_key':'private-key'})
        self.assertEqual(ai.configuration(),('team-code','team-managed','https://team.example/v1/responses'))
    def test_team_ai_rejects_insecure_url(self):
        o.save_json(self.root/'config.json',{'ai_gateway_url':'http://team.example'})
        with self.assertRaises(ValueError):ai.configuration()
    def test_local_ai_allows_only_explicit_loopback_http(self):
        self.assertEqual(ai.validate_url('http://127.0.0.1:8766'),'http://127.0.0.1:8766')
        for url in ['http://localhost:8766','http://127.0.0.1.evil.example:8766','http://192.168.1.2:8766','http://127.0.0.1','http://user:password@127.0.0.1:8766']:
            with self.assertRaises(ValueError):ai.validate_url(url)
    def test_gateway_overrides_model_and_caps_daily_usage(self):
        with patch.dict('os.environ',{'OPENAI_MODEL':'team-model','AI_GATEWAY_DB':str(self.root/'usage.sqlite'),'AI_DAILY_REQUEST_LIMIT':'2'}):
            p=gateway.payload({'model':'expensive','input':'facts','instructions':'fit','text':{}})
            self.assertEqual(p['model'],'team-model');self.assertFalse(p['store']);self.assertEqual(p['max_output_tokens'],2000)
            self.assertTrue(gateway.reserve('person-a'));self.assertTrue(gateway.reserve('person-a'));self.assertFalse(gateway.reserve('person-a'));self.assertTrue(gateway.reserve('person-b'))
            with self.assertRaises(ValueError):gateway.payload({'input':'x','instructions':'x','text':{},'tools':[]})
