"""Lightweight, explainable intelligence for Raspberry Pi 4 (no paid AI API)."""
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

CHANNEL_RE = re.compile(r"(?<![\w/])(?:https?://)?(?:t\.me|telegram\.me)/([A-Za-z][A-Za-z0-9_]{4,31})(?![\w])", re.I)
RISK_RULES = (
    ('seed_phrase', 90, ('seed phrase', 'seed-фраз', 'сид фраз', 'private key', 'приватний ключ', 'секретн')), 
    ('payment', 65, ('оплатіть доставку', 'оплатите доставку', 'передоплат', 'платна участь', 'депозит для участі', 'entry fee', 'deposit required')),
    ('credentials', 80, ('пароль від telegram', 'пароль телеграм', 'код із sms', 'код з sms', 'cvv', '2fa code')),
    ('guaranteed', 25, ('гарантований виграш', 'гарантированно выигра', 'guaranteed win')),
    ('external_login', 20, ('авторизуйтесь за посиланням', 'увійдіть через сайт', 'войдите через сайт')),
)

def channel_mentions(text):
    """Only public channel-shaped usernames; no joining, no scraping arbitrary links."""
    found = set()
    for m in CHANNEL_RE.finditer(text or ''):
        username = m.group(1)
        if username.casefold() in ('share', 'addstickers', 'joinchat', 'proxy', 'socks', 'iv', 'login', 'addemoji'):
            continue
        # Ignore message links only if path contains a numeric message ID.
        tail = (text or '')[m.end():m.end()+20]
        if re.match(r'/\d+(?:\b|[/?#])', tail):
            continue
        found.add(username.lower())
    return found

def risk_assessment(text, entry_cost='unknown', existing_risk=0):
    t = (text or '').casefold()
    signals = []
    risk = 0
    for code, weight, phrases in RISK_RULES:
        if any(phrase in t for phrase in phrases):
            signals.append(code)
            risk += weight
    if entry_cost == 'paid' and 'payment' not in signals:
        signals.append('paid_entry')
        risk += 55
    # Do not mistake legacy risk_score=35 (default for all candidates) for an observed threat.
    if not t and existing_risk >= 75:
        signals.append('legacy_risk_unverified')
    risk = min(100, risk)
    return {'risk_score':risk, 'signals':signals, 'explanation':'Виявлено конкретні ризикові фрази' if signals else 'Явних текстових сигналів ризику не знайдено; це не гарантія безпеки'}

def giveaway_score(row, text='', source_approved=None):
    """Heuristic priority score, NOT win probability or machine-learned prediction."""
    risk = risk_assessment(text, row.get('entry_cost','unknown'), row.get('risk_score',0))
    score = 45
    reasons = []
    if row.get('entry_cost') == 'free':
        score += 15; reasons.append('Безкоштовна участь +15')
    elif row.get('entry_cost') == 'paid':
        score -= 30; reasons.append('Платна участь −30')
    tasks = row.get('task_count') or 0
    if tasks == 1: score += 10; reasons.append('Одна умова +10')
    elif tasks >= 4: score -= 12; reasons.append('Багато умов −12')
    if row.get('review_status') == 'APPROVED':
        score += 10; reasons.append('Ручне підтвердження +10')
    if row.get('linked_giveaway_id'):
        score -= 25; reasons.append('Повторна публікація −25')
    if row.get('winner_at'):
        try:
            d=datetime.fromisoformat(row['winner_at'].replace('Z','+00:00'))
            if d.tzinfo is None: d=d.replace(tzinfo=timezone.utc)
            if d < datetime.now(timezone.utc): score -= 15; reasons.append('Дата результату минула −15')
        except ValueError: pass
    score -= round(risk['risk_score'] * .65)
    if risk['risk_score']: reasons.append('Текстові ризики −'+str(round(risk['risk_score']*.65)))
    score = max(0,min(100,score))
    return {'score':score,'label':'Високий пріоритет' if score>=75 else 'Середній пріоритет' if score>=45 else 'Низький пріоритет',
            'method':'rules_v1', 'is_win_probability':False, 'reasons':reasons,'scam':risk}
