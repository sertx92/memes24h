#!/usr/bin/env python3
"""
MEMES 24H - AI News Generator
Always includes: Market Recap, Top 3 Memes, Top 3 SuperRare
Then adds up to 10 additional AI-generated news.
Filters out low-activity waves (<3 msgs in 6h).
"""

import json
import os
import sys
import urllib.request
from datetime import datetime, timezone, timedelta

# === CONFIG ===
OPENROUTER_KEY = os.environ.get('OPENROUTER_KEY', '')
OPENSEA_KEY = os.environ.get('OPENSEA_KEY', '0763c7f2c4104d288f734c0f91602913')
AI_MODEL = 'google/gemma-3-27b-it:free'
GIST_ID = os.environ.get('GIST_ID', '1b84f8b762cd2f6640ed7086cc9b7c69')
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN', '')
MIN_MSGS_6H = 3  # Minimum messages in 6 hours to be newsworthy

MEMES_WAVE_ID = 'b6128077-ea78-4dd9-b381-52c4eadb2077'
SR_WAVE_ID = 'd22e3046-a00e-48b9-b245-a339a44c37cd'
TDH_MILLIONAIRES_WAVE_ID = '9cc8118b-0ae0-4b22-8d15-3b8ed6604bac'

# punk6529 tracking
PUNK6529_HANDLE = 'punk6529'
PUNK6529_PFP = 'https://d3lqz0a4bldqgf.cloudfront.net/pfp/production/413e24a8-b2d2-4746-a10e-d66575d0043f.webp?d=1714229232938'
PUNK6529_MIN_MSGS = 5  # 5+ msgs in 6h = "6529 Talks about"

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'data', 'waves-config.json')


# === API HELPERS ===
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


def fetch_6529_drops(wave_id, limit=20):
    return fetch_json(f'https://api.6529.io/api/drops?wave_id={wave_id}&limit={limit}') or []


def fetch_ranked_submissions(wave_id, pages=30):
    """Fetch top ranked submissions from a wave."""
    all_ranked = []
    sn = 999999
    for _ in range(pages):
        data = fetch_json(f'https://api.6529.io/api/drops?wave_id={wave_id}&drop_type=PARTICIPATION&limit=20&serial_no_less_than={sn}')
        if not data:
            break
        for d in data:
            if d.get('rank') is not None:
                media = d['parts'][0].get('media', []) if d.get('parts') else []
                all_ranked.append({
                    'rank': d['rank'],
                    'title': d.get('title') or (d['parts'][0].get('content', '')[:40] if d.get('parts') else 'Untitled'),
                    'author': d['author']['handle'],
                    'tdh': d.get('realtime_rating', 0),
                    'voters': d.get('raters_count', 0),
                    'img': media[0]['url'] if media else None,
                    'drop_id': d['id'],
                    'wave_id': wave_id
                })
        sn = data[-1]['serial_no']
        if len(all_ranked) >= 10:
            break

    # Deduplicate and sort by rank
    all_ranked.sort(key=lambda x: x['rank'])
    seen = set()
    unique = []
    for d in all_ranked:
        key = f"{d['rank']}-{d['author']}"
        if key not in seen:
            seen.add(key)
            unique.append(d)
    return unique


def fetch_opensea_stats(slug):
    return fetch_json(f'https://api.opensea.io/api/v2/collections/{slug}/stats', {'X-API-KEY': OPENSEA_KEY})


def fetch_opensea_sales(slug, limit=30):
    return fetch_json(f'https://api.opensea.io/api/v2/events/collection/{slug}?event_type=sale&limit={limit}', {'X-API-KEY': OPENSEA_KEY})


def format_tdh(tdh):
    if tdh >= 1_000_000:
        return f"{tdh / 1_000_000:.1f}M"
    if tdh >= 1_000:
        return f"{tdh / 1_000:.0f}K"
    return str(tdh)


# =============================================
# FIXED NEWS: Always generated (no AI needed)
# =============================================

