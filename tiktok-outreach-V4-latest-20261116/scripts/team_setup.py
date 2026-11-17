"""Import a privately distributed team connection file; never import mailbox tokens."""
import argparse
import json
from pathlib import Path
from urllib.parse import urlparse
import outreach as o
import ai_connection


def install(path):
    path = Path(path)
    if path.stat().st_size > 20000:
        raise ValueError('Team connection file is too large.')
    data = json.loads(path.read_text())
    allowed = {'version', 'google_client', 'ai_gateway_url', 'ai_gateway_token', 'easykol_email', 'easykol_key'}
    if not isinstance(data, dict) or set(data) - allowed or data.get('version') != 1:
        raise ValueError('Unsupported team connection file. Do not use a personal config or Gmail token file.')
    url = data.get('ai_gateway_url', '')
    token = data.get('ai_gateway_token', '')
    if not isinstance(url, str) or not isinstance(token, str):
        raise ValueError('Invalid AI connection.')
    ai_connection.validate_url(url)
    if urlparse(url).scheme != 'https' or len(token) < 32 or len(token) > 500 or any(c.isspace() for c in token):
        raise ValueError('Team AI requires an HTTPS URL and a valid private access code.')
    desktop = data.get('google_client', {}).get('installed', {}) if isinstance(data.get('google_client'), dict) else {}
    if not isinstance(desktop, dict) or not isinstance(desktop.get('client_id'), str) or not desktop['client_id'].endswith('.apps.googleusercontent.com'):
        raise ValueError('Include the team Google Desktop client configuration.')
    if not isinstance(desktop.get('client_secret'), str) or not desktop['client_secret']:
        raise ValueError('Google Desktop client configuration is incomplete.')
    # Keep only expected client metadata, not arbitrary account or token fields.
    client = {'installed': {k: desktop[k] for k in ('client_id','client_secret')}}
    cfg = o.load_config()
    cfg.update(ai_gateway_url=url.rstrip('/'), ai_gateway_token=token)
    if 'easykol_email' in data or 'easykol_key' in data:
        email = o.valid_email(data.get('easykol_email'))
        key = data.get('easykol_key')
        if not isinstance(key, str) or not key or len(key) > 500 or any(c.isspace() for c in key):
            raise ValueError('Invalid EasyKOL team configuration.')
        cfg.update(easykol_email=email, easykol_key=key)
    o.private_dir()
    o.save_json(o.ROOT / 'google-client.json', client)
    o.save_json(o.ROOT / 'config.json', cfg)
    return 'Team connections installed. Open Dashboard and connect your own Google account.'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('file', nargs='?', default=str(Path(__file__).resolve().parents[1] / 'team-connection.json'))
    args = parser.parse_args()
    try:
        print(install(args.file))
    except (ValueError, OSError, TypeError, AttributeError):
        raise SystemExit('Could not install team connections. Ask your team administrator for a valid team-connection.json file; your Gmail authorization is not shared.') from None


if __name__ == '__main__':
    main()
