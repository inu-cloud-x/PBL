import { getConfig } from '../config'
import { createHeliosClient } from './helios'
import type { SmartWalletClient } from './wallet'

const ABI = [
  {
    name: 'register',
    type: 'function',
    stateMutability: 'nonpayable',
    inputs: [{ name: 'name', type: 'string' }],
    outputs: [],
  },
  {
    name: 'release',
    type: 'function',
    stateMutability: 'nonpayable',
    inputs: [],
    outputs: [],
  },
  {
    name: 'resolve',
    type: 'function',
    stateMutability: 'view',
    inputs: [{ name: 'name', type: 'string' }],
    outputs: [{ name: '', type: 'address' }],
  },
  {
    name: 'reverseLookup',
    type: 'function',
    stateMutability: 'view',
    inputs: [{ name: 'addr', type: 'address' }],
    outputs: [{ name: '', type: 'string' }],
  },
] as const

function getContractAddress(): `0x${string}` {
  const addr = getConfig().miniEnsAddress
  if (!addr) throw new Error('VITE_MINI_ENS_ADDRESS가 설정되지 않았습니다')
  return addr
}

export async function ensRegister(client: SmartWalletClient, name: string): Promise<`0x${string}`> {
  return client.writeContract({
    address: getContractAddress(),
    abi: ABI,
    functionName: 'register',
    args: [name],
  })
}

export async function ensRelease(client: SmartWalletClient): Promise<`0x${string}`> {
  return client.writeContract({
    address: getContractAddress(),
    abi: ABI,
    functionName: 'release',
    args: [],
  })
}

// Read via Helios-verified light client — no raw RPC fallback
export async function ensResolve(name: string): Promise<`0x${string}`> {
  const heliosClient = createHeliosClient()
  return heliosClient.readContract({
    address: getContractAddress(),
    abi: ABI,
    functionName: 'resolve',
    args: [name],
  })
}

// Read via Helios-verified light client — no raw RPC fallback
export async function ensReverseLookup(addr: `0x${string}`): Promise<string> {
  const heliosClient = createHeliosClient()
  return heliosClient.readContract({
    address: getContractAddress(),
    abi: ABI,
    functionName: 'reverseLookup',
    args: [addr],
  })
}
