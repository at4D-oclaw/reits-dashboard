#!/usr/bin/env python3
"""
Generate REITs trading dashboard HTML.

Pipeline:
  1. Fetch live quotes from Tencent Finance API
  2. Load manual config (dividend yields, notes)
  3. Calculate corrected metrics (real PB, spread, 52w percentile)
  4. Generate trading signals
  5. Fill HTML template → output reits-dashboard.html

Usage:
  python3 generate_dashboard.py [--config data/config.json] [--template templates/dashboard.html] [--output reits-dashboard.html]
"""

import json
import sys
import os
import urllib.request
import urllib.error
import argparse
import re
from datetime import datetime, timezone, timedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CONFIG = os.path.join(SCRIPT_DIR, "..", "data", "config.json")
DEFAULT_TEMPLATE = os.path.join(SCRIPT_DIR, "..", "templates", "dashboard.html")
DEFAULT_OUTPUT = os.path.join(SCRIPT_DIR, "..", "reits-dashboard.html")

REIT_CODES = [
    "sh508050", "sz180401", "sh508016", "sh508018",
    "sh508030", "sh508096", "sh508028", "sh508059", "sh508007",
]


def fetch_quotes(codes):
    """Fetch real-time quotes from Tencent Finance API."""
    url = f"https://qt.gtimg.cn/q={','.join(codes)}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        raw = resp.read().decode("gbk")

    results = {}
    for line in raw.strip().split(";"):
        line = line.strip()
        if not line or "=" not in line:
            continue
        key, val = line.split("=", 1)
        val = val.strip('"').strip("'")
        if not val:
            continue
        parts = val.split("~")
        if len(parts) < 50:
            continue

        code = key.strip()
        # Strip leading 'v_' from Tencent API key (e.g. 'v_sh508050' → 'sh508050')
        if code.startswith('v_'):
            code = code[2:]
        name = parts[1]
        price = float(parts[3])
        prev_close = float(parts[4])

        try:
            chg_pct = float(parts[32])
        except (ValueError, IndexError):
            chg_pct = 0.0

        # NAV: find "CNY" marker, NAV is 2 fields after it
        nav = 0.0
        cny_idx = -1
        for i, p in enumerate(parts):
            if p == "CNY":
                cny_idx = i
                break
        if cny_idx >= 0 and cny_idx + 2 < len(parts):
            try:
                nav = float(parts[cny_idx + 2])
            except (ValueError, IndexError):
                pass

        # 52-week high/low: after "FJ" marker, +4 and +5
        high52 = 0.0
        low52 = 0.0
        fj_idx = -1
        for i, p in enumerate(parts):
            if p == "FJ":
                fj_idx = i
                break
        if fj_idx >= 0 and fj_idx + 5 < len(parts):
            try:
                high52 = float(parts[fj_idx + 4])
                low52 = float(parts[fj_idx + 5])
            except (ValueError, IndexError):
                pass

        results[code] = {
            "name": name,
            "price": price,
            "prev_close": prev_close,
            "chg_pct": chg_pct,
            "nav": nav,
            "high52": high52,
            "low52": low52,
        }

    return results


