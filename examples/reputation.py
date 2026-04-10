"""
Proof-of-Spend reputation score computation.

Computes asset reputation from on-chain payment observations only.
No stars, no downloads, no ratings --- just verified economic decisions.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass
class Observation:
    asset_id: str
    agent_address: str
    creator_address: str
    amount_usdc: float
    tx_hash: str
    timestamp: datetime


@dataclass
class AssetReputation:
    asset_id: str
    spend_count: int
    unique_agents: int
    recurrence_rate: float  # fraction of agents with 2+ purchases
    velocity_30d: int  # payments in last 30 days
    score: float


# Tunable weights
W_SPEND = 1.0
W_AGENTS = 1.5  # diversity matters more than volume
W_RECURRENCE = 2.0  # retention is the hardest to fake
W_VELOCITY = 0.8


def compute_reputation(
    observations: list[Observation],
    now: datetime | None = None,
) -> dict[str, AssetReputation]:
    """Compute reputation scores for all assets from payment observations."""

    now = now or datetime.utcnow()
    window_30d = now - timedelta(days=30)

    # Group by asset
    by_asset: dict[str, list[Observation]] = defaultdict(list)
    for obs in observations:
        by_asset[obs.asset_id].append(obs)

    results = {}

    for asset_id, obs_list in by_asset.items():
        # Basic counts
        spend_count = len(obs_list)
        agents = set(o.agent_address for o in obs_list)
        unique_agents = len(agents)

        # Recurrence: how many agents came back?
        agent_counts: dict[str, int] = defaultdict(int)
        for o in obs_list:
            agent_counts[o.agent_address] += 1
        recurring = sum(1 for c in agent_counts.values() if c >= 2)
        recurrence_rate = recurring / unique_agents if unique_agents > 0 else 0.0

        # Velocity: payments in last 30 days
        velocity_30d = sum(1 for o in obs_list if o.timestamp >= window_30d)

        # Composite score (log-scaled to prevent volume dominance)
        score = (
            W_SPEND * math.log1p(spend_count)
            + W_AGENTS * math.log1p(unique_agents)
            + W_RECURRENCE * recurrence_rate
            + W_VELOCITY * math.log1p(velocity_30d)
        )

        results[asset_id] = AssetReputation(
            asset_id=asset_id,
            spend_count=spend_count,
            unique_agents=unique_agents,
            recurrence_rate=recurrence_rate,
            velocity_30d=velocity_30d,
            score=round(score, 4),
        )

    return results


# --- Example usage ---

if __name__ == "__main__":
    now = datetime(2026, 4, 11)

    sample_observations = [
        # Popular skill: many agents, some recurring
        *[
            Observation("skill-a", f"agent-{i}", "creator-1", 0.01, f"0xaaa{i}", now - timedelta(days=i % 60))
            for i in range(200)
        ],
        # Recurring agents for skill-a
        *[
            Observation("skill-a", f"agent-{i}", "creator-1", 0.01, f"0xbbb{i}", now - timedelta(days=3))
            for i in range(50)
        ],
        # Niche skill: fewer agents, but very high recurrence
        *[
            Observation("skill-b", f"agent-{i}", "creator-2", 0.05, f"0xccc{i}{j}", now - timedelta(days=j * 3))
            for i in range(20)
            for j in range(5)
        ],
        # Low-quality skill: one agent inflating (sybil-like)
        *[
            Observation("skill-c", "agent-sybil", "creator-3", 0.001, f"0xddd{i}", now - timedelta(days=i))
            for i in range(500)
        ],
    ]

    reputations = compute_reputation(sample_observations, now=now)

    print("=== Proof-of-Spend Reputation Scores ===\n")
    for rep in sorted(reputations.values(), key=lambda r: r.score, reverse=True):
        print(f"  {rep.asset_id}")
        print(f"    score:           {rep.score}")
        print(f"    spend_count:     {rep.spend_count}")
        print(f"    unique_agents:   {rep.unique_agents}")
        print(f"    recurrence_rate: {rep.recurrence_rate:.2%}")
        print(f"    velocity_30d:    {rep.velocity_30d}")
        print()
