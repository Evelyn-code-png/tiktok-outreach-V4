import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from email.message import EmailMessage
from email import policy

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import outreach as o
import workspace as w
import engagement as e
import reply_sync as rs


def message(sender='creator@example.com',reference='<original@example.com>',body='Yes, interested!',mid='<reply@example.com>',automatic=False):
    m=EmailMessage();m['From']=sender;m['To']='sender@example.com';m['Message-ID']=mid;m['In-Reply-To']=reference;m['References']=reference;m['Subject']='Re: Collaboration';m['Date']='Sat, 17 Oct 2026 12:00:00 -0700'
    if automatic:m['Auto-Submitted']='auto-replied'
    m.set_content(body)
    return m.as_bytes()


class FakeIMAP:
    def __init__(self,messages):self.messages=messages;self.calls=[];self.logged_out=False;self.on_header=None
    def login(self,*args):return 'OK',[]
    def list(self):return 'OK',[b'(\\HasNoChildren \\All) "/" "[Gmail]/All Mail"']
    def select(self,mailbox,readonly=False):self.calls.append(('SELECT',mailbox,readonly));return 'OK',[b'2']
    def uid(self,command,*args):
        self.calls.append((command,*args))
        if command=='SEARCH':return 'OK',[b' '.join(self.messages)]
        uid,query=args;raw=self.messages[uid]
        if 'HEADER.FIELDS' in query:
            if self.on_header:self.on_header()
            head=raw.split(b'\n\n',1)[0]+b'\n\n'
            return 'OK',[(b'1 (RFC822.SIZE '+str(len(raw)).encode()+b' BODY[HEADER] {'+str(len(head)).encode()+b'}',head),b')']
        return 'OK',[(b'1 (BODY[] {123}',raw),b')']
    def logout(self):self.logged_out=True


class ReplySyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.patch=patch.object(o,'ROOT',Path(self.tmp.name));self.patch.start()
        self.env=patch.dict('os.environ',{'GMAIL_APP_PASSWORD':''});self.env.start()
        o.save_json(o.ROOT/'config.json',{'sender':'sender@example.com','gmail_app_password':'fake-password'})
        self.run=w.add_contact({'email':'creator@example.com','name':'Creator'})['run']
        self.draft=w.create_campaign({'run_id':self.run['id'],'selected_emails':['creator@example.com'],'subject':'Collaboration','body':'Hi Creator'})
        with o.db_open() as db:db.execute('INSERT INTO deliveries VALUES (?,?,?,?,?)',(self.draft['campaign_id'],'creator@example.com','accepted_by_smtp','<original@example.com>',1))
        self.fake=FakeIMAP({b'1':message()});self.imap=patch.object(rs.imaplib,'IMAP4_SSL',return_value=self.fake);self.factory=self.imap.start()
    def tearDown(self):self.imap.stop();self.env.stop();self.patch.stop();self.tmp.cleanup()
    def allow(self):return rs.consent({'allow':True,'consent_version':rs.CONSENT_VERSION})
    def test_no_consent_never_connects(self):
        with self.assertRaises(ValueError):rs.sync_once()
        self.factory.assert_not_called()
    def test_permission_is_bound_to_account_and_credential(self):
        self.allow();self.assertTrue(rs.status()['authorized']);cfg=o.load_config();cfg['sender']='another@example.com';o.save_json(o.ROOT/'config.json',cfg)
        self.assertFalse(rs.status()['authorized']);self.assertTrue(rs.status()['prompt_needed'])
        with self.assertRaises(ValueError):rs.sync_once()
        self.factory.assert_not_called()
    def test_changed_password_requires_new_consent(self):
        self.allow();cfg=o.load_config();cfg['gmail_app_password']='changed';o.save_json(o.ROOT/'config.json',cfg);self.assertFalse(rs.status()['authorized'])
    def test_decline_is_remembered_without_connecting(self):
        rs.consent({'allow':False});self.assertFalse(rs.status()['authorized']);self.assertFalse(rs.status()['prompt_needed']);self.factory.assert_not_called()
    def test_consent_rejects_missing_credentials_or_version(self):
        with self.assertRaises(ValueError):rs.consent({'allow':True,'consent_version':999})
        o.save_json(o.ROOT/'config.json',{'sender':'sender@example.com'})
        with self.assertRaises(ValueError):self.allow()
    def test_read_only_exact_match_is_saved_and_counted(self):
        self.allow();r=rs.sync_once();self.assertEqual((r['new_replies'],r['human_replies']),(1,1));self.assertEqual(o.metrics()['reply_rate'],100)
        self.assertTrue(self.fake.logged_out);self.assertIn(('SELECT','"[Gmail]/All Mail"',True),self.fake.calls)
        self.assertTrue(all('BODY.PEEK' in str(call) for call in self.fake.calls if call[0]=='FETCH'))
        search=next(c for c in self.fake.calls if c[0]=='SEARCH');self.assertIn('"<original@example.com>"',search)
        rec=list(e.load()['records'].values())[0];self.assertEqual(rec['stage'],'replied');self.assertEqual(rec['replies'][0]['source'],'Gmail sync')
        self.assertNotIn('fake-password',json.dumps(rs.status()))
    def test_repeat_sync_does_not_duplicate_text_tasks_or_metrics(self):
        self.allow();rs.sync_once();r=rs.sync_once();self.assertEqual(r['new_replies'],0);rec=list(e.load()['records'].values())[0];self.assertEqual((len(rec['replies']),len(rec['todos'])),(1,1));self.assertEqual(o.metrics()['replied'],1)
    def test_unrelated_mail_bodies_are_never_fetched(self):
        self.fake.messages={b'1':message(reference='<not-ours@example.com>'),b'2':message(sender='stranger@example.com')};self.allow();self.assertEqual(rs.sync_once()['new_replies'],0)
        self.assertFalse(any(c[0]=='FETCH' and c[-1]=='(BODY.PEEK[])' for c in self.fake.calls));self.assertEqual(e.load()['records'],{})
    def test_automatic_reply_does_not_inflate_reply_rate(self):
        self.fake.messages={b'1':message(automatic=True,body='I am away')};self.allow();r=rs.sync_once();self.assertEqual(r['automatic_replies'],1);self.assertEqual(o.metrics()['replied'],0)
    def test_quoted_original_does_not_control_classification(self):
        self.fake.messages={b'1':message(body='Yes, interested!\n\nOn Sat, Someone wrote:\nPlease send rates $100')};self.allow();rs.sync_once();reply=list(e.load()['records'].values())[0]['replies'][0];self.assertEqual(reply['category'],'interested');self.assertNotIn('$100',reply['body'])
    def test_revoke_during_header_read_stops_before_body(self):
        self.allow();self.fake.on_header=lambda:rs.consent({'allow':False})
        with self.assertRaises(ValueError):rs.sync_once()
        self.assertFalse(any(c[0]=='FETCH' and c[-1]=='(BODY.PEEK[])' for c in self.fake.calls));self.assertEqual(e.load()['records'],{})
    def test_large_related_message_uses_header_only_notice(self):
        self.fake.messages={b'1':message(body='x'*(rs.MAX_MESSAGE_BYTES+1))};self.allow();r=rs.sync_once();self.assertEqual(r['new_replies'],1);self.assertFalse(any(c[0]=='FETCH' and c[-1]=='(BODY.PEEK[])' for c in self.fake.calls))
    def test_reply_pauses_existing_followup(self):
        e.mutate({'run_id':self.run['id'],'creator_key':e.key_for(self.run['id'],self.run['contacts'][0]),'operation':'followup','due_at':1800000000,'subject':'Follow-up','body':'Hello'})
        self.allow();rs.sync_once();rec=list(e.load()['records'].values())[0];self.assertEqual(rec['todos'][0]['status'],'paused')
    def test_failed_sends_and_orphan_events_do_not_inflate_rates(self):
        with o.db_open() as db:db.execute('INSERT INTO deliveries VALUES (?,?,?,?,?)',('failed','other@example.com','failed_before_submission','<failed@example.com>',1))
        o.record_tracking('failed','other@example.com','reply');o.record_tracking('orphan','orphan@example.com','reply');self.allow();rs.sync_once();self.assertEqual((o.metrics()['sent'],o.metrics()['replied'],o.metrics()['reply_rate']),(1,1,100))
    def test_body_html_is_plain_text_and_skips_scripts(self):
        m=EmailMessage();m.set_content('<p>Hello</p><script>bad()</script><p>Interested</p>',subtype='html');self.assertEqual(rs.reply_text(m),'Hello\nInterested')
    def test_auth_failure_is_actionable_without_secret(self):
        self.allow();self.fake.login=lambda *a:(_ for _ in ()).throw(rs.imaplib.IMAP4.error('secret fake-password'))
        with self.assertRaisesRegex(ValueError,'Gmail refused') as err:rs.sync_once()
        self.assertNotIn('fake-password',str(err.exception))
    def test_references_match_closest_original_and_exact_sender(self):
        from email.parser import BytesParser
        m=BytesParser(policy=policy.default).parsebytes(message(sender='Someone <creator@example.com>'))
        self.assertIsNotNone(rs.match_reply(m,{'<original@example.com>':{'email':'creator@example.com'}}))
        self.assertIsNone(rs.match_reply(m,{'<original@example.com>':{'email':'different@example.com'}}))

if __name__=='__main__':unittest.main()
