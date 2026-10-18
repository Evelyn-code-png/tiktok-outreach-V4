import importlib.util
import json
from pathlib import Path
import smtplib
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch, MagicMock

spec = importlib.util.spec_from_file_location('outreach', Path(__file__).resolve().parents[1] / 'scripts/outreach.py')
o = importlib.util.module_from_spec(spec)
spec.loader.exec_module(o)

class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = patch.object(o, 'ROOT', self.root / 'private')
        self.home.start()
        o.private_dir()
        o.save_json(o.ROOT / 'config.json', {'sender': 'sender@example.com', 'gmail_app_password': 'mock-password'})

    def tearDown(self):
        self.home.stop()
        self.tmp.cleanup()

    def campaign(self):
        contacts = self.root / 'contacts.csv'
        o.csv_write(contacts, o.normalize([
            {'name': 'Alice', 'email': 'alice@example.com', 'profileUrl': 'https://www.tiktok.com/@alice'},
            {'name': 'Duplicate', 'email': 'ALICE@example.com'},
            {'name': 'No email'},
            {'name': 'Bob', 'email': 'bob@example.com'}]))
        body = self.root / 'body.txt'; body.write_text('Hi $name, see $profile_url')
        out = self.root / 'campaign.json'
        result = o.draft(NS(csv=str(contacts), body=str(body), subject='Hello $name', out=str(out)))
        self.assertEqual(result['recipients'], 2)
        return NS(campaign=str(out), execute=True, campaign_id=result['campaign_id'], max_messages=20, delay=1)

    def test_dry_run_never_connects(self):
        args = self.campaign(); args.execute = False
        with patch.object(o.smtplib, 'SMTP_SSL') as smtp:
            self.assertTrue(o.send(args)['dry_run'])
            smtp.assert_not_called()

    def test_sends_once_and_suppression_rechecked(self):
        args = self.campaign()
        o.suppress(NS(email='bob@example.com'))
        with patch.object(o.smtplib, 'SMTP_SSL') as factory, patch.object(o.time, 'sleep'):
            smtp = factory.return_value.__enter__.return_value
            smtp.send_message.return_value = {}
            result = o.send(args)
            self.assertEqual(result['results'][0]['status'], 'accepted_by_smtp')
            o.send(args)
            self.assertEqual(smtp.send_message.call_count, 1)
            msg = smtp.send_message.call_args.args[0]
            self.assertEqual(msg['To'], 'alice@example.com')
            self.assertIn('Hi Alice', msg.get_content())

    def test_uncertain_submission_is_not_retried(self):
        args = self.campaign()
        with patch.object(o.smtplib, 'SMTP_SSL') as factory, patch.object(o.time, 'sleep'):
            smtp = factory.return_value.__enter__.return_value
            smtp.send_message.side_effect = smtplib.SMTPServerDisconnected('lost response')
            self.assertEqual(o.send(args)['results'][0]['status'], 'unknown')
            o.suppress(NS(email='bob@example.com'))
            o.send(args)
            self.assertEqual(smtp.send_message.call_count, 1)

    def test_tamper_and_missing_campaign_id(self):
        args = self.campaign()
        args.campaign_id = 'wrong'
        with self.assertRaises(ValueError): o.send(args)
        p = Path(args.campaign); c = json.loads(p.read_text())
        c['messages'][0]['to'] = 'other@example.com'; p.write_text(json.dumps(c))
        with self.assertRaises(ValueError): o.send(args)

    def test_search_contract_and_budget(self):
        args = NS(query='skincare', queries_file=None, limit=20, budget=20,
                  min_followers=100, max_followers=None, avg_min=0, regions='US', languages='en', has_email=True, out=str(self.root / 'run'))
        with patch.object(o, 'api', side_effect=[{'remaining': 100}, {'data': [{'nickname': 'Alice', 'email': 'alice@example.com', 'profileUrl': 'https://www.tiktok.com/@alice'}]}]) as api:
            result = o.search(args)
            self.assertEqual(o.csv_read(result['csv'])[0]['email'], 'alice@example.com')
            self.assertEqual(api.call_args.args[1]['platform'], 'TIKTOK')
            self.assertTrue(api.call_args.args[1]['hasContactInfo'])
        args.budget = 1
        with patch.object(o, 'api') as api:
            with self.assertRaises(ValueError): o.search(args)
            api.assert_not_called()

    def test_business_error_does_not_look_successful(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps({'statusCode': 1403, 'data': None}).encode()
        with patch.dict(o.os.environ, {'EASYKOL_API_KEY': 'mock-key', 'EASYKOL_API_EMAIL': 'account@example.com'}), patch.object(o.urllib.request, 'build_opener') as opener:
            opener.return_value.open.return_value = response
            with self.assertRaises(ValueError): o.api('/quota')

    def test_spreadsheet_and_email_injection(self):
        path = self.root / 'safe.csv'
        o.csv_write(path, o.normalize([{'name': '=HYPERLINK("evil")', 'email': 'alice@example.com'}]))
        self.assertIn("'=HYPERLINK", path.read_text(encoding='utf-8-sig'))
        self.assertEqual(o.csv_read(path)[0]['name'], '=HYPERLINK("evil")')
        for name in ['\t=EVIL()', '  =EVIL()', '\r+EVIL()', '\n@EVIL()']:
            o.csv_write(path, o.normalize([{'name': name, 'email': 'alice@example.com'}]))
            self.assertEqual(o.csv_read(path)[0]['name'], name)
            self.assertTrue(o.needs_csv_quote(name))
        with self.assertRaises(ValueError): o.valid_email('a@example.com\r\nBcc:b@example.com')

    def test_email_job_validates_url_and_preserves_id(self):
        path = self.root / 'contacts.csv'
        o.csv_write(path, o.normalize([{'profileUrl': 'https://www.tiktok.com/@alice'}]))
        with patch.object(o, 'api', return_value={'taskId': 'task-123'}) as api:
            result = o.emails_start(NS(csv=str(path), budget=1))
            self.assertEqual(result['task']['taskId'], 'task-123')
            self.assertEqual(api.call_args.args[1]['ttUrls'], ['https://www.tiktok.com/@alice'])
            self.assertTrue(list(o.ROOT.glob('email-task-*.json')))

    def test_failed_csv_save_preserves_previous_complete_snapshot(self):
        path=self.root/'contacts.csv'
        o.csv_write(path,o.normalize([{'name':'Original','email':'original@example.com'}]))
        def interrupted_rows():
            yield {'name':'Partial','email':'partial@example.com'}
            raise OSError('simulated interrupted export')
        with self.assertRaises(OSError):o.csv_write(path,interrupted_rows())
        self.assertEqual(o.csv_read(path)[0]['email'],'original@example.com')
        self.assertFalse(list(self.root.glob('.contacts.csv-*')))

if __name__ == '__main__':
    unittest.main()
