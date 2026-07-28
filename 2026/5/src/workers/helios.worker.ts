import { createHeliosProvider } from '@a16z/helios'
import { expose } from 'comlink'

let provider: Awaited<ReturnType<typeof createHeliosProvider>> | null = null
let keepAliveTimer: ReturnType<typeof setInterval> | null = null

// Fetch the latest finalized block root from the beacon API.
// Helios requires a finalized checkpoint to bootstrap — without it,
// it may pick a non-finalized block and receive a 404 from the beacon node.
async function fetchFinalizedCheckpoint(consensusRpc: string): Promise<string | undefined> {
  try {
    const res = await fetch(`${consensusRpc}/eth/v1/beacon/blocks/finalized/root`)
    if (!res.ok) return undefined
    const json = await res.json()
    return json?.data?.root as string | undefined
  } catch {
    return undefined
  }
}

const api = {
  async init(executionRpc: string, consensusRpc: string): Promise<void> {
    const checkpoint = await fetchFinalizedCheckpoint(consensusRpc)

    provider = await createHeliosProvider(
      {
        executionRpc,
        consensusRpc,
        network: 'sepolia',
        dbType: 'config',
        ...(checkpoint ? { checkpoint } : {}),
      },
      'ethereum',
    )

    // BLS verification + Merkle proof work runs here, off the main thread
    await provider.waitSynced()

    // Keepalive: poll every slot (12s) to keep the WASM sync loop alive
    keepAliveTimer = setInterval(async () => {
      try {
        await provider!.request({ method: 'eth_blockNumber', params: [] })
      } catch {
        // drift detected — main thread will reset via isOutOfSync check
      }
    }, 12_000)
  },

  async request(method: string, params: unknown[] = []): Promise<unknown> {
    if (!provider) throw new Error('Helios worker: not initialized')
    return provider.request({ method, params } as Parameters<typeof provider.request>[0])
  },

  dispose(): void {
    if (keepAliveTimer !== null) {
      clearInterval(keepAliveTimer)
      keepAliveTimer = null
    }
    provider = null
  },
}

expose(api)
