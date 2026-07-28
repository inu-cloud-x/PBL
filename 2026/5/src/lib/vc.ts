import { p256 } from '@noble/curves/nist.js'
import { sha256 } from '@noble/hashes/sha256.js'
import { base64url } from '@scure/base'
import { keccak256 } from 'viem'
import { getConfig } from '../config'
import { createHeliosClient } from './helios'
import { publicKeyBytesFromDid } from './did'
import type { SmartWalletClient } from './wallet'
import type { StoredKey } from './passkey'

// ── Types ─────────────────────────────────────────────────────────────────────

export type VcInput = {
  vcName: string      // ≤40 bytes
  issuerEns: string
  issuerDid: string
  subjectDid: string
  details: string     // ≤100 bytes
  issuedAt: Date
}

export type VcPayload = {
  '@context': string[]
  type: string[]
  issuer: { id: string; name: string }
  issuanceDate: string
  expirationDate: string
  credentialSubject: { id: string; details: string }
}

export type VcProof = {
  type: 'PasskeyP256Signature2026'
  created: string
  verificationMethod: string    // `${did}#key-1`
  proofPurpose: 'assertionMethod'
  proofValue: string            // base64url(r||s 64 bytes)
  authenticatorData: string     // base64url(authData) — needed for WebAuthn sig verification
  clientDataHash: string        // base64url(sha256(clientDataJSON))
}

export type VerifiableCredential = VcPayload & { proof: VcProof }

// ── On-chain types (mirrored from VCRegistry.sol) ─────────────────────────────

export type VcFormat = {
  id: bigint
  issuer: `0x${string}`
  name: string
  active: boolean
  createdAt: bigint
}

export type VcRequest = {
  id: bigint
  formatId: bigint
  requester: `0x${string}`
  subjectDid: string
  status: 0 | 1 | 2    // 0=Pending, 1=Approved, 2=Rejected
  createdAt: bigint
}

export type VcIssued = {
  id: bigint
  formatId: bigint
  issuer: `0x${string}`
  subject: `0x${string}`
  details: string
  jsonHash: `0x${string}`
  issuedAt: bigint
  expiresAt: bigint
}

export const VC_STATUS = { Pending: 0, Approved: 1, Rejected: 2 } as const
export const VC_STATUS_LABEL: Record<number, string> = { 0: '대기', 1: '승인', 2: '거절' }

// ── ABI ───────────────────────────────────────────────────────────────────────

const FORMAT_COMPONENTS = [
  { name: 'id',        type: 'uint256' },
  { name: 'issuer',    type: 'address' },
  { name: 'name',      type: 'string'  },
  { name: 'active',    type: 'bool'    },
  { name: 'createdAt', type: 'uint64'  },
] as const

const REQUEST_COMPONENTS = [
  { name: 'id',         type: 'uint256' },
  { name: 'formatId',   type: 'uint256' },
  { name: 'requester',  type: 'address' },
  { name: 'subjectDid', type: 'string'  },
  { name: 'status',     type: 'uint8'   },
  { name: 'createdAt',  type: 'uint64'  },
] as const

const ISSUED_COMPONENTS = [
  { name: 'id',        type: 'uint256'  },
  { name: 'formatId',  type: 'uint256'  },
  { name: 'issuer',    type: 'address'  },
  { name: 'subject',   type: 'address'  },
  { name: 'details',   type: 'string'   },
  { name: 'jsonHash',  type: 'bytes32'  },
  { name: 'issuedAt',  type: 'uint64'   },
  { name: 'expiresAt', type: 'uint64'   },
] as const

