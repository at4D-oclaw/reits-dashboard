#!/usr/bin/env python3
"""
Fetch real-time REITs data from Tencent Finance API.
Applies known corrections for REIT-specific field distortions.

Usage: python3 fetch_reits.py [--output json|csv]
"""

import json
import sys
import os
import urllib.request
import urllib.error

# REIT codes to track (Tencent prefix: sh=SSE, sz=SZSE)
REITS = {
    "sh508050": {"name": "华夏中核清洁能源",   "sector": "水电",     "tier": "stable"},
    "sz180401": {"name": "鹏华深圳能源",       "sector": "燃气热电",  "tier": "stable"},
    "sh508016": {"name": "华夏华电清洁能源",   "sector": "燃气热电",  "tier": "stable"},
    "sh508018": {"name": "华夏中国交建",       "sector": "多高速",    "tier": "stable"},
    "sh508030": {"name": "中航中核汇能新能源",  "sector": "跨区域风光", "tier": "flexible"},
    "sh508096": {"name": "中航京能国际能源",    "sector": "跨区域风光", "tier": "flexible"},
    "sh508028": {"name": "中信建投国家电投新能源","sector": "海上风电", "tier": "volatile"},
    "sh508059": {"name": "华泰三峡新能源",      "sector": "海上风电",  "tier": "volatile"},
    "sh508007": {"name": "中金山东高速",       "sector": "单高速",    "tier": "volatile"},
}

def fetch_quotes(codes):
    """Fetch real-time quotes from Tencent Finance API."""
    url = f"https://qt.gtimg.cn/q={','.join(codes)}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
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
        name = parts[1]
        price = float(parts[3])
        prev_close = float(parts[4])

        # Change percent
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

        # 52-week high/low: after "FJ" marker
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

        # Amplitude
        try:
            amp = float(parts[38])
        except (ValueError, IndexError):
            amp = 0.0

        results[code] = {
            "name": name,
            "price": price,
            "prev_close": prev_close,
            "chg_pct": chg_pct,
            "nav": nav,
            "high52": high52,
            "low52": low52,
            "amp": amp,
        }

    return results


def calculate_metrics(data):
    """
    Apply REIT-specific corrections:
    1. premium_rate = (price - nav) / nav (RELIABLE from API)
    2. real_pb = price / nav (NOT the API's PB field)
    3. dividend_yield = MANUAL INPUT (API is broken for REITs)
    """
    for code, d in data.items():
        if d["nav"] > 0:
            d["premium_rate"] = (d["price"] - d["nav"]) / d["nav"] * 100
            d["real_pb"] = d["price"] / d["nav"]
        else:
            d["premium_rate"] = 0.0
            d["real_pb"] = 0.0

        # 52-week percentile
        if d["high52"] > d["low52"]:
            d["pct_52w"] = (d["price"] - d["low52"]) / (d["high52"] - d["low52"]) * 100
        else:
            d["pct_52w"] = 50.0

        # Dividend yield: MUST be filled manually from prospectus
        # Placeholder - agent must fill this from prospectus data
        d["dividend_yield"] = None  # unit: %

    return data


def main():
    codes = list(REITS.keys())
    data = fetch_quotes(codes)
    data = calculate_metrics(data)

    # Merge metadata
    for code, meta in REITS.items():
        if code in data:
            data[code].update(meta)

    output = sys.argv[1] if len(sys.argv) > 1 else "json"
    if output == "json":
        print(json.dumps(data, ensure_ascii=False, indent=2))
    elif output == "csv":
        import csv, io
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["code", "name", "sector", "tier", "price", "nav",
                          "premium_rate", "real_pb", "dividend_yield",
                          "pct_52w", "chg_pct", "high52", "low52"])
        for code, d in data.items():
            writer.writerow([
                code, d["name"], d["sector"], d["tier"],
                d["price"], d["nav"],
                f"{d['premium_rate']:.2f}%", f"{d['real_pb']:.2f}",
                d["dividend_yield"] if d["dividend_yield"] else "N/A",
                f"{d['pct_52w']:.0f}%", f"{d['chg_pct']:.2f}%",
                d["high52"], d["low52"]
            ])
        print(buf.getvalue())


if __name__ == "__main__":
    main()
