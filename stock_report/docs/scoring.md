# Scoring Model

## Goal

Keep the base scoring deterministic, readable, and easy to audit. Use the same base structure for stocks and ETFs, then apply theme-specific adjustments only where needed.

## Base Score Structure

- Trend score: 35%
- Fundamentals score: 25%
- News score: 20%
- Risk score: 20%

Total score:

```text
total_score =
  0.35 * trend_score +
  0.25 * fundamentals_score +
  0.20 * news_score +
  0.20 * risk_score
```

## Verdict Mapping

- `review`: 70-100
- `hold`: 50-69
- `avoid`: 0-49

Confidence should be reduced when data is stale, the news set is sparse, or signals conflict heavily.

## Base Section Inputs

### Trend Score

- 5D, 20D, 60D, 252D returns
- price relative to 20D, 50D, 200D moving averages
- 20D and 60D benchmark-relative strength
- drawdown from a recent high
- realized volatility penalty

### Fundamentals Score

- revenue and earnings growth
- gross margin and operating margin
- valuation snapshot
- leverage or balance-sheet pressure
- ETF metadata quality and category context for ETF reports

### News Score

- materiality of headlines
- earnings, guidance, or product launch relevance
- regulatory or supply-chain relevance
- net directional impact across the most recent news window

### Risk Score

- volatility and drawdown
- event concentration
- valuation stretch
- stale or missing data
- theme hype unsupported by evidence

## HBF Overlay

`HBF` should not be scored only as another memory ticker. The model should explicitly ask whether the theme is becoming commercially relevant.

### HBF-Specific Positive Signals

- standardization progress
- new ecosystem partners
- references to AI inference deployment
- controller, software, packaging, or interoperability milestones
- volume ramp or customer sampling language

### HBF-Specific Negative Signals

- repeated concept announcements with no partner expansion
- no product timeline or no commercial sampling details
- weak link between HBF news and actual inference workload adoption
- deterioration in memory or storage pricing with no offsetting demand signal

### HBF Overlay Rules

- Add up to `+10` points when there is clear progress in standardization, ecosystem support, and commercialization evidence
- Subtract up to `-10` points when HBF coverage is mostly narrative without operational proof
- Cap the net HBF overlay to keep total scores comparable across themes
- Lower confidence if the HBF narrative depends on one company press release without corroborating ecosystem activity

## Korea HBM/HBF Coverage Rule

Korea names are included only when they are directly relevant to HBM or HBF. The default covered names are:

- `000660.KS` for SK hynix
- `005930.KS` for Samsung Electronics

These should still use the same scoring engine, but reports should mention when benchmark and peer comparisons span multiple markets.

## Suggested Implementation Shape

1. Compute the base section scores
2. Load the asset theme
3. Apply any theme overlay such as `hbf_memory_storage`
4. Recompute total score and confidence
5. Emit a score breakdown showing the base score and overlay effect
