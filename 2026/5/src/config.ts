import { sepolia } from 'viem/chains'
import type { Chain } from 'viem'

function requireEnv(key: string): string {
  const val = import.meta.env[key]
  if (!val) throw new Error(`Missing env var: ${key}`)
  return val
}

function optionalEnv(key: string): string | undefined {
  return import.meta.env[key] || undefined
}

const CHAIN_MAP: Record<number, Chain> = {
  11155111: sepolia,
}

export function getChain(): Chain {
  const chainId = Number(import.meta.env.VITE_TARGET_CHAIN_ID)
  const chain = CHAIN_MAP[chainId]
  if (!chain) throw new Error(`Unsupported VITE_TARGET_CHAIN_ID: ${chainId}`)
  return chain
}

export function getConfig() {
  return {
    chainId: Number(import.meta.env.VITE_TARGET_CHAIN_ID),
    executionRpcUrl: optionalEnv('VITE_EXECUTION_RPC_URL'),
    consensusRpcUrl: optionalEnv('VITE_CONSENSUS_RPC_URL'),
    bundlerUrl: optionalEnv('VITE_BUNDLER_URL'),
    paymasterUrl: optionalEnv('VITE_PAYMASTER_URL'),
    dataStoreAddress: optionalEnv('VITE_DATA_STORE_ADDRESS') as `0x${string}` | undefined,
    smartWalletFactory: optionalEnv('VITE_SMART_WALLET_FACTORY') as `0x${string}` | undefined,
    passkeyRegistryAddress: optionalEnv('VITE_PASSKEY_REGISTRY_ADDRESS') as `0x${string}` | undefined,
    zerodevProjectId: optionalEnv('VITE_ZERODEV_PROJECT_ID'),
    miniEnsAddress: optionalEnv('VITE_MINI_ENS_ADDRESS') as `0x${string}` | undefined,
    votingRegistryAddress: optionalEnv('VITE_VOTING_REGISTRY_ADDRESS') as `0x${string}` | undefined,
    vcRegistryAddress: optionalEnv('VITE_VC_REGISTRY_ADDRESS') as `0x${string}` | undefined,
  } as const
}

export type Config = ReturnType<typeof getConfig>

export function getMissingEnvKeys(): string[] {
  const required = [
    'VITE_TARGET_CHAIN_ID',
    'VITE_EXECUTION_RPC_URL',
    'VITE_CONSENSUS_RPC_URL',
    'VITE_BUNDLER_URL',
    'VITE_DATA_STORE_ADDRESS',
    'VITE_ZERODEV_PROJECT_ID',
  ]
  return required.filter((k) => !import.meta.env[k])
}

// Optional v2/v3 contracts — app starts without them; individual tabs show "미배포" notice.
export function getMissingOptionalEnvKeys(): string[] {
  const optional = [
    'VITE_MINI_ENS_ADDRESS',
    'VITE_VOTING_REGISTRY_ADDRESS',
    'VITE_VC_REGISTRY_ADDRESS',
  ]
  return optional.filter((k) => !import.meta.env[k])
}

void requireEnv
