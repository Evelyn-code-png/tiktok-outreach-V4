"""Optional, user-triggered provider photo lookups with a local cache."""
import hashlib
import json
import threading
import time
import outreach as o
import personalization

LOCK = threading.Lock()
TTL = 7 * 86400

def cache_path(profile):
    return o.ROOT / 'creator-photos' / (hashlib.sha256(profile.encode()).hexdigest() + '.json')

def cached(profile):
    try:
        data = json.loads(cache_path(profile).read_text())
        if time.time() - data['saved'] < TTL: return data
    except (OSError, ValueError, KeyError, TypeError): pass
    return None

def enrich(rows, directory):
    photos = {}
    for file in directory.glob('raw-*.json'):
        try:
            raw = json.loads(file.read_text())
            items = raw.get('data', []) if isinstance(raw, dict) else raw
            if not isinstance(items, list): continue
            for row in items:
                if isinstance(row, dict):
                    photos[row.get('profileUrl') or row.get('profile_url')] = o.avatar_url(row)
        except (OSError, ValueError): continue
    for row in rows:
        profile = row.get('profile_url', '')
        photo = cached(profile) if profile else None
        row['avatar_url'] = o.avatar_url(row) or photos.get(profile, '') or (o.avatar_url(photo) if photo else '')

def resolve(data):
    import workspace as w
    profile = personalization.valid_tiktok_url(data.get('profile_url'))
    run = w.get_run(data.get('run_id'))
    if not any(row.get('profile_url') == profile for row in run['contacts']):
        raise ValueError('Choose a creator from the saved contact list.')
    with LOCK:
        existing = cached(profile)
        if existing is not None: return {'avatar_url': o.avatar_url(existing), 'cached': True}
        details = personalization.fetch_kol_details(profile)
        photo = o.avatar_url(details)
        path = cache_path(profile)
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        o.save_json(path, {'avatar_url': photo, 'saved': time.time()})
        return {'avatar_url': photo, 'cached': False}
