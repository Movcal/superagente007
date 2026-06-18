# Superagente007 — Autonomous AI Trading Agent on BNB Chain

> BNB Hack: AI Trading Agent Edition — Track 1 Submission

## Overview

Superagente007 is a fully autonomous trading agent running 24/7 on BNB Chain. It reads market data, identifies narrative-driven opportunities, confirms them with technical analysis, executes trades, and manages exits — all without human intervention.

The agent was designed around one core principle: **autonomy requires clarity upfront**. Rather than watching every asset in the market, the agent operates on a curated universe of BEP-20 tokens with solid market cap and verified liquidity on PancakeSwap. This keeps the agent focused, reduces noise, and avoids the volatility risk that comes with low-liquidity assets.

---

## Fiat-to-Crypto Bridge: Funding in Under 2 Minutes

One of the biggest barriers to crypto adoption is moving money from the traditional financial system into a self-custody wallet. Superagente007 addresses this directly.

A Telegram-based funding bot allows the agent wallet to be topped up with USDT in under 2 minutes, using a payment link from a widely adopted payment provider in Argentina. The user sends a simple Telegram message requesting the amount, receives a payment link, approves the bank transfer, and the USDT arrives in the agent wallet automatically. The only manual step is the bank approval — everything else is handled by the bot.

This full flow is demonstrated in the video linked in the Demo section.

