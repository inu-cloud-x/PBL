import { keccak256 } from 'viem'
import type { WebAuthnKey } from '@zerodev/webauthn-key'

const RP_NAME = 'Trustless dApp PoC'

const KEYS_KEY    = 'dapp_webauthn_keys'  // new: array of StoredKey
const LEGACY_KEY  = 'dapp_webauthn_key'   // old: single StoredKey (migrated on first read)
const LAST_ID_KEY = 'dapp_last_auth_id'

export type StoredKey = {
  pubX: string
  pubY: string
  authenticatorId: string
  authenticatorIdHash: `0x${string}`
  aaAddress: string   // cached AA wallet address; '' if not yet resolved
  addedAt: number     // Unix ms
}

// ── storage ───────────────────────────────────────────────────────────────────

function loadAll(): StoredKey[] {
  const raw = localStorage.getItem(KEYS_KEY)
  if (raw) {
    try { return JSON.parse(raw) as StoredKey[] } catch { return [] }
  }
  // Migrate legacy single-key format to array on first read
  const legacyRaw = localStorage.getItem(LEGACY_KEY)
  if (legacyRaw) {
    try {
      const legacy = JSON.parse(legacyRaw)
      if (legacy.pubX && legacy.authenticatorId) {
        const migrated: StoredKey = {
          pubX:               legacy.pubX,
          pubY:               legacy.pubY,
          authenticatorId:    legacy.authenticatorId,
          authenticatorIdHash: legacy.authenticatorIdHash,
          aaAddress:          legacy.aaAddress ?? '',
          addedAt:            Date.now(),
        }
        _persist([migrated])
        localStorage.removeItem(LEGACY_KEY)
        return [migrated]
      }
    } catch { /* fall through */ }
  }
  return []
}

function _persist(keys: StoredKey[]): void {
  localStorage.setItem(KEYS_KEY, JSON.stringify(keys))
}

// ── public read API ───────────────────────────────────────────────────────────

export function listSavedWebAuthnKeys(): StoredKey[] {
  return loadAll()
}

export function hasSavedPasskey(): boolean {
  return loadAll().length > 0
}

/** Returns the last-used key, or the most recently added key as fallback. */
export function getLastUsedKey(): WebAuthnKey | null {
  const keys = loadAll()
  if (keys.length === 0) return null
  const lastId = localStorage.getItem(LAST_ID_KEY)
  const match  = lastId ? keys.find((k) => k.authenticatorId === lastId) : null
  return _toWebAuthnKey(match ?? keys[keys.length - 1])
}

export function loadWebAuthnKeyById(authenticatorId: string): WebAuthnKey | null {
  const key = loadAll().find((k) => k.authenticatorId === authenticatorId)
  return key ? _toWebAuthnKey(key) : null
}

// ── public write API ──────────────────────────────────────────────────────────

/**
 * Upsert a key. Call after createSmartWalletClient so aaAddress is known.
 * Also marks this key as last-used.
 */
export function saveWebAuthnKey(key: WebAuthnKey, aaAddress: string): void {
  const keys   = loadAll()
  const idx    = keys.findIndex((k) => k.authenticatorId === key.authenticatorId)
  const stored: StoredKey = {
    pubX:               key.pubX.toString(),
    pubY:               key.pubY.toString(),
    authenticatorId:    key.authenticatorId,
    authenticatorIdHash: key.authenticatorIdHash,
    aaAddress,
    addedAt: idx >= 0 ? keys[idx].addedAt : Date.now(),
  }
  if (idx >= 0) keys[idx] = stored
  else          keys.push(stored)
  _persist(keys)
  setLastUsedId(key.authenticatorId)
}

export function setLastUsedId(authenticatorId: string): void {
  localStorage.setItem(LAST_ID_KEY, authenticatorId)
}

export function removeWebAuthnKey(authenticatorId: string): void {
  _persist(loadAll().filter((k) => k.authenticatorId !== authenticatorId))
  if (localStorage.getItem(LAST_ID_KEY) === authenticatorId) {
    localStorage.removeItem(LAST_ID_KEY)
  }
}