const ABI = [
  {
    name: 'registerFormat',
    type: 'function',
    stateMutability: 'nonpayable',
    inputs:  [{ name: 'name', type: 'string' }],
    outputs: [{ name: '', type: 'uint256' }],
  },
  {
    name: 'deactivateFormat',
    type: 'function',
    stateMutability: 'nonpayable',
    inputs:  [{ name: 'formatId', type: 'uint256' }],
    outputs: [],
  },
  {
    name: 'requestVc',
    type: 'function',
    stateMutability: 'nonpayable',
    inputs:  [
      { name: 'formatId',   type: 'uint256' },
      { name: 'subjectDid', type: 'string'  },
    ],
    outputs: [{ name: '', type: 'uint256' }],
  },
  {
    name: 'approveRequest',
    type: 'function',
    stateMutability: 'nonpayable',
    inputs:  [
      { name: 'requestId', type: 'uint256' },
      { name: 'details',   type: 'string'  },
      { name: 'jsonHash',  type: 'bytes32' },
    ],
    outputs: [{ name: 'issuedId', type: 'uint256' }],
  },
  {
    name: 'rejectRequest',
    type: 'function',
    stateMutability: 'nonpayable',
    inputs:  [{ name: 'requestId', type: 'uint256' }],
    outputs: [],
  },
  {
    name: 'listFormats',
    type: 'function',
    stateMutability: 'view',
    inputs:  [
      { name: 'cursor', type: 'uint256' },
      { name: 'limit',  type: 'uint256' },
    ],
    outputs: [
      { name: 'formats',    type: 'tuple[]', components: FORMAT_COMPONENTS },
      { name: 'nextCursor', type: 'uint256' },
    ],
  },
  {
    name: 'getRequestsByIssuer',
    type: 'function',
    stateMutability: 'view',
    inputs:  [{ name: 'issuer', type: 'address' }],
    outputs: [{ name: '', type: 'tuple[]', components: REQUEST_COMPONENTS }],
  },
  {
    name: 'getRequestsByRequester',
    type: 'function',
    stateMutability: 'view',
    inputs:  [{ name: 'requester', type: 'address' }],
    outputs: [{ name: '', type: 'tuple[]', components: REQUEST_COMPONENTS }],
  },
  {
    name: 'getIssuedToSubject',
    type: 'function',
    stateMutability: 'view',
    inputs:  [{ name: 'subject', type: 'address' }],
    outputs: [{ name: '', type: 'tuple[]', components: ISSUED_COMPONENTS }],
  },
] as const

// ── Helpers ───────────────────────────────────────────────────────────────────

function getContractAddress(): `0x${string}` {
  const addr = getConfig().vcRegistryAddress
  if (!addr) throw new Error('VITE_VC_REGISTRY_ADDRESS가 설정되지 않았습니다')
  return addr
}

// @scure/base base64url requires padded input (length divisible by 4).
// WebAuthn credential.id and our proof fields may be unpadded → add padding first.
function b64urlToBytes(b64url: string): Uint8Array {
  const rem = b64url.length % 4
  const padded = rem === 0 ? b64url : b64url + '='.repeat(4 - rem)
  return base64url.decode(padded)
}

// ── Core VC functions ─────────────────────────────────────────────────────────

/**
 * Recursive key-sorted JSON serialization (RFC 8785 subset — no floats in VC payload).
 */
export function canonicalize(obj: unknown): string {
  if (typeof obj !== 'object' || obj === null) return JSON.stringify(obj)
  if (Array.isArray(obj)) return `[${obj.map(canonicalize).join(',')}]`
  const keys = Object.keys(obj as Record<string, unknown>).sort()
  const pairs = keys.map((k) => {
    const v = (obj as Record<string, unknown>)[k]
    return `${JSON.stringify(k)}:${canonicalize(v)}`
  })
  return `{${pairs.join(',')}}`
}

export function buildVcPayload(input: VcInput): VcPayload {
  const issuanceDate   = input.issuedAt.toISOString()
  const expirationDate = new Date(
    input.issuedAt.getTime() + 365 * 24 * 60 * 60 * 1000,
  ).toISOString()

  return {
    '@context': ['https://www.w3.org/2018/credentials/v1'],
    type: ['VerifiableCredential', input.vcName],
    issuer: { id: input.issuerDid, name: input.issuerEns },
    issuanceDate,
    expirationDate,
    credentialSubject: { id: input.subjectDid, details: input.details },
  }
}

/**
 * Signs the VC payload using a WebAuthn assertion.
 * Triggers a biometric prompt — inform the user beforehand.
 */
export async function signVc(
  payload: VcPayload,
  issuerKey: StoredKey,
): Promise<VerifiableCredential> {
  // challenge = SHA-256(canonical JSON bytes)
  const canonical      = canonicalize(payload)
  const canonicalBytes = new TextEncoder().encode(canonical)
  const challengeBytes = sha256(canonicalBytes)
  const challenge      = challengeBytes.buffer.slice(
    challengeBytes.byteOffset,
    challengeBytes.byteOffset + challengeBytes.byteLength,
  ) as ArrayBuffer

  const credIdBytes = b64urlToBytes(issuerKey.authenticatorId)
  const credId = credIdBytes.buffer.slice(
    credIdBytes.byteOffset,
    credIdBytes.byteOffset + credIdBytes.byteLength,
  ) as ArrayBuffer
  const assertion = (await navigator.credentials.get({
    publicKey: {
      challenge,
      allowCredentials: [{ id: credId, type: 'public-key' }],
      userVerification: 'required',
      timeout: 60_000,
    },
  })) as PublicKeyCredential | null

  if (!assertion) throw new Error('서명이 취소되었습니다')

  const resp = assertion.response as AuthenticatorAssertionResponse

  // Convert DER-encoded signature to raw r||s compact bytes (64 bytes)
  const derBytes = new Uint8Array(resp.signature)
  const sig      = p256.Signature.fromBytes(derBytes, 'der')
  const rawSig   = sig.toBytes('compact') as Uint8Array

  const authData       = new Uint8Array(resp.authenticatorData)
  const clientDataJson = new Uint8Array(resp.clientDataJSON)
  const clientDataHash = sha256(clientDataJson)

  const proof: VcProof = {
    type:               'PasskeyP256Signature2026',
    created:            new Date().toISOString(),
    verificationMethod: `${payload.issuer.id}#key-1`,
    proofPurpose:       'assertionMethod',
    proofValue:         base64url.encode(rawSig),
    authenticatorData:  base64url.encode(authData),
    clientDataHash:     base64url.encode(clientDataHash),
  }

  return { ...payload, proof }
}