**Vision:** The adoption of CVU (Argentina's instant transfer standard) by Binance Argentina would allow this same flow with significantly lower fees, making self-custody crypto accessible to millions of first-time users through just a few Telegram messages. This is the real entry point for mass crypto adoption.

---

## How the Agent Works

### 1. Market Intelligence — CoinMarketCap AI Agent Hub

The agent continuously scans news from the **CoinMarketCap AI Agent Hub** MCP interface. Each token in the monitored universe has been assigned categories, subcategories, and keyword connectors. When news articles mention a token, the agent matches keywords to identify the narrative and classifies the sentiment as `BULLISH_HIGH`, `BULLISH_LOW`, `BEARISH`, or `NEUTRAL`.

Tokens with confirmed bullish narratives are added to a watchlist with a lower volume trigger threshold. The agent tracks how many days a narrative has been building — a narrative confirmed over multiple days carries more weight than a single spike. This allows the agent to position itself ahead of the volume move, not after.

The **CoinMarketCap AI Agent Hub** also provides:
- Global market metrics (Fear & Greed Index, total market cap, BTC dominance)
- Technical analysis per token (RSI, MACD, Fibonacci)
- Latest token-specific news
- Trending market narratives and macro events

### 2. Technical Screening

Once a token enters the watchlist, the agent runs a technical analysis screen using data from the **CoinMarketCap AI Agent Hub**:
- **RSI**: identifies oversold recovery zones vs. overbought exhaustion
- **MACD**: confirms momentum direction via histogram
- **Momentum**: measures 7-day and 30-day price performance

Tokens are rated `good_entry`, `wait`, or `avoid`. Only `good_entry` or `wait` tokens proceed to the entry evaluation stage.

### 3. Entry Decision — Claude (Anthropic)

When a volume spike is detected on a watchlist token, the agent evaluates the entry using **Claude Haiku (Anthropic)**. Claude receives:
- The full market context (Fear & Greed, global metrics, macro events)
- The token's technical analysis summary
- Whether the token has a pre-confirmed narrative in the watchlist
- The operator's trading rules — built from real trading experience, not generic templates

Claude responds with `PROCEED`, `SKIP`, or `REDUCE_SIZE`, and its reasoning is logged for full transparency.

For tokens **without** a prior narrative, Claude investigates the cause of the spike — distinguishing between panic buying, euphoria, or an emerging narrative — before allowing entry.

Volume thresholds are dynamic:
- **5x** average volume — tokens with no prior narrative
- **3x** — tokens in the watchlist
- **2x** — tokens that have held a confirmed narrative for 3+ days

### 4. Trade Execution — Trust Wallet Agent Kit

All trades are executed on BSC via the **Trust Wallet Agent Kit (TWAK)**:
- Token swaps on PancakeSwap through TWAK's self-custody execution layer
- Private keys never leave the agent's local environment — full self-custody at every step
- Gas fees are sponsored by MegaFuel (Trust Wallet infrastructure), enabling gasless transactions
- Competition registration was submitted on-chain via `twak compete register`

TWAK is the sole execution layer — no centralized exchange, no custodial intermediary.

### 5. Position Management & Exits

Open positions are monitored every 5 minutes. Exits are triggered by:

1. **Negative news** — keywords like `hack`, `exploit`, `rug`, `ban`, `lawsuit` in recent news trigger immediate exit
2. **Technical exhaustion** — requires all three signals simultaneously: RSI > 70, MACD histogram crossing negative, and volume returning to baseline
3. **Trailing stop** — activates when price rises 2% from entry; stop is set at 2% below the highest price reached
4. **Hard stop loss** — -8% from entry price, active before the trailing stop kicks in
5. **Macro protection** — BTC drops more than 3% in 1 hour triggers exit from all altcoin positions

There is no maximum hold time. The agent stays in a position as long as none of the exit conditions are met.

### 6. Trained on Real Trading Experience

The agent was trained with a knowledge base built from the operator's actual trading history. `knowledge/MARKET_RULES.md` encodes pattern recognition developed through real market exposure — which narratives tend to sustain, what news signals precede dumps, and how to size positions relative to signal strength. Claude uses this as its decision framework on every trade evaluation.

---

## BNB AI Agent SDK

The agent operates exclusively on **BNB Smart Chain** using BEP-20 tokens. The BNB Chain infrastructure provides the settlement layer for all swaps, the on-chain competition contract, and the PancakeSwap liquidity pools used for trade execution.

---

## Public Dashboard

A live dashboard is accessible at [http://161.35.127.148:8080](http://161.35.127.148:8080).

The dashboard was built as a public window into the agent's decision-making. Visitors can see in real time which market narratives the agent is tracking, what trades it has opened or closed, and the reasoning behind each decision. The goal is to let anyone — regardless of technical background — understand how the agent thinks and why it acts. This transparency is the foundation for trust, and trust is what turns a curious visitor into a future user.

---

## Tech Stack

| Component | Tool |
|---|---|
| News & market data | CoinMarketCap AI Agent Hub (MCP) |
| Technical analysis | CoinMarketCap AI Agent Hub (MCP) |
| Decision intelligence | Claude Haiku (Anthropic) |
| Trade execution | Trust Wallet Agent Kit (TWAK) |
| Blockchain | BNB Smart Chain (BEP-20) |
| DEX | PancakeSwap |
| Gas sponsorship | MegaFuel (Trust Wallet) |
| Fiat bridge | Telegram bot + MercadoPago |
| Hosting | DigitalOcean VPS (Ubuntu 22.04, systemd 24/7) |
| Backend | Python 3.11 |
| Dashboard | FastAPI + HTML/JS |

---

## Agent Wallet

```
BSC: 0xABC819c3aeE6419333d2D7df365484E5CC833222
```

Registration TX: [0x5719c66...](https://bscscan.com/tx/0x5719c66126366033e48d8b10dbe3d9ce7db3092028de004ebe973e208c7709a5)

---

## Setup

```bash
git clone https://github.com/Movcal/superagente007
cd superagente007
python -m venv venv && source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env   # fill in your API keys
python agent.py        # start the agent
python dashboard.py    # start the dashboard (separate terminal)
```

**Required environment variables:**
```
CMC_API_KEY=
ANTHROPIC_API_KEY=
TWAK_BSC_SPONSORED_RPC_URL=https://bsc-dataseed.binance.org
CLAUDE_ENABLED=true
PAPER_MODE=false
```

---

## Demo

- Live dashboard: [http://161.35.127.148:8080](http://161.35.127.148:8080)
- Fiat-to-crypto funding demo (video): *(coming soon)*

---

## License

MIT