export function clearSavedPasskey(): void {
  localStorage.removeItem(KEYS_KEY)
  localStorage.removeItem(LEGACY_KEY)
  localStorage.removeItem(LAST_ID_KEY)
}

// ── passkey operations ────────────────────────────────────────────────────────

function _toWebAuthnKey(stored: StoredKey): WebAuthnKey {
  return {
    pubX:               BigInt(stored.pubX),
    pubY:               BigInt(stored.pubY),
    authenticatorId:    stored.authenticatorId,
    authenticatorIdHash: stored.authenticatorIdHash,
    rpID:               window.location.hostname,
  }
}

function _b64urlToUint8Array(b64url: string): Uint8Array {
  const b64    = b64url.replace(/-/g, '+').replace(/_/g, '/')
  const padded = b64.padEnd(b64.length + ((4 - (b64.length % 4)) % 4), '=')
  return new Uint8Array([...atob(padded)].map((c) => c.charCodeAt(0)))
}

function _uint8ToHex(arr: Uint8Array): `0x${string}` {
  return `0x${[...arr].map((b) => b.toString(16).padStart(2, '0')).join('')}`
}

async function _extractP256Coords(spkiDer: ArrayBuffer): Promise<{ pubX: bigint; pubY: bigint }> {
  const key = await crypto.subtle.importKey(
    'spki', spkiDer, { name: 'ECDSA', namedCurve: 'P-256' }, true, ['verify'],
  )
  const raw  = new Uint8Array(await crypto.subtle.exportKey('raw', key))
  return {
    pubX: BigInt(_uint8ToHex(raw.subarray(1, 33))),
    pubY: BigInt(_uint8ToHex(raw.subarray(33, 65))),
  }
}

/**
 * Performs a WebAuthn assertion (navigator.credentials.get) for a stored key.
 * Triggers the biometric/PIN prompt and throws if the user cancels or fails.
 * Does not use the result — this is purely for liveness/consent verification.
 */
export async function assertPasskeyBiometric(key: WebAuthnKey): Promise<void> {
  const credBytes = _b64urlToUint8Array(key.authenticatorId)
  const credId    = credBytes.buffer.slice(
    credBytes.byteOffset, credBytes.byteOffset + credBytes.byteLength,
  ) as ArrayBuffer
  const challengeArr = crypto.getRandomValues(new Uint8Array(32))
  const challenge    = challengeArr.buffer.slice(0, 32) as ArrayBuffer
  const credential   = (await navigator.credentials.get({
    publicKey: {
      challenge,
      rpId:             window.location.hostname,
      allowCredentials: [{ type: 'public-key', id: credId }],
      userVerification: 'required',
      timeout:          60_000,
    },
  })) as PublicKeyCredential | null
  if (!credential) throw new Error('생체 인증이 취소되었습니다')
}

/**
 * Creates a new WebAuthn credential and returns the public key.
 * Does NOT save to localStorage — caller must call saveWebAuthnKey() after
 * creating the wallet client so aaAddress can be included.
 */
export async function registerPasskey(): Promise<WebAuthnKey> {
  const challenge = crypto.getRandomValues(new Uint8Array(32))
  const userId    = crypto.getRandomValues(new Uint8Array(16))

  const credential = (await navigator.credentials.create({
    publicKey: {
      challenge,
      rp:   { name: RP_NAME, id: window.location.hostname },
      user: { id: userId, name: RP_NAME, displayName: RP_NAME },
      pubKeyCredParams: [{ alg: -7, type: 'public-key' }],
      authenticatorSelection: { userVerification: 'required', residentKey: 'required' },
      timeout: 60_000,
    },
  })) as PublicKeyCredential | null

  if (!credential) throw new Error('Passkey 생성이 취소되었습니다')

  const response = credential.response as AuthenticatorAttestationResponse
  const spkiDer  = response.getPublicKey()
  if (!spkiDer) throw new Error('공개키를 추출할 수 없습니다')

  const { pubX, pubY }       = await _extractP256Coords(spkiDer)
  const authenticatorId      = credential.id
  const authenticatorIdHash  = keccak256(_uint8ToHex(_b64urlToUint8Array(authenticatorId)))

  return { pubX, pubY, authenticatorId, authenticatorIdHash, rpID: window.location.hostname }
}
