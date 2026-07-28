import { toHex, fromHex } from 'viem'
import { getConfig } from '../config'
import { createHeliosClient } from './helios'
import type { SmartWalletClient } from './wallet'

const ABI = [
  {
    name: 'store',
    type: 'function',
    stateMutability: 'nonpayable',
    inputs: [{ name: 'value', type: 'bytes' }],
    outputs: [],
  },
  {
    name: 'remove',
    type: 'function',
    stateMutability: 'nonpayable',
    inputs: [{ name: 'index', type: 'uint256' }],
    outputs: [],
  },
  {
    name: 'getAll',
    type: 'function',
    stateMutability: 'view',
    inputs: [{ name: 'user', type: 'address' }],
    outputs: [
      {
        name: '',
        type: 'tuple[]',
        components: [
          { name: 'data', type: 'bytes' },
          { name: 'timestamp', type: 'uint256' },
        ],
      },
    ],
  },
] as const

export type Entry = {
  text: string
  timestamp: bigint
  index: number   // storage index (needed for remove())
}

function getContractAddress(): `0x${string}` {
  const config = getConfig()
  if (!config.dataStoreAddress) throw new Error('VITE_DATA_STORE_ADDRESS가 설정되지 않았습니다')
  return config.dataStoreAddress
}

export async function datastoreAdd(client: SmartWalletClient, text: string): Promise<`0x${string}`> {
  return client.writeContract({
    address: getContractAddress(),
    abi: ABI,
    functionName: 'store',
    args: [toHex(new TextEncoder().encode(text))],
  })
}

export async function datastoreRemove(client: SmartWalletClient, index: number): Promise<`0x${string}`> {
  return client.writeContract({
    address: getContractAddress(),
    abi: ABI,
    functionName: 'remove',
    args: [BigInt(index)],
  })
}

// Read via Helios-verified light client — no raw RPC fallback
export async function datastoreGetAll(userAddress: `0x${string}`): Promise<Entry[]> {
  const heliosClient = createHeliosClient()
  const raw = await heliosClient.readContract({
    address: getContractAddress(),
    abi: ABI,
    functionName: 'getAll',
    args: [userAddress],
  })

  // Attach original storage index before sorting (swap-and-pop changes order)
  const entries: Entry[] = raw.map((item, index) => ({
    text: new TextDecoder().decode(fromHex(item.data, 'bytes')),
    timestamp: item.timestamp,
    index,
  }))

  // Sort by timestamp DESC (latest first)
  return entries.sort((a, b) => (b.timestamp > a.timestamp ? 1 : -1))
}
