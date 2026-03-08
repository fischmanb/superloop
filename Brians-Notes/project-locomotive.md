# Project Locomotive: Infrastructure Modernization Roadmap

## Phase 1: Foundation (Week 1-2)

### 1.1 Data Infrastructure
- Build data ingestion pipeline for high-frequency time-series data (OHLCV, order book depth, tick data)
- Sources: Polygon.io, Alpaca, Interactive Brokers API, FRED, SEC EDGAR, alternative data feeds
- Storage: local DuckDB for backtesting speed, Parquet for columnar analysis
- Real-time: WebSocket feeds with local buffer and deduplication
- The system specs the pipeline, builds it, validates data integrity mechanically

### 1.2 Backtesting Framework
- Event-driven backtester with realistic execution modeling
- Transaction costs: commission, slippage (volume-weighted), market impact
- Regime-aware: the same strategy is tested across identified market regimes (trending, mean-reverting, volatile, quiet)
- Walk-forward validation: train on window N, test on N+1, slide forward. No lookahead bias.
- Statistical significance: minimum 100 trades per regime. Sharpe confidence intervals. Bootstrap resampling.
- The system builds this from a spec. The verification loop checks: does the backtester produce statistically valid results? Does it handle edge cases (gaps, halts, splits, dividends)?

### 1.3 Execution Layer
- Paper trading integration (Alpaca, IBKR paper)
- Order management: limit, market, stop, bracket
- Position sizing: Kelly criterion, fixed fractional, volatility-scaled
- Risk management: max drawdown circuit breaker, position limits, correlation limits
- The system builds, tests against historical fills, validates execution logic


## Phase 2: Signal Research Engine (Week 2-4)

### 2.1 The Strategy Space Explorer
This is where the superloop pattern maps directly. The system:
1. Ingests academic literature (SSRN, arXiv quant-ph, Journal of Financial Economics)
2. Extracts strategy hypotheses from papers (mean reversion, momentum, carry, value, volatility)
3. For each hypothesis, generates a concrete implementation spec
4. Builds the strategy from its own spec
5. Backtests with full statistical rigor
6. Rejects what fails. Refines what passes.
7. Compounds — each cycle's learnings inform the next cycle's hypotheses

### 2.2 Signal Categories to Explore (Non-Exhaustive)
- **Price/Volume**: Momentum (cross-sectional, time-series), mean reversion, breakout, volume profile
- **Microstructure**: Order flow imbalance, bid-ask spread dynamics, trade-to-quote ratio
- **Fundamental**: Earnings surprise, analyst revision, insider activity, short interest changes
- **Alternative data**: Satellite imagery (parking lots, shipping), NLP on earnings calls, patent filings, job postings
- **Cross-asset**: Equity-bond correlation regime shifts, commodity-equity links, FX carry implications
- **Macro**: Yield curve shape, credit spreads, liquidity proxies, central bank communication NLP

### 2.3 The Verification Loop for Strategies
Every strategy goes through:
1. **Hypothesis**: Clear statement of edge and why it should persist
2. **Implementation**: Code that generates signals from data
3. **Backtest**: Walk-forward, out-of-sample, regime-segmented
4. **Statistical gates**: Sharpe > 1.5 after costs? Max drawdown < 15%? Win rate statistically significant (p < 0.05)? Profit factor > 1.5? 
5. **Regime robustness**: Does it work in bull, bear, sideways, and crisis? If it only works in one regime, label it as regime-conditional, don't discard it
6. **Decay analysis**: When was the signal strongest? Is it decaying? Half-life estimation
7. **Capacity analysis**: How much capital before market impact degrades returns?

Strategies that pass all gates enter the portfolio. Strategies that fail get logged with failure reasons — the system learns what doesn't work as fast as what does.


## Phase 3: Portfolio Construction & Risk (Week 4-6)

### 3.1 Multi-Strategy Portfolio
- Correlation matrix across validated strategies
- Allocation: risk parity, mean-variance optimization, or hierarchical risk parity
- Strategy diversification: at least 5 uncorrelated strategies before going live
- Dynamic allocation: increase weight to strategies performing in-regime, decrease to those out-of-regime
- The system builds the portfolio optimizer, backtests the combined portfolio, validates that diversification actually reduces drawdown

### 3.2 Risk Management System
- Real-time P&L tracking
- VaR and CVaR at portfolio and strategy level
- Correlation breakdown monitoring (when correlations spike, reduce exposure)
- Regime detection: HMM or change-point detection for real-time regime identification
- Circuit breakers: max daily loss, max drawdown, max correlation spike
- The system builds this and validates it against historical crises (2008, 2020 March, 2022)

### 3.3 The Meta-Strategy Layer
This is where the learning loop compounds:
- After N strategy cycles, the system has a dataset: {hypothesis_type, market_conditions, result, failure_reason}
- Pattern detection: which types of strategies work in which regimes?
- The system starts generating better hypotheses because it knows what to skip
- After 1000 cycles, the hypothesis generator is dramatically more efficient than after 10
- This is the CIS (campaign intelligence system) applied to finance — same architecture, different domain

