import { useState, useEffect, useCallback } from 'react'
import { datastoreGetAll, datastoreRemove, type Entry } from '../lib/datastore'
import { initHelios, resetHelios, heliosStatus, isOutOfSync, type HeliosStatus } from '../lib/helios'
import { useENSName } from '../hooks/useENSName'
import type { SmartWalletClient } from '../lib/wallet'

type Props = {
  client: SmartWalletClient
  refreshTrigger: number
}

const STATUS_LABEL: Record<HeliosStatus, string> = {
  idle: 'Helios 대기 중',
  initializing: 'Helios 동기화 중... (첫 실행은 10~60초 소요)',
  ready: 'Helios 검증 완료',
  failed: 'Helios 검증 실패',
}

const STATUS_COLOR: Record<HeliosStatus, string> = {
  idle: '#888',
  initializing: '#a60',
  ready: '#2a6',
  failed: '#c33',
}

function formatTime(timestamp: bigint): string {
  return new Date(Number(timestamp) * 1000).toLocaleString('ko-KR')
}

export default function DataViewer({ client, refreshTrigger }: Props) {
  const [syncStatus, setSyncStatus] = useState<HeliosStatus>(heliosStatus())
  const [syncError, setSyncError] = useState<string | null>(null)
  const [entries, setEntries] = useState<Entry[] | null>(null)
  const [fetchError, setFetchError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [deletingIndex, setDeletingIndex] = useState<number | null>(null)

  const address = client.account.address
  const ensName = useENSName(address, syncStatus === 'ready')

  function triggerResync() {
    resetHelios()
    setSyncStatus('initializing')
    setSyncError(null)
    setFetchError(null)
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

  const fetchEntries = useCallback(async () => {
    if (heliosStatus() !== 'ready') return
    setLoading(true)
    setFetchError(null)
    try {
      const result = await datastoreGetAll(address)
      setEntries(result)
    } catch (e) {
      if (isOutOfSync(e)) {
        triggerResync()
      } else {
        setFetchError(e instanceof Error ? e.message : String(e))
      }
    } finally {
      setLoading(false)
    }
  }, [address])

  useEffect(() => {
    if (syncStatus === 'ready') fetchEntries()
  }, [syncStatus, refreshTrigger, fetchEntries])

  async function handleDelete(entry: Entry) {
    setDeletingIndex(entry.index)
    try {
      await datastoreRemove(client, entry.index)
      // Re-fetch after deletion (swap-and-pop changes indices)
      await fetchEntries()
    } catch (e) {
      setFetchError(e instanceof Error ? e.message : String(e))
    } finally {
      setDeletingIndex(null)
    }
  }

  return (
    <div style={{ marginTop: '1.5rem' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap' }}>
        <h3 style={{ margin: 0 }}>
          저장된 데이터
          {ensName && (
            <span style={{ fontWeight: 'normal', fontSize: '0.85rem', color: '#2a6', marginLeft: '0.5rem' }}>
              ({ensName})
            </span>
          )}
        </h3>
        <span style={{ fontSize: '0.8rem', color: STATUS_COLOR[syncStatus] }}>
          {STATUS_LABEL[syncStatus]}
        </span>
        {syncStatus === 'ready' && (
          <button onClick={fetchEntries} disabled={loading} style={{ fontSize: '0.8rem', padding: '0.2rem 0.5rem' }}>
            새로고침
          </button>
        )}
      </div>

      {syncError && (
        <p style={{ color: '#c33', fontSize: '0.85rem', marginTop: '0.5rem' }}>검증 오류: {syncError}</p>
      )}
      {syncStatus === 'failed' && (
        <p style={{ color: '#c33', fontSize: '0.85rem', fontWeight: 'bold', marginTop: '0.25rem' }}>
          Helios 검증 실패 — 미검증 RPC 데이터는 표시하지 않습니다.
        </p>
      )}

      {syncStatus === 'ready' && (
        <>
          {loading && <p style={{ color: '#888', fontSize: '0.85rem', marginTop: '0.75rem' }}>조회 중...</p>}

          {!loading && entries !== null && entries.length === 0 && (
            <p style={{ color: '#888', fontStyle: 'italic', fontSize: '0.9rem', marginTop: '0.75rem' }}>저장된 데이터 없음</p>
          )}

          {!loading && entries !== null && entries.length > 0 && (
            <ul style={{ listStyle: 'none', padding: 0, margin: '0.75rem 0 0' }}>
              {entries.map((entry) => (
                <li
                  key={`${entry.index}-${entry.timestamp}`}
                  style={{
                    border: '1px solid #ddd',
                    borderRadius: '4px',
                    padding: '0.6rem 0.75rem',
                    marginBottom: '0.5rem',
                    background: '#fafafa',
                  }}
                >
                  <div style={{ fontSize: '0.75rem', color: '#888', marginBottom: '0.3rem' }}>
                    {formatTime(entry.timestamp)}
                  </div>
                  <pre style={{ margin: 0, fontFamily: 'monospace', fontSize: '0.9rem', whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
                    {entry.text}
                  </pre>
                  <button
                    onClick={() => handleDelete(entry)}
                    disabled={deletingIndex !== null}
                    style={{ marginTop: '0.4rem', fontSize: '0.8rem', border: '1px solid #c66', color: '#c33', background: '#fde', padding: '0.15rem 0.5rem' }}
                  >
                    {deletingIndex === entry.index ? '삭제 중...' : '삭제'}
                  </button>
                </li>
              ))}
            </ul>
          )}

          {fetchError && (
            <p style={{ color: '#c33', fontSize: '0.85rem', marginTop: '0.5rem' }}>조회 오류: {fetchError}</p>
          )}
        </>
      )}
    </div>
  )
}
