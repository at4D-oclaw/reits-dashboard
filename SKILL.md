# REITs Dashboard Skill

Generates a real-time Chinese REITs trading dashboard as a self-contained HTML file.

## What It Does

Fetches live quotes for Chinese public REITs (公募REITs), applies known data corrections,
fills an HTML template, and outputs an interactive dark-mode dashboard.

## Usage

```
Skill: reits-dashboard
```

The agent will:
1. Fetch real-time prices, premium rates, NAV from Tencent Finance API
2. Manually calculate dividend yield (NOT using the broken API field)
3. Apply PB field corrections (API PB = underlying asset discount, NOT fund PB)
4. Fill the HTML template with corrected data
5. Write the final HTML to workspace

## Output

`reits-dashboard.html` — open directly in any browser, no server needed.

## Data Sources

| Data | Source | Reliability |
|------|--------|-------------|
| Price, premium rate, NAV | 腾讯财经实时行情 API | ✅ Absolute |
| Dividend yield | Manual calc from prospectus | ✅ Correct (API is broken) |
| PB | Manual calc = price / NAV | ✅ Correct (API PB is wrong) |
| 52-week range | 腾讯财经 API | ✅ |

## Known API Pitfalls (MUST apply)

1. **Dividend yield**: Tencent API returns garbage (e.g. 55.5%). Always compute manually:
   `dividend_yield = per_share_distribution / price × 100%`
   Use prospectus (招募书) annual prediction or latest quarterly report.

2. **PB field**: Tencent PB = underlying real estate assessment discount, NOT fund PB.
   Real fund PB = `price / NAV`. For REITs this is almost always ≈ 1 + premium_rate.

3. **Premium rate**: `(price - NAV) / NAV × 100%`. This is the most reliable valuation metric.

## Template Variables

The HTML template uses `{{PLACEHOLDER}}` syntax. After fetching data, replace all placeholders.

Key placeholders:
- `{{SNAPSHOT_TIME}}` — data timestamp
- `{{US30Y}}` — 30Y US Treasury yield
- `{{CN10Y}}` — 10Y China Treasury yield
- `{{STRATEGY_STATUS}}` — current strategy state
- Card data blocks are pre-filled in the template; agent updates values directly.

## REIT List

The skill tracks these REITs by risk tier:

**Stable (稳健)**: 508050, 180401, 508016, 508018
**Flexible (弹性)**: 508030, 508096
**High Volatility (高波动)**: 508028, 508059, 508007

## Files

- `SKILL.md` — this file
- `scripts/fetch_reits.py` — data fetching script
- `templates/dashboard.html` — HTML dashboard template
- `README.md` — GitHub README
