import io
import json
from pathlib import Path
import sys
import unittest
import urllib.error
import urllib.parse
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import outreach as o


class EasyKOLErrorTests(unittest.TestCase):
    def error(self, body):
        return urllib.error.HTTPError('https://app.easykol.com/external/v1/intelligent-search',
                                      403, 'Forbidden', {}, io.BytesIO(body))

    def test_provider_reason_redacts_credentials_before_display(self):
        secret = 'PRIVATE_KEY_123456789'
        email = 'private@example.com'
        body = json.dumps({'message': secret + ' ' + email + ' ' + urllib.parse.quote(email, safe=''),
                           'code': 'ACCESS_DENIED'}).encode()
        message = str(o.easykol_http_error('/intelligent-search', self.error(body), secret, email))
        self.assertIn('creator search', message)
        self.assertIn('ACCESS_DENIED', message)
        self.assertNotIn(secret, message)
        self.assertNotIn(email, message)
        self.assertNotIn('private%40example.com', message)

    def test_html_is_not_displayed_and_edge_code_is_distinguished(self):
        message = str(o.easykol_http_error('/intelligent-search', self.error(b'error code: 1010'), '', ''))
        self.assertIn('client signature (1010)', message)
        hidden = str(o.easykol_http_error('/quota', self.error(b'<html>PRIVATE SERVER PAGE</html>'), '', ''))
        self.assertIn('balance check', hidden)
        self.assertNotIn('PRIVATE SERVER PAGE', hidden)

    def test_http_failure_never_retries_the_provider(self):
        with patch.object(o, 'load_config', return_value={'easykol_key': 'secret', 'easykol_email': 'me@example.com'}), \
                patch.object(o.urllib.request, 'build_opener') as factory:
            factory.return_value.open.side_effect = self.error(b'{"message":"Denied"}')
            with self.assertRaisesRegex(ValueError, 'Provider reason: Denied'):
                o.api('/intelligent-search', {'limit': 1})
            self.assertEqual(factory.return_value.open.call_count, 1)


if __name__ == '__main__':
    unittest.main()
