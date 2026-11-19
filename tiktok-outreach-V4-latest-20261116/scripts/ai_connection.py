"""Select personal OpenAI credentials or a separately authenticated team gateway."""
import os
from urllib.parse import urlparse
import outreach as o


def validate_url(url):
    parsed = urlparse(url)
    local = parsed.scheme == 'http' and parsed.hostname == '127.0.0.1' and parsed.port is not None
    if (parsed.scheme != 'https' and not local) or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('Team AI URL must use HTTPS (HTTP is allowed only on 127.0.0.1 with a port for local testing).')
    return url


def configuration():
    cfg = o.load_config()
    url = os.environ.get('OUTREACH_AI_URL') or cfg.get('ai_gateway_url', '')
    if url:
        validate_url(url)
        return (os.environ.get('OUTREACH_AI_TOKEN') or cfg.get('ai_gateway_token', ''), 'team-managed', url.rstrip('/')+'/v1/responses')
    return (os.environ.get('OPENAI_API_KEY') or cfg.get('openai_key'),
            os.environ.get('OPENAI_MODEL') or cfg.get('openai_model'), 'https://api.openai.com/v1/responses')
