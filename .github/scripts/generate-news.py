#!/usr/bin/env python3
"""
6529 NEWS - AI News Generator
FIXED cards: SR Top 3, Memes Top 3, Minting Status, Sales Recap
CONDITIONAL: punk6529 activity, dive bar hot topic, new submissions
HEADLINE BAR: dive bar topics, pebbles market, high sales, sweeps
TICKER: 24h volume, 24h sales, floor, leaderboard
"""

import json
import os
import urllib.request
from datetime import datetime, timezone, timedelta

# === CONFIG ===
OPENROUTER_KEY = os.environ.get('OPENROUTER_KEY', '')
OPENSEA_KEY = os.environ.get('OPENSEA_KEY', '0763c7f2c4104d288f734c0f91602913')
AI_MODEL = 'google/gemma-3-27b-it:free'
GIST_ID = os.environ.get('GIST_ID', '')
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN', '')

MEMES_WAVE_ID = 'b6128077-ea78-4dd9-b381-52c4eadb2077'
SR_WAVE_ID = 'd22e3046-a00e-48b9-b245-a339a44c37cd'
DIVEBAR_WAVE_ID = 'b38288e6-ca9d-45ce-8323-3dc5e094f04e'
PUNK6529_HANDLE = 'punk6529'
PUNK6529_PFP = 'https://d3lqz0a4bldqgf.cloudfront.net/pfp/production/413e24a8-b2d2-4746-a10e-d66575d0043f.webp?d=1714229232938'

MEMES_CONTRACT = '0x33fd426905f149f8376e227d0c9d3340aad17af1'
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'data', 'waves-config.json')


def fetch_json(url, headers=None):
    req = urllib.request.Request(url)
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"  Fetch error: {e}")
        return None


def format_tdh(tdh):
    if tdh >= 1_000_000: return f"{tdh/1_000_000:.1f}M"
    if tdh >= 1_000: return f"{tdh/1_000:.0f}K"
    return str(tdh)


