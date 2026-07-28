import { useState } from 'react'
import { votingCreate } from '../lib/voting'
import { getConfig } from '../config'
import type { SmartWalletClient } from '../lib/wallet'

const MAX_TITLE_BYTES = 100
const MAX_DESC_BYTES  = 500
const MIN_HOURS = 1
const MAX_HOURS = 720  // 30 days

function byteLength(text: string): number {
  return new TextEncoder().encode(text).length
}

type Props = {
  client: SmartWalletClient
  onSuccess: () => void
}

export default function CreateProposal({ client, onSuccess }: Props) {
  const [title,    setTitle]    = useState('')
  const [desc,     setDesc]     = useState('')
  const [hours,    setHours]    = useState(24)
  const [status,   setStatus]   = useState('')
  const [error,    setError]    = useState('')
  const [loading,  setLoading]  = useState(false)
  const [expanded, setExpanded] = useState(false)

  const titleBytes = byteLength(title)
  const descBytes  = byteLength(desc)
  const titleOver  = titleBytes > MAX_TITLE_BYTES
  const descOver   = descBytes  > MAX_DESC_BYTES
  const hoursValid = hours >= MIN_HOURS && hours <= MAX_HOURS
  const canSubmit  = title.length > 0 && !titleOver && !descOver && hoursValid && !loading

  if (!getConfig().votingRegistryAddress) {
    return (
      <div style={{ padding: '1rem', background: '#fff3cd', border: '1px solid #856404', borderRadius: '4px' }}>
        <strong>컨트랙트 미배포</strong>
        <p style={{ margin: '0.5rem 0 0', fontSize: '0.85rem' }}>
          VITE_VOTING_REGISTRY_ADDRESS를 설정하세요.
        </p>
      </div>
    )
  }

  async function handleSubmit() {
    if (!canSubmit) return
    setError('')
    setStatus('Passkey로 서명 중...')
    setLoading(true)
    try {
      const txHash = await votingCreate(client, title, desc, hours * 3600)
      setStatus(`제안 생성 완료. tx: ${txHash}`)
      setTitle('')
      setDesc('')
      setHours(24)
      setExpanded(false)
      onSuccess()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      setStatus('')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ marginBottom: '1.5rem' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
        <h3 style={{ margin: 0 }}>제안</h3>
        <button
          onClick={() => setExpanded((v) => !v)}
          style={{ fontSize: '0.8rem', padding: '0.2rem 0.6rem', background: '#eee', color: '#333' }}
        >
          {expanded ? '▲ 닫기' : '▼ 새 제안 작성'}
        </button>
      </div>

      {expanded && (
        <div style={{ marginTop: '1rem', padding: '1rem', border: '1px solid #ddd', borderRadius: '4px', background: '#fafafa' }}>
          {/* Title */}
          <div style={{ marginBottom: '0.75rem' }}>
            <label style={{ fontSize: '0.85rem', color: '#555' }}>제목 *</label>
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="제안 제목"
              disabled={loading}
              style={{
                display: 'block',
                width: '100%',
                marginTop: '0.25rem',
                fontFamily: 'monospace',
                fontSize: '0.9rem',
                padding: '0.35rem 0.6rem',
                border: `1px solid ${titleOver ? '#c33' : '#ccc'}`,
                borderRadius: '4px',
                boxSizing: 'border-box',
              }}
            />
            <span style={{ fontSize: '0.75rem', color: titleOver ? '#c33' : '#888' }}>
              {titleBytes} / {MAX_TITLE_BYTES} bytes{titleOver && ' — 초과'}
            </span>
          </div>

          {/* Description */}
          <div style={{ marginBottom: '0.75rem' }}>
            <label style={{ fontSize: '0.85rem', color: '#555' }}>설명 (선택)</label>
            <textarea
              value={desc}
              onChange={(e) => setDesc(e.target.value)}
              rows={4}
              placeholder="제안 내용을 자세히 설명해 주세요"
              disabled={loading}
              style={{
                display: 'block',
                width: '100%',
                marginTop: '0.25rem',
                fontFamily: 'monospace',
                fontSize: '0.9rem',
                padding: '0.35rem 0.6rem',
                border: `1px solid ${descOver ? '#c33' : '#ccc'}`,
                borderRadius: '4px',
                boxSizing: 'border-box',
                resize: 'vertical',
              }}
            />
            <span style={{ fontSize: '0.75rem', color: descOver ? '#c33' : '#888' }}>
              {descBytes} / {MAX_DESC_BYTES} bytes{descOver && ' — 초과'}
            </span>
          </div>

          {/* Duration */}
          <div style={{ marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <label style={{ fontSize: '0.85rem', color: '#555' }}>투표 기간</label>
            <input
              type="number"
              value={hours}
              min={MIN_HOURS}
              max={MAX_HOURS}
              onChange={(e) => setHours(Number(e.target.value))}
              disabled={loading}
              style={{
                width: '80px',
                fontFamily: 'monospace',
                fontSize: '0.9rem',
                padding: '0.3rem 0.5rem',
                border: `1px solid ${hoursValid ? '#ccc' : '#c33'}`,
                borderRadius: '4px',
              }}
            />
            <span style={{ fontSize: '0.85rem', color: '#555' }}>시간 (1~720)</span>
          </div>

          <button onClick={handleSubmit} disabled={!canSubmit}>
            {loading ? '처리 중...' : '온체인에 제안 올리기'}
          </button>

          {status && (
            <p style={{ marginTop: '0.6rem', color: '#2a6', fontSize: '0.85rem', wordBreak: 'break-all' }}>{status}</p>
          )}
          {error && (
            <p style={{ marginTop: '0.6rem', color: '#c33', fontSize: '0.85rem' }}>오류: {error}</p>
          )}
        </div>
      )}
    </div>
  )
}
