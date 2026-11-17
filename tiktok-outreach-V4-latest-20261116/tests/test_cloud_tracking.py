import hashlib
import json
from pathlib import Path
import secrets
import sys
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import cloud_tracking as t


class CloudTrackingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.patcher = patch.object(t.o, 'ROOT', self.root)
        self.patcher.start()
        t.o.save_json(self.root / 'config.json', {'sender': 'me@example.com', 'gmail_app_password': 'LOCAL_ONLY_SECRET'})
        self.token = secrets.token_urlsafe(32)
        t.save({'origin': 'https://receiver.test-account.workers.dev', 'token': self.token,
                'enabled': True, 'verified': True})

    def tearDown(self):
        self.patcher.stop()
        self.tmp.cleanup()

    def test_only_fixed_cloud_origin_allowed(self):
        for url in ['http://receiver.test-account.workers.dev', 'https://127.0.0.1',
                    'https://localhost', 'https://receiver.test-account.workers.dev/anything',
                    'https://receiver.test-account.workers.dev:443', 'https://evil.example',
                    'https://receiver.test-account.workers.dev?x=1',
                    'https://secret@receiver.test-account.workers.dev']:
            with self.subTest(url=url), self.assertRaises(ValueError):
                t.origin(url)

    def test_cloud_payload_excludes_personal_data_and_paths(self):
        body = 'Hi Jane, private note /Users/person/Documents/secret.txt & <script>\nhttps://example.com/product?a=1&b=2.'
        with patch.object(t, 'request', side_effect=lambda path, data, cfg: {'id': data['id']}) as req:
            with t.o.db_open() as db:
                rendered = t.prepare(db, 'campaign', 'jane@example.com', body)
        payload = req.call_args.args[1]
        self.assertEqual(set(payload), {'id', 'links'})
        self.assertEqual(set(payload['links'][0]), {'id', 'target'})
        self.assertNotIn('jane@example.com', json.dumps(payload))
        self.assertNotIn('/Users/', json.dumps(payload))
        self.assertNotIn('LOCAL_ONLY_SECRET', json.dumps(payload))
        self.assertNotIn(self.token, rendered)
        self.assertIn('&lt;script&gt;', rendered)
        self.assertIn('/c/', rendered)
        self.assertNotIn('?url=', rendered)
        self.assertEqual(payload['links'][0]['target'], 'https://example.com/product?a=1&b=2')

    def test_configure_checks_service_and_preserves_mail_credentials(self):
        before = (self.root / 'config.json').read_bytes()
        with patch.object(t, 'request', return_value={'service': 'wrong', 'version': 1}):
            with self.assertRaises(ValueError):
                t.configure({'origin': 'https://other.test-account.workers.dev', 'token': self.token})
        self.assertEqual(t.load()['origin'], 'https://receiver.test-account.workers.dev')
        with patch.object(t, 'request', return_value={'service': 'outreach-tracking', 'version': 1}):
            state = t.configure({'origin': 'https://other.test-account.workers.dev', 'token': self.token})
        self.assertNotIn('token', state)
        self.assertEqual((self.root / 'cloud-tracking.json').stat().st_mode & 0o777, 0o600)
        self.assertEqual(before, (self.root / 'config.json').read_bytes())

    def delivered(self, mid=None):
        mid = mid or secrets.token_urlsafe(32)
        with t.o.db_open() as db:
            db.execute('INSERT INTO deliveries VALUES(?,?,?,?,?)', ('campaign', 'jane@example.com', 'accepted_by_smtp', 'm1', 1))
            db.execute('INSERT INTO cloud_tracking_messages VALUES(?,?,?,?)', ('campaign', 'jane@example.com', mid, t.load()['origin']))
        return mid

    def test_sync_validates_cloud_data_before_writing(self):
        mid = self.delivered()
        for event in [{'id': mid, 'event': 'open', 'occurred': 1, 'path': '/Users/secret'},
                      {'id': mid, 'event': '__import__("os")', 'occurred': 1},
                      {'id': secrets.token_urlsafe(32), 'event': 'open', 'occurred': 1}]:
            with self.subTest(event=event), patch.object(t, 'request', return_value={'events': [event]}):
                with self.assertRaises(ValueError):
                    t.sync()
        with t.o.db_open() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM tracking_events').fetchone()[0], 0)

    def test_sync_deduplicates_and_excludes_old_untracked_sends(self):
        mid = self.delivered()
        with t.o.db_open() as db:
            db.execute('INSERT INTO deliveries VALUES(?,?,?,?,?)', ('old', 'other@example.com', 'accepted_by_smtp', 'm2', 1))
        with patch.object(t, 'request', return_value={'events': [{'id': mid, 'event': 'open', 'occurred': 1}]}):
            t.sync(); t.sync()
        metrics = t.metrics(t.o.metrics())
        self.assertEqual((metrics['sent'], metrics['tracked_sent'], metrics['opened'], metrics['open_rate']), (2, 1, 1, 100.0))

    def test_registration_failure_stops_before_smtp(self):
        c = {'sender': 'me@example.com', 'messages': [{'to': 'jane@example.com', 'subject': 'Hello', 'body': 'Hi https://example.com'}]}
        c['id'] = t.o.campaign_hash(c)
        p = self.root / 'campaign.json'; t.o.save_json(p, c)
        args = NS(campaign=str(p), execute=True, campaign_id=c['id'], max_messages=1, delay=1)
        with patch.object(t, 'request', side_effect=ValueError('Unavailable')), patch.object(t.o.smtplib, 'SMTP_SSL') as smtp:
            with self.assertRaises(ValueError):
                t.o.send(args)
            smtp.assert_not_called()
        with t.o.db_open() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM deliveries').fetchone()[0], 0)

    def test_pause_preserves_records_and_never_registers(self):
        self.delivered()
        t.configure({'enabled': False})
        with patch.object(t, 'request') as req, t.o.db_open() as db:
            self.assertIsNone(t.prepare(db, 'other', 'jane@example.com', 'Hi'))
            req.assert_not_called()
        self.assertEqual(t.metrics(t.o.metrics())['tracked_sent'], 1)


if __name__ == '__main__':
    unittest.main()
