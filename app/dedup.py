import re
from datetime import datetime,timezone
from difflib import SequenceMatcher

def find_linked_giveaway(c,sid,text,published_at,native,exclude_id=None):
    """Conservative: only adjacent messages in same channel and <=48h.
    Never merge two separate native giveaways or two text announcements.
    Generic native captions with no prize are ambiguous; require exactly one match.
    """
    if not published_at:return None
    try:stamp=datetime.fromisoformat(published_at.replace('Z','+00:00'))
    except ValueError:return None
    if stamp.tzinfo is None:stamp=stamp.replace(tzinfo=timezone.utc)
    rows=c.execute("""SELECT g.id,g.title,g.original_text,g.published_at,g.native_giveaway
        FROM giveaways g JOIN raw_items r ON r.id=g.raw_item_id
        WHERE r.source_id=? AND g.linked_giveaway_id IS NULL AND g.review_status!='REJECTED'
        ORDER BY g.id DESC LIMIT 50""",(sid,)).fetchall()
    matches=[]
    for row in rows:
        if row['id']==exclude_id or bool(row['native_giveaway'])==bool(native):continue
        try:other=datetime.fromisoformat(row['published_at'].replace('Z','+00:00'))
        except (TypeError,ValueError):continue
        if other.tzinfo is None:other=other.replace(tzinfo=timezone.utc)
        hours=abs((stamp-other).total_seconds())/3600
        if hours>48:continue
        a=re.sub(r'\W+',' ',text.lower()).strip()
        b=re.sub(r'\W+',' ',(row['original_text'] or '').lower()).strip()
        # A generic native giveaway must be very close to the announcement.
        generic=('вбудован' in a or 'telegram giveaway' in a or len(a)<35 or
                 'вбудован' in b or 'telegram giveaway' in b or len(b)<35)
        if generic:
            if hours<=4:matches.append((hours,row['id'],'native_near_announcement'))
        elif SequenceMatcher(None,a[:400],b[:400]).ratio()>=0.73:
            matches.append((hours,row['id'],'similar_announcement'))
    # Ambiguity is safer than merging two independent giveaways.
    if len(matches)!=1:return None
    _,gid,reason=matches[0]
    return gid,reason