def build_market_recap(collections):
    """FIXED: Market recap with sales, floor, volume, whales."""
    print("Building market recap...")
    news = []

    all_sales_text = []
    all_data_boxes = []
    all_whales = []

    for c in collections:
        stats = fetch_opensea_stats(c['slug'])
        if not stats:
            continue

        floor = stats['total'].get('floor_price', 0)
        floor_sym = stats['total'].get('floor_price_symbol', 'ETH')
        holders = stats['total'].get('num_owners', 0)
        vol_24h = stats['intervals'][0].get('volume', 0) if stats.get('intervals') else 0
        sales_24h = stats['intervals'][0].get('sales', 0) if stats.get('intervals') else 0
        vol_7d = stats['intervals'][1].get('volume', 0) if stats.get('intervals') and len(stats['intervals']) > 1 else 0

        all_data_boxes.append({'label': f"{c['name']} Floor", 'value': str(floor), 'sub': floor_sym})
        if sales_24h > 0:
            all_data_boxes.append({'label': f"{c['name']} 24h", 'value': f"{vol_24h:.2f}", 'sub': f'ETH ({sales_24h} sales)'})
            all_sales_text.append(f"{c['name']}: {sales_24h} sales, {vol_24h:.2f} ETH volume, floor {floor} {floor_sym}")
        else:
            all_sales_text.append(f"{c['name']}: no sales in 24h, floor {floor} {floor_sym}")

        # Whale detection
        sales_data = fetch_opensea_sales(c['slug'], 50)
        if sales_data and 'asset_events' in sales_data:
            buyers = {}
            notable_sales = []
            for e in sales_data['asset_events']:
                price = int(e['payment']['quantity']) / 1e18
                buyer = e['buyer']
                name = e['nft']['name']
                if price >= 0.1:  # Notable sale threshold
                    notable_sales.append(f'"{name}" for {price:.3f} ETH')
                if buyer not in buyers:
                    buyers[buyer] = {'count': 0, 'spent': 0, 'last': ''}
                buyers[buyer]['count'] += 1
                buyers[buyer]['spent'] += price
                if not buyers[buyer]['last']:
                    buyers[buyer]['last'] = name

            for addr, info in buyers.items():
                if info['count'] >= 3:
                    short = addr[:6] + '...' + addr[-4:]
                    all_whales.append({
                        'address': short,
                        'count': info['count'],
                        'spent': info['spent'],
                        'last': info['last'],
                        'collection': c['name']
                    })

            if notable_sales:
                all_sales_text.append(f"Notable: {', '.join(notable_sales[:3])}")

    # Build market recap card
    summary = ' | '.join(all_sales_text[:4])
    news.append({
        'category': 'MARKET RECAP',
        'headline': 'Daily Market Overview',
        'summary': summary,
        'source': 'OpenSea',
        'link': 'https://opensea.io/collection/thememes6529',
        'image': None,
        'dataBoxes': all_data_boxes[:4]
    })

    # Whale alerts (if any)
    all_whales.sort(key=lambda x: x['count'], reverse=True)
    for whale in all_whales[:2]:
        news.append({
            'category': 'WHALE ALERT',
            'headline': f"Whale {whale['address']} Buys {whale['count']} {whale['collection']}",
            'summary': f"Total spent: {whale['spent']:.3f} ETH. Last purchase: \"{whale['last']}\".",
            'source': 'OpenSea',
            'link': f'https://opensea.io/collection/thememes6529',
            'image': None,
            'dataBoxes': None
        })

    return news


def build_top3_leaderboard(wave_id, wave_name, category):
    """FIXED: Top 3 leaderboard for a voting wave."""
    print(f"Building top 3: {wave_name}...")
    subs = fetch_ranked_submissions(wave_id, pages=30)
    top3 = subs[:3]

    if not top3:
        return []

    summary_parts = []
    data_boxes = []
    for s in top3:
        summary_parts.append(f"#{s['rank']} \"{s['title']}\" by {s['author']} ({format_tdh(s['tdh'])} TDH, {s['voters']} voters)")
        data_boxes.append({
            'label': f"#{s['rank']} {s['author']}",
            'value': format_tdh(s['tdh']),
            'sub': f"TDH ({s['voters']} votes)"
        })

    # Use #1's image if available
    image = None
    if top3[0].get('img'):
        image = {'url': top3[0]['img'], 'label': f"#{top3[0]['rank']} {top3[0]['title']} - {top3[0]['author']}"}

    return [{
        'category': category,
        'headline': f"#{top3[0]['rank']} {top3[0]['author']} Leads with {format_tdh(top3[0]['tdh'])} TDH",
        'summary': ' | '.join(summary_parts),
        'source': wave_name,
        'link': f'https://6529.io/waves/{wave_id}',
        'image': image,
        'dataBoxes': data_boxes[:4]
    }]


# =============================================
# VARIABLE NEWS: AI-generated from wave activity
# =============================================

