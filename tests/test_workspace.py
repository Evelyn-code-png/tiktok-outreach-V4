import io
import base64
import json
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace as NS
import unittest
from unittest.mock import MagicMock, patch
import urllib.error
import urllib.request
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import outreach as o
import workspace as w
import email_results as er
import dashboard as d
import personalization as p

class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = patch.object(o, 'ROOT', Path(self.tmp.name))
        self.root.start()
        o.save_json(o.ROOT / 'config.json', {'sender': 'sender@example.com',
            'easykol_key': 'ek_test_secret', 'easykol_email': 'account@example.com',
            'openai_key': 'test_ai_secret', 'openai_model': 'test-model'})

    def tearDown(self):
        self.root.stop(); self.tmp.cleanup()

    def run_data(self):
        return w.import_csv({'title': 'Test list', 'csv_text': 'nickname,URL,Email,Followers\nAlice,https://www.tiktok.com/@alice,alice@example.com,1000\nBob,https://www.tiktok.com/@bob,bob@example.com,2000\n'})

    def campaign(self):
        run = self.run_data()
        return w.create_campaign({'run_id': run['id'], 'selected_emails': ['alice@example.com'], 'subject': 'Hi $name', 'body': 'Hello $name. $profile_url'})

    def test_manual_contact_email_only_persists_and_can_draft(self):
        with patch.object(o, 'api', side_effect=AssertionError('No provider call allowed')):
            result = w.add_contact({'email': 'Creator@Example.com'})
        self.assertTrue(result['added'])
        run = w.get_run(result['run']['id'])
        self.assertEqual(run['title'], 'My contacts')
        self.assertEqual(run['contacts'][0]['email'], 'creator@example.com')
        self.assertEqual(run['contacts'][0]['name'], 'creator')
        self.assertEqual(run['contacts'][0]['followers'], '')
        draft = w.create_campaign({'run_id': run['id'], 'selected_emails': ['creator@example.com'],
                                   'subject': 'Hi $name', 'body': 'Hello $name'})
        self.assertEqual(o.load_campaign(draft['campaign_file'])['messages'][0]['to'], 'creator@example.com')

    def test_manual_contact_duplicate_does_not_overwrite(self):
        first = w.add_contact({'email': 'alice@example.com', 'name': 'Alice'})
        second = w.add_contact({'email': 'ALICE@example.com', 'name': 'Changed name'})
        self.assertFalse(second['added'])
        self.assertEqual(second['run']['id'], first['run']['id'])
        self.assertEqual(second['run']['rows'], 1)
        self.assertEqual(second['run']['contacts'][0]['name'], 'Alice')

    def test_manual_contact_append_preserves_existing_list(self):
        run = self.run_data()
        before = w.read_json(w.location('runs', run['id'])/'meta.json')
        result = w.add_contact({'run_id': run['id'], 'email': 'new@example.com', 'name': 'New creator'})
        self.assertEqual(result['run']['rows'], 3)
        self.assertEqual(result['run']['contacts'][:2], run['contacts'])
        self.assertEqual(w.read_json(w.location('runs', run['id'])/'meta.json'), before)

    def test_manual_contact_validation_has_no_side_effects(self):
        for data in ({'email': ''}, {'email':'a@example.com,b@example.com'}, {'email':'bad'},
                     {'email':'a@example.com', 'name':'x'*121}, {'email':'a@example.com', 'name':'a\nb'},
                     {'email':['a@example.com']}, {'email':'a@example.com','run_id':'../escape'},
                     {'email':'a@example.com','run_id':'missing-list'}):
            with self.subTest(data=data), self.assertRaises(ValueError): w.add_contact(data)
        self.assertEqual(w.list_runs(), [])

    def test_manual_contact_waits_for_background_task(self):
        with w.WORK_LOCK:
            with self.assertRaisesRegex(ValueError, 'background task'):
                w.add_contact({'email': 'a@example.com'})
        self.assertEqual(w.list_runs(), [])

    def test_import_draft_reopen(self):
        c = self.campaign()
        self.assertEqual(c['recipients'], 1)
        loaded = o.load_campaign(c['campaign_file'])
        self.assertEqual(loaded['messages'][0]['subject'], 'Hi Alice')
        self.assertEqual(w.list_campaigns()[0]['id'], c['campaign_id'])
        self.assertEqual(w.list_runs()[0]['rows'], 2)
        self.assertEqual(w.list_runs()[0]['emails'], 2)

    def test_edit_one_message_creates_unsent_revision(self):
        run = self.run_data()
        original = w.create_campaign({
            'run_id': run['id'],
            'selected_emails': ['alice@example.com', 'bob@example.com'],
            'subject': 'Hi $name',
            'body': 'Original for $name'
        })
        revised = w.update_campaign_message({
            'campaign_id': original['campaign_id'],
            'email': 'alice@example.com',
            'subject': 'A special subject for Alice',
            'body': 'A personal message for Alice'
        })
        self.assertNotEqual(revised['campaign_id'], original['campaign_id'])
        by_email = {m['to']: m for m in revised['campaign']['messages']}
        self.assertEqual(by_email['alice@example.com']['body'], 'A personal message for Alice')
        self.assertEqual(by_email['bob@example.com']['body'], 'Original for Bob')
        self.assertEqual(w.list_campaigns()[0]['id'], revised['campaign_id'])
        with o.db_open() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM deliveries').fetchone()[0], 0)

    def test_edit_rejects_started_campaign(self):
        original = self.campaign()
        with o.db_open() as db:
            db.execute('INSERT INTO deliveries VALUES (?,?,?,?,?)',
                       (original['campaign_id'], 'alice@example.com', 'sent_browser', '', 1))
        with self.assertRaises(ValueError):
            w.update_campaign_message({'campaign_id': original['campaign_id'],
                                       'email': 'alice@example.com',
                                       'subject': 'Changed', 'body': 'Changed'})

    def test_manual_video_personalization_is_grounded_and_does_not_send(self):
        run = self.run_data()
        videos = ('https://www.tiktok.com/@alice/video/123 | A real caption about cat adoption\n'
                  'https://www.tiktok.com/@alice/video/456 | A real caption about calming a new cat')
        options = [{'paragraph': f'Opening {i}', 'reason': 'Uses supplied caption',
                    'evidence_url': 'https://www.tiktok.com/@alice/video/123'} for i in range(3)]
        profile = {'name': 'Alice', 'username': 'alice',
                   'profile_url': 'https://www.tiktok.com/@alice',
                   'description': 'Cat adoption educator'}
        with patch.object(p, 'fetch_kol_details', return_value=profile), \
             patch.object(p, 'call_ai', return_value={'options': options}) as ai:
            result = w.personalize_contact({'run_id': run['id'], 'email': 'alice@example.com',
                'recent_videos': videos, 'brand_name': 'Pawsome', 'product': 'Cat bed',
                'campaign_goal': 'Introduce the product', 'offer': 'Paid partnership',
                'language': 'English'})
        self.assertEqual(len(result['options']), 3)
        self.assertEqual(len(ai.call_args.args[1]), 2)
        with o.db_open() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM deliveries').fetchone()[0], 0)

    def test_profile_only_personalization_does_not_require_video_list_api(self):
        run = self.run_data()
        profile = {'name': 'Alice', 'username': 'alice',
                   'profile_url': 'https://www.tiktok.com/@alice',
                   'description': 'Cat adoption educator', 'ai_tags': 'cats,adoption'}
        options = [{'paragraph': f'Opening {i}', 'reason': 'Uses profile facts',
                    'evidence_url': profile['profile_url']} for i in range(3)]
        with patch.object(p, 'fetch_kol_details', return_value=profile) as kol, \
             patch.object(p, 'call_ai', return_value={'options': options}) as ai:
            result = w.personalize_contact({'run_id': run['id'], 'email': 'alice@example.com',
                'brand_name': 'Pawsome', 'product': 'Cat bed',
                'campaign_goal': 'Introduce the product'})
        self.assertEqual(result['videos'], [])
        kol.assert_called_once_with('https://www.tiktok.com/@alice')
        self.assertEqual(ai.call_args.args[0]['description'], 'Cat adoption educator')

    def test_easykol_video_endpoint_normalizes_known_video(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps({
            'statusCode': 1000, 'error': None, 'data': {'platform': 'TIKTOK',
            'title': 'Cat adoption tips', 'description': 'Three ways to help a new cat settle in',
            'viewCount': 1200, 'likeCount': 80, 'commentCount': 5,
            'shareCount': 2, 'publishedAt': '2026-09-20T00:00:00Z'}}).encode()
        with patch.object(p.urllib.request, 'urlopen', return_value=response) as call:
            video = p.fetch_video_details('https://www.tiktok.com/@alice/video/123')
        self.assertIn('Cat adoption tips', video['caption'])
        self.assertEqual((video['views'], video['likes']), (1200, 80))
        request = call.call_args.args[0]
        self.assertIn('/external/v1/video?', request.full_url)
        self.assertNotIn('ek_test_secret', request.full_url)

    def test_easykol_kol_endpoint_normalizes_profile(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps({
            'statusCode': 1000, 'error': None, 'data': {'platform': 'TIKTOK',
            'username': 'alice', 'nickname': 'Alice',
            'url': 'https://www.tiktok.com/@alice',
            'description': 'Cat adoption educator',
            'oneLinePitch': 'Helps new cat owners', 'aiTags': 'cats,adoption',
            'followerCount': 12000, 'region': 'US', 'language': 'en',
            'averagePlayCount': 8000}}).encode()
        with patch.object(p.urllib.request, 'urlopen', return_value=response) as call:
            creator = p.fetch_kol_details('https://www.tiktok.com/@alice')
        self.assertEqual(creator['one_line_pitch'], 'Helps new cat owners')
        self.assertEqual(creator['average_play_count'], 8000)
        request = call.call_args.args[0]
        self.assertIn('/external/v1/kol?', request.full_url)
        self.assertNotIn('ek_test_secret', request.full_url)

    def test_import_rejects_broken_or_ambiguous_csv(self):
        for text in ['name\nAlice', 'email,Email\na@b.com,b@c.com', 'email\na@b.com,extra']:
            with self.assertRaises(ValueError): w.import_csv({'csv_text': text})

    def test_path_escape_is_rejected(self):
        for value in ['../config', '/tmp/secret', 'abc.json/../config', 'x.json.json', '']:
            with self.assertRaises(ValueError): w.location('campaigns', value)

    def test_draft_rejects_recipient_not_in_list(self):
        run = self.run_data()
        with self.assertRaises(ValueError):
            w.create_campaign({'run_id': run['id'], 'selected_emails': ['outside@example.com'], 'subject': 'Hi', 'body': 'Hello'})

    def test_browser_and_smtp_share_dedupe(self):
        c = self.campaign(); args = NS(campaign=c['campaign_file'], email='alice@example.com')
        self.assertEqual(len(o.browser_plan(args)['pending']), 1)
        o.browser_claim(args)
        self.assertEqual(len(o.browser_plan(args)['pending']), 0)
        with self.assertRaises(ValueError): o.browser_claim(args)
        args.result = 'sent_browser'; o.browser_result(args)
        with self.assertRaises(ValueError): o.browser_result(args)
        with o.db_open() as db:
            self.assertEqual(db.execute('SELECT status FROM deliveries').fetchone()[0], 'sent_browser')

    def test_browser_rechecks_suppression(self):
        c = self.campaign(); o.suppress(NS(email='alice@example.com'))
        args = NS(campaign=c['campaign_file'], email='alice@example.com')
        self.assertFalse(o.browser_plan(args)['pending'])
        with self.assertRaises(ValueError): o.browser_claim(args)

    def test_job_is_idempotent_and_restart_marks_unknown(self):
        data={'request_id': 'test-request-1', 'queries': ['beauty'], 'regions': 'US', 'limit': 1, 'budget': 1}
        with patch.object(w.threading, 'Thread') as worker:
            first = w.start_job('search', data)
            second = w.start_job('search', data)
            self.assertEqual(first['id'], second['id'])
            self.assertEqual(worker.call_count, 1)
            with self.assertRaises(ValueError): w.start_job('search', dict(data, queries=['different']))
        w.recover_jobs()
        self.assertEqual(w.get_job(first['id'])['status'], 'interrupted')

    def test_complete_search_job_with_mock_api(self):
        data={'request_id':'test-search','queries':['beauty'],'regions':'US','limit':1,'budget':1}
        job={'id':'test-search','kind':'search','status':'queued','created':1}
        with patch.object(o,'api',side_effect=[{'remaining':100},{'data':[{'nickname':'Alice','email':'alice@example.com','profileUrl':'https://tiktok.com/@alice'}]}]):
            w.run_job(job,data)
        self.assertEqual(w.get_job('test-search')['status'],'completed')
        self.assertEqual(w.get_run('search-test-search')['emails'],1)

    def test_merge_is_keyed_not_positional(self):
        original=o.normalize([{'profileUrl':'https://www.tiktok.com/@alice'},{'profileUrl':'https://tiktok.com/@bob'}])
        exported=[{'URL':'https://www.tiktok.com/@bob','Email':'bob@example.com'}, {'URL':'https://tiktok.com/@alice','Email':'alice@example.com'}, {'URL':'https://evil.example/@alice','Email':'wrong@example.com'}]
        merged,skipped=er.merge_rows(original,exported)
        self.assertEqual([r['email'] for r in merged],['alice@example.com','bob@example.com'])
        self.assertEqual(skipped,1)

    def test_xlsx_strings_and_formula_are_safe(self):
        buf=io.BytesIO()
        xml='''<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>URL</t></is></c><c r="B1" t="inlineStr"><is><t>Email</t></is></c></row><row r="2"><c r="A2" t="inlineStr"><is><t>https://tiktok.com/@alice</t></is></c><c r="B2" t="inlineStr"><is><t>alice@example.com</t></is></c></row><row r="3"><c r="B3"><f>EVIL()</f><v>other@example.com</v></c></row></sheetData></worksheet>'''
        with zipfile.ZipFile(buf,'w') as z:z.writestr('xl/worksheets/sheet1.xml',xml)
        rows=er.xlsx_rows(buf.getvalue())
        self.assertEqual(rows[0]['Email'],'alice@example.com')
        self.assertEqual(rows[1]['Email'],'')

    def test_atomic_config_preserves_private_permissions(self):
        p=o.ROOT/'config.json'
        o.save_json(p,{'sender':'a@example.com'})
        self.assertEqual(p.stat().st_mode & 0o777,0o600)
        self.assertEqual(json.loads(p.read_text())['sender'],'a@example.com')

    def test_cancel_queued_job_never_calls_provider(self):
        data={'request_id':'cancel-test','queries':['beauty'],'regions':'US','limit':1,'budget':1}
        with patch.object(w.threading,'Thread'):
            job=w.start_job('search',data)
        w.cancel_job(job['id'])
        with patch.object(o,'api') as provider:
            w.run_job(job,data)
        provider.assert_not_called()
        self.assertEqual(w.get_job(job['id'])['status'],'cancelled')

    def test_cancel_search_preserves_first_result(self):
        qfile=o.ROOT/'queries.txt';qfile.write_text('first\nsecond')
        args=NS(query=None,queries_file=str(qfile),regions='US',languages='',min_followers=0,max_followers=None,
                avg_min=0,limit=1,budget=2,has_email=True,out=str(o.ROOT/'partial'))
        calls=[]
        def provider(path,body=None):
            calls.append(path)
            return {'remaining':100} if path=='/quota' else {'data':[{'email':'alice@example.com'}]}
        args.should_stop=lambda: len(calls)>=2
        with patch.object(o,'api',side_effect=provider),patch.object(o.time,'sleep'):
            with self.assertRaises(o.OperationCancelled):o.search(args)
        self.assertEqual(calls,['/quota','/intelligent-search'])
        self.assertEqual(o.csv_read(o.ROOT/'partial/creators.csv')[0]['email'],'alice@example.com')

    def test_resume_only_polls_existing_provider_task(self):
        run=self.run_data()
        prior={'id':'interrupted-emails','kind':'emails','status':'interrupted','created':1,
               'provider_task_id':'existing-provider-task','source_run_id':run['id']}
        w.save_job(prior)
        data={'request_id':'resume-test','source_job_id':prior['id']}
        with patch.object(w.threading,'Thread'):job=w.start_job('emails-resume',data)
        with patch.object(o,'emails_start') as create,patch.object(o,'emails_collect',return_value={'status':'COMPLETED','rows':2}) as collect,patch.object(w.time,'sleep'):
            w.run_job(job,data)
        create.assert_not_called()
        self.assertEqual(collect.call_args.args[0].task_id,'existing-provider-task')
        self.assertEqual(w.get_job('resume-test')['status'],'completed')

    def test_xlsx_import_and_corrupt_file_handling(self):
        buf=io.BytesIO()
        xml='<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row><c r="A1" t="inlineStr"><is><t>Email</t></is></c></row><row><c r="A2" t="inlineStr"><is><t>alice@example.com</t></is></c></row></sheetData></worksheet>'
        with zipfile.ZipFile(buf,'w') as z:z.writestr('xl/worksheets/sheet1.xml',xml)
        result=w.import_xlsx({'xlsx_base64':base64.b64encode(buf.getvalue()).decode(),'title':'test.xlsx'})
        self.assertEqual(result['contacts'][0]['email'],'alice@example.com')
        for content in ['not-base64!',base64.b64encode(b'not a zip').decode()]:
            with self.assertRaises(ValueError):w.import_xlsx({'xlsx_base64':content})

    def test_send_partial_failure_has_distinct_job_status(self):
        c=self.campaign()
        job={'id':'send-partial','kind':'send','status':'queued','created':1}
        with patch.object(o,'send',return_value={'failed_or_unknown':1,'accepted':1}):
            w.run_job(job,{'campaign_id':c['campaign_id'],'max_messages':20})
        self.assertEqual(w.get_job(job['id'])['status'],'completed_with_errors')

    def test_history_pages_and_filters_keep_older_records_accessible(self):
        with o.db_open() as db:
            db.executemany('INSERT INTO deliveries VALUES (?,?,?,?,?)',
                [('campaign-a',f'person{i}@example.com','sent_browser','',i) for i in range(205)])
        first=o.history(NS(limit=100,offset=0))
        last=o.history(NS(limit=100,offset=200))
        self.assertEqual(first['total'],205)
        self.assertEqual(len(last['deliveries']),5)
        self.assertEqual(last['deliveries'][-1]['email'],'person0@example.com')
        one=o.history(NS(campaign_id='campaign-a',email='person42@example.com'))
        self.assertEqual(one['total'],1)
        with self.assertRaises(ValueError):o.history(NS(limit=0))

    def test_templates_and_metrics_are_local_and_deduplicated(self):
        t=w.save_template({'name':'新品合作','subject':'Hi $name','body':'Hello $username'})
        self.assertEqual(w.list_templates()[0]['id'],t['id'])
        w.save_template({'name':'新品合作','subject':'Updated $name','body':'Updated'})
        self.assertEqual(len(w.list_templates()),1)
        with o.db_open() as db:
            db.execute('INSERT INTO deliveries VALUES (?,?,?,?,?)',('campaign-x','a@example.com','sent_browser','',1))
        o.record_tracking('campaign-x','a@example.com','sent');o.record_tracking('campaign-x','a@example.com','open');o.record_tracking('campaign-x','a@example.com','open');o.record_tracking('campaign-x','a@example.com','reply')
        m=o.metrics('campaign-x');self.assertEqual((m['sent'],m['opened'],m['replied'],m['open_rate'],m['reply_rate']),(1,1,1,100.0,100.0))

    def test_tracking_token_and_reply_event_are_deduplicated(self):
        with o.db_open() as db:
            db.execute('INSERT INTO deliveries VALUES (?,?,?,?,?)',('campaign-x','a@example.com','accepted_by_smtp','<test@example.com>',1))
        token=o.tracking_token('campaign-x','a@example.com')
        self.assertEqual(len(token),40)
        o.record_tracking('campaign-x','a@example.com','reply');o.record_tracking('campaign-x','a@example.com','reply')
        self.assertEqual(o.metrics('campaign-x')['replied'],1)

class DashboardHTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=patch.object(o,'ROOT',Path(self.tmp.name));self.root.start()
        o.save_json(o.ROOT/'config.json',{'sender':'sender@example.com','easykol_key':'ek_secret_for_test'})
        self.server=d.LocalServer(('127.0.0.1',0),d.Handler);self.server.token='test-token'
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.base='http://127.0.0.1:'+str(self.server.server_port)

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.root.stop();self.tmp.cleanup()

    def request(self,path,data=None,headers=None):
        h={'X-Outreach-Token':'test-token','Content-Type':'application/json'};h.update(headers or {})
        return urllib.request.urlopen(urllib.request.Request(self.base+path,data=None if data is None else json.dumps(data).encode(),headers=h),timeout=5)

    def test_status_never_returns_secret(self):
        with self.request('/api/status') as r:
            body=r.read().decode();self.assertNotIn('ek_secret',body);self.assertIn('sender@example.com',body)
            self.assertEqual(r.headers['Cache-Control'],'no-store')

    def test_team_comparison_illustrations_are_served_locally(self):
        assets = [
            ('/team-meeting-collaboration.svg', 'image/svg+xml', b'<svg'),
            ('/single-user-workspace.png', 'image/png', b'\x89PNG'),
        ]
        for path, content_type, signature in assets:
            with self.subTest(path=path), self.request(path) as r:
                self.assertEqual(r.status, 200)
                self.assertEqual(r.headers['Content-Type'], content_type)
                self.assertIn(signature, r.read(512))

    def test_csrf_and_wrong_token_rejected(self):
        for headers in [{'X-Outreach-Token':'bad'},{'Origin':'https://evil.example'},{'Host':'evil.example'}]:
            with self.assertRaises(urllib.error.HTTPError) as ctx:self.request('/api/config',{'sender':'wrong@example.com'},headers)
            self.assertEqual(ctx.exception.code,403)
        self.assertEqual(o.load_config()['sender'],'sender@example.com')

    def test_config_update_preserves_blank_secrets(self):
        with self.request('/api/config',{'sender':'sender@example.com','easykol_email':'account@example.com','easykol_key':''}) as r:self.assertEqual(r.status,200)
        self.assertEqual(o.load_config()['easykol_key'],'ek_secret_for_test')

    def test_mail_permission_routes_never_read_before_consent(self):
        import reply_sync
        with patch.object(reply_sync.imaplib,'IMAP4_SSL') as imap:
            with self.request('/api/mail/status') as response:
                value=json.load(response);self.assertFalse(value['authorized']);self.assertFalse(value['configured'])
            with self.assertRaises(urllib.error.HTTPError) as denied:
                self.request('/api/mail/sync',{})
            self.assertEqual(denied.exception.code,400)
            with self.assertRaises(urllib.error.HTTPError) as unauth:
                self.request('/api/mail/consent',{'allow':True,'consent_version':1},headers={'X-Outreach-Token':'bad'})
            self.assertEqual(unauth.exception.code,403)
            cfg=o.load_config();cfg['gmail_app_password']='not-real';o.save_json(o.ROOT/'config.json',cfg)
            with self.request('/api/mail/consent',{'allow':True,'consent_version':1}) as response:
                value=json.load(response);self.assertTrue(value['authorized']);self.assertNotIn('not-real',str(value));self.assertNotIn('identity',value)
            imap.assert_not_called()
            with self.request('/api/mail/consent',{'allow':False}) as response:self.assertFalse(json.load(response)['authorized'])
            imap.assert_not_called()

    def test_send_status_restores_saved_outcome_without_sending(self):
        run=w.import_csv({'csv_text':'name,email\nAlex,a@example.com'})
        draft=w.create_campaign({'run_id':run['id'],'selected_emails':['a@example.com'],'subject':'Hi','body':'Hello'})
        cid=draft['campaign_id']
        with self.request('/api/send-status?campaign_id='+cid) as response:
            self.assertIsNone(json.load(response)['job'])
        for stamp,status in ((1,'completed'),(2,'failed')):
            w.save_job({'id':'send-'+str(stamp),'kind':'send','campaign_id':cid,'status':status,'created':stamp})
        with patch.object(o,'send') as send:
            with self.request('/api/send-status?campaign_id='+cid) as response:
                self.assertEqual(json.load(response)['job']['id'],'send-2')
            send.assert_not_called()
        with self.assertRaises(urllib.error.HTTPError) as denied:
            self.request('/api/send-status?campaign_id='+cid,headers={'X-Outreach-Token':'bad'})
        self.assertEqual(denied.exception.code,403)
        with self.assertRaises(urllib.error.HTTPError) as invalid:
            self.request('/api/send-status?campaign_id=../escape')
        self.assertEqual(invalid.exception.code,400)

    def test_http_manual_contact_to_preview_and_authorization(self):
        with self.assertRaises(urllib.error.HTTPError) as denied:
            self.request('/api/contact', {'email':'a@example.com'}, {'X-Outreach-Token':'bad'})
        self.assertEqual(denied.exception.code, 403)
        self.assertEqual(w.list_runs(), [])
        with self.request('/api/contact', {'email':'a@example.com','name':'Alex'}) as r: result=json.load(r)
        with self.request('/api/draft', {'run_id':result['run']['id'], 'selected_emails':['a@example.com'],
                                        'subject':'Hi $name','body':'Hello $name'}) as r: draft=json.load(r)
        with self.request('/api/campaign/'+draft['campaign_id']) as r:
            self.assertEqual(json.load(r)['messages'][0]['body'], 'Hello Alex')
        with self.assertRaises(urllib.error.HTTPError) as invalid:
            self.request('/api/contact', {'email':'not-an-email'})
        self.assertEqual(invalid.exception.code, 400)
        self.assertEqual(w.get_run(result['run']['id'])['rows'], 1)

    def test_http_import_to_preview(self):
        with self.request('/api/import',{'csv_text':'name,email\nAlice,alice@example.com'}) as r: run=json.load(r)
        with self.request('/api/draft',{'run_id':run['id'],'selected_emails':['alice@example.com'],'subject':'Hi $name','body':'Hello $name'}) as r: campaign=json.load(r)
        with self.request('/api/campaign/'+campaign['campaign_id']) as r:self.assertEqual(json.load(r)['messages'][0]['body'],'Hello Alice')

    def test_engagement_api_persists_brief_details_and_reply(self):
        with self.request('/api/import', {'csv_text':'name,email,region,language,followers\nAlice,alice@example.com,US,en,20000'}) as r: run=json.load(r)
        with self.request('/api/brand-brief', {'name':'LUMA','product':'Sunscreen','regions':'US','language':'English'}) as r: brand=json.load(r)
        with self.request('/api/brand-context', {'run_id':run['id'],'brand_id':brand['id']}) as r: self.assertEqual(r.status,200)
        with self.request('/api/engagement?run_id='+run['id']) as r: result=json.load(r)
        base={'run_id':run['id'],'creator_key':result['creators'][0]['key']}
        self.assertEqual(result['creators'][0]['match']['label'],'Strong filter fit')
        with self.request('/api/engagement',{**base,'operation':'details','priority':'high','stage':'contacted','notes':'Ask about dates'}) as r: self.assertEqual(r.status,200)
        with self.request('/api/engagement',{**base,'operation':'reply','body':'What is your budget?'}) as r: result=json.load(r)
        self.assertEqual(result['records'][0]['replies'][0]['category'],'pricing')
        self.assertEqual(result['records'][0]['todos'][0]['kind'],'reply')
        with self.request('/api/history') as r:self.assertEqual(json.load(r)['deliveries'],[])

    def test_engagement_rejects_unauthorized_and_invalid_context(self):
        for path,data in [('/api/engagement',None),('/api/brand-brief',{'name':'LUMA','product':'Sunscreen'}),('/api/engagement',{'operation':'reply'})]:
            with self.assertRaises(urllib.error.HTTPError) as ctx:self.request(path,data,{'X-Outreach-Token':'wrong'})
            self.assertEqual(ctx.exception.code,403)
        with self.assertRaises(urllib.error.HTTPError) as ctx:self.request('/api/engagement?run_id=..%2Fescape')
        self.assertEqual(ctx.exception.code,404)

    def test_creator_fit_route_explains_missing_ai_and_rejects_wrong_token(self):
        import creator_fit
        with self.request('/api/import', {'csv_text':'name,email,region\nAlice,alice@example.com,US'}) as r: run=json.load(r)
        with self.request('/api/brand-brief', {'name':'LUMA','product':'Sunscreen'}) as r: brand=json.load(r)
        with self.request('/api/brand-context', {'run_id':run['id'],'brand_id':brand['id']}) as r: self.assertEqual(r.status,200)
        data={'run_id':run['id'],'creator_key':creator_fit.e.key_for(run['id'],run['contacts'][0])}
        with self.assertRaises(urllib.error.HTTPError) as ctx:self.request('/api/creator-fit',data,{'X-Outreach-Token':'wrong'})
        self.assertEqual(ctx.exception.code,403)
        with self.assertRaises(urllib.error.HTTPError) as ctx:self.request('/api/creator-fit',data)
        self.assertEqual(ctx.exception.code,400)
        self.assertIn('Account Setup',json.load(ctx.exception)['error'])

    def test_engagement_assets_are_local_and_english(self):
        for path,mime in [('/engagement.js','text/javascript'),('/engagement.css','text/css')]:
            with self.request(path) as r:
                self.assertIn(mime,r.headers['Content-Type'])
                self.assertTrue(r.read())
        with self.request('/') as r:
            html=r.read().decode()
            self.assertIn('>Instruction</span>',html)
            self.assertIn('Card wall',html)
            self.assertIn('Creator details',html)
            self.assertFalse(any('\u4e00'<=c<='\u9fff' for c in html))

if __name__=='__main__':unittest.main()
