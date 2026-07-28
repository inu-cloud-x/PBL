import { useState } from 'react'
import { datastoreAdd } from '../lib/datastore'
import type { SmartWalletClient } from '../lib/wallet'

const MAX_BYTES = 300

function byteLength(text: string): number {
  return new TextEncoder().encode(text).length
}

type Props = {
  client: SmartWalletClient
  onSuccess: () => void
}

export default function DataEditor({ client, onSuccess }: Props) {
  const [text, setText] = useState('')
  const [status, setStatus] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const bytes = byteLength(text)
  const overLimit = bytes > MAX_BYTES

  async function handleSubmit() {
    if (overLimit || loading) return
    setError('')
    setStatus('Passkey로 서명 중...')
    setLoading(true)
    try {
      const txHash = await datastoreAdd(client, text)
      setStatus(`전송 완료. tx: ${txHash}`)
      setText('')
      onSuccess()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      setStatus('')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ marginTop: '1.5rem' }}>
      <h3>데이터 쓰기</h3>
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={5}
        style={{
          width: '100%',
          fontFamily: 'monospace',
          fontSize: '0.9rem',
          boxSizing: 'border-box',
          border: overLimit ? '2px solid #c33' : '1px solid #ccc',
          borderRadius: '4px',
          padding: '0.5rem',
        }}
        placeholder="온체인에 저장할 텍스트 (최대 300 bytes)"
        disabled={loading}
      />
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '0.25rem' }}>
        <span style={{ fontSize: '0.85rem', color: overLimit ? '#c33' : '#666' }}>
          {bytes} / {MAX_BYTES} bytes {overLimit && '— 초과'}
        </span>
        <button onClick={handleSubmit} disabled={overLimit || loading || text.length === 0}>
          {loading ? '처리 중...' : '온체인에 저장'}
        </button>
      </div>
      {status && <p style={{ color: '#2a6', fontSize: '0.85rem', marginTop: '0.5rem', wordBreak: 'break-all' }}>{status}</p>}
      {error && <p style={{ color: '#c33', fontSize: '0.85rem', marginTop: '0.5rem' }}>오류: {error}</p>}
    </div>
  )
}
