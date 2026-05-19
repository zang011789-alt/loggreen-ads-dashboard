# -*- coding: utf-8 -*-
"""
TikTok 광고 자동 수집 - 일별(하루씩) 저장 방식
tiktok_history[날짜] = { scraped_at, summary, campaigns[] }
매일 오늘/어제 데이터 수집 → tiktok_history.js git push
Chrome이 디버그 모드로 열려있어야 함 (포트 9222)
"""
import json, sys, re, subprocess, os
from playwright.sync_api import sync_playwright
from datetime import datetime, date, timedelta

sys.stdout.reconfigure(encoding="utf-8")

ADV_ID       = "7556508952121393153"
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
        return True
    except:
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

def collect_day(page, target_date_str):
    """단일 날짜 하루치 수집 (st=et=target_date)"""
    url = (f"https://ads.tiktok.com/i18n/manage/campaign"
           f"?aadvid={ADV_ID}&st={target_date_str}&et={target_date_str}")
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=20000)
    except Exception as e:
        print(f"  [{target_date_str}] 이동 오류(무시): {e}", flush=True)
    page.wait_for_timeout(3000)

    apply_custom_columns(page)
    campaigns = scrape_campaigns(page)

    active = [c for c in campaigns if c['status'] == 'active']
    total_spend   = sum(c['spend']   for c in campaigns)
    total_revenue = sum(c['revenue'] for c in campaigns)
    total_roas    = round(total_revenue / total_spend, 2) if total_spend else 0

    print(f"  [{target_date_str}] 캠페인 {len(campaigns)}개(활성:{len(active)}) | 소진:{total_spend:,} | 매출:{total_revenue:,} | ROAS:{total_roas}", flush=True)

    return {
        "scraped_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "summary": {"spend": total_spend, "revenue": total_revenue, "roas": total_roas},
        "campaigns": campaigns,
    }

def load_history():
    if os.path.exists(HISTORY_JSON):
        with open(HISTORY_JSON, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_history(history):
    with open(HISTORY_JSON, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)
    with open(HISTORY_JS, "w", encoding="utf-8") as f:
        f.write("window.TIKTOK_HISTORY = ")
        json.dump(history, f, ensure_ascii=False, indent=2)
        f.write(";\n")
    print(f"  저장 완료 ({len(history)}개 날짜)", flush=True)

def git_push():
    try:
        subprocess.run(["git", "-C", SITE_DIR, "add", "tiktok_history.js"], capture_output=True, timeout=30)
        subprocess.run(["git", "-C", SITE_DIR, "commit", "-m", f"tiktok auto {datetime.now().strftime('%Y-%m-%d %H:%M')}"], capture_output=True, timeout=30)
        r = subprocess.run(["git", "-C", SITE_DIR, "push"], capture_output=True, text=True, timeout=60)
        print(f"  git push: {'OK' if r.returncode == 0 else r.stderr[:80]}", flush=True)
    except Exception as e:
        print(f"  git push 실패: {e}", flush=True)

def run(dates_to_collect, skip_push=False):
    history = load_history()

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp("http://localhost:9222")
        ctx = browser.contexts[0]
        page = next((pg for pg in ctx.pages if "ads.tiktok.com" in pg.url), ctx.pages[0])

        for d in dates_to_collect:
            d_str = d.isoformat() if hasattr(d, 'isoformat') else d
            data = collect_day(page, d_str)
            # 날짜 키에 새 데이터 덮어쓰기 (오늘은 실시간 갱신)
            history[d_str] = data

        browser.close()

    save_history(history)
    if not skip_push:
        git_push()

if __name__ == "__main__":
    args = sys.argv[1:]
    skip_push = "--no-push" in args
    args = [a for a in args if not a.startswith("--")]

    today     = date.today()
    yesterday = today - timedelta(days=1)

    if len(args) == 0:
        # 기본: 오늘 + 어제
        dates = [yesterday, today]
        print(f"=== TikTok 일별 수집 {datetime.now().strftime('%Y-%m-%d %H:%M')} ===", flush=True)
    elif len(args) == 1:
        # 특정 날짜 하루
        dates = [args[0]]
        print(f"=== TikTok 수집 {args[0]} ===", flush=True)
    elif len(args) == 2:
        # 날짜 범위 (백필용)
        from datetime import datetime as dt
        st = dt.strptime(args[0], "%Y-%m-%d").date()
        et = dt.strptime(args[1], "%Y-%m-%d").date()
        dates = []
        d = st
        while d <= et:
            dates.append(d)
            d += timedelta(days=1)
        print(f"=== TikTok 백필 {args[0]}~{args[1]} ({len(dates)}일) ===", flush=True)

    run(dates, skip_push=skip_push)
    print("완료", flush=True)