## Phase 4: Live Deployment (Week 6-8)

### 4.1 Paper Trading Validation
- Run top 5 strategies in paper trading for minimum 2 weeks
- Compare paper results to backtest expectations
- Detect implementation bugs: slippage model accurate? Fills realistic? Latency accounted for?
- The auto-QA pipeline validates: does live execution match backtested expectations within statistical tolerance?

### 4.2 Small Capital Live
- Start with minimal capital ($5K-25K depending on strategy capacity requirements)
- Monitor for 30 days
- Compare live Sharpe to backtested Sharpe — if live is >1 standard deviation below backtest, investigate
- Gradual scale-up: double allocation monthly if live matches backtest

### 4.3 Monitoring & Alerting
- Real-time dashboard (the system builds this — it's a web app, which is what it already does)
- Anomaly detection on P&L, volume, fill rates, latency
- Automated position reports
- Drawdown alerts with automatic de-risking


## Phase 5: Recursive Improvement (Ongoing)

### 5.1 The Compounding Loop
- Every trading day produces data
- Every data point refines regime detection
- Every regime shift tests strategy robustness
- Failed strategies produce learnings that improve hypothesis generation
- Successful strategies produce capacity estimates that inform allocation
- The system runs this loop continuously — it doesn't sleep

### 5.2 Signal Decay & Replacement
- All signals decay. Alpha has a half-life.
- The system monitors each strategy's rolling Sharpe
- When a strategy's Sharpe decays below threshold, it triggers a replacement cycle
- The replacement cycle uses everything learned from the decayed strategy to generate better hypotheses
- The portfolio self-heals — dying strategies are replaced before they drag performance

### 5.3 Market Regime Adaptation
- The system maintains a real-time regime model
- When regime changes: immediately reweight portfolio to strategies validated for the new regime
- Regime-conditional strategies activate/deactivate automatically
- The human reviews regime change decisions but doesn't make them

---

## What the Superloop Pattern Provides That Others Don't

| Traditional Quant Shop | Superloop Applied to Finance |
|---|---|
| PhD researchers manually generate hypotheses | System generates hypotheses from literature + accumulated learnings |
| Weeks to implement and backtest one strategy | Minutes to implement, hours to rigorously backtest |
| Manual code review for backtest validity | Mechanical verification — no lookahead bias, walk-forward enforced |
| Strategy goes live after committee review | Strategy goes live after passing statistical gates automatically |
| Team of 10-50 explores maybe 100 strategies/year | System explores 1000+ strategies/month |
| $10M+ annual payroll | Electricity |

---

## Key Risks & Honest Limitations

1. **Overfitting**: The biggest risk. The system can find patterns that don't exist. Mitigation: extreme out-of-sample discipline, walk-forward only, minimum trade count requirements, regime segmentation.

2. **Execution gap**: Backtest ≠ live. Slippage models are approximations. Mitigation: paper trading validation phase, small capital start, gradual scale-up.

3. **Regime change**: A strategy that worked for 10 years can stop working permanently. Markets are adaptive — when enough capital exploits a pattern, the pattern dies. Mitigation: signal decay monitoring, automatic replacement cycle, regime-conditional activation.

4. **Data quality**: Garbage in, garbage out. Survivorship bias in equity data, backfill bias in alternative data. Mitigation: source data from providers with point-in-time databases (avoid survivorship bias), validate data integrity as first pipeline step.

5. **Latency**: This system won't compete with HFT. Microsecond-level strategies require co-located hardware and FPGA. The sweet spot is strategies with holding periods of hours to weeks — where the edge comes from signal quality, not execution speed.

6. **Regulatory**: Algorithmic trading has reporting requirements. Pattern day trader rules apply under $25K. Automated systems need appropriate disclosures. Legal review before live deployment.

7. **Capital requirements**: Some strategies need minimum capital for position sizing to work (can't buy 0.3 shares of BRK.A). Start with liquid, low-priced instruments (ETFs, liquid equities, futures if licensed).

---

## Timeline Summary

| Week | Phase | Deliverable |
|---|---|---|
| 1-2 | Foundation | Data pipeline, backtesting framework, execution layer — all built by superloop |
| 2-4 | Signal Research | Strategy space explorer running 100+ hypothesis cycles |
| 4-6 | Portfolio | Multi-strategy portfolio with risk management, validated against historical crises |
| 6-8 | Live | Paper trading → small capital live, monitoring dashboard |
| 8+ | Recursive | Continuous improvement loop, signal replacement, regime adaptation |

---

## The Core Insight

The same closed loop that works for software — spec, build, verify, diagnose, fix, learn — works for trading strategies. The "spec" is the hypothesis. The "build" is the implementation. The "verify" is the backtest with statistical gates. The "diagnose" is failure analysis (why did this strategy not work?). The "fix" is hypothesis refinement. The "learn" is accumulated pattern knowledge across all tested strategies.

The system that's run 1000 strategy cycles has explored more of the strategy space than a quant team explores in a career. And it does it for the cost of electricity.

The edge isn't in any single strategy. The edge is in the speed and rigor of the exploration loop, and the compounding intelligence that accumulates across iterations.


---

## Phase 0: The Meta-Prompt

Everything above is a curriculum for humans to read. The system doesn't read curricula. It reads a single prompt and generates the specs itself.

### The Seed Prompt (Phase 1 — Infrastructure)

```
You are building a quantitative trading research platform. The platform has three components that must be built in order:

1. Data Pipeline: Ingest OHLCV, order book, and tick data from Polygon.io and Alpaca APIs. Store in DuckDB for fast analytical queries. Parquet for archival. WebSocket for real-time feeds. Data integrity validation on every ingestion — no silent corruption.

2. Backtesting Engine: Event-driven backtester with walk-forward validation, transaction cost modeling (commission + slippage + market impact), regime segmentation (trending/mean-reverting/volatile/quiet via HMM), and statistical significance gates (minimum 100 trades per regime, Sharpe confidence intervals, bootstrap resampling). No lookahead bias — enforce mechanically, not by convention.

3. Execution Layer: Paper trading via Alpaca API. Order types: limit, market, stop, bracket. Position sizing: Kelly criterion and volatility-scaled. Risk management: max drawdown circuit breaker, position limits, correlation limits. Real-time P&L tracking.

Generate a roadmap with features ordered by dependency. Each feature must be completable in a single agent context window. No mock data. No fake endpoints. Real API calls, real data validation, real statistical tests.
```

This prompt produces a `roadmap.md` and `.specs/` directory. The build loop consumes those. Infrastructure is built and validated mechanically — the same way CRE was.

### The Seed Prompt (Phase 2 — Signal Research)

This prompt is fed AFTER Phase 1 infrastructure is built and validated:

```
You are a quantitative research system. You have access to a backtesting engine with walk-forward validation, regime segmentation, and statistical significance gates.

Your task: systematically explore the strategy space.

1. Ingest the following academic sources: [list of SSRN paper IDs, arXiv quant-ph papers, or research topics]. For each, extract the core trading hypothesis.

2. For each hypothesis, generate an implementation spec: what data it needs, what signal it computes, what the entry/exit rules are, what the expected holding period is.

3. Build each strategy from the spec. Backtest with full statistical rigor. Report: Sharpe (net of costs), max drawdown, win rate, profit factor, regime performance, signal decay estimate, capacity estimate.

4. Reject strategies that fail any gate. Log failure reasons. Refine strategies that are close to passing — adjust parameters, test variations.

5. After all hypotheses are tested, produce a summary: which strategies passed, which failed, what patterns emerged in the failures, and what the next batch of hypotheses should explore based on what was learned.

Run this as a campaign. Each strategy is a feature. The build loop handles implementation. The eval sidecar scores statistical rigor. The verification loop checks backtest validity.
```

### The Seed Prompt (Phase 3 — Portfolio)

Fed AFTER Phase 2 produces validated strategies:

```
You have N validated trading strategies with known Sharpe ratios, drawdown profiles, regime dependencies, and correlation structures.

Build a portfolio management system that:
1. Computes optimal allocation across strategies using hierarchical risk parity
2. Monitors real-time regime state and reweights when regime changes
3. Tracks per-strategy rolling Sharpe and triggers replacement when decay detected
4. Enforces portfolio-level risk limits: max drawdown, max correlation spike, VaR/CVaR
5. Produces a real-time dashboard showing P&L, allocation, regime state, and risk metrics
6. Paper trades the portfolio via Alpaca with all strategies running simultaneously

The dashboard is a web app. The system already builds web apps. This is just another build campaign.
```

### The Seed Prompt (Phase 4 — Live + Recursive)

```
The portfolio management system is running in paper trading mode. After 14 days of paper results:

1. Compare paper performance to backtested expectations. Flag any strategy where live Sharpe is >1 standard deviation below backtest.
2. Investigate flagged strategies: is the gap from execution (slippage model wrong?), regime (market shifted?), or signal (alpha decayed?).
3. For strategies that pass validation, generate a deployment spec for small capital live trading.
4. For the signal research engine: generate the next batch of hypotheses based on everything learned from the first batch. What worked, what didn't, what adjacent hypotheses are suggested by the failure patterns.
5. Run the next research campaign autonomously. Report results when complete.

This is the recursive loop. Each cycle produces better hypotheses, better strategies, and more accumulated intelligence. The system that ran 100 cycles is qualitatively different from the system that ran 10.
```

### The Key Insight

Each seed prompt produces a spec. The spec produces a build campaign. The campaign produces software + data. The data informs the next seed prompt. The system generates its own specs from accumulated intelligence.

The human writes the first prompt. The system writes every subsequent spec.
