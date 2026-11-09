"""Safe, version-tolerant Telegram giveaway metadata extraction."""
import json
from datetime import datetime, timezone


def extract(message):
    media = getattr(message, 'media', None)
    action = getattr(message, 'action', None)
    obj = media if media and 'Giveaway' in type(media).__name__ else action if action and 'Giveaway' in type(action).__name__ else None
    if obj is None:
        return None
    result = {'kind': type(obj).__name__}
    for key in ('quantity', 'months', 'prize_description', 'countries_iso2', 'channels', 'only_new_subscribers', 'winners_are_visible', 'stars', 'winner_count', 'winners_count'):
        value = getattr(obj, key, None)
        if value is None: continue
        if key == 'channels':
            result[key] = [int(v) for v in value if isinstance(v, int)]
        elif isinstance(value, (str, int, float, bool)):
            result[key] = value
        elif isinstance(value, (list, tuple)) and all(isinstance(x, str) for x in value):
            result[key] = list(value)
    dt = getattr(obj, 'until_date', None)
    if isinstance(dt, datetime):
        if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
        result['until_date'] = dt.astimezone(timezone.utc).isoformat()
    return result


def is_ended(metadata, now=None):
    if not metadata or not metadata.get('until_date'): return False
    dt = datetime.fromisoformat(metadata['until_date'].replace('Z', '+00:00'))
    return dt <= (now or datetime.now(timezone.utc))


def metadata_title(metadata):
    if not metadata: return 'Вбудований розіграш Telegram'
    prize = metadata.get('prize_description')
    if prize: return ('Telegram Giveaway: ' + str(prize))[:190]
    months, qty = metadata.get('months'), metadata.get('quantity')
    if months and qty: return f'Telegram Giveaway: {qty} × Premium на {months} міс.'
    return 'Вбудований розіграш Telegram'


def serialize(metadata):
    return json.dumps(metadata, ensure_ascii=False, separators=(',', ':')) if metadata else None
