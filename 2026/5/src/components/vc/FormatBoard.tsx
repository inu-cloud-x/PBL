import { useState, useEffect, useCallback } from 'react'
import {
  vcListFormats, vcRegisterFormat, vcDeactivateFormat,
  vcRequestVc, type VcFormat,
} from '../../lib/vc'
import { derivePasskeyDid, storedKeyToPub } from '../../lib/did'
import { listSavedWebAuthnKeys, getLastUsedKey } from '../../lib/passkey'
import { useENSName } from '../../hooks/useENSName'
import type { SmartWalletClient } from '../../lib/wallet'

type Props = {
  client: SmartWalletClient
  heliosReady: boolean
}

const utf8len = (s: string) => new TextEncoder().encode(s).length

export default function FormatBoard({ client, heliosReady }: Props) {
  const address = client.account.address

  const [formats,       setFormats]       = useState<VcFormat[] | null>(null)
  const [loadError,     setLoadError]     = useState<string | null>(null)
  const [nameInput,     setNameInput]     = useState('')
  const [regStatus,     setRegStatus]     = useState('')
  const [regError,      setRegError]      = useState('')
  const [regLoading,    setRegLoading]    = useState(false)

  // Request modal state
  const [reqFormat,     setReqFormat]     = useState<VcFormat | null>(null)
  const [reqStatus,     setReqStatus]     = useState('')
  const [reqError,      setReqError]      = useState('')
  const [reqLoading,    setReqLoading]    = useState(false)

  // Deactivate state
  const [deactLoading,  setDeactLoading]  = useState<bigint | null>(null)
  const [deactError,    setDeactError]    = useState('')

  const myEns = useENSName(address, heliosReady)

  const load = useCallback(async () => {
    setLoadError(null)
    try {
      const list = await vcListFormats({ onlyActive: true })
      setFormats(list.slice().reverse())  // newest first
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : String(e))
    }
  }, [])

  useEffect(() => {
    if (!heliosReady) return
    load()
  }, [heliosReady, load])

  async function handleRegister() {
    setRegError('')
    setRegStatus('')
    setRegLoading(true)
    try {
      await vcRegisterFormat(client, nameInput)
      setRegStatus('등록 완료!')
      setNameInput('')
      await load()
    } catch (e) {
      setRegError(e instanceof Error ? e.message : String(e))
    } finally {
      setRegLoading(false)
    }
  }

  async function handleDeactivate(formatId: bigint) {
    setDeactError('')
    setDeactLoading(formatId)
    try {
      await vcDeactivateFormat(client, formatId)
      await load()
    } catch (e) {
      setDeactError(e instanceof Error ? e.message : String(e))
    } finally {
      setDeactLoading(null)
    }
  }

  async function handleRequest(fmt: VcFormat) {
    setReqError('')
    setReqStatus('')
    setReqLoading(true)
    try {
      const lastKey = getLastUsedKey()
      if (!lastKey) throw new Error('Passkey를 찾을 수 없습니다')
      const stored = listSavedWebAuthnKeys().find(k => k.authenticatorId === lastKey.authenticatorId)
      if (!stored) throw new Error('Passkey 정보를 찾을 수 없습니다')
      const pub        = storedKeyToPub(stored.pubX, stored.pubY)
      const subjectDid = derivePasskeyDid(pub)
      await vcRequestVc(client, fmt.id, subjectDid)
      setReqStatus('요청이 전송되었습니다! "내 요청" 탭에서 확인하세요.')
    } catch (e) {
      setReqError(e instanceof Error ? e.message : String(e))
    } finally {
      setReqLoading(false)
    }
  }

  const nameBytes   = utf8len(nameInput)
  const nameTooLong = nameBytes > 40
  const nameEmpty   = nameInput.trim() === ''
  const hasEns      = !!myEns

  return (
    <div>
      {/* ── Register form ─────────────────────────────── */}
      <section style={styles.card}>
        <h3 style={styles.sectionTitle}>새 VC 형식 등록</h3>
        {!hasEns ? (
          <p style={{ color: '#a60', fontSize: '0.85rem' }}>
            ENS 이름이 있어야 형식을 등록할 수 있습니다. "ENS 이름" 탭에서 먼저 이름을 등록하세요.
          </p>
        ) : (
          <>
            <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'flex-start' }}>
              <div style={{ flex: 1 }}>
                <input
                  type="text"
                  placeholder="VC 형식 이름 (≤40 bytes)"
                  value={nameInput}
                  onChange={(e) => setNameInput(e.target.value)}
                  style={{ ...styles.input, borderColor: nameTooLong ? '#c33' : '#ccc' }}
                />
                <div style={{ fontSize: '0.75rem', color: nameTooLong ? '#c33' : '#888', marginTop: '2px' }}>
                  {nameBytes}/40 bytes
                </div>
              </div>
              <button
                onClick={handleRegister}
                disabled={regLoading || nameEmpty || nameTooLong}
                style={styles.btn}
              >
                {regLoading ? '등록 중...' : '등록'}
              </button>
            </div>
            {regStatus && <p style={{ color: '#2a6', marginTop: '0.5rem', fontSize: '0.85rem' }}>{regStatus}</p>}
            {regError  && <p style={{ color: '#c33', marginTop: '0.5rem', fontSize: '0.85rem' }}>{regError}</p>}
          </>
        )}
      </section>

      {/* ── Format list ───────────────────────────────── */}
      <section>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
          <h3 style={styles.sectionTitle}>Active 형식 목록</h3>
          <button onClick={load} style={styles.smallBtn}>새로고침</button>
        </div>

        {!heliosReady && <p style={{ color: '#a60', fontSize: '0.85rem' }}>Helios 동기화 대기 중...</p>}
        {loadError    && <p style={{ color: '#c33', fontSize: '0.85rem' }}>{loadError}</p>}
        {deactError   && <p style={{ color: '#c33', fontSize: '0.85rem' }}>{deactError}</p>}

        {formats !== null && formats.length === 0 && (
          <p style={{ color: '#888', fontSize: '0.85rem' }}>등록된 형식이 없습니다.</p>
        )}

        {formats?.map((fmt) => (
          <FormatCard
            key={fmt.id.toString()}
            fmt={fmt}
            myAddress={address}
            heliosReady={heliosReady}
            deactLoading={deactLoading}
            onDeactivate={handleDeactivate}
            onRequest={setReqFormat}
          />
        ))}
      </section>

      {/* ── Request modal ─────────────────────────────── */}
      {reqFormat && (
        <div style={styles.overlay} onClick={() => !reqLoading && setReqFormat(null)}>
          <div style={styles.modal} onClick={(e) => e.stopPropagation()}>
            <h3 style={{ margin: '0 0 1rem' }}>VC 요청</h3>
            <p style={{ fontSize: '0.9rem', marginBottom: '0.5rem' }}>
              <strong>{reqFormat.name}</strong>
            </p>
            <p style={{ fontSize: '0.85rem', color: '#555', marginBottom: '1rem' }}>
              요청 시 본인의 DID가 Issuer에게 전달됩니다.
            </p>
            {reqStatus ? (
              <>
                <p style={{ color: '#2a6', fontSize: '0.85rem' }}>{reqStatus}</p>
                <button onClick={() => setReqFormat(null)} style={styles.btn}>닫기</button>
              </>
            ) : (
              <>
                {reqError && <p style={{ color: '#c33', fontSize: '0.85rem', marginBottom: '0.5rem' }}>{reqError}</p>}
                <div style={{ display: 'flex', gap: '0.5rem' }}>
                  <button
                    onClick={() => handleRequest(reqFormat)}
                    disabled={reqLoading}
                    style={styles.btn}
                  >
                    {reqLoading ? '요청 중...' : '요청'}
                  </button>
                  <button
                    onClick={() => setReqFormat(null)}
                    disabled={reqLoading}
                    style={{ ...styles.btn, background: '#eee', color: '#333' }}
                  >
                    취소
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// ── FormatCard: per-card sub-component so useENSName runs per issuer ──────────

type CardProps = {
  fmt: VcFormat
  myAddress: string
  heliosReady: boolean
  deactLoading: bigint | null
  onDeactivate: (id: bigint) => void
  onRequest: (fmt: VcFormat) => void
}

function FormatCard({ fmt, myAddress, heliosReady, deactLoading, onDeactivate, onRequest }: CardProps) {
  const issuerEns = useENSName(fmt.issuer, heliosReady)
  const issuerLabel = issuerEns ?? `${fmt.issuer.slice(0, 10)}...`
  const isMyFormat = fmt.issuer.toLowerCase() === myAddress.toLowerCase()

  return (
    <div style={styles.card}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <strong>{fmt.name}</strong>
          <div style={{ fontSize: '0.8rem', color: '#666', marginTop: '2px' }}>
            Issuer: {issuerLabel}&nbsp;
            · 등록일 {new Date(Number(fmt.createdAt) * 1000).toLocaleDateString()}
          </div>
        </div>
        {isMyFormat ? (
          <button
            onClick={() => onDeactivate(fmt.id)}
            disabled={deactLoading === fmt.id}
            style={{ ...styles.smallBtn, color: '#c33', borderColor: '#c33' }}
          >
            {deactLoading === fmt.id ? '처리 중...' : '비활성화'}
          </button>
        ) : (
          <button onClick={() => onRequest(fmt)} style={styles.smallBtn}>
            이 형식 요청하기
          </button>
        )}
      </div>
    </div>
  )
}

const styles = {
  card: {
    border: '1px solid #ddd',
    borderRadius: '6px',
    padding: '0.75rem 1rem',
    marginBottom: '0.75rem',
    background: '#fafafa',
  } as React.CSSProperties,
  sectionTitle: {
    margin: '0 0 0.75rem',
    fontSize: '1rem',
  } as React.CSSProperties,
  input: {
    width: '100%',
    padding: '0.4rem 0.6rem',
    fontFamily: 'monospace',
    fontSize: '0.9rem',
    border: '1px solid #ccc',
    borderRadius: '4px',
    boxSizing: 'border-box' as const,
  } as React.CSSProperties,
  btn: {
    padding: '0.4rem 0.9rem',
    fontFamily: 'monospace',
    fontSize: '0.85rem',
    background: '#222',
    color: '#fff',
    border: '1px solid #222',
    borderRadius: '4px',
    cursor: 'pointer',
    whiteSpace: 'nowrap' as const,
  } as React.CSSProperties,
  smallBtn: {
    padding: '0.25rem 0.6rem',
    fontFamily: 'monospace',
    fontSize: '0.8rem',
    background: '#fff',
    color: '#333',
    border: '1px solid #ccc',
    borderRadius: '4px',
    cursor: 'pointer',
    whiteSpace: 'nowrap' as const,
  } as React.CSSProperties,
  overlay: {
    position: 'fixed' as const,
    inset: 0,
    background: 'rgba(0,0,0,0.4)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 100,
  } as React.CSSProperties,
  modal: {
    background: '#fff',
    border: '1px solid #ccc',
    borderRadius: '8px',
    padding: '1.5rem',
    minWidth: '320px',
    maxWidth: '480px',
    fontFamily: 'monospace',
  } as React.CSSProperties,
}

