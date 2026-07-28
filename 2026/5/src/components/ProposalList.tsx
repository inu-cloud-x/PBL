import { useState, useEffect, useCallback } from 'react'
import { initHelios, resetHelios, heliosStatus, isOutOfSync, type HeliosStatus } from '../lib/helios'
import { votingGetRecent, type Proposal } from '../lib/voting'
import { getConfig } from '../config'
import ProposalCard from './ProposalCard'
import type { SmartWalletClient } from '../lib/wallet'

const RECENT_COUNT = 20

type Props = {
  client: SmartWalletClient
  refreshTrigger: number
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

export default function ProposalList({ client, refreshTrigger }: Props) {
  const [syncStatus, setSyncStatus] = useState<HeliosStatus>(heliosStatus())
  const [syncError,  setSyncError]  = useState<string | null>(null)
  const [proposals,  setProposals]  = useState<Proposal[] | null>(null)
  const [fetchError, setFetchError] = useState<string | null>(null)
  const [loading,    setLoading]    = useState(false)

  const heliosReady = syncStatus === 'ready'

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

  const fetchProposals = useCallback(async () => {
    if (heliosStatus() !== 'ready' || !getConfig().votingRegistryAddress) return
    setLoading(true)
    setFetchError(null)
    try {
      const result = await votingGetRecent(RECENT_COUNT)
      setProposals(result)
    } catch (e) {
      if (isOutOfSync(e)) {
        triggerResync()
      } else {
        setFetchError(e instanceof Error ? e.message : String(e))
      }
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (heliosReady) fetchProposals()
  }, [heliosReady, refreshTrigger, fetchProposals])

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

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap', marginBottom: '0.75rem' }}>
        <h3 style={{ margin: 0 }}>제안 목록 (최신 {RECENT_COUNT}개)</h3>
        <span style={{ fontSize: '0.8rem', color: STATUS_COLOR[syncStatus] }}>
          {STATUS_LABEL[syncStatus]}
        </span>
        {heliosReady && (
          <button
            onClick={fetchProposals}
            disabled={loading}
            style={{ fontSize: '0.8rem', padding: '0.2rem 0.5rem' }}
          >
            새로고침
          </button>
        )}
      </div>

      {syncError && (
        <p style={{ color: '#c33', fontSize: '0.85rem' }}>검증 오류: {syncError}</p>
      )}
      {syncStatus === 'failed' && (
        <p style={{ color: '#c33', fontSize: '0.85rem', fontWeight: 'bold' }}>
          Helios 검증 실패 — 미검증 RPC 데이터는 표시하지 않습니다.
        </p>
      )}

      {heliosReady && (
        <>
          {loading && (
            <p style={{ color: '#888', fontSize: '0.85rem' }}>조회 중...</p>
          )}

          {!loading && proposals !== null && proposals.length === 0 && (
            <p style={{ color: '#888', fontStyle: 'italic', fontSize: '0.9rem' }}>제안이 없습니다. 첫 제안을 올려보세요.</p>
          )}

          {!loading && proposals !== null && proposals.length > 0 && (
            <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
              {proposals.map((p) => (
                <ProposalCard
                  key={p.id}
                  proposal={p}
                  client={client}
                  heliosReady={heliosReady}
                  onVoted={fetchProposals}
                />
              ))}
            </ul>
          )}

          {fetchError && (
            <p style={{ color: '#c33', fontSize: '0.85rem' }}>조회 오류: {fetchError}</p>
          )}
        </>
      )}
    </div>
  )
}
