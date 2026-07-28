import { base58 } from '@scure/base'

export type P256PublicKey = { x: Uint8Array; y: Uint8Array }

export type JsonDidDocument = {
  '@context': string[]
  id: string
  verificationMethod: Array<{
    id: string
    type: string
    controller: string
    publicKeyMultibase: string
  }>
  assertionMethod: string[]
}

// multicodec varint for P-256 compressed public key: 0x1200 → [0x80, 0x24]
const P256_MULTICODEC_PREFIX = new Uint8Array([0x80, 0x24])

/**
 * Compressed SEC1 encoding of a P-256 public key.
 * Format: [0x02 | y_is_odd, x[0..31]] — 33 bytes total.
 */
function compressSEC1(pub: P256PublicKey): Uint8Array {
  const compressed = new Uint8Array(33)
  const yIsOdd = pub.y[pub.y.length - 1] & 1
  compressed[0] = 0x02 | yIsOdd
  compressed.set(pub.x.slice(0, 32), 1)
  return compressed
}

function _encodeMultibase(pub: P256PublicKey): string {
  const compressed = compressSEC1(pub)
  const payload = new Uint8Array(P256_MULTICODEC_PREFIX.length + compressed.length)
  payload.set(P256_MULTICODEC_PREFIX, 0)
  payload.set(compressed, P256_MULTICODEC_PREFIX.length)
  return `z${base58.encode(payload)}`
}

/**
 * Derives a did:key string from a P-256 public key.
 * Format: did:key:z<base58btc(varint(0x1200) || compressed_sec1)>
 */
export function derivePasskeyDid(pub: P256PublicKey): string {
  return `did:key:${_encodeMultibase(pub)}`
}

/** Returns the verificationMethod URI for a did:key DID. */
export function didKeyId(did: string): string {
  return `${did}#key-1`
}

/** Minimal DID document for a did:key DID. */
export function didDocument(did: string, pub: P256PublicKey): JsonDidDocument {
  const multibase = _encodeMultibase(pub)
  const keyId = didKeyId(did)

  return {
    '@context': [
      'https://www.w3.org/ns/did/v1',
      'https://w3id.org/security/suites/jws-2020/v1',
    ],
    id: did,
    verificationMethod: [
      {
        id:                 keyId,
        type:               'JsonWebKey2020',
        controller:         did,
        publicKeyMultibase: multibase,
      },
    ],
    assertionMethod: [keyId],
  }
}

/**
 * Returns the compressed SEC1 public key (33 bytes) from a did:key string.
 * @noble/curves p256.verify accepts compressed form directly.
 */
export function publicKeyBytesFromDid(did: string): Uint8Array {
  const prefix = 'did:key:z'
  if (!did.startsWith(prefix)) throw new Error('not a did:key')
  const encoded = did.slice(prefix.length)
  const decoded = base58.decode(encoded)
  // Strip 2-byte multicodec prefix → 33-byte compressed SEC1
  return decoded.slice(2)
}

/**
 * Derives a P256PublicKey from a StoredKey's hex pubX/pubY strings.
 * pubX and pubY from passkey.ts are stored as decimal bigint strings.
 */
export function storedKeyToPub(pubX: string, pubY: string): P256PublicKey {
  const toBE32 = (decimal: string) => {
    let hex = BigInt(decimal).toString(16).padStart(64, '0')
    const bytes = new Uint8Array(32)
    for (let i = 0; i < 32; i++) {
      bytes[i] = parseInt(hex.slice(i * 2, i * 2 + 2), 16)
    }
    return bytes
  }
  return { x: toBE32(pubX), y: toBE32(pubY) }
}
