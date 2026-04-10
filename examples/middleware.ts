/**
 * Minimal x402 skill marketplace middleware.
 *
 * Returns 402 Payment Required with creator's wallet address.
 * Verifies on-chain payment receipt before granting access.
 * The server never touches funds.
 */

import { type Request, type Response, type NextFunction } from "express";
import { createPublicClient, http, parseAbi } from "viem";
import { base } from "viem/chains";

const USDC_ADDRESS = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913";
const USDC_DECIMALS = 6;

const client = createPublicClient({ chain: base, transport: http() });

interface Asset {
  id: string;
  name: string;
  creatorAddress: `0x${string}`;
  priceUsdc: number; // in human-readable units, e.g. 0.01
}

// In-memory asset registry (replace with your own storage)
const assets: Map<string, Asset> = new Map();

/**
 * Middleware: returns 402 if no valid payment receipt is provided.
 */
export function requirePayment(
  getAsset: (id: string) => Asset | undefined
) {
  return async (req: Request, res: Response, next: NextFunction) => {
    const asset = getAsset(req.params.id);
    if (!asset) return res.status(404).json({ error: "Asset not found" });

    const receipt = req.header("X-PAYMENT-RECEIPT");

    // No receipt: return 402 challenge
    if (!receipt) {
      return res.status(402).json({
        x402Version: 1,
        accepts: [
          {
            scheme: "exact",
            network: "base",
            maxAmountRequired: String(
              BigInt(asset.priceUsdc * 10 ** USDC_DECIMALS)
            ),
            resource: `${req.protocol}://${req.get("host")}${req.originalUrl}`,
            description: `Access to skill: ${asset.name}`,
            payTo: asset.creatorAddress,
            maxTimeoutSeconds: 300,
            asset: USDC_ADDRESS,
          },
        ],
      });
    }

    // Has receipt: verify on-chain
    const { txHash } = JSON.parse(receipt) as { txHash: `0x${string}` };

    const verified = await verifyPayment(
      txHash,
      asset.creatorAddress,
      asset.priceUsdc
    );

    if (!verified) {
      return res.status(402).json({ error: "Payment verification failed" });
    }

    // Record observation (the only thing the marketplace "does" with money)
    recordObservation({
      assetId: asset.id,
      agentAddress: req.header("X-AGENT-ADDRESS") || "unknown",
      creatorAddress: asset.creatorAddress,
      amount: asset.priceUsdc,
      txHash,
      timestamp: new Date().toISOString(),
    });

    next();
  };
}

/**
 * Verify that a USDC transfer occurred on Base.
 */
async function verifyPayment(
  txHash: `0x${string}`,
  expectedRecipient: `0x${string}`,
  expectedAmount: number
): Promise<boolean> {
  const receipt = await client.getTransactionReceipt({ hash: txHash });
  if (receipt.status !== "success") return false;

  const transferEventAbi = parseAbi([
    "event Transfer(address indexed from, address indexed to, uint256 value)",
  ]);

  const expectedValue = BigInt(expectedAmount * 10 ** USDC_DECIMALS);

  for (const log of receipt.logs) {
    if (log.address.toLowerCase() !== USDC_ADDRESS.toLowerCase()) continue;
    try {
      const [, to, value] = [
        log.topics[1], // from
        log.topics[2], // to
        log.data, // value
      ];
      const toAddress = `0x${to?.slice(26)}` as `0x${string}`;
      const transferValue = BigInt(value || "0");

      if (
        toAddress.toLowerCase() === expectedRecipient.toLowerCase() &&
        transferValue >= expectedValue
      ) {
        return true;
      }
    } catch {
      continue;
    }
  }
  return false;
}

/**
 * Record a payment observation. This is the atomic unit of Proof-of-Spend.
 * Replace with your own persistence layer.
 */
function recordObservation(obs: {
  assetId: string;
  agentAddress: string;
  creatorAddress: string;
  amount: number;
  txHash: string;
  timestamp: string;
}) {
  console.log("[proof-of-spend] observation:", JSON.stringify(obs));
}