def gather_significant_wave_data(waves):
    """Only gather waves with significant activity (>= MIN_MSGS_6H in 6 hours)."""
    wave_data = []
    six_hours_ago = (datetime.now(timezone.utc) - timedelta(hours=6)).timestamp() * 1000

    for w in waves:
        drops = fetch_6529_drops(w['id'], 20)
        if not drops:
            continue

        # Count messages in last 6 hours
        recent = [d for d in drops if d['created_at'] > six_hours_ago]

        if len(recent) < MIN_MSGS_6H:
            print(f"  Skipping {w['name']}: only {len(recent)} msgs in 6h (min {MIN_MSGS_6H})")
            continue

        messages = []
        for d in recent[:10]:
            parts = d.get('parts', [])
            content = (parts[0].get('content') or '')[:200] if parts else ''
            author = d.get('author', {}).get('handle', '?')
            if content:
                messages.append(f"{author}: {content}")

        # Unique participants
        authors = list(set(d.get('author', {}).get('handle', '?') for d in recent))

        wave_data.append({
            'name': w['name'],
            'type': w.get('type', 'chat'),
            'msgs_6h': len(recent),
            'participants': authors[:10],
            'sample_messages': messages[:5],
            'wave_id': w['id']
        })

    return wave_data


def generate_additional_news_ai(wave_data, max_news=7):
    """Use AI to generate additional news from wave activity."""
    if not OPENROUTER_KEY or not wave_data:
        return generate_additional_fallback(wave_data)

    prompt = f"""You are a news editor for MEMES 24H, a daily broadcast covering the 6529 NFT ecosystem.
Today is {datetime.now(timezone.utc).strftime('%B %d, %Y')}.

Below is significant wave/chat activity from the last 6 hours.
Generate {min(max_news, len(wave_data) * 2)} news items highlighting the most interesting discussions, quotes, trends, and community moments.

RULES:
- Only include genuinely interesting content (notable quotes, debates, announcements, milestones)
- Do NOT include simple "gm" or greeting messages as news
- Attribute quotes to their authors
- Be specific with names and details
- Each news item must be distinct (no duplicates)

=== WAVE ACTIVITY (last 6 hours) ===
{json.dumps(wave_data, indent=2)[:4000]}

Return ONLY a valid JSON array. No markdown, no explanation.
[
  {{
    "category": "COMMUNITY|CULTURE|BREAKING",
    "headline": "Short punchy headline",
    "summary": "2-3 sentences with quotes and specific details",
    "source": "Wave name",
    "link": "https://6529.io/waves/WAVE_ID",
    "image": null,
    "dataBoxes": null
  }}
]"""

    body = json.dumps({
        'model': AI_MODEL,
        'messages': [{'role': 'user', 'content': prompt}],
        'max_tokens': 2500,
        'temperature': 0.7
    }).encode()

    req = urllib.request.Request(
        'https://openrouter.ai/api/v1/chat/completions',
        data=body,
        headers={
            'Authorization': f'Bearer {OPENROUTER_KEY}',
            'Content-Type': 'application/json'
        }
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            result = json.loads(r.read())

        content = result['choices'][0]['message']['content']

        if '```json' in content:
            content = content.split('```json')[1].split('```')[0]
        elif '```' in content:
            content = content.split('```')[1].split('```')[0]

        news = json.loads(content.strip())
        print(f"AI generated {len(news)} additional news items")
        return news[:max_news]

    except Exception as e:
        print(f"AI generation failed: {e}")
        return generate_additional_fallback(wave_data)


def generate_additional_fallback(wave_data):
    """Fallback: generate news from wave data without AI."""
    news = []
    for w in wave_data:
        if w['msgs_6h'] >= 10:
            activity = 'buzzing'
        elif w['msgs_6h'] >= 5:
            activity = 'active'
        else:
            continue

        # Pick a non-trivial message
        best_msg = ''
        for msg in w['sample_messages']:
            # Skip simple greetings
            lower = msg.lower()
            if any(g in lower for g in ['gm', 'good morning', 'hello', 'hi ']):
                continue
            best_msg = msg
            break

        if not best_msg and w['sample_messages']:
            best_msg = w['sample_messages'][0]

        summary = f"{w['msgs_6h']} messages in the last 6 hours with {len(w['participants'])} participants."
        if best_msg:
            summary += f' Latest: {best_msg[:150]}'

        news.append({
            'category': 'COMMUNITY',
            'headline': f"{w['name']} is {activity}: {w['msgs_6h']} messages, {len(w['participants'])} participants",
            'summary': summary,
            'source': w['name'],
            'link': f"https://6529.io/waves/{w['wave_id']}",
            'image': None,
            'dataBoxes': None
        })

    return news[:5]


# =============================================
# OUTPUT
# =============================================

def build_output(fixed_news, variable_news, market_data_raw):
    """Combine fixed + variable news, build ticker."""
    all_news = fixed_news + variable_news
    all_news = all_news[:13]  # Cap at 13 (3 fixed + 10 variable max)

    ticker = []
    for m in market_data_raw:
        ticker.append({'label': f"{m['name']} Floor", 'value': f"{m.get('floor', '?')} {m.get('floor_sym', 'ETH')}"})

    return {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'model': AI_MODEL,
        'news': all_news,
        'ticker': ticker
    }


def update_gist(output):
    if not GITHUB_TOKEN or not GIST_ID:
        return

    body = json.dumps({
        'files': {'news-latest.json': {'content': json.dumps(output, indent=2)}}
    }).encode()

    req = urllib.request.Request(
        f'https://api.github.com/gists/{GIST_ID}',
        data=body, method='PATCH',
        headers={'Authorization': f'Bearer {GITHUB_TOKEN}', 'Content-Type': 'application/json'}
    )

    try:
        with urllib.request.urlopen(req) as r:
            print(f"Gist updated")
    except Exception as e:
        print(f"Gist update failed: {e}")


# =============================================
# PUNK6529 TRACKING
# =============================================

def build_punk6529_news():
    """Track punk6529's activity. If 5+ msgs in 6h: '6529 Talks about'. Otherwise: last seen."""
    print("Tracking punk6529...")
    news = []

    # Get punk6529's recent drops across all waves
    drops = fetch_json(f'https://api.6529.io/api/drops?author={PUNK6529_HANDLE}&limit=20')
    if not drops:
        return news

    now_ms = datetime.now(timezone.utc).timestamp() * 1000
    six_h_ago = now_ms - 6 * 3600 * 1000
    twenty_four_h_ago = now_ms - 24 * 3600 * 1000

    recent_6h = [d for d in drops if d['created_at'] > six_h_ago]
    recent_24h = [d for d in drops if d['created_at'] > twenty_four_h_ago]

    if len(recent_6h) >= PUNK6529_MIN_MSGS:
        # 6529 is actively talking - summarize what about
        messages = []
        topics = set()
        for d in recent_6h[:10]:
            parts = d.get('parts', [])
            content = (parts[0].get('content') or '')[:200] if parts else ''
            wave_name = d.get('wave', {}).get('name', '?')
            if content:
                messages.append(content)
                topics.add(wave_name)

        # Pick best quotes (skip very short ones)
        best_quotes = [m for m in messages if len(m) > 30][:3]
        quote_text = ' | '.join([f'"{q[:100]}"' for q in best_quotes])

        news.append({
            'category': '6529 TALKS',
            'headline': f'6529 Talks About: {len(recent_6h)} Messages in the Last 6 Hours',
            'summary': f'punk6529 has been active in {", ".join(topics)}. {quote_text}',
            'source': list(topics)[0] if topics else 'Network',
            'link': 'https://6529.io/punk6529',
            'image': {'url': PUNK6529_PFP, 'label': 'punk6529'},
            'dataBoxes': None
        })
        print(f"  6529 active: {len(recent_6h)} msgs in 6h")

    elif recent_24h:
        # Active in last 24h but not heavily - skip (not newsworthy)
        print(f"  6529 mildly active: {len(recent_24h)} msgs in 24h (below threshold)")

    else:
        # Not active in 24h - show last seen
        if drops:
            last = drops[0]
            last_ts = last['created_at'] / 1000
            last_dt = datetime.fromtimestamp(last_ts, tz=timezone.utc)
            last_wave = last.get('wave', {}).get('name', 'unknown')
            time_str = last_dt.strftime('%b %d, %H:%M UTC')

            news.append({
                'category': '6529 STATUS',
                'headline': f'6529 Last Seen in {last_wave}',
                'summary': f'punk6529 was last active on {time_str} in "{last_wave}". No messages in the last 24 hours.',
                'source': last_wave,
                'link': 'https://6529.io/punk6529',
                'image': {'url': PUNK6529_PFP, 'label': 'punk6529 - last seen'},
                'dataBoxes': None
            })
            print(f"  6529 inactive: last seen {time_str}")

    return news


def build_tdh_millionaires_news():
    """TDH Millionaires wave - only if 10+ msgs in 6h."""
    print("Checking TDH Millionaires wave...")
    drops = fetch_6529_drops(TDH_MILLIONAIRES_WAVE_ID, 20)
    if not drops:
        print("  Wave restricted or empty")
        return []

    now_ms = datetime.now(timezone.utc).timestamp() * 1000
    six_h_ago = now_ms - 6 * 3600 * 1000
    recent = [d for d in drops if d['created_at'] > six_h_ago]

    if len(recent) < 10:
        print(f"  Only {len(recent)} msgs in 6h (need 10+)")
        return []

    # Gather discussion topics
    messages = []
    authors = set()
    for d in recent[:15]:
        parts = d.get('parts', [])
        content = (parts[0].get('content') or '')[:150] if parts else ''
        author = d.get('author', {}).get('handle', '?')
        if content and len(content) > 20:
            messages.append(f'{author}: "{content}"')
            authors.add(author)

    summary = f'{len(recent)} messages in the last 6 hours from {len(authors)} TDH millionaires. ' + ' | '.join(messages[:3])

    print(f"  Active: {len(recent)} msgs, {len(authors)} participants")
    return [{
        'category': 'TDH MILLIONAIRES',
        'headline': f'TDH Millionaires Talk: {len(recent)} Messages, {len(authors)} Participants',
        'summary': summary,
        'source': 'Memes Talk - 1M TDH',
        'link': 'https://6529.io/waves/9cc8118b-0ae0-4b22-8d15-3b8ed6604bac',
        'image': None,
        'dataBoxes': None
    }]


# =============================================
# MAIN
# =============================================

def main():
    print(f"=== MEMES 24H News Generator ===")
    print(f"Time: {datetime.now(timezone.utc).isoformat()}")

    # Load config
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH) as f:
            config = json.load(f)
    else:
        config = {
            'waves': [
                {'id': 'b38288e6-ca9d-45ce-8323-3dc5e094f04e', 'name': "maybe's dive bar", 'type': 'chat'},
                {'id': 'b6128077-ea78-4dd9-b381-52c4eadb2077', 'name': 'The Memes - Main Stage', 'type': 'votes'},
                {'id': 'd22e3046-a00e-48b9-b245-a339a44c37cd', 'name': 'SuperRare Chat & Application Boost', 'type': 'votes'},
            ],
            'collections': [
                {'slug': 'thememes6529', 'name': 'The Memes'},
                {'slug': 'pebbles-by-zeblocks', 'name': 'Pebbles'},
            ]
        }

    # ---- FIXED NEWS (always present) ----
    print("\n--- Fixed: Market Recap ---")
    market_news = build_market_recap(config['collections'])

    print("\n--- Fixed: Top 3 Memes ---")
    memes_top3 = build_top3_leaderboard(MEMES_WAVE_ID, 'The Memes - Main Stage', 'MAIN STAGE TOP 3')

    print("\n--- Fixed: Top 3 SuperRare ---")
    sr_top3 = build_top3_leaderboard(SR_WAVE_ID, 'SuperRare x 6529', 'SUPERRARE TOP 3')

    print("\n--- Fixed: punk6529 Status ---")
    punk6529_news = build_punk6529_news()

    print("\n--- Fixed: TDH Millionaires ---")
    tdh_mill_news = build_tdh_millionaires_news()

    fixed_news = market_news + memes_top3 + sr_top3 + punk6529_news + tdh_mill_news

    # ---- VARIABLE NEWS (AI-generated) ----
    print("\n--- Gathering wave activity (min 3 msgs/6h) ---")
    wave_data = gather_significant_wave_data(config['waves'])
    print(f"  {len(wave_data)} waves with significant activity")

    print("\n--- Generating additional news via AI ---")
    max_additional = 10 - len(fixed_news)
    variable_news = generate_additional_news_ai(wave_data, max_news=max(0, max_additional))

    # ---- BUILD OUTPUT ----
    # Store raw market data for ticker
    market_raw = []
    for c in config['collections']:
        stats = fetch_opensea_stats(c['slug'])
        if stats:
            market_raw.append({
                'name': c['name'],
                'floor': stats['total'].get('floor_price', 0),
                'floor_sym': stats['total'].get('floor_price_symbol', 'ETH')
            })

    output = build_output(fixed_news, variable_news, market_raw)
    print(f"\n--- Total: {len(output['news'])} news items ({len(fixed_news)} fixed + {len(variable_news)} variable) ---")

    # ---- PUBLISH ----
    print("\n--- Publishing ---")
    update_gist(output)

    output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'data', 'news-latest.json')
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2)
    print(f"Written to {output_path}")

    print("\nDone!")


if __name__ == '__main__':
    main()
