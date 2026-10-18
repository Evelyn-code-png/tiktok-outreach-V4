"""Grounded creator-email personalization for the local workspace."""
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from urllib.parse import urlparse

import outreach as o


def valid_tiktok_url(value):
    value = str(value or '').strip()
    parsed = urlparse(value)
    if parsed.scheme != 'https' or parsed.hostname not in ('tiktok.com', 'www.tiktok.com'):
        raise ValueError('Video and creator profile links must be valid TikTok HTTPS URLs')
    return value


def manual_videos(text):
    """Accept up to five TikTok URLs, with optional user-supplied caption after |."""
    if not isinstance(text, str):
        raise ValueError('Recent video details must be provided as text')
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if '|' in line:
            url, content = (part.strip() for part in line.split('|', 1))
        else:
            url, content = line, ''
        rows.append({'url': valid_tiktok_url(url), 'caption': content[:5000],
                     'transcript': '', 'views': 0, 'likes': 0, 'posted_at': ''})
        if len(rows) > 5:
            raise ValueError('You can analyze up to five videos per creator')
    return rows


def fetch_video_details(video_url):
    """Resolve one known TikTok video URL with EasyKOL GET /external/v1/video."""
    cfg = o.load_config()
    key = os.environ.get('EASYKOL_API_KEY') or cfg.get('easykol_key')
    email = os.environ.get('EASYKOL_API_EMAIL') or cfg.get('easykol_email')
    if not key or not email:
        raise ValueError('Configure an EasyKOL API key and account email before retrieving video details')
    endpoint = ('https://talent-marketing-api.aiwaifu.top/external/v1/video?'
                + urllib.parse.urlencode({'url': valid_tiktok_url(video_url)}))
    request = urllib.request.Request(endpoint, headers={
        'ek-api-key': key, 'ek-api-email': email, 'Accept': 'application/json'})
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            result = json.load(response)
    except urllib.error.HTTPError as error:
        if error.code in (401, 403):
            raise ValueError('The EasyKOL API key, account email, or video endpoint permission is invalid') from None
        if error.code == 429:
            raise ValueError('EasyKOL is rate-limiting the request or the account has insufficient credits; try again later') from None
        raise ValueError(f'The EasyKOL video endpoint returned HTTP {error.code}') from None
    except (urllib.error.URLError, TimeoutError):
        raise ValueError('The EasyKOL video request failed; check your credits before submitting it again') from None
    if not isinstance(result, dict) or result.get('statusCode') != 1000 or not isinstance(result.get('data'), dict):
        raise ValueError('EasyKOL did not return valid video details')
    data = result['data']
    if str(data.get('platform', '')).upper() != 'TIKTOK':
        raise ValueError('Personalization currently accepts TikTok videos only')
    title = str(data.get('title') or '').strip()
    description = str(data.get('description') or '').strip()
    if not title and not description:
        raise ValueError('The video has no title or description, so it cannot support evidence-based personalization')
    return {
        'url': video_url, 'caption': '\n'.join(x for x in (title, description) if x)[:5000],
        'transcript': '', 'views': data.get('viewCount') or 0,
        'likes': data.get('likeCount') or 0, 'comments': data.get('commentCount') or 0,
        'shares': data.get('shareCount') or 0, 'posted_at': str(data.get('publishedAt') or '')[:100],
        'cover_url': str(data.get('coverUrl') or '')[:2000],
        'author_name': str(data.get('authorName') or '')[:500]
    }


def fetch_kol_details(profile_url):
    """Resolve one social profile with EasyKOL GET /external/v1/kol."""
    cfg = o.load_config()
    key = os.environ.get('EASYKOL_API_KEY') or cfg.get('easykol_key')
    email = os.environ.get('EASYKOL_API_EMAIL') or cfg.get('easykol_email')
    if not key or not email:
        raise ValueError('Configure an EasyKOL API key and account email before retrieving the creator profile')
    endpoint = ('https://talent-marketing-api.aiwaifu.top/external/v1/kol?'
                + urllib.parse.urlencode({'url': valid_tiktok_url(profile_url)}))
    request = urllib.request.Request(endpoint, headers={
        'ek-api-key': key, 'ek-api-email': email, 'Accept': 'application/json'})
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            result = json.load(response)
    except urllib.error.HTTPError as error:
        if error.code in (401, 403):
            raise ValueError('The EasyKOL API key, account email, or creator endpoint permission is invalid') from None
        if error.code == 429:
            raise ValueError('EasyKOL is rate-limiting the request or the account has insufficient credits; try again later') from None
        raise ValueError(f'The EasyKOL creator endpoint returned HTTP {error.code}') from None
    except (urllib.error.URLError, TimeoutError):
        raise ValueError('The EasyKOL creator request failed; check your credits before submitting it again') from None
    if not isinstance(result, dict) or result.get('statusCode') != 1000 or not isinstance(result.get('data'), dict):
        raise ValueError('EasyKOL did not return a valid creator profile')
    data = result['data']
    if str(data.get('platform', '')).upper() != 'TIKTOK':
        raise ValueError('Personalization currently accepts TikTok creators only')
    return {
        'name': str(data.get('nickname') or data.get('username') or '')[:500],
        'username': str(data.get('username') or '')[:500],
        'profile_url': str(data.get('url') or profile_url)[:2000],
        'description': str(data.get('description') or '')[:5000],
        'one_line_pitch': str(data.get('oneLinePitch') or '')[:2000],
        'ai_tags': str(data.get('aiTags') or '')[:2000],
        'followers': data.get('followerCount') or 0,
        'region': str(data.get('region') or '')[:100],
        'language': str(data.get('language') or '')[:100],
        'average_play_count': data.get('averagePlayCount') or 0
    }


