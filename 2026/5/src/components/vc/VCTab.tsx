import { useState, useEffect } from 'react'
import { initHelios, resetHelios, heliosStatus, type HeliosStatus } from '../../lib/helios'
import { getConfig } from '../../config'
import FormatBoard from './FormatBoard'
import IssuerInbox from './IssuerInbox'
import MyRequests from './MyRequests'
import MyCredentials from './MyCredentials'
import type { SmartWalletClient } from '../../lib/wallet'

type VcSubTab = 'formats' | 'inbox' | 'my-requests' | 'vault'

const SUB_TABS: { id: VcSubTab; label: string }[] = [
  { id: 'formats',     label: '형식 게시판' },
  { id: 'inbox',       label: '받은 요청'  },
  { id: 'my-requests', label: '내 요청'    },
  { id: 'vault',       label: '내 보관함'  },
]

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

type Props = { client: SmartWalletClient }

export default function VCTab({ client }: Props) {
  const [subTab,      setSubTab]     = useState<VcSubTab>('formats')
  const [syncStatus,  setSyncStatus] = useState<HeliosStatus>(heliosStatus())
  const [syncError,   setSyncError]  = useState<string | null>(null)

  const heliosReady = syncStatus === 'ready'
  const vcAddr      = getConfig().vcRegistryAddress

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
  }, [])  // eslint-disable-line react-hooks/exhaustive-deps

  if (!vcAddr) {
    return (
      <div style={{ color: '#888', fontSize: '0.9rem', padding: '1rem 0' }}>
        VCRegistry 컨트랙트가 미배포 상태입니다.
        <br />
        <code>VITE_VC_REGISTRY_ADDRESS</code>를 .env에 설정하세요.
      </div>
    )
  }

  return (
    <div>
      {/* ── Helios status ─── */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.75rem', fontSize: '0.8rem' }}>
        <span style={{ color: STATUS_COLOR[syncStatus] }}>● {STATUS_LABEL[syncStatus]}</span>
        {syncStatus === 'failed' && (
          <button onClick={triggerResync} style={styles.smallBtn}>재시도</button>
        )}
        {syncError && <span style={{ color: '#c33', fontSize: '0.75rem' }}>{syncError}</span>}
      </div>

      {/* ── Sub-nav ─────────── */}
      <nav style={{ display: 'flex', gap: '0.25rem', borderBottom: '1px solid #ddd', marginBottom: '1.25rem' }}>
        {SUB_TABS.map(({ id, label }) => (
          <button
            key={id}
            onClick={() => setSubTab(id)}
            style={{
              padding: '0.3rem 0.75rem',
              fontFamily: 'monospace',
              fontSize: '0.82rem',
              border: '1px solid #ddd',
              borderBottom: subTab === id ? '1px solid #fff' : '1px solid #ddd',
              borderRadius: '4px 4px 0 0',
              background: subTab === id ? '#fff' : '#f5f5f5',
              color: subTab === id ? '#000' : '#555',
              cursor: 'pointer',
              position: 'relative',
              top: '1px',
            }}
          >
            {label}
          </button>
        ))}
      </nav>

      {/* ── Content ─────────── */}
      {subTab === 'formats'     && <FormatBoard  client={client}                          heliosReady={heliosReady} />}
      {subTab === 'inbox'       && <IssuerInbox  client={client}                          heliosReady={heliosReady} />}
      {subTab === 'my-requests' && <MyRequests   address={client.account.address}         heliosReady={heliosReady} />}
      {subTab === 'vault'       && <MyCredentials address={client.account.address}        heliosReady={heliosReady} />}
    </div>
  )
}

const styles = {
  smallBtn: {
    padding: '0.2rem 0.5rem',
    fontFamily: 'monospace',
    fontSize: '0.78rem',
    background: '#fff',
    color: '#333',
    border: '1px solid #ccc',
    borderRadius: '4px',
    cursor: 'pointer',
  } as React.CSSProperties,
}
