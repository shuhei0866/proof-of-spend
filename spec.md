# Proof-of-Spend Protocol Specification

**Version**: 0.1.0-draft
**Status**: Proposal

## 1. Overview

Proof-of-Spend defines a trust layer for agent-to-agent asset markets. It uses verifiable payment logs as the sole input for reputation computation, replacing cost-free signals (stars, downloads, ratings) that lose information content when evaluation cost approaches zero.

The protocol assumes:
- Assets are served over HTTP
- Payment is handled via [x402](https://x402.org) (HTTP 402 Payment Required)
- Settlement occurs on an EVM-compatible chain (e.g., Base)
- The marketplace is non-custodial

## 2. Actors

| Actor | Role | Touches funds? |
|-------|------|---------------|
| **Agent** | Discovers, evaluates, and purchases assets | Yes (own wallet) |
| **Creator** | Publishes assets and receives payment | Yes (own wallet) |
| **Marketplace** | Serves catalog, issues 402 challenges, observes payments | **No** |
| **Chain** | Settles payments, provides verifiable receipts | N/A |

The marketplace MUST NOT hold private keys, custody funds, execute transactions on behalf of users, or perform any form of fund splitting or escrow.

## 3. Payment flow

### 3.1 Discovery

```
Agent -> Marketplace: GET /catalog
Marketplace -> Agent: 200 OK (asset list with metadata)
```

The catalog includes asset IDs, descriptions, creator addresses, and price. No payment is required for browsing.

### 3.2 Access request

```
Agent -> Marketplace: GET /assets/{id}/access
Marketplace -> Agent: 402 Payment Required
```

The 402 response body follows the x402 payment challenge format:

```json
{
  "x402Version": 1,
  "accepts": [
    {
      "scheme": "exact",
      "network": "base",
      "maxAmountRequired": "10000",
      "resource": "https://marketplace.example/assets/{id}/access",
      "description": "Access to skill: {asset_name}",
      "mimeType": "application/json",
      "payTo": "0x<creator_wallet_address>",
      "maxTimeoutSeconds": 300,
      "asset": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
    }
  ]
}
```

Key design point: `payTo` is the **creator's address**, not the marketplace's. Payment flows P2P.

### 3.3 Payment

The agent pays directly to the creator's wallet using its own CLI wallet. This transaction occurs entirely outside the marketplace's control.

```
Agent -> Chain: Transfer USDC to creator address
Chain -> Agent: tx hash
```

### 3.4 Verification and access

```
Agent -> Marketplace: GET /assets/{id}/access
  Header: X-PAYMENT-RECEIPT: <signed_receipt_with_tx_hash>
Marketplace -> Chain: Verify transaction (recipient, amount, asset, status)
Chain -> Marketplace: Confirmed
Marketplace -> Agent: 200 OK (asset payload)
```

The marketplace verifies the on-chain transaction matches the 402 challenge parameters. If valid, the asset is delivered.

### 3.5 Observation

Upon successful verification, the marketplace records a payment observation:

```json
{
  "assetId": "skill-xyz",
  "agentAddress": "0x<agent>",
  "creatorAddress": "0x<creator>",
  "amount": "10000",
  "asset": "USDC",
  "network": "base",
  "txHash": "0x<hash>",
  "blockNumber": 12345678,
  "timestamp": "2026-04-11T00:00:00Z"
}
```

This observation is the atomic unit of the Proof-of-Spend reputation system.

## 4. Reputation computation

### 4.1 Input

All reputation scores are computed from the set of payment observations. No other input is used.

### 4.2 Asset-level signals

For a given asset `a`:

| Signal | Definition |
|--------|-----------|
| `spend_count(a)` | Total number of payment observations |
| `unique_agents(a)` | Count of distinct agent addresses |
| `recurrence_rate(a)` | Fraction of agents with 2+ payments |
| `spend_velocity(a, window)` | Payment count within a rolling time window |
| `price_trend(a, window)` | Direction of price change over time |

### 4.3 Composite score

A simple composite score for ranking:

```
score(a) = w1 * log(spend_count(a))
         + w2 * log(unique_agents(a))
         + w3 * recurrence_rate(a)
         + w4 * spend_velocity(a, 30d)
```

Weights `w1..w4` are tunable. The logarithmic scaling prevents high-volume assets from dominating purely by spend count.

Important: this is NOT pay-to-rank. A high price does not improve score. The signal is in the *pattern of decisions*, not the magnitude of any single payment.

### 4.4 Agent-level signals

For a given agent `g`:

| Signal | Definition |
|--------|-----------|
| `total_spend(g)` | Total USDC spent across all assets |
| `asset_diversity(g)` | Count of distinct assets purchased |
| `hit_rate(g)` | Fraction of purchased assets that agent continues to use |

Agent-level signals enable a secondary trust layer: an agent that consistently discovers high-quality assets early becomes a valuable signal source itself --- analogous to a PageRank hub.

### 4.5 Co-purchase graph

When agents `g1` and `g2` both pay for assets `a1` and `a2`, a co-purchase edge is formed. The co-purchase graph enables collaborative filtering:

- "Agents who paid for X also paid for Y"
- Cluster detection reveals asset categories
- Anomalous co-purchase patterns may indicate gaming attempts

## 5. Anti-gaming considerations

### 5.1 Sybil spending

An attacker creates multiple agent wallets and pays for their own asset to inflate `spend_count`.

Mitigations:
- `unique_agents` weighted by agent history (new wallets with no prior spend carry less weight)
- Cost of attack is real (actual USDC spent, even if cycling between own wallets)
- Co-purchase analysis: sybil agents have abnormally low `asset_diversity`

### 5.2 Wash trading

Creator pays themselves through agent wallets they control.

Mitigations:
- On-chain fund flow analysis can detect circular patterns
- `recurrence_rate` and `spend_velocity` patterns differ from organic usage
- Economic cost remains real --- gas fees and capital lockup

### 5.3 Fundamental constraint

Unlike star-based gaming which costs nothing, every attack on Proof-of-Spend requires spending real money. The cost of attack scales linearly with the desired reputation boost. This does not make gaming impossible, but it makes the cost of gaming *visible and measurable*.

## 6. Open questions

- How should free/OSS assets coexist with paid assets in the reputation layer?
- Can payment observations be privacy-preserved while remaining verifiable (e.g., ZK proofs of spend)?
- What bootstrapping mechanisms help new assets with zero payment history gain initial visibility?
- Should the marketplace publish raw observations or only computed scores?

## 7. References

- [x402 Protocol](https://x402.org)
- [HTTP 402 Payment Required (RFC 9110)](https://httpwg.org/specs/rfc9110.html#status.402)
- Brin, S. & Page, L. (1998). "The Anatomy of a Large-Scale Hypertextual Web Search Engine"
