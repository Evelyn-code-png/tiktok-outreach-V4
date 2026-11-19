import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import outreach as o
import team_setup
import google_mail


class TeamSetup(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        p = patch.object(o, 'ROOT', self.root / 'private'); p.start(); self.addCleanup(p.stop)
        self.data = {'version':1, 'ai_gateway_url':'https://team.example.com', 'ai_gateway_token':'x'*40,
                     'google_client':{'installed':{'client_id':'test.apps.googleusercontent.com','client_secret':'test'}}}
        self.path = self.root / 'team.json'

    def install(self):
        self.path.write_text(json.dumps(self.data))
        return team_setup.install(self.path)

    def test_preserves_personal_mailbox_and_contacts(self):
        o.save_json(o.ROOT/'config.json', {'sender':'member@example.com','mail_transport':'google'})
        o.save_json(o.ROOT/'google-token.json', {'refresh_token':'member-only'})
        self.install()
        self.assertEqual(o.load_config()['sender'],'member@example.com')
        self.assertEqual(google_mail.load()['refresh_token'],'member-only')
        self.assertEqual(google_mail.client()['client_id'],'test.apps.googleusercontent.com')
        self.assertEqual((o.ROOT/'config.json').stat().st_mode & 0o777, 0o600)

    def test_rejects_personal_secrets_and_local_only_gateway(self):
        for key in ['openai_key','gmail_app_password','refresh_token']:
            self.data[key] = 'private'
            with self.assertRaises(ValueError): self.install()
            del self.data[key]
        self.data['ai_gateway_url']='http://127.0.0.1:1234'
        with self.assertRaises(ValueError): self.install()
        self.assertFalse((o.ROOT/'config.json').exists())

    def test_validates_optional_search_config_before_writing(self):
        self.data['easykol_email']='invalid'
        self.data['easykol_key']='test'
        with self.assertRaises(ValueError): self.install()
        self.assertFalse((o.ROOT/'google-client.json').exists())

    def test_no_network_during_install(self):
        with patch('urllib.request.urlopen', side_effect=AssertionError('No external request')):
            self.install()
        self.assertEqual(o.load_config()['ai_gateway_url'],'https://team.example.com')
