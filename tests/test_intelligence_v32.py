"""Offline v3.2 smoke tests; never touch production SQLite."""
import os
from app.intelligence import channel_mentions, giveaway_score, risk_assessment

def test_risk_and_score():
    danger=risk_assessment('Для виграшу введіть seed phrase')
    assert danger['risk_score'] >= 80
    assert 'seed_phrase' in danger['signals']
    g={'entry_cost':'free','review_status':'APPROVED','task_count':1,'winner_at':None,'linked_giveaway_id':None}
    assert giveaway_score(g,'Підпишіться')['score'] >= 70
    assert not giveaway_score(g,'Підпишіться')['is_win_probability']

def test_discovery_links():
    result=channel_mentions('https://t.me/channel_alpha and t.me/channel_alpha and https://t.me/other_channel/123')
    assert result == {'channel_alpha'}