def _response_text(result):
    pieces = []
    for item in result.get('output', []):
        if item.get('type') != 'message':
            continue
        for part in item.get('content', []):
            if part.get('type') == 'output_text':
                pieces.append(part.get('text', ''))
    text = ''.join(pieces).strip()
    if not text:
        raise ValueError('The AI service did not return personalized copy')
    return text


def call_ai(creator, videos, brand):
    cfg = o.load_config()
    api_key = os.environ.get('OPENAI_API_KEY') or cfg.get('openai_key')
    model = os.environ.get('OPENAI_MODEL') or cfg.get('openai_model')
    if not api_key or not model:
        raise ValueError('No AI API key and model are configured; you can still edit the email manually')

    source = {'creator': {k: str(creator.get(k, ''))[:5000]
                           for k in ('name', 'username', 'profile_url', 'description',
                                     'one_line_pitch', 'ai_tags', 'followers', 'region',
                                     'language', 'average_play_count')},
              'brand': brand, 'recent_videos': videos[:5]}
    schema = {
        'type': 'object', 'additionalProperties': False, 'required': ['options'],
        'properties': {'options': {'type': 'array', 'minItems': 3, 'maxItems': 3,
            'items': {'type': 'object', 'additionalProperties': False,
                'required': ['paragraph', 'reason', 'evidence_url'],
                'properties': {
                    'paragraph': {'type': 'string'}, 'reason': {'type': 'string'},
                    'evidence_url': {'type': 'string'}}}}}}
    payload = {
        'model': model,
        'instructions': (
            'Write exactly three short creator-outreach opening paragraphs in the requested language. '
            'Use only supplied facts. Each option must cite the supplied creator profile URL or one supplied video URL. '
            'If no videos are supplied, personalize from the profile description, one-line pitch, and tags without '
            'claiming to have seen a specific post. Never claim to have watched, liked, or understood anything not proven. '
            'Connect one specific content detail to the brand naturally; do not invent demographics, '
            'performance, product use, or personal opinions.'),
        'input': json.dumps(source, ensure_ascii=False),
        'text': {'format': {'type': 'json_schema', 'name': 'creator_personalization',
                            'strict': True, 'schema': schema}}}
    request = urllib.request.Request('https://api.openai.com/v1/responses',
        data=json.dumps(payload).encode('utf-8'), method='POST',
        headers={'Authorization': 'Bearer ' + api_key, 'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            result = json.load(response)
    except urllib.error.HTTPError as error:
        if error.code in (401, 403):
            raise ValueError('The AI API key is invalid or lacks permission') from None
        if error.code == 429:
            raise ValueError('The AI account has insufficient credits or is being rate-limited; try again later') from None
        raise ValueError('The AI service could not generate copy at this time') from None
    except (urllib.error.URLError, TimeoutError):
        raise ValueError('The AI service could not be reached; check the network and try again') from None
    try:
        output = json.loads(_response_text(result))
    except (json.JSONDecodeError, TypeError, KeyError):
        raise ValueError('The AI response format was invalid; try again') from None
    if not isinstance(output.get('options'), list) or len(output['options']) != 3:
        raise ValueError('The AI service did not return three opening options')
    allowed = {creator.get('profile_url')} | {video['url'] for video in videos}
    for option in output['options']:
        if option.get('evidence_url') not in allowed:
            raise ValueError('The AI cited information that was not provided, so the result was blocked')
    return output


def personalize(creator, data):
    if not creator:
        raise ValueError('The creator selected for personalization could not be found')
    cfg = o.load_config()
    if not ((os.environ.get('OPENAI_API_KEY') or cfg.get('openai_key'))
            and (os.environ.get('OPENAI_MODEL') or cfg.get('openai_model'))):
        raise ValueError('No AI API key and model are configured; you can still edit the email manually')
    creator = {**creator, **fetch_kol_details(creator.get('profile_url'))}
    supplied = str(data.get('recent_videos', '')).strip()
    videos = manual_videos(supplied) if supplied else []
    videos = [video if video.get('caption') else fetch_video_details(video['url']) for video in videos]
    brand = {
        'brand_name': str(data.get('brand_name', '')).strip()[:200],
        'product': str(data.get('product', '')).strip()[:1000],
        'campaign_goal': str(data.get('campaign_goal', '')).strip()[:2000],
        'offer': str(data.get('offer', '')).strip()[:1000],
        'language': str(data.get('language', 'English')).strip()[:100]
    }
    if not brand['brand_name'] or not brand['product'] or not brand['campaign_goal']:
        raise ValueError('Enter a brand name, product description, and campaign goal')
    return {'creator': creator, 'videos': videos, **call_ai(creator, videos, brand)}
