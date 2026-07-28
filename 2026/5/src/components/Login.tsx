import { useState } from 'react'
import {
  listSavedWebAuthnKeys,
  registerPasskey,
  assertPasskeyBiometric,
  loadWebAuthnKeyById,
  saveWebAuthnKey,
  setLastUsedId,
  removeWebAuthnKey,
  type StoredKey,
} from '../lib/passkey'
import { createSmartWalletClient, linkToPasskeyRegistry, getAccountAddress, type SmartWalletClient } from '../lib/wallet'
import { getConfig } from '../config'

type Props = {
  onLogin: (client: SmartWalletClient) => void
}

function fmtAddr(addr: string): string {
  if (!addr) return '주소 미확인'
  return `${addr.slice(0, 8)}…${addr.slice(-6)}`
}

function fmtDate(ms: number): string {
  return new Date(ms).toLocaleDateString('ko-KR')
}

export default function Login({ onLogin }: Props) {
  const [status,  setStatus]  = useState('')
  const [error,   setError]   = useState('')
  const [loading, setLoading] = useState(false)
  // force re-render after delete
  const [, setTick] = useState(0)

  const savedKeys   = listSavedWebAuthnKeys()
  const hasRegistry = !!getConfig().passkeyRegistryAddress

  async function handleLoginWithKey(stored: StoredKey) {
    setError('')
    setLoading(true)
    try {
      const webAuthnKey = loadWebAuthnKeyById(stored.authenticatorId)
      if (!webAuthnKey) throw new Error('저장된 키를 불러올 수 없습니다')

      setStatus('지문 인증 중...')
      await assertPasskeyBiometric(webAuthnKey)

      setStatus('AA 지갑을 복원하는 중...')
      const client  = await createSmartWalletClient(webAuthnKey)
      const address = getAccountAddress(client)

      // Update aaAddress in storage if it was missing (migration case)
      if (!stored.aaAddress || stored.aaAddress !== address) {
        saveWebAuthnKey(webAuthnKey, address)
      } else {
        setLastUsedId(stored.authenticatorId)
      }

      sessionStorage.setItem('dapp_session', '1')
      setStatus(`복원 완료 — AA: ${address}`)
      onLogin(client)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      setStatus('')
    } finally {
      setLoading(false)
    }
  }

  async function handleRegister() {
    setError('')
    setLoading(true)
    try {
      setStatus('Passkey를 생성하는 중...')
      const webAuthnKey = await registerPasskey()

      setStatus('AA 지갑을 초기화하는 중...')
      const client  = await createSmartWalletClient(webAuthnKey)
      const address = getAccountAddress(client)

      // Save with the resolved AA address now that we have it
      saveWebAuthnKey(webAuthnKey, address)

      if (hasRegistry) {
        setStatus('PasskeyRegistry에 등록하는 중...')
        const result = await linkToPasskeyRegistry(client, webAuthnKey.authenticatorIdHash)
        setStatus(result === 'linked' ? `등록 완료 — AA: ${address}` : `지갑 준비 완료 — AA: ${address}`)
      } else {
        setStatus(`지갑 준비 완료 — AA: ${address}`)
      }

      sessionStorage.setItem('dapp_session', '1')
      onLogin(client)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      setStatus('')
    } finally {
      setLoading(false)
    }
  }

  function handleRemove(authenticatorId: string) {
    if (!window.confirm(
      '이 계정을 목록에서 삭제하시겠습니까?\n\n삭제 후에는 같은 지갑 주소로 접근할 수 없습니다.',
    )) return
    removeWebAuthnKey(authenticatorId)
    setTick((n) => n + 1)  // force re-render to refresh savedKeys
  }

  return (
    <div style={{ paddingTop: '0.5rem', maxWidth: '480px', fontFamily: 'monospace' }}>
      <h2 style={{ marginTop: 0 }}>Passkey 로그인</h2>
      <p style={{ fontSize: '0.9rem', color: '#555', marginTop: 0 }}>
        개인키를 저장하지 않습니다. 모든 서명은 Passkey(WebAuthn)로만 이루어집니다.
      </p>

      {/* ── Saved accounts ─────────────────────────────────────── */}
      {savedKeys.length > 0 && (
        <div style={{ marginBottom: '1.25rem' }}>
          <div style={{ fontSize: '0.82rem', color: '#888', marginBottom: '0.4rem', letterSpacing: '0.03em' }}>
            저장된 계정 ({savedKeys.length}개)
          </div>
          {savedKeys.map((k) => (
            <div
              key={k.authenticatorId}
              style={{
                border: '1px solid #ddd',
                borderRadius: '4px',
                padding: '0.6rem 0.75rem',
                marginBottom: '0.4rem',
                background: '#fafafa',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                gap: '0.5rem',
                flexWrap: 'wrap',
              }}
            >
              <div>
                <code style={{ fontSize: '0.88rem' }}>{fmtAddr(k.aaAddress)}</code>
                <div style={{ fontSize: '0.73rem', color: '#aaa', marginTop: '0.15rem' }}>
                  추가됨 {fmtDate(k.addedAt)}
                </div>
              </div>
              <div style={{ display: 'flex', gap: '0.4rem', flexShrink: 0 }}>
                <button
                  onClick={() => handleLoginWithKey(k)}
                  disabled={loading}
                  style={{ fontSize: '0.85rem', padding: '0.25rem 0.75rem' }}
                >
                  {loading ? '...' : '로그인'}
                </button>
                <button
                  onClick={() => handleRemove(k.authenticatorId)}
                  disabled={loading}
                  style={{ fontSize: '0.8rem', padding: '0.25rem 0.5rem', color: '#c33', background: '#fde', border: '1px solid #c66' }}
                >
                  삭제
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* ── Register new account ────────────────────────────────── */}
      <button onClick={handleRegister} disabled={loading}>
        {savedKeys.length === 0 ? '새 Passkey 등록' : '+ 새 계정 추가'}
      </button>

      {status && <p style={{ marginTop: '1rem', color: '#2a6' }}>{status}</p>}
      {error  && <p style={{ marginTop: '1rem', color: '#c33' }}>오류: {error}</p>}
    </div>
  )
}
