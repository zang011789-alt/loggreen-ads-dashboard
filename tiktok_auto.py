# -*- coding: utf-8 -*-
"""
TikTok 광고 자동 수집 - cafe24_auto.py와 동일 방식
tiktok_history.json 날짜별 누적 저장 → tiktok_history.js git push
Chrome이 디버그 모드로 열려있어야 함 (포트 9222)
"""
import json, sys, re, subprocess, os
from playwright.sync_api import sync_playwright
from datetime import datetime, date, timedelta

sys.stdout.reconfigure(encoding="utf-8")

ADV_ID = "7556508952121393153"
HISTORY_JSON = r"C:\Users\zang0\Desktop\my-site\tiktok_history.json"
HISTORY_JS   = r"C:\Users\zang0\Desktop\my-site\tiktok_history.js"
SITE_DIR     = r"C:\Users\zang0\Desktop\my-site"

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
        print("  장동훈 컬럼 적용", flush=True)
        return True
    except Exception as e:
        print(f"  커스텀 컬럼 적용 실패: {e}", flush=True)
        return False

def scrape_campaigns(page):
    page.wait_for_timeout(3000)
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

            offset = 2
            nxt = lines[i+offset] if i+offset < len(lines) else ''
            if any(x in nxt.lower() for x in ['paused','delivering','deleted','not run']):
                offset += 1

            def gl(n):
                idx = i + offset + n
                return lines[idx] if idx < len(lines) else '0'

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

def collect_range(start_date, end_date):
    url = (f"https://ads.tiktok.com/i18n/manage/campaign"
           f"?aadvid={ADV_ID}&st={start_date}&et={end_date}")

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp("http://localhost:9222")
        ctx = browser.contexts[0]
        page = next((pg for pg in ctx.pages if "ads.tiktok.com" in pg.url), ctx.pages[0])

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
        except Exception as e:
            print(f"  페이지 이동 오류(무시): {e}", flush=True)
        page.wait_for_timeout(3000)

        apply_custom_columns(page)
        campaigns = scrape_campaigns(page)

        active = [c for c in campaigns if c['status'] == 'active']
        total_spend   = sum(c['spend']   for c in campaigns)
        total_revenue = sum(c['revenue'] for c in campaigns)
        total_roas    = round(total_revenue / total_spend, 2) if total_spend else 0

        print(f"  캠페인 {len(campaigns)}개 (활성: {len(active)}개) | 소진: {total_spend:,} | 매출: {total_revenue:,} | ROAS: {total_roas}", flush=True)

        browser.close()
        return {
            "scraped_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "start_date": start_date,
            "end_date": end_date,
            "summary": {"spend": total_spend, "revenue": total_revenue, "roas": total_roas},
            "campaigns": campaigns,
        }

def save_history(today_str, data_7d, data_14d, data_30d):
    # JSON 로드
    if os.path.exists(HISTORY_JSON):
        with open(HISTORY_JSON, "r", encoding="utf-8") as f:
            history = json.load(f)
    else:
        history = {}

    if today_str not in history:
        history[today_str] = {}

    history[today_str]["7d"]  = data_7d
    history[today_str]["14d"] = data_14d
    history[today_str]["30d"] = data_30d

    # JSON 저장
    with open(HISTORY_JSON, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

    # JS 저장 (대시보드용)
    with open(HISTORY_JS, "w", encoding="utf-8") as f:
        f.write("window.TIKTOK_HISTORY = ")
        json.dump(history, f, ensure_ascii=False, indent=2)
        f.write(";\n")

    print(f"  tiktok_history.js 저장 ({len(history)}개 날짜)", flush=True)

def git_push():
    try:
        result = subprocess.run(
            ["git", "-C", SITE_DIR, "add", "tiktok_history.js"],
            capture_output=True, text=True, timeout=30
        )
        result2 = subprocess.run(
            ["git", "-C", SITE_DIR, "commit", "-m", f"tiktok auto {datetime.now().strftime('%Y-%m-%d %H:%M')}"],
            capture_output=True, text=True, timeout=30
        )
        result3 = subprocess.run(
            ["git", "-C", SITE_DIR, "push"],
            capture_output=True, text=True, timeout=60
        )
        print(f"  git push: {result3.returncode == 0 and 'OK' or result3.stderr[:80]}", flush=True)
    except Exception as e:
        print(f"  git push 실패: {e}", flush=True)

if __name__ == "__main__":
    today = date.today()
    today_str = today.isoformat()

    args = sys.argv[1:]
    skip_push = "--no-push" in args

    print(f"=== TikTok 자동 수집 {datetime.now().strftime('%Y-%m-%d %H:%M')} ===", flush=True)

    # 7일
    st7  = (today - timedelta(days=6)).isoformat()
    print(f"\n[7일] {st7} ~ {today_str}", flush=True)
    data_7d = collect_range(st7, today_str)

    # 14일
    st14 = (today - timedelta(days=13)).isoformat()
    print(f"\n[14일] {st14} ~ {today_str}", flush=True)
    data_14d = collect_range(st14, today_str)

    # 30일
    st30 = (today - timedelta(days=29)).isoformat()
    print(f"\n[30일] {st30} ~ {today_str}", flush=True)
    data_30d = collect_range(st30, today_str)

    save_history(today_str, data_7d, data_14d, data_30d)

    if not skip_push:
        git_push()

    print("\n완료", flush=True)