def ai_summarize(prompt_text, max_tokens=250):
    """Call AI for summarization. Returns None on failure."""
    if not OPENROUTER_KEY:
        return None
    try:
        body = json.dumps({
            'model': AI_MODEL,
            'messages': [{'role': 'user', 'content': prompt_text}],
            'max_tokens': max_tokens, 'temperature': 0.5
        }).encode()
        req = urllib.request.Request('https://openrouter.ai/api/v1/chat/completions',
            data=body, headers={'Authorization': f'Bearer {OPENROUTER_KEY}', 'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=30) as r:
            result = json.loads(r.read())
        return result['choices'][0]['message']['content'].strip()
    except Exception as e:
        print(f"  AI error: {e}")
        return None


# =============================================
# 1. TOP 3 LEADERBOARD (Memes + SuperRare)
# =============================================
def build_top3(wave_id, wave_name, category):
    print(f"Building top 3: {wave_name}...")
    all_ranked = []
    sn = 999999
    for _ in range(30):
        data = fetch_json(f'https://api.6529.io/api/drops?wave_id={wave_id}&drop_type=PARTICIPATION&limit=20&serial_no_less_than={sn}')
        if not data: break
        for d in data:
            if d.get('rank') is not None:
                media = d['parts'][0].get('media', []) if d.get('parts') else []
                all_ranked.append({
                    'rank': d['rank'], 'title': d.get('title') or 'Untitled',
                    'author': d['author']['handle'], 'tdh': d.get('realtime_rating', 0),
                    'voters': d.get('raters_count', 0),
                    'img': media[0]['url'] if media else None
                })
        sn = data[-1]['serial_no']
        if len(all_ranked) >= 10: break

    all_ranked.sort(key=lambda x: x['rank'])
    seen, top3 = set(), []
    for d in all_ranked:
        if d['author'] not in seen:
            seen.add(d['author'])
            top3.append(d)
        if len(top3) >= 3: break

    if not top3: return []
    image = {'url': top3[0]['img'], 'label': f"#{top3[0]['rank']} {top3[0]['title']}"} if top3[0].get('img') else None
    return [{
        'category': category,
        'headline': f"#{top3[0]['rank']} {top3[0]['author']} Leads with {format_tdh(top3[0]['tdh'])} TDH",
        'summary': ' | '.join([f"#{s['rank']} \"{s['title']}\" by {s['author']} ({format_tdh(s['tdh'])} TDH, {s['voters']} voters)" for s in top3]),
        'source': wave_name,
        'link': f'https://6529.io/waves/{wave_id}',
        'image': image,
        'dataBoxes': [{'label': f"#{s['rank']} {s['author']}", 'value': format_tdh(s['tdh']), 'sub': f"TDH ({s['voters']} votes)"} for s in top3]
    }]


# =============================================
# 2. MINTING STATUS
# =============================================
def build_minting_status():
    print("Checking minting status...")
    now = datetime.now(timezone.utc)
    mint_days = {0: 'Monday', 2: 'Wednesday', 4: 'Friday'}

    # Find next mint day
    for i in range(7):
        d = now + timedelta(days=i)
        if d.weekday() in mint_days:
            mint_date = d.replace(hour=0, minute=0, second=0, microsecond=0)
            checkpoint = mint_date - timedelta(days=2)
            checkpoint = checkpoint.replace(hour=17, minute=0, second=0, microsecond=0)

            if d.date() == now.date():
                headline = f"MINTING TODAY - {mint_days[d.weekday()]}"
                summary = "A new Meme Card is being minted today! The winner was selected at the checkpoint 2 days ago."
                cat = 'MINTING TODAY'
            else:
                days_left = (mint_date - now).days
                headline = f"Next Mint: {mint_days[d.weekday()]} ({d.strftime('%b %d')})"
                summary = f"Next Meme Card mint in {days_left} day{'s' if days_left != 1 else ''}. Checkpoint: {checkpoint.strftime('%a %b %d at %H:%M UTC')}."
                cat = 'MINTING SOON'

            return [{
                'category': cat,
                'headline': headline,
                'summary': summary,
                'source': 'The Memes', 'link': 'https://6529.io/the-memes',
                'image': None, 'dataBoxes': None
            }]
    return []


# =============================================
# 3. SALES RECAP (24h)
# =============================================
def build_sales_recap():
    print("Building sales recap...")
    stats = fetch_json(f'https://api.opensea.io/api/v2/collections/thememes6529/stats', {'X-API-KEY': OPENSEA_KEY})
    sales_data = fetch_json(f'https://api.opensea.io/api/v2/events/collection/thememes6529?event_type=sale&limit=50', {'X-API-KEY': OPENSEA_KEY})

    if not stats: return [], [], []

    floor = stats['total'].get('floor_price', 0)
    floor_sym = stats['total'].get('floor_price_symbol', 'ETH')
    vol_24h = stats['intervals'][0].get('volume', 0) if stats.get('intervals') else 0
    sales_24h = stats['intervals'][0].get('sales', 0) if stats.get('intervals') else 0

    highest = {'name': '', 'price': 0}
    high_sales = []  # Sales > 0.3 ETH
    sweeps = {}  # card_id -> count (detect sweeps)
    headline_extras = []

    if sales_data and 'asset_events' in sales_data:
        for e in sales_data['asset_events']:
            price = int(e['payment']['quantity']) / 1e18
            name = e['nft']['name']
            card_id = e['nft']['identifier']

            if price > highest['price']:
                highest = {'name': name, 'price': price}
            if price >= 0.3:
                high_sales.append(f'"{name}" {price:.3f} ETH')
            sweeps[card_id] = sweeps.get(card_id, 0) + 1

    # Detect sweeps (5+ sales of same card)
    sweep_cards = [(cid, cnt) for cid, cnt in sweeps.items() if cnt >= 5]

    summary = f'{sales_24h} sales in 24h for {vol_24h:.2f} ETH.'
    if highest['price'] > 0:
        summary += f' Highest: "{highest["name"]}" at {highest["price"]:.3f} ETH.'
    if sweep_cards:
        summary += f' Sweep detected: {len(sweep_cards)} card(s) with 5+ sales.'

    news = [{
        'category': 'SALES RECAP',
        'headline': f'{sales_24h} Sales Today - {vol_24h:.2f} ETH Volume',
        'summary': summary,
        'source': 'OpenSea', 'link': 'https://opensea.io/collection/thememes6529',
        'image': None,
        'dataBoxes': [
            {'label': 'Sales 24h', 'value': str(sales_24h), 'sub': ''},
            {'label': 'Volume 24h', 'value': f'{vol_24h:.2f}', 'sub': 'ETH'},
            {'label': 'Top Sale', 'value': f'{highest["price"]:.3f}', 'sub': highest['name'][:20] if highest['name'] else ''},
            {'label': 'Floor', 'value': str(floor), 'sub': floor_sym}
        ]
    }]

    # Build headline extras for the NEWS bar
    if high_sales:
        headline_extras.append(f"HIGH SALE: {high_sales[0]}")
    for cid, cnt in sweep_cards[:1]:
        headline_extras.append(f"SWEEP ALERT: CARD #{cid} - {cnt} SALES IN 24H")

    # Pebbles market for headline
    pebbles = fetch_json('https://api.opensea.io/api/v2/collections/pebbles-by-zeblocks/stats', {'X-API-KEY': OPENSEA_KEY})
    if pebbles:
        p_floor = pebbles['total'].get('floor_price', 0)
        p_vol = pebbles['intervals'][0].get('volume', 0) if pebbles.get('intervals') else 0
        headline_extras.append(f"PEBBLES: FLOOR {p_floor} ETH | 24H VOL {p_vol:.2f} ETH")

    ticker_data = [{
        'name': 'Memes', 'floor': floor, 'floor_sym': floor_sym,
        'vol_24h': vol_24h, 'sales_24h': sales_24h
    }]

    return news, headline_extras, ticker_data


# =============================================
# 4. PUNK6529 (conditional: wrote in last 24h)
# =============================================
def build_punk6529():
    print("Checking punk6529...")
    drops = fetch_json(f'https://api.6529.io/api/drops?author={PUNK6529_HANDLE}&limit=20')
    if not drops: return [], []

    now_ms = datetime.now(timezone.utc).timestamp() * 1000
    twenty_four_h = now_ms - 24 * 3600 * 1000
    recent = [d for d in drops if d['created_at'] > twenty_four_h]

    headline_extra = []

    if not recent:
        # Last seen
        last = drops[0]
        last_dt = datetime.fromtimestamp(last['created_at']/1000, tz=timezone.utc)
        wave_name = last.get('wave', {}).get('name', 'unknown')
        headline_extra.append(f"6529 LAST SEEN: {wave_name} ({last_dt.strftime('%b %d %H:%M UTC')})")
        return [], headline_extra

    if len(recent) < 5:
        print(f"  Only {len(recent)} msgs in 24h (need 5+)")
        headline_extra.append(f"PUNK6529: {len(recent)} MESSAGES TODAY")
        return [], headline_extra

    # Get messages for AI summary
    messages = []
    waves_active = set()
    for d in recent[:15]:
        content = (d['parts'][0].get('content') or '')[:200] if d.get('parts') else ''
        waves_active.add(d.get('wave', {}).get('name', '?'))
        if content and len(content) > 20:
            messages.append(content)

    summary = ai_summarize(
        f"Summarize what punk6529 (a key figure in the 6529 NFT community) talked about in these messages. 2-3 sentences, factual:\n\n" +
        '\n'.join([f'- {m}' for m in messages[:8]])
    )
    if not summary:
        best = [m for m in messages if len(m) > 40][:2]
        summary = f'punk6529 posted {len(recent)} messages in {", ".join(waves_active)}. ' + ' | '.join([f'"{q[:80]}"' for q in best])

    print(f"  Active: {len(recent)} msgs")
    return [{
        'category': '6529 TALKS',
        'headline': f'punk6529: {len(recent)} Messages Today',
        'summary': summary,
        'source': list(waves_active)[0] if waves_active else 'Network',
        'link': 'https://6529.io/punk6529',
        'image': {'url': PUNK6529_PFP, 'label': 'punk6529'},
        'dataBoxes': None
    }], []


# =============================================
# 5. MAYBE'S DIVE BAR HOT TOPIC (100+ msgs in 30 min window)
# =============================================
def build_divebar_hot():
    print("Checking dive bar hot topics...")
    drops = fetch_json(f'https://api.6529.io/api/drops?wave_id={DIVEBAR_WAVE_ID}&limit=20')
    if not drops: return [], []

    now_ms = datetime.now(timezone.utc).timestamp() * 1000
    twenty_four_h = now_ms - 24 * 3600 * 1000
    recent_24h = [d for d in drops if d['created_at'] > twenty_four_h]

    # Check if there's a burst (many messages in short time)
    # With only 20 drops we check if all 20 happened in <30 min
    headline_extras = []

    if len(recent_24h) >= 15:
        times = [d['created_at'] for d in recent_24h]
        span_min = (times[0] - times[-1]) / 60000
        msgs_per_hour = len(recent_24h) / (span_min / 60) if span_min > 0 else 0

        if msgs_per_hour >= 40:  # Very active
            messages = []
            authors = set()
            for d in recent_24h[:15]:
                content = (d['parts'][0].get('content') or '')[:150] if d.get('parts') else ''
                author = d.get('author', {}).get('handle', '?')
                if content and len(content) > 15:
                    messages.append(f'{author}: {content}')
                    authors.add(author)

            summary = ai_summarize(
                f"Summarize the key topics from these chat messages in maybe's dive bar (6529 NFT community). 2-3 sentences:\n\n" +
                '\n'.join(messages[:10])
            )
            if not summary:
                summary = f"{len(recent_24h)} messages, {len(authors)} participants. " + ' | '.join(messages[:3])

            # Headline extra about dive bar
            headline_extras.append(f"DIVE BAR: {int(msgs_per_hour)} MSG/H - {len(authors)} PEOPLE TALKING")

            return [{
                'category': 'DIVE BAR',
                'headline': f"Hot Topic: {int(msgs_per_hour)} Messages/Hour in the Dive Bar",
                'summary': summary,
                'source': "maybe's dive bar",
                'link': f'https://6529.io/waves/{DIVEBAR_WAVE_ID}',
                'image': None, 'dataBoxes': None
            }], headline_extras
        else:
            # Not hot enough for a card, but add to headline
            headline_extras.append(f"DIVE BAR: {int(msgs_per_hour)} MSG/H TODAY")

    return [], headline_extras


# =============================================
# 6. NEW SUBMISSIONS (24h, best by TDH)
# =============================================
def build_new_submissions():
    print("Checking new submissions...")
    midnight_ms = int(datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000)

    data = fetch_json(f'https://api.6529.io/api/drops?wave_id={MEMES_WAVE_ID}&drop_type=PARTICIPATION&limit=20')
    if not data: return []

    today = []
    for d in data:
        if d['created_at'] >= midnight_ms:
            media = d['parts'][0].get('media', []) if d.get('parts') else []
            today.append({
                'title': d.get('title') or 'Untitled',
                'author': d['author']['handle'],
                'tdh': d.get('realtime_rating', 0),
                'img': media[0]['url'] if media else None
            })

    if not today: return []

    # Sort by TDH, show the top one
    today.sort(key=lambda x: x['tdh'], reverse=True)
    best = today[0]
    count = len(today)

    summary = f'{count} new submission{"s" if count > 1 else ""} today.'
    if count > 1:
        others = ', '.join([f'{s["author"]}' for s in today[1:4]])
        summary += f' Also: {others}.'
    summary += f' Top: "{best["title"]}" by {best["author"]} ({format_tdh(best["tdh"])} TDH).'

    image = {'url': best['img'], 'label': f'{best["title"]} - {best["author"]}'} if best.get('img') else None

    print(f"  {count} submissions, best: {best['author']} ({format_tdh(best['tdh'])})")
    return [{
        'category': 'NEW SUBMISSIONS',
        'headline': f'{count} New Submission{"s" if count > 1 else ""} Today',
        'summary': summary,
        'source': 'Main Stage',
        'link': f'https://6529.io/waves/{MEMES_WAVE_ID}',
        'image': image, 'dataBoxes': None
    }]


# =============================================
# OUTPUT
# =============================================
def build_output(news, ticker_data, headline_extras):
    ticker = []
    for m in ticker_data:
        ticker.append({'label': f"{m['name']} Floor", 'value': f"{m['floor']} {m['floor_sym']}"})
        if m.get('vol_24h', 0) > 0:
            ticker.append({'label': f"24h Volume", 'value': f"{m['vol_24h']:.2f} ETH"})
        if m.get('sales_24h', 0) > 0:
            ticker.append({'label': f"24h Sales", 'value': f"{m['sales_24h']}"})

    return {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'model': AI_MODEL,
        'news': news[:10],
        'ticker': ticker,
        'headline_extras': headline_extras[:8]
    }


def update_gist(output):
    if not GITHUB_TOKEN or not GIST_ID: return
    body = json.dumps({'files': {'news-latest.json': {'content': json.dumps(output, indent=2)}}}).encode()
    req = urllib.request.Request(f'https://api.github.com/gists/{GIST_ID}', data=body, method='PATCH',
        headers={'Authorization': f'Bearer {GITHUB_TOKEN}', 'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req) as r: print("Gist updated")
    except Exception as e: print(f"Gist error: {e}")


# =============================================
# MAIN
# =============================================
def main():
    print(f"=== 6529 NEWS Generator ===")
    print(f"Time: {datetime.now(timezone.utc).isoformat()}")

    all_news = []
    all_headlines = []

    # --- FIXED CARDS ---
    print("\n--- SR Top 3 ---")
    all_news += build_top3(SR_WAVE_ID, 'SuperRare x 6529', 'SUPERRARE TOP 3')

    print("\n--- Memes Top 3 ---")
    all_news += build_top3(MEMES_WAVE_ID, 'The Memes - Main Stage', 'MAIN STAGE TOP 3')

    print("\n--- Minting Status ---")
    all_news += build_minting_status()

    print("\n--- Sales Recap ---")
    sales_news, sales_headlines, ticker_data = build_sales_recap()
    all_news += sales_news
    all_headlines += sales_headlines

    # --- CONDITIONAL CARDS ---
    print("\n--- punk6529 ---")
    p6529_news, p6529_headlines = build_punk6529()
    all_news += p6529_news
    all_headlines += p6529_headlines

    print("\n--- Dive Bar ---")
    bar_news, bar_headlines = build_divebar_hot()
    all_news += bar_news
    all_headlines += bar_headlines

    print("\n--- New Submissions ---")
    all_news += build_new_submissions()

    # --- BUILD OUTPUT ---
    output = build_output(all_news, ticker_data, all_headlines)
    print(f"\n--- Total: {len(output['news'])} cards, {len(output['headline_extras'])} headline extras ---")

    # --- PUBLISH ---
    update_gist(output)
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'data', 'news-latest.json')
    with open(out_path, 'w') as f:
        json.dump(output, f, indent=2)
    print(f"Written to {out_path}\nDone!")


if __name__ == '__main__':
    main()