/**
 * Verifies the P-256 signature in the proof against the WebAuthn signed data.
 * Does NOT check expiration — use isExpired() separately.
 */
export async function verifyVcSignature(vc: VerifiableCredential): Promise<boolean> {
  try {
    const { proof } = vc
    const did = proof.verificationMethod.split('#')[0]
    const pubKeyBytes = publicKeyBytesFromDid(did)

    const rawSig         = b64urlToBytes(proof.proofValue)
    const authData       = b64urlToBytes(proof.authenticatorData)
    const clientDataHash = b64urlToBytes(proof.clientDataHash)

    // WebAuthn signed data: authenticatorData || SHA-256(clientDataJSON)
    const dataToVerify = new Uint8Array(authData.length + clientDataHash.length)
    dataToVerify.set(authData, 0)
    dataToVerify.set(clientDataHash, authData.length)

    // ES256 = ECDSA P-256 + SHA-256: prehash:true makes the library hash internally
    return p256.verify(rawSig, dataToVerify, pubKeyBytes, { prehash: true, format: 'compact' })
  } catch {
    return false
  }
}

export function isExpired(vc: VerifiableCredential, now: Date = new Date()): boolean {
  return new Date(vc.expirationDate) <= now
}

/** keccak256 of the complete canonicalized VC JSON (including proof). */
export function vcHash(vc: VerifiableCredential): `0x${string}` {
  const canonical = canonicalize(vc as unknown as Record<string, unknown>)
  const bytes     = new TextEncoder().encode(canonical)
  return keccak256(bytes)
}

// ── localStorage ─────────────────────────────────────────────────────────────

const VC_KEY   = (chainId: number, hash: string) => `vc:${chainId}:${hash}`
const IDX_KEY  = (chainId: number)                => `vc-index:${chainId}`

function _loadIndex(chainId: number): string[] {
  try { return JSON.parse(localStorage.getItem(IDX_KEY(chainId)) ?? '[]') as string[] }
  catch { return [] }
}

export function saveVc(vc: VerifiableCredential, chainId: number): string {
  const hash = vcHash(vc)
  localStorage.setItem(VC_KEY(chainId, hash), JSON.stringify(vc))
  const idx = _loadIndex(chainId)
  if (!idx.includes(hash)) {
    idx.push(hash)
    localStorage.setItem(IDX_KEY(chainId), JSON.stringify(idx))
  }
  return hash
}

export function loadAllVcs(chainId: number): VerifiableCredential[] {
  return _loadIndex(chainId).flatMap((h) => {
    const raw = localStorage.getItem(VC_KEY(chainId, h))
    if (!raw) return []
    try { return [JSON.parse(raw) as VerifiableCredential] } catch { return [] }
  })
}

export function removeVc(chainId: number, hash: string): void {
  localStorage.removeItem(VC_KEY(chainId, hash))
  const idx = _loadIndex(chainId).filter((h) => h !== hash)
  localStorage.setItem(IDX_KEY(chainId), JSON.stringify(idx))
}

export function exportVcAsJson(vc: VerifiableCredential): { filename: string; blob: Blob } {
  const hash       = vcHash(vc)
  const shortHash  = hash.slice(2, 10)
  const vcName     = vc.type[1] ?? 'vc'
  const shortDid   = vc.credentialSubject.id.slice(-8)
  const safeName   = vcName.replace(/[^a-zA-Z0-9\-_]/g, '_').slice(0, 30)
  const filename   = `${safeName}-${shortDid}-${shortHash}.vc.json`
  const blob       = new Blob([JSON.stringify(vc, null, 2)], { type: 'application/json' })
  return { filename, blob }
}

export async function importVcFromFile(file: File): Promise<VerifiableCredential> {
  const text = await file.text()
  const obj  = JSON.parse(text) as Record<string, unknown>
  if (!obj['@context'] || !obj.type || !obj.proof) {
    throw new Error('유효하지 않은 VC 파일 형식입니다')
  }
  return obj as unknown as VerifiableCredential
}

