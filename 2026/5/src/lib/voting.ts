import { toHex, fromHex } from 'viem'
import { getConfig } from '../config'
import { createHeliosClient } from './helios'
import type { SmartWalletClient } from './wallet'

// ── types ─────────────────────────────────────────────────────────────────────

export const Choice = { Yes: 0, No: 1, Abstain: 2 } as const
export type ChoiceValue = 0 | 1 | 2

export const CHOICE_LABEL: Record<ChoiceValue, string> = { 0: 'Yes', 1: 'No', 2: '기권' }
export const CHOICE_COLOR: Record<ChoiceValue, string> = { 0: '#4caf50', 1: '#f44336', 2: '#9e9e9e' }

export type Proposal = {
  id: number
  creator: `0x${string}`
  title: string
  description: string
  deadline: number  // Unix seconds
  yesVotes: number
  noVotes: number
  abstainVotes: number
}

// ── ABI ───────────────────────────────────────────────────────────────────────

const ABI = [
  {
    name: 'proposalCount',
    type: 'function',
    stateMutability: 'view',
    inputs: [],
    outputs: [{ name: '', type: 'uint256' }],
  },
  {
    name: 'createProposal',
    type: 'function',
    stateMutability: 'nonpayable',
    inputs: [
      { name: 'title',       type: 'string'  },
      { name: 'description', type: 'bytes'   },
      { name: 'duration',    type: 'uint256' },
    ],
    outputs: [],
  },
  {
    name: 'vote',
    type: 'function',
    stateMutability: 'nonpayable',
    inputs: [
      { name: 'proposalId', type: 'uint256' },
      { name: 'choice',     type: 'uint8'   },
    ],
    outputs: [],
  },
  {
    name: 'getProposal',
    type: 'function',
    stateMutability: 'view',
    inputs: [{ name: 'id', type: 'uint256' }],
    outputs: [
      {
        name: '',
        type: 'tuple',
        components: [
          { name: 'creator',      type: 'address' },
          { name: 'title',        type: 'string'  },
          { name: 'description',  type: 'bytes'   },
          { name: 'deadline',     type: 'uint64'  },
          { name: 'yesVotes',     type: 'uint128' },
          { name: 'noVotes',      type: 'uint128' },
          { name: 'abstainVotes', type: 'uint128' },
        ],
      },
    ],
  },
  {
    name: 'hasVoted',
    type: 'function',
    stateMutability: 'view',
    inputs: [
      { name: 'proposalId', type: 'uint256' },
      { name: 'voter',      type: 'address' },
    ],
    outputs: [{ name: '', type: 'bool' }],
  },
] as const

// ── helpers ───────────────────────────────────────────────────────────────────

function getContractAddress(): `0x${string}` {
  const addr = getConfig().votingRegistryAddress
  if (!addr) throw new Error('VITE_VOTING_REGISTRY_ADDRESS가 설정되지 않았습니다')
  return addr
}

type RawProposal = {
  creator: `0x${string}`
  title: string
  description: `0x${string}`
  deadline: bigint
  yesVotes: bigint
  noVotes: bigint
  abstainVotes: bigint
}

function decodeProposal(raw: RawProposal, id: number): Proposal {
  return {
    id,
    creator:     raw.creator,
    title:       raw.title,
    description: new TextDecoder().decode(fromHex(raw.description, 'bytes')),
    deadline:    Number(raw.deadline),
    yesVotes:    Number(raw.yesVotes),
    noVotes:     Number(raw.noVotes),
    abstainVotes: Number(raw.abstainVotes),
  }
}

// ── write functions (AA-routed) ───────────────────────────────────────────────

export async function votingCreate(
  client: SmartWalletClient,
  title: string,
  description: string,
  durationSecs: number,
): Promise<`0x${string}`> {
  return client.writeContract({
    address: getContractAddress(),
    abi: ABI,
    functionName: 'createProposal',
    args: [title, toHex(new TextEncoder().encode(description)), BigInt(durationSecs)],
  })
}

export async function votingVote(
  client: SmartWalletClient,
  proposalId: number,
  choice: ChoiceValue,
): Promise<`0x${string}`> {
  return client.writeContract({
    address: getContractAddress(),
    abi: ABI,
    functionName: 'vote',
    args: [BigInt(proposalId), choice],
  })
}

// ── read functions (Helios-verified) ─────────────────────────────────────────

export async function votingGetRecent(count: number): Promise<Proposal[]> {
  const heliosClient  = createHeliosClient()
  const contractAddr  = getContractAddress()

  const total = Number(
    await heliosClient.readContract({
      address: contractAddr, abi: ABI, functionName: 'proposalCount',
    }),
  )
  if (total === 0) return []

  const start = Math.max(0, total - count)
  // newest-first: [total-1, total-2, ..., start]
  const ids = Array.from({ length: total - start }, (_, i) => total - 1 - i)

  const raws = await Promise.all(
    ids.map((id) =>
      heliosClient.readContract({
        address: contractAddr, abi: ABI, functionName: 'getProposal', args: [BigInt(id)],
      }),
    ),
  )

  return raws.map((raw, i) => decodeProposal(raw as unknown as RawProposal, ids[i]))
}

export async function votingGetProposal(id: number): Promise<Proposal> {
  const raw = await createHeliosClient().readContract({
    address: getContractAddress(), abi: ABI, functionName: 'getProposal', args: [BigInt(id)],
  })
  return decodeProposal(raw as unknown as RawProposal, id)
}

export async function votingHasVoted(proposalId: number, voter: `0x${string}`): Promise<boolean> {
  return createHeliosClient().readContract({
    address: getContractAddress(),
    abi: ABI,
    functionName: 'hasVoted',
    args: [BigInt(proposalId), voter],
  }) as Promise<boolean>
}
