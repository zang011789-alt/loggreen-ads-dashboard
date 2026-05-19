# -*- coding: utf-8 -*-
"""
TikTok 광고 캠페인 성과 DOM 스크래핑
Custom Columns '장동훈' 뷰 사용 (ROAS 포함)
컬럼 순서: budget / budget_type / CPA / 소진 / 매출 / ROAS / CPC / CTR / ... / 클릭 / 노출 / CPM / 전환
"""
import json, sys, re
from playwright.sync_api import sync_playwright
from datetime import datetime, date, timedelta

sys.stdout.reconfigure(encoding="utf-8")

ADV_ID = "7556508952121393153"

def parse_krw(s):
    s = str(s).strip()
    if not s or s == '-': return 0
    return int(re.sub(r'[^0-9]', '', s) or 0)

def parse_float(s):
    s = str(s).strip()
    if not s or s == '-': return 0.0
    try: return float(re.sub(r'[^0-9\.]', '', s))
    except: return 0.0

def parse_pct(s):
    s = str(s).strip()
    if not s or s == '-': return 0.0
    try: return float(s.replace('%',''))
    except: return 0.0

def parse_num(s):
    s = str(s).strip()
    if not s or s == '-': return 0
    try: return int(re.sub(r'[^0-9]', '', s))
    except: return 0

def apply_custom_columns(page):
    try:
        page.wait_for_timeout(2000)
        page.locator('text="Custom Columns"').first.click()
        page.wait_for_timeout(1000)
        page.locator('text="장동훈"').first.click()
        page.wait_for_timeout(2500)
        print("장동훈 컬럼 적용 완료", flush=True)
        return True
    except Exception as e:
        print(f"Custom Columns 적용 실패: {e}", flush=True)
        return False

def scrape_campaigns(page):
    page.wait_for_timeout(3000)

    # 가상 스크롤 처리
    for _ in range(12):
        page.evaluate("window.scrollBy(0, 500)")
        page.wait_for_timeout(300)
    page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_timeout(1000)

    text = page.evaluate("document.body.innerText")
    lines = [l.strip() for l in text.split('\n') if l.strip()]

    campaigns = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if not re.search(r'(tk_do|TK_DO|do_|spc_)', line, re.IGNORECASE):
            i += 1; continue

        try:
            name = line
            status_raw = lines[i+1] if i+1 < len(lines) else ''
            if status_raw not in ('Active', 'Paused', 'Deleted', 'Not delivering'):
                i += 1; continue

            # offset: Active=2, Paused=3 (Campaign paused 줄 스킵)
            offset = 2
            nxt = lines[i+offset] if i+offset < len(lines) else ''
            if any(x in nxt.lower() for x in ['paused','delivering','deleted','not run']):
                offset += 1

            def gl(n):
                idx = i + offset + n
                return lines[idx] if idx < len(lines) else '0'

            # 장동훈 커스텀 컬럼 순서 (offset 기준)
            # +0: budget, +1: budget_type,
            # +2: CPA, +3: Cost(spend), +4: PurchaseValue(revenue), +5: ROAS
            # +6: CPC, +7: CTR, +8: metric8, +9: metric9, +10: metric10
            # +11: Clicks, +12: Impressions, +13: CPM, +14: Conversions
            camp = {
                'name':        name,
                'status':      'active' if status_raw == 'Active' else 'paused',
                'budget':      parse_krw(gl(0)),
                'cpa':         parse_krw(gl(2)),
                'spend':       parse_krw(gl(3)),
                'revenue':     parse_krw(gl(4)),
                'roas':        parse_float(gl(5)),
                'cpc':         parse_krw(gl(6)),
                'ctr':         parse_pct(gl(7)),
                'clicks':      parse_num(gl(11)),
                'impressions': parse_num(gl(12)),
                'cpm':         parse_krw(gl(13)),
                'conversions': parse_num(gl(14)),
            }
            campaigns.append(camp)
            i += offset + 18
            continue
        except:
            pass
        i += 1

    return campaigns

def collect(start_date=None, end_date=None):
    if not end_date:   end_date   = date.today().isoformat()
    if not start_date: start_date = (date.today() - timedelta(days=6)).isoformat()

    url = (f"https://ads.tiktok.com/i18n/manage/campaign"
           f"?aadvid={ADV_ID}&st={start_date}&et={end_date}")

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp("http://localhost:9222")
        ctx = browser.contexts[0]
        page = next((pg for pg in ctx.pages if "ads.tiktok.com" in pg.url), ctx.pages[0])

        print(f"날짜: {start_date} ~ {end_date}", flush=True)
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
        except Exception as e:
            print(f"이동 오류(무시): {e}", flush=True)
        page.wait_for_timeout(3000)

        apply_custom_columns(page)
        campaigns = scrape_campaigns(page)

        active = [c for c in campaigns if c['status'] == 'active']
        total_spend   = sum(c['spend']   for c in campaigns)
        total_revenue = sum(c['revenue'] for c in campaigns)
        total_roas    = round(total_revenue / total_spend, 2) if total_spend else 0

        print(f"\n=== 캠페인 {len(campaigns)}개 (활성: {len(active)}개) ===", flush=True)
        for c in campaigns:
            if c['spend'] == 0 and c['status'] == 'paused': continue
            mark = "▶" if c['status'] == 'active' else "■"
            print(f"{mark} {c['name']}", flush=True)
            print(f"   소진:{c['spend']:,} | 매출:{c['revenue']:,} | ROAS:{c['roas']} | CPA:{c['cpa']:,} | 클릭:{c['clicks']:,} | 전환:{c['conversions']}", flush=True)

        print(f"\n총 소진: {total_spend:,} | 총 매출: {total_revenue:,} | ROAS: {total_roas}", flush=True)

        result = {
            "scraped_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "start_date": start_date,
            "end_date": end_date,
            "advertiser_id": ADV_ID,
            "summary": {"spend": total_spend, "revenue": total_revenue, "roas": total_roas},
            "campaigns": campaigns,
        }
        with open("tiktok_data.json", "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"\ntiktok_data.json 저장", flush=True)
        browser.close()
        return result

if __name__ == "__main__":
    args = sys.argv[1:]
    st = args[0] if len(args) > 0 else None
    et = args[1] if len(args) > 1 else None
    collect(st, et)
