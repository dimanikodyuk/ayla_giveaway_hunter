"""Conservative, explainable giveaway detection and deadline extraction."""
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from urllib.parse import urlparse

KYIV=ZoneInfo('Europe/Kyiv')
MONTHS={'січня':1,'января':1,'лютого':2,'февраля':2,'березня':3,'марта':3,'квітня':4,'апреля':4,'травня':5,'мая':5,'червня':6,'июня':6,'липня':7,'июля':7,'серпня':8,'августа':8,'вересня':9,'сентября':9,'жовтня':10,'октября':10,'листопада':11,'ноября':11,'грудня':12,'декабря':12}
TASKS=[('Підписатися на канал',('підписат','подписат','subscribe','join channel')),('Натиснути кнопку участі',('натисніть кнопку','нажмите кнопку','click participate','join giveaway')),('Залишити коментар',('коментар','комментар','comment')),('Поставити вподобайку',('лайк','like post'))]
DANGER=('seed phrase','seed-фраз','приватний ключ','private key','cvv','код із sms','код з sms')
PAID=('депозит для участі','платна участь','entry fee','deposit required','купіть квиток для участі')
DIRECT=('щоб виграти','щоб взяти участь','для участі','умови розіграшу','беріть участь','розігруємо','розыгрываем','участвуйте','условия розыгрыша','to enter the giveaway','enter to win','participate in the giveaway','giveaway ends','розіграш опублікуємо')
MENTION=('розіграш','розыгрыш','giveaway','raffle','виграти','win a ','win an ','даруємо','разыграем')
NEWS=('це розіграш для мешканців сша','розіграш для мешканців сша','giveaway for us residents','не доступна','not available for sale','це реальна штука')
AD=('замість ','знижк','скидк','купуйте','обирайте','вибирайте','ціна ','грн замість','shop now','sale ') 

def normalize_url(value):
    value=value.strip()
    if not value:raise ValueError('URL is required')
    if '://' not in value:value='https://'+value
    u=urlparse(value)
    if u.scheme not in ('https','http') or not u.hostname or u.username or u.password or any(c.isspace() for c in value):raise ValueError('Invalid URL')
    if u.hostname=='localhost' or u.hostname.endswith('.local'):raise ValueError('Local URL not allowed')
    return value

def extract_dates(text, published_at=None):
    """Return separately labelled events; never infer entry deadline from winner draw."""
    if isinstance(published_at,str):
        try:published_at=datetime.fromisoformat(published_at.replace('Z','+00:00'))
        except ValueError:published_at=None
    anchor=(published_at or datetime.now(timezone.utc))
    if anchor.tzinfo is None:anchor=anchor.replace(tzinfo=timezone.utc)
    anchor=anchor.astimezone(KYIV)
    found=[]
    pattern=r'(?:(сьогодні|завтра|today|tomorrow)|(\d{1,2})[.\/](\d{1,2})(?:[.\/](\d{4}))?|(\d{1,2})\s+('+'|'.join(MONTHS)+r'))(?:\s*(?:року|года|р\.)?)\s*(?:о|в|at)?\s*(\d{1,2})[:.](\d{2})'
    for m in re.finditer(pattern,text,re.I):
        try:
            if m.group(1):d=anchor.date()+timedelta(days=1 if m.group(1).lower() in ('завтра','tomorrow') else 0)
            elif m.group(2):d=anchor.date().replace(year=int(m.group(4) or anchor.year),month=int(m.group(3)),day=int(m.group(2)))
            else:d=anchor.date().replace(month=MONTHS[m.group(6).lower()],day=int(m.group(5)))
            dt=datetime(d.year,d.month,d.day,int(m.group(7)),int(m.group(8)),tzinfo=KYIV)
        except ValueError:continue
        context=text[max(0,m.start()-95):min(len(text),m.end()+90)].lower()
        after=re.split(r'[.!?\n]',text[m.end():min(len(text),m.end()+85)],maxsplit=1)[0].lower()
        if any(w in after for w in ('переможц','победител','winner','результат','рандомайзер','оберемо','виберемо')):kind='winner_selection'
        elif any(w in context for w in ('опублікуємо','опубликуем','старт','почат','starts','launch')):kind='announcement'
        elif any(w in context for w in ('до ','закінч','заверш','deadline','ends','until')):kind='entry_deadline'
        else:kind='unclassified'
        found.append({'kind':kind,'at':dt.isoformat(),'phrase':m.group(0)})
    return found

