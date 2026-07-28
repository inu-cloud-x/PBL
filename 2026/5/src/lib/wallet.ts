import { createPublicClient, http, zeroAddress } from 'viem'
import { entryPoint07Address } from 'viem/account-abstraction'
import { createKernelAccount, createKernelAccountClient, createZeroDevPaymasterClient } from '@zerodev/sdk'
import { toPasskeyValidator, PasskeyValidatorContractVersion } from '@zerodev/passkey-validator'
import type { WebAuthnKey } from '@zerodev/webauthn-key'
import { getChain, getConfig } from '../config'

const ENTRY_POINT = {
  address: entryPoint07Address,
  version: '0.7' as const,
}

const KERNEL_VERSION = '0.3.3'

const REGISTRY_ABI = [
  {
    name: 'accountOf',
    type: 'function',
    stateMutability: 'view',
    inputs: [{ name: 'credentialIdHash', type: 'bytes32' }],
    outputs: [{ name: '', type: 'address' }],
  },
  {
    name: 'link',
    type: 'function',
    stateMutability: 'nonpayable',
    inputs: [{ name: 'credentialIdHash', type: 'bytes32' }],
    outputs: [],
  },
] as const

export type SmartWalletClient = Awaited<ReturnType<typeof createSmartWalletClient>>

export async function createSmartWalletClient(webAuthnKey: WebAuthnKey) {
  const config = getConfig()
  const chain = getChain()

  if (!config.executionRpcUrl) throw new Error('VITE_EXECUTION_RPC_URL이 설정되지 않았습니다')
  if (!config.bundlerUrl) throw new Error('VITE_BUNDLER_URL이 설정되지 않았습니다')

  const publicClient = createPublicClient({
    chain,
    transport: http(config.executionRpcUrl),
  })

  const passkeyValidator = await toPasskeyValidator(publicClient, {
    webAuthnKey,
    entryPoint: ENTRY_POINT,
    kernelVersion: KERNEL_VERSION,
    validatorContractVersion: PasskeyValidatorContractVersion.V0_0_3_PATCHED,
  })

  const account = await createKernelAccount(publicClient, {
    plugins: { sudo: passkeyValidator },
    entryPoint: ENTRY_POINT,
    kernelVersion: KERNEL_VERSION,
  })

  const paymasterClient = config.paymasterUrl
    ? createZeroDevPaymasterClient({ chain, transport: http(config.paymasterUrl) })
    : undefined

  const kernelClient = createKernelAccountClient({
    account,
    chain,
    bundlerTransport: http(config.bundlerUrl),
    ...(paymasterClient && { paymaster: paymasterClient }),
  })

  return kernelClient
}

/// Link this wallet to PasskeyRegistry so other dApps can discover it
/// by credentialIdHash. No-ops silently if registry is not configured
/// or the credential is already linked.
export async function linkToPasskeyRegistry(
  client: SmartWalletClient,
  credentialIdHash: `0x${string}`,
): Promise<'linked' | 'already_linked' | 'skipped'> {
  const config = getConfig()
  if (!config.passkeyRegistryAddress) return 'skipped'

  const chain = getChain()
  const publicClient = createPublicClient({
    chain,
    transport: http(config.executionRpcUrl!),
  })

  const existing = await publicClient.readContract({
    address: config.passkeyRegistryAddress,
    abi: REGISTRY_ABI,
    functionName: 'accountOf',
    args: [credentialIdHash],
  })

  if (existing !== zeroAddress) return 'already_linked'

  await client.writeContract({
    address: config.passkeyRegistryAddress,
    abi: REGISTRY_ABI,
    functionName: 'link',
    args: [credentialIdHash],
  })

  return 'linked'
}

export function getAccountAddress(client: SmartWalletClient): `0x${string}` {
  return client.account.address
}
