"""Select personal OpenAI credentials or a separately authenticated team gateway."""
import os
import json
import re
import logging
from urllib.parse import urlparse
import outreach as o


def validate_url(url):
    parsed = urlparse(url)
    local = parsed.scheme == 'http' and parsed.hostname == '127.0.0.1' and parsed.port is not None
    if (parsed.scheme != 'https' and not local) or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('Team AI URL must use HTTPS (HTTP is allowed only on 127.0.0.1 with a port for local testing).')
    return url


def mode():
    cfg = o.load_config()
    return cfg.get('ai_mode') or ('team' if os.environ.get('OUTREACH_AI_URL') or cfg.get('ai_gateway_url') else 'personal')


def configuration():
    cfg = o.load_config()
    url = os.environ.get('OUTREACH_AI_URL') or cfg.get('ai_gateway_url', '')
    if mode() == 'team':
        if not url:
            return ('', 'team-managed', '')
        validate_url(url)
        return (os.environ.get('OUTREACH_AI_TOKEN') or cfg.get('ai_gateway_token', ''), 'team-managed', url.rstrip('/')+'/v1/responses')
    return (os.environ.get('OPENAI_API_KEY') or cfg.get('openai_key'),
            os.environ.get('OPENAI_MODEL') or cfg.get('openai_model'), 'https://api.openai.com/v1/responses')


def http_error(error):
    """Expose actionable categories, never raw provider bodies or credentials."""
    try:
        raw = error.read(8192)
        value = json.loads(raw).get('error', {})
    except (OSError, ValueError, AttributeError):
        value = {}
    code = value.get('code') or value.get('type') or '' if isinstance(value, dict) else ''
    code = code if isinstance(code, str) and re.fullmatch(r'[A-Za-z0-9_-]{1,80}', code) else ''
    request_id = error.headers.get('x-request-id', '') if error.headers else ''
    request_id = request_id if re.fullmatch(r'[A-Za-z0-9_-]{1,100}', request_id) else ''
    team = mode() == 'team'
    logging.getLogger(__name__).warning('AI request failed: mode=%s status=%s code=%s request_id=%s',
                                        'team' if team else 'personal', error.code, code, request_id)
    settings = ' Open Settings → AI connection to change it.'
    if code in ('insufficient_quota', 'credit_balance_exhausted', 'billing_hard_limit_reached', 'provider_insufficient_quota'):
        return ValueError(('The team AI account' if team else 'Your OpenAI API account') + ' has no available credits. Add API credits or use another account.' + settings)
    if error.code in (401, 403) or code == 'provider_authentication_failed':
        return ValueError(('The team access code or the team provider key is invalid.' if team else 'Your OpenAI API key is invalid or lacks permission.') + settings)
    if error.code == 429:
        return ValueError('The AI request limit was reached. Wait before retrying, or check the account credit balance.' + settings)
    if error.code == 404 or code in ('model_not_found', 'provider_model_not_found'):
        return ValueError('The selected AI model is unavailable to this API account. Choose an accessible model that supports structured output.' + settings)
    if team and error.code >= 500:
        return ValueError('The team AI service could not reach its model provider. You can switch to My OpenAI API key in Settings → AI connection, save your key and model, then test 3 options.')
    if error.code in (400, 422):
        return ValueError('The AI service rejected the model or output settings. Choose a model that supports structured output.' + settings)
    return ValueError('The AI service is temporarily unavailable (HTTP ' + str(error.code) + '). Try again later.' + settings)
