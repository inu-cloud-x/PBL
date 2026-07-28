import { useState, useEffect } from 'react'
import { ensReverseLookup } from '../lib/ens'
import { getConfig } from '../config'

// Module-level cache persists across component mounts within the session.
const _cache = new Map<string, string>()

// Call after register/release transactions so the next hook render re-fetches.
export function invalidateENSCache(address: `0x${string}`): void {
  _cache.delete(address.toLowerCase())
}

/**
 * Passively resolves an address to its MiniENS name.
 *
 * @param address  - The AA wallet address to look up.
 * @param heliosReady - Pass `syncStatus === 'ready'` from the caller's Helios state.
 *                     The effect re-runs when this transitions to true.
 * @returns The registered name, or undefined if not registered / not yet resolved.
 */
export function useENSName(
  address: `0x${string}` | undefined,
  heliosReady: boolean,
): string | undefined {
  const [name, setName] = useState<string | undefined>(undefined)

  useEffect(() => {
    if (!address || !heliosReady || !getConfig().miniEnsAddress) return

    const key = address.toLowerCase()
    if (_cache.has(key)) {
      setName(_cache.get(key) || undefined)
      return
    }

    let cancelled = false
    ensReverseLookup(address)
      .then((result) => {
        if (cancelled) return
        _cache.set(key, result)
        setName(result || undefined)
      })
      .catch(() => {
        // Helios not synced or contract not deployed — leave as undefined
      })

    return () => {
      cancelled = true
    }
  }, [address, heliosReady])

  return name
}
