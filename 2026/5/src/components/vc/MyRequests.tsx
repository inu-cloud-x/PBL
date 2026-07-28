import { useState, useEffect, useCallback } from 'react'
import {
  vcListOutgoingRequests, vcListFormats,
  VC_STATUS_LABEL, type VcRequest,
} from '../../lib/vc'

type Props = {
  address: `0x${string}`
  heliosReady: boolean
}

const STATUS_COLOR: Record<number, string> = {
  0: '#a60',   // Pending
  1: '#2a6',   // Approved
  2: '#888',   // Rejected
}

export default function MyRequests({ address, heliosReady }: Props) {
  const [requests,  setRequests]  = useState<VcRequest[] | null>(null)
  const [formatMap, setFormatMap] = useState(new Map<string, string>())
  const [error,     setError]     = useState<string | null>(null)
  const [loading,   setLoading]   = useState(false)

  const load = useCallback(async () => {
    setError(null)
    setLoading(true)
    try {
      const [reqs, formats] = await Promise.all([
        vcListOutgoingRequests(address),
        vcListFormats(),
      ])
      const map = new Map(formats.map((f) => [f.id.toString(), f.name]))
      setFormatMap(map)
      setRequests(reqs.slice().sort((a, b) => Number(b.createdAt - a.createdAt)))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [address])

  useEffect(() => {
    if (!heliosReady) return
    load()
  }, [heliosReady, load])

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
        <h3 style={styles.title}>내 요청 현황</h3>
        <button onClick={load} disabled={loading} style={styles.smallBtn}>새로고침</button>
      </div>

      {!heliosReady && <p style={{ color: '#a60', fontSize: '0.85rem' }}>Helios 동기화 대기 중...</p>}
      {loading && <p style={{ color: '#888', fontSize: '0.85rem' }}>불러오는 중...</p>}
      {error   && <p style={{ color: '#c33', fontSize: '0.85rem' }}>{error}</p>}

      {requests !== null && requests.length === 0 && (
        <p style={{ color: '#888', fontSize: '0.85rem' }}>요청 내역이 없습니다.</p>
      )}

      {requests?.map((req) => (
        <div key={req.id.toString()} style={styles.card}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <div>
              <strong>{formatMap.get(req.formatId.toString()) ?? `형식 #${req.formatId}`}</strong>
              <div style={{ fontSize: '0.8rem', color: '#666', marginTop: '2px' }}>
                {new Date(Number(req.createdAt) * 1000).toLocaleString()}
              </div>
            </div>
            <span style={{ ...styles.badge, color: STATUS_COLOR[req.status] }}>
              {VC_STATUS_LABEL[req.status]}
            </span>
          </div>

          {req.status === 1 && (
            <p style={{ fontSize: '0.8rem', color: '#555', marginTop: '0.5rem', borderTop: '1px solid #eee', paddingTop: '0.5rem' }}>
              ✓ Issuer가 승인했습니다. Issuer로부터 <code>.vc.json</code> 파일을 받아 "내 보관함"에서 가져오기를 하세요.
            </p>
          )}
        </div>
      ))}
    </div>
  )
}

const styles = {
  title: { margin: '0', fontSize: '1rem' } as React.CSSProperties,
  card: {
    border: '1px solid #ddd',
    borderRadius: '6px',
    padding: '0.75rem 1rem',
    marginBottom: '0.75rem',
    background: '#fafafa',
  } as React.CSSProperties,
  badge: {
    fontSize: '0.8rem',
    fontWeight: 600,
    padding: '0.2rem 0.5rem',
    border: '1px solid currentColor',
    borderRadius: '4px',
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
  } as React.CSSProperties,
}
