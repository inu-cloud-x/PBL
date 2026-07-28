import { useState, useEffect, useCallback } from 'react'
import { initHelios, resetHelios, heliosStatus, isOutOfSync, type HeliosStatus } from '../lib/helios'
import { ensRegister, ensRelease, ensReverseLookup } from '../lib/ens'
import { invalidateENSCache } from '../hooks/useENSName'
import { getConfig } from '../config'
import type { SmartWalletClient } from '../lib/wallet'

type Props = {
  client: SmartWalletClient
}

const STATUS_LABEL: Record<HeliosStatus, string> = {
  idle:         'Helios 대기 중',
  initializing: 'Helios 동기화 중... (첫 실행은 10~60초 소요)',
  ready:        'Helios 검증 완료',
  failed:       'Helios 검증 실패',
}

const STATUS_COLOR: Record<HeliosStatus, string> = {
  idle:         '#888',
  initializing: '#a60',
  ready:        '#2a6',
  failed:       '#c33',
}

export default function ENSRegistrar({ client }: Props) {
  const [syncStatus, setSyncStatus]   = useState<HeliosStatus>(heliosStatus())
  const [syncError, setSyncError]     = useState<string | null>(null)
  // null = not yet loaded; '' = no name registered; non-empty = registered name
  const [currentName, setCurrentName] = useState<string | null>(null)
  const [nameInput, setNameInput]     = useState('')
  const [status, setStatus]           = useState('')
  const [error, setError]             = useState('')
  const [loading, setLoading]         = useState(false)

  const address        = client.account.address
  const miniEnsAddress = getConfig().miniEnsAddress
  const normalizedInput = nameInput.toLowerCase()
  const showLowercaseHint = nameInput.length > 0 && nameInput !== normalizedInput

  function triggerResync() {
    resetHelios()
    setSyncStatus('initializing')
    setSyncError(null)
    initHelios()
      .then(() => setSyncStatus('ready'))
      .catch((e) => {
        setSyncStatus('failed')
        setSyncError(e instanceof Error ? e.message : String(e))
      })
  }

  useEffect(() => {
    if (syncStatus === 'ready') return
    setSyncStatus('initializing')
    initHelios()
      .then(() => setSyncStatus('ready'))
      .catch((e) => {
        setSyncStatus('failed')
        setSyncError(e instanceof Error ? e.message : String(e))
      })
  }, [])

  const loadCurrentName = useCallback(async () => {
    if (heliosStatus() !== 'ready' || !miniEnsAddress) return
    try {
      const name = await ensReverseLookup(address)
      setCurrentName(name)
    } catch (e) {
      if (isOutOfSync(e)) {
        triggerResync()
      }
      // leave currentName as null on other errors — UI shows nothing until resolved
    }
  }, [address, miniEnsAddress])

  useEffect(() => {
    if (syncStatus === 'ready') loadCurrentName()
  }, [syncStatus, loadCurrentName])

  async function handleRegister() {
    if (loading) return
    const name = normalizedInput
    if (name.length < 3) return
    setError('')
    setStatus('Passkey로 서명 중...')
    setLoading(true)
    try {
      const txHash = await ensRegister(client, name)
      setStatus(`등록 완료. tx: ${txHash}`)
      setNameInput('')
      invalidateENSCache(address)
      await loadCurrentName()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      setStatus('')
    } finally {
      setLoading(false)
    }
  }

  async function handleRelease() {
    if (loading) return
    setError('')
    setStatus('Passkey로 서명 중...')
    setLoading(true)
    try {
      const txHash = await ensRelease(client)
      setStatus(`해제 완료. tx: ${txHash}`)
      invalidateENSCache(address)
      await loadCurrentName()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      setStatus('')
    } finally {
      setLoading(false)
    }
  }

  if (!miniEnsAddress) {
    return (
      <div style={{ marginTop: '1.5rem', padding: '1rem', background: '#fff3cd', border: '1px solid #856404', borderRadius: '4px' }}>
        <strong>컨트랙트 미배포</strong>
        <p style={{ margin: '0.5rem 0 0', fontSize: '0.85rem' }}>
          VITE_MINI_ENS_ADDRESS를 설정하세요.{' '}
          <code>forge script script/DeployENS.s.sol --broadcast</code> 실행 후 .env에 주소를 기입합니다.
        </p>
      </div>
    )
  }

  return (
    <div style={{ marginTop: '0.5rem' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap', marginBottom: '1rem' }}>
        <h3 style={{ margin: 0 }}>ENS 이름</h3>
        <span style={{ fontSize: '0.8rem', color: STATUS_COLOR[syncStatus] }}>
          {STATUS_LABEL[syncStatus]}
        </span>
      </div>

      {syncError && (
        <p style={{ color: '#c33', fontSize: '0.85rem', marginTop: '0' }}>검증 오류: {syncError}</p>
      )}
      {syncStatus === 'failed' && (
        <p style={{ color: '#c33', fontSize: '0.85rem', fontWeight: 'bold', marginTop: '0.25rem' }}>
          Helios 검증 실패 — 이름 조회를 표시하지 않습니다.
        </p>
      )}

      {syncStatus === 'ready' && (
        <>
          {currentName === null && (
            <p style={{ color: '#888', fontSize: '0.9rem' }}>이름 조회 중...</p>
          )}

          {currentName !== null && currentName !== '' && (
            <div style={{ marginBottom: '1rem', padding: '0.75rem 1rem', background: '#e8f5e9', border: '1px solid #4caf50', borderRadius: '4px' }}>
              <div style={{ fontSize: '0.8rem', color: '#555' }}>현재 등록된 이름</div>
              <div style={{ fontSize: '1.3rem', fontWeight: 'bold', marginTop: '0.2rem', letterSpacing: '0.02em' }}>
                {currentName}
              </div>
              <p style={{ margin: '0.5rem 0 0.6rem', fontSize: '0.8rem', color: '#666' }}>
                이 이름은 투표 결과 등 다른 dApp에서 주소 대신 표시됩니다.
              </p>
              <button
                onClick={handleRelease}
                disabled={loading}
                style={{ fontSize: '0.85rem', border: '1px solid #c66', color: '#c33', background: '#fde', padding: '0.25rem 0.75rem' }}
              >
                {loading ? '처리 중...' : '이름 해제'}
              </button>
            </div>
          )}

          {currentName !== null && currentName === '' && (
            <div>
              <p style={{ fontSize: '0.9rem', color: '#555', marginTop: 0, marginBottom: '0.75rem' }}>
                등록된 이름이 없습니다. 이름을 등록하면 투표 등에서 주소 대신 표시됩니다.
              </p>
              <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'flex-start', flexWrap: 'wrap' }}>
                <div>
                  <input
                    value={nameInput}
                    onChange={(e) => setNameInput(e.target.value)}
                    placeholder="my-name (3~32자, a-z 0-9 -)"
                    disabled={loading}
                    style={{
                      fontFamily: 'monospace',
                      fontSize: '0.9rem',
                      padding: '0.35rem 0.6rem',
                      border: '1px solid #ccc',
                      borderRadius: '4px',
                      width: '240px',
                    }}
                  />
                  {showLowercaseHint && (
                    <div style={{ fontSize: '0.75rem', color: '#a60', marginTop: '0.2rem' }}>
                      소문자로 변환됩니다: {normalizedInput}
                    </div>
                  )}
                </div>
                <button
                  onClick={handleRegister}
                  disabled={loading || normalizedInput.length < 3}
                >
                  {loading ? '처리 중...' : '이름 등록'}
                </button>
              </div>
            </div>
          )}
        </>
      )}

      {status && (
        <p style={{ marginTop: '0.75rem', color: '#2a6', fontSize: '0.85rem', wordBreak: 'break-all' }}>{status}</p>
      )}
      {error && (
        <p style={{ marginTop: '0.75rem', color: '#c33', fontSize: '0.85rem' }}>오류: {error}</p>
      )}
    </div>
  )
}
