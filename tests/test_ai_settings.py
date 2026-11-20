import io
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import outreach as o
import ai_connection as ai
import dashboard as d
import personalization as p


class AISettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for replacement in (patch.object(o, 'ROOT', self.root), patch.dict(os.environ, {
            'OPENAI_API_KEY': '', 'OPENAI_MODEL': '', 'OUTREACH_AI_URL': '', 'OUTREACH_AI_TOKEN': ''})):
            replacement.start(); self.addCleanup(replacement.stop)
        o.save_json(self.root / 'config.json', {'ai_gateway_url': 'https://team.example',
                    'ai_gateway_token': 'team-secret', 'sender': 'sender@example.com'})

    def api(self, path, data=None):
        server = d.LocalServer(('127.0.0.1', 0), d.Handler); server.token = 'local-test'
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            request = urllib.request.Request(f'http://127.0.0.1:{server.server_port}'+path,
                data=None if data is None else json.dumps(data).encode(),
                headers={'X-Outreach-Token': 'local-test', 'Content-Type': 'application/json'})
            with urllib.request.urlopen(request, timeout=5) as response: return json.load(response)
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=2)

    def test_personal_save_bypasses_saved_team_and_does_not_return_key(self):
        result = self.api('/api/config', {'ai_mode': 'personal', 'openai_key': 'personal-secret', 'openai_model': 'available-model'})
        self.assertNotIn('personal-secret', json.dumps(result))
        self.assertEqual(ai.configuration(), ('personal-secret', 'available-model', 'https://api.openai.com/v1/responses'))
        status = self.api('/api/status')
        self.assertEqual(status['ai_mode'], 'personal')
        self.assertTrue(status['personal_ai_key_saved'])
        self.assertEqual(status['openai_model'], 'available-model')
        self.assertNotIn('personal-secret', json.dumps(status))
        self.api('/api/config', {'ai_mode': 'team'})
        self.assertEqual(ai.configuration(), ('team-secret', 'team-managed', 'https://team.example/v1/responses'))

    def test_explicit_personal_mode_ignores_environment_team_gateway(self):
        o.save_json(self.root / 'config.json', {'ai_mode': 'personal', 'openai_key': 'personal-secret', 'openai_model': 'available-model'})
        with patch.dict(os.environ, {'OUTREACH_AI_URL': 'https://team.example', 'OUTREACH_AI_TOKEN': 'team-secret'}):
            self.assertEqual(ai.configuration()[2], 'https://api.openai.com/v1/responses')

    def test_missing_personal_key_does_not_replace_working_team_settings(self):
        before = (self.root / 'config.json').read_bytes()
        with self.assertRaises(urllib.error.HTTPError) as raised:
            self.api('/api/config', {'ai_mode': 'personal', 'openai_model': 'available-model'})
        self.assertEqual(raised.exception.code, 400)
        self.assertEqual((self.root / 'config.json').read_bytes(), before)

    def test_three_option_test_uses_no_creator_lookup_or_email_transport(self):
        options = [{'paragraph': f'Opening {n}', 'reason': 'Sample facts', 'evidence_url': 'https://www.tiktok.com/@sample'} for n in range(3)]
        with patch.object(p, 'call_ai', return_value={'options': options}) as model, patch.object(p, 'fetch_kol_details') as lookup, patch.object(o.smtplib, 'SMTP_SSL') as smtp:
            result = self.api('/api/ai/test', {})
        self.assertEqual(len(result['options']), 3)
        self.assertIn('fictional', model.call_args.args[0]['description'])
        lookup.assert_not_called(); smtp.assert_not_called()

    def test_generation_accepts_exactly_three_valid_options(self):
        o.save_json(self.root / 'config.json', {'ai_mode': 'personal', 'openai_key': 'test-secret', 'openai_model': 'available-model'})
        creator = {'profile_url': 'https://www.tiktok.com/@sample'}
        options = [{'paragraph': f'Opening {n}', 'reason': 'Sample facts', 'evidence_url': creator['profile_url']} for n in range(3)]
        def response(output):
            return io.BytesIO(json.dumps({'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': json.dumps(output)}]}]}).encode())
        with patch.object(p.urllib.request, 'urlopen', return_value=response({'options': options})):
            self.assertEqual(len(p.call_ai(creator, [], {})['options']), 3)
        for invalid in ({'options': options[:2]}, {'options': [None]*3}, []):
            with self.subTest(invalid=invalid), patch.object(p.urllib.request, 'urlopen', return_value=response(invalid)), self.assertRaises(ValueError):
                p.call_ai(creator, [], {})

    def test_team_failure_explains_personal_alternative_without_leaking_body(self):
        error = urllib.error.HTTPError('https://team.example/v1/responses', 502, 'Bad gateway', {}, io.BytesIO(b'{"error":"secret-body"}'))
        with self.assertLogs(ai.__name__, level='WARNING') as logged:
            message = str(ai.http_error(error))
        self.assertIn('My OpenAI API key', message)
        self.assertNotIn('secret-body', message + ''.join(logged.output))

    def test_quota_and_model_errors_have_distinct_next_steps(self):
        for code, status, expected in [('insufficient_quota',429,'credits'), ('model_not_found',404,'model'), ('invalid_api_key',401,'invalid')]:
            error = urllib.error.HTTPError('https://api.openai.com/v1/responses', status, 'Error', {}, io.BytesIO(json.dumps({'error': {'code': code, 'message':'secret-body'}}).encode()))
            with self.subTest(code=code), self.assertLogs(ai.__name__, level='WARNING'):
                self.assertIn(expected, str(ai.http_error(error)))


if __name__ == '__main__': unittest.main()