def participation_hint(t):
    return any(p in t for p in ('підписатися','підпишіться','натиснути кнопку','натисніть кнопку','залишити коментар','поставити лайк','підписатись'))

def analyze(text,published_at=None,native=False):
    """Conservative, auditable classification. Review-only is NOT a giveaway."""
    t=(text or '').casefold()
    tasks=[label for label,phrases in TASKS if any(x in t for x in phrases)]
    danger=any(x in t for x in DANGER)
    paid=any(x in t for x in PAID) or bool(re.search(
        r'(?:для участі|щоб взяти участь|для участия|щоб виграти).{0,120}(?:куп[иі]|придба|оформ[иі]|оплат|замов|покуп|депозит|внесок)',t,re.S)) or bool(re.search(
        r'(?:куп[иі]|придба|оформ[иі]|оплат|замов).{0,120}(?:для участі|щоб взяти участь|розіграш)',t,re.S))
    free=not paid and (native or bool(tasks) or participation_hint(t))
    direct=any(x in t for x in DIRECT)
    mention=any(x in t for x in MENTION)
    # Explicitly reported false positives, plus broad sales/news indicators.
    sales=any(x in t for x in AD) or any(x in t for x in (
        'оновлюйте кухню', 'ще більшою вигодою', 'зігрівайтеся',
        'вибирайте обігрівачі', 'обирайте обігрівачі',
        'акційна ціна', 'ціни від', 'промокод на знижку'))
    news=any(x in t for x in NEWS) or any(x in t for x in (
        'консоль-алігатор', 'x-bite', 'для мешканців сша',
        'для жителей сша', 'лише для жителів сша',
        'тільки для мешканців сша', 'only for us residents'))
    participation=bool(tasks) or any(x in t for x in (
        'щоб виграти','щоб взяти участь','для участі','умови розіграшу',
        'беріть участь','участвуйте','условия розыгрыша',
        'to enter the giveaway','enter to win','join giveaway',
        'для участі потрібно','для участия нужно'))
    # "розіграш опублікуємо" alone is an announcement, not open participation.
    if native:
        category,confidence,reason='NATIVE_GIVEAWAY',99,'Вбудований розіграш Telegram'
    elif news:
        category,confidence,reason='NEWS',95,'Новина про сторонній або недоступний розіграш'
    elif sales and not participation:
        category,confidence,reason='ADVERTISEMENT',96,'Реклама товарів або знижок без умов участі'
    elif participation and (direct or mention):
        category,confidence,reason='GIVEAWAY',93 if tasks else 82,'Є умови або інструкція участі'
    elif mention:
        category,confidence,reason='REVIEW',40,'Згадка розіграшу без підтвердженої механіки участі'
    else:
        category,confidence,reason='OTHER',96,'Ознак доступного розіграшу немає'
    if danger or paid:reason+='; небезпечна або платна умова'
    return {
        'candidate':category in ('GIVEAWAY','NATIVE_GIVEAWAY') and not (danger or paid),
        'category':category,'confidence':confidence,'reason':reason,
        'review_status':'REJECTED' if danger or paid else 'REVIEW',
        'risk_score':95 if danger else 85 if paid else 35,
        'tasks':tasks,'dates':extract_dates(text,published_at),
        'entry_cost':'paid' if paid else 'free' if free else 'unknown'
    }