// ── Contract write functions (AA-routed) ──────────────────────────────────────

export async function vcRegisterFormat(
  client: SmartWalletClient,
  name: string,
): Promise<`0x${string}`> {
  return client.writeContract({
    address: getContractAddress(), abi: ABI, functionName: 'registerFormat', args: [name],
  })
}

export async function vcDeactivateFormat(
  client: SmartWalletClient,
  formatId: bigint,
): Promise<`0x${string}`> {
  return client.writeContract({
    address: getContractAddress(), abi: ABI, functionName: 'deactivateFormat', args: [formatId],
  })
}

export async function vcRequestVc(
  client: SmartWalletClient,
  formatId: bigint,
  subjectDid: string,
): Promise<`0x${string}`> {
  return client.writeContract({
    address: getContractAddress(), abi: ABI, functionName: 'requestVc', args: [formatId, subjectDid],
  })
}

export async function vcApproveRequest(
  client: SmartWalletClient,
  requestId: bigint,
  details: string,
  hash: `0x${string}`,
): Promise<`0x${string}`> {
  return client.writeContract({
    address: getContractAddress(),
    abi:     ABI,
    functionName: 'approveRequest',
    args:    [requestId, details, hash],
  })
}

export async function vcRejectRequest(
  client: SmartWalletClient,
  requestId: bigint,
): Promise<`0x${string}`> {
  return client.writeContract({
    address: getContractAddress(), abi: ABI, functionName: 'rejectRequest', args: [requestId],
  })
}

// ── Contract read functions (Helios-verified) ─────────────────────────────────

const PAGE_SIZE = 50n

/**
 * Fetches all formats, paging through the contract. Returns only active formats
 * if onlyActive=true.
 */
export async function vcListFormats(opts?: { onlyActive?: boolean }): Promise<VcFormat[]> {
  const helios  = createHeliosClient()
  const addr    = getContractAddress()
  const results: VcFormat[] = []

  let cursor = 0n
  for (;;) {
    const [page, next] = (await helios.readContract({
      address: addr, abi: ABI, functionName: 'listFormats', args: [cursor, PAGE_SIZE],
    })) as [readonly { id: bigint; issuer: `0x${string}`; name: string; active: boolean; createdAt: bigint }[], bigint]

    for (const f of page) {
      if (!opts?.onlyActive || f.active) {
        results.push({ id: f.id, issuer: f.issuer, name: f.name, active: f.active, createdAt: f.createdAt })
      }
    }

    if (next === 0n) break
    cursor = next
  }

  return results
}

export async function vcListIncomingRequests(issuer: `0x${string}`): Promise<VcRequest[]> {
  const raw = (await createHeliosClient().readContract({
    address: getContractAddress(),
    abi:     ABI,
    functionName: 'getRequestsByIssuer',
    args:    [issuer],
  })) as readonly { id: bigint; formatId: bigint; requester: `0x${string}`; subjectDid: string; status: number; createdAt: bigint }[]

  return raw.map((r) => ({
    id:         r.id,
    formatId:   r.formatId,
    requester:  r.requester,
    subjectDid: r.subjectDid,
    status:     r.status as 0 | 1 | 2,
    createdAt:  r.createdAt,
  }))
}

export async function vcListOutgoingRequests(requester: `0x${string}`): Promise<VcRequest[]> {
  const raw = (await createHeliosClient().readContract({
    address: getContractAddress(),
    abi:     ABI,
    functionName: 'getRequestsByRequester',
    args:    [requester],
  })) as readonly { id: bigint; formatId: bigint; requester: `0x${string}`; subjectDid: string; status: number; createdAt: bigint }[]

  return raw.map((r) => ({
    id:         r.id,
    formatId:   r.formatId,
    requester:  r.requester,
    subjectDid: r.subjectDid,
    status:     r.status as 0 | 1 | 2,
    createdAt:  r.createdAt,
  }))
}

export async function vcListIssuedToMe(subject: `0x${string}`): Promise<VcIssued[]> {
  const raw = (await createHeliosClient().readContract({
    address: getContractAddress(),
    abi:     ABI,
    functionName: 'getIssuedToSubject',
    args:    [subject],
  })) as readonly { id: bigint; formatId: bigint; issuer: `0x${string}`; subject: `0x${string}`; details: string; jsonHash: `0x${string}`; issuedAt: bigint; expiresAt: bigint }[]

  return raw.map((r) => ({
    id:        r.id,
    formatId:  r.formatId,
    issuer:    r.issuer,
    subject:   r.subject,
    details:   r.details,
    jsonHash:  r.jsonHash,
    issuedAt:  r.issuedAt,
    expiresAt: r.expiresAt,
  }))
}