def load_config(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def calculate_metrics(quotes, config):
    """Merge quotes with config, calculate corrected metrics and signals."""
    risk_free = config["meta"]["risk_free_rate"]
    buy_prem = config["meta"]["buy_threshold_premium"]
    buy_spread = config["meta"]["buy_threshold_spread"]
    hold_prem = config["meta"]["hold_threshold_premium"]
    warn_prem = config["meta"]["warn_threshold_premium"]

    results = []
    for code in REIT_CODES:
        if code not in quotes or code not in config["reits"]:
            continue

        q = quotes[code]
        c = config["reits"][code]

        price = q["price"]
        nav = q["nav"]
        premium = ((price - nav) / nav * 100) if nav > 0 else 0.0
        real_pb = (price / nav) if nav > 0 else 0.0
        div_yield = c.get("dividend_yield", 0.0)
        spread = div_yield - risk_free

        # 52-week percentile
        if q["high52"] > q["low52"]:
            pct_52w = (price - q["low52"]) / (q["high52"] - q["low52"]) * 100
        else:
            pct_52w = 50.0

        # Trading signal
        if premium < buy_prem and spread > buy_spread:
            signal = "buy"
            signal_text = "✅ 买入信号"
            signal_class = "sig-buy"
        elif premium < hold_prem:
            signal = "hold"
            signal_text = "⏳ 持有"
            signal_class = "sig-hold"
        elif premium > warn_prem:
            signal = "avoid"
            signal_text = "❌ 回避"
            signal_class = "sig-avoid"
        else:
            signal = "warn"
            signal_text = "⚠️ 警告"
            signal_class = "sig-warn"

        # Premium display class
        if premium < 5:
            prem_class = "prem-low"
        elif premium < 15:
            prem_class = "prem-ok"
        elif premium < 25:
            prem_class = "prem-high"
        else:
            prem_class = "prem-danger"

        # Spread display
        if spread > 4:
            spread_class = "good"
        elif spread > 2:
            spread_class = "warn"
        else:
            spread_class = "bad"

        # 52w percentile display
        if pct_52w < 40:
            pct_class = "good"
        elif pct_52w < 70:
            pct_class = "warn"
        else:
            pct_class = "bad"

        results.append({
            "code": code,
            "name": c["name"],
            "sector": c["sector"],
            "tier": c["tier"],
            "price": price,
            "chg_pct": q["chg_pct"],
            "nav": nav,
            "premium": premium,
            "prem_class": prem_class,
            "real_pb": real_pb,
            "dividend_yield": div_yield,
            "dividend_source": c.get("dividend_source", "手动"),
            "spread": spread,
            "spread_class": spread_class,
            "pct_52w": pct_52w,
            "pct_52w_class": pct_class,
            "high52": q["high52"],
            "low52": q["low52"],
            "signal": signal,
            "signal_text": signal_text,
            "signal_class": signal_class,
            "note": c.get("note", ""),
        })

    # Sort by tier order: stable, flexible, volatile
    tier_order = {"stable": 0, "flexible": 1, "volatile": 2}
    results.sort(key=lambda x: tier_order.get(x["tier"], 9))

    return results


def chg_color(val):
    if val > 0:
        return f'+{val:.2f}%', "c-green"
    elif val < 0:
        return f'{val:.2f}%', "c-red"
    return f'{val:.2f}%', "c-gray"


def render_card(r):
    """Render a single REIT card HTML."""
    chg_str, chg_cls = chg_color(r["chg_pct"])

    # PB display
    if r["code"] == "sh508096":
        pb_display = f'<span style="color:#22c55e">~1.01</span>'
        pb_note = '<span style="font-size:9px">⚠️底层折扣0.32≠PB</span>'
    else:
        pb_display = f'{r["real_pb"]:.2f}'
        pb_note = ""

    # 52w range text
    range_str = f'{r["low52"]:.2f} ~ {r["high52"]:.2f}' if r["low52"] > 0 else "N/A"

    # Signal text — include spread info
    if r["signal"] == "buy":
        sig_detail = f"溢价{r['premium']:+.1f}% · 利差{r['spread']:+.1f}% · 52w低位{r['pct_52w']:.0f}%"
    elif r["signal"] == "hold":
        sig_detail = f"溢价{r['premium']:+.1f}% · 利差{r['spread']:+.1f}%"
    elif r["signal"] == "warn":
        sig_detail = f"溢价{r['premium']:+.1f}% · 利差{r['spread']:+.1f}%"
    else:
        sig_detail = f"溢价{r['premium']:+.1f}% · 利差{r['spread']:+.1f}%"

    return f"""
      <div class="card">
        <div class="card-top">
          <div>
            <div class="card-name">{r['name']}</div>
            <div class="card-code">{r['code'].upper()} · {r['sector']}</div>
          </div>
          <span class="card-tag tag-{r['tier'][:4]}">{tier_label(r['tier'])}</span>
        </div>
        <div class="card-price-row">
          <div class="card-price">{r['price']:.3f}</div>
          <div class="card-chg {chg_cls}">{chg_str}</div>
          <div class="card-premium {r['prem_class']}">溢价 {r['premium']:+.1f}%</div>
        </div>
        <div class="metrics">
          <div class="m"><span class="m-label">现价</span><span class="m-val">{r['price']:.3f}</span></div>
          <div class="m"><span class="m-label">NAV</span><span class="m-val">{r['nav']:.3f}</span></div>
          <div class="m"><span class="m-label">52周区间</span><span class="m-val">{range_str}</span></div>
          <div class="m"><span class="m-label">52周分位</span><span class="m-val {r['pct_52w_class']}">{r['pct_52w']:.0f}%</span></div>
          <div class="m"><span class="m-label">分派率 <span class="src-tag est">{r['dividend_source']}</span></span><span class="m-val info">{r['dividend_yield']:.1f}%</span></div>
          <div class="m"><span class="m-label">vs 国债利差</span><span class="m-val {r['spread_class']}">{r['spread']:+.1f}%</span></div>
        </div>
        <div class="signal {r['signal_class']}">{r['signal_text']}：{sig_detail}</div>
        <div class="source-row">
          <span class="src-tag real">实时价</span>
          <span class="src-tag real">溢价率</span>
          <span class="src-tag est">分派率={r['dividend_source']}</span>
        </div>
      </div>"""


def tier_label(tier):
    return {"stable": "稳健", "flexible": "弹性", "volatile": "高波动"}.get(tier, tier)


def render_column(title, tier_class, items):
    cards = "\n".join(render_card(r) for r in items)
    return f"""
  <div>
    <div class="col-header col-{tier_class}">{title}</div>
    <div class="col-body">
{cards}
    </div>
  </div>"""


def generate_html(records, config, template_path, output_path):
    """Fill template with data and write final HTML."""

    tz_cst = timezone(timedelta(hours=8))
    now = datetime.now(tz_cst)
    snapshot_time = now.strftime("%Y-%m-%d %H:%M CST")
    us30y = config["meta"].get("us30y", "5.28")
    cn10y = config["meta"]["risk_free_rate"]

    # Determine strategy status
    try:
        us30y_val = float(us30y)
        if us30y_val >= 5.0:
            strategy = "观望 — 30Y美债≥5.0%，不加仓"
            strategy_short = "观望"
            strategy_rule = "30Y ≥ 5.0%，仅观察"
            strategy_class = "c-amber"
        else:
            strategy = "可逐步建仓 — 长端回落中"
            strategy_short = "可建仓"
            strategy_rule = "长端回落中"
            strategy_class = "c-green"
    except ValueError:
        strategy = "观望 — 等待信号"
        strategy_short = "观望"
        strategy_rule = "等待信号"
        strategy_class = "c-amber"

    # Group by tier
    stable = [r for r in records if r["tier"] == "stable"]
    flexible = [r for r in records if r["tier"] == "flexible"]
    volatile = [r for r in records if r["tier"] == "volatile"]

    columns_html = (
        render_column("🛡️ 稳健优先 — 现金流稳、抗波动", "stable", stable)
        + render_column("📈 风光弹性 — 跨区域分散", "flexible", flexible)
        + render_column("🌊 高波动 — 海上风电 / 单高速", "risk", volatile)
    )

    # Build replacement map
    replacements = {
        "{{SNAPSHOT_TIME}}": snapshot_time,
        "{{US30Y}}": str(us30y),
        "{{CN10Y}}": str(cn10y),
        "{{STRATEGY_STATUS}}": strategy,
        "{{STRATEGY_SHORT}}": strategy_short,
        "{{STRATEGY_RULE}}": strategy_rule,
        "{{STRATEGY_CLASS}}": strategy_class,
        "{{COLUMNS}}": columns_html,
    }

    with open(template_path, "r", encoding="utf-8") as f:
        html = f.read()

    # Replace all {{PLACEHOLDER}} tokens
    for key, val in replacements.items():
        html = html.replace(key, val)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"✅ Dashboard written to {output_path}")
    print(f"   Time: {snapshot_time}")
    print(f"   REITs: {len(records)} records")
    print(f"   30Y UST: {us30y}% | 10Y CN: {cn10y}%")


def main():
    parser = argparse.ArgumentParser(description="Generate REITs trading dashboard")
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    parser.add_argument("--template", default=DEFAULT_TEMPLATE)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    print("📡 Fetching live quotes...")
    quotes = fetch_quotes(REIT_CODES)
    print(f"   Got {len(quotes)}/{len(REIT_CODES)} REITs")

    print("📋 Loading config...")
    config = load_config(args.config)

    print("🧮 Calculating metrics & signals...")
    records = calculate_metrics(quotes, config)

    print("🎨 Rendering dashboard...")
    generate_html(records, config, args.template, args.output)


if __name__ == "__main__":
    main()
