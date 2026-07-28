import { useState, useEffect, useCallback } from 'react'
import {
  vcListIncomingRequests, vcListFormats, vcApproveRequest, vcRejectRequest,
  buildVcPayload, signVc, vcHash, saveVc, exportVcAsJson,
  type VcRequest, type VcFormat, type VerifiableCredential,
} from '../../lib/vc'
import { derivePasskeyDid, storedKeyToPub } from '../../lib/did'
import { listSavedWebAuthnKeys, getLastUsedKey } from '../../lib/passkey'
import { ensReverseLookup } from '../../lib/ens'
import { getConfig } from '../../config'
import type { SmartWalletClient } from '../../lib/wallet'

type Props = {
  client: SmartWalletClient
  heliosReady: boolean
}

const utf8len = (s: string) => new TextEncoder().encode(s).length

export default function IssuerInbox({ client, heliosReady }: Props) {
  const address = client.account.address

  const [requests,  setRequests]  = useState<VcRequest[] | null>(null)
  const [formatMap, setFormatMap] = useState(new Map<string, VcFormat>())
  const [loadError, setLoadError] = useState<string | null>(null)
  const [loading,   setLoading]   = useState(false)

  // Approve modal
  const [approveReq,  setApproveReq]  = useState<VcRequest | null>(null)
  const [details,     setDetails]     = useState('')
  const [approveStep, setApproveStep] = useState<string>('')
  const [approveErr,  setApproveErr]  = useState<string>('')
  const [approving,   setApproving]   = useState(false)
  const [pendingVc,   setPendingVc]   = useState<VerifiableCredential | null>(null)
  const [doneVc,      setDoneVc]      = useState<VerifiableCredential | null>(null)

  // Reject
  const [rejectLoading, setRejectLoading] = useState<bigint | null>(null)
  const [rejectError,   setRejectError]   = useState<string>('')
  const [confirmReject, setConfirmReject] = useState<VcRequest | null>(null)

  const load = useCallback(async () => {
    setLoadError(null)
    setLoading(true)
    try {
      const [reqs, formats] = await Promise.all([
        vcListIncomingRequests(address),
        vcListFormats(),
      ])
      const fmap = new Map(formats.map((f) => [f.id.toString(), f]))
      setFormatMap(fmap)
      // Show only Pending
      setRequests(
        reqs
          .filter((r) => r.status === 0)
          .sort((a, b) => Number(b.createdAt - a.createdAt)),
      )
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [address])

  useEffect(() => {
    if (!heliosReady) return
    load()
  }, [heliosReady, load])

  function openApprove(req: VcRequest) {
    setApproveReq(req)
    setDetails('')
    setApproveStep('')
    setApproveErr('')
    setApproving(false)
    setPendingVc(null)
    setDoneVc(null)
  }

  async function handleApprove() {
    if (!approveReq) return
    setApproveErr('')
    setApproving(true)

    try {
      const lastKey = getLastUsedKey()
      if (!lastKey) throw new Error('Passkey를 찾을 수 없습니다')
      const stored = listSavedWebAuthnKeys().find(k => k.authenticatorId === lastKey.authenticatorId)
      if (!stored) throw new Error('Passkey 정보를 찾을 수 없습니다')

      const pub        = storedKeyToPub(stored.pubX, stored.pubY)
      const issuerDid  = derivePasskeyDid(pub)
      const formatId   = approveReq.formatId
      const format     = formatMap.get(formatId.toString())

      // Step 1: Get ENS name
      setApproveStep('ENS 이름 조회 중...')
      let issuerEns = ''
      if (getConfig().miniEnsAddress) {
        try { issuerEns = await ensReverseLookup(address) } catch { /* fallback to empty */ }
      }

      // Step 2: Build payload and sign
      setApproveStep('지문 인증이 필요합니다 (발급을 위해 Passkey 확인)...')
      const issuedAt = new Date()
      const payload = buildVcPayload({
        vcName:     format?.name ?? `Format#${formatId}`,
        issuerEns,
        issuerDid,
        subjectDid: approveReq.subjectDid,
        details,
        issuedAt,
      })
      const vc = await signVc(payload, stored)
      setPendingVc(vc)

      // Step 3: Record on-chain
      setApproveStep('트랜잭션 전송 중...')
      const hash = vcHash(vc)
      await vcApproveRequest(client, approveReq.id, details, hash)

      // Step 4: Save and download
      saveVc(vc, getConfig().chainId)
      const { filename, blob } = exportVcAsJson(vc)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url; a.download = filename; a.click()
      URL.revokeObjectURL(url)

      setDoneVc(vc)
      setPendingVc(null)
      setApproveStep('')
      await load()
    } catch (e) {
      setApproveErr(e instanceof Error ? e.message : String(e))
      setApproveStep('')
    } finally {
      setApproving(false)
    }
  }

  async function handleRetry() {
    if (!approveReq || !pendingVc) return
    setApproveErr('')
    setApproving(true)
    try {
      setApproveStep('트랜잭션 재전송 중...')
      const hash = vcHash(pendingVc)
      await vcApproveRequest(client, approveReq.id, details, hash)
      saveVc(pendingVc, getConfig().chainId)
      const { filename, blob } = exportVcAsJson(pendingVc)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url; a.download = filename; a.click()
      URL.revokeObjectURL(url)
      setDoneVc(pendingVc)
      setPendingVc(null)
      setApproveStep('')
      await load()
    } catch (e) {
      setApproveErr(e instanceof Error ? e.message : String(e))
      setApproveStep('')
    } finally {
      setApproving(false)
    }
  }

  function downloadAgain() {
    if (!doneVc) return
    const { filename, blob } = exportVcAsJson(doneVc)
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = filename; a.click()
    URL.revokeObjectURL(url)
  }

  async function handleReject(req: VcRequest) {
    setRejectError('')
    setRejectLoading(req.id)
    try {
      await vcRejectRequest(client, req.id)
      setConfirmReject(null)
      await load()
    } catch (e) {
      setRejectError(e instanceof Error ? e.message : String(e))
    } finally {
      setRejectLoading(null)
    }
  }

  const detailBytes   = utf8len(details)
  const detailTooLong = detailBytes > 100
  const detailEmpty   = details.trim() === ''

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
        <h3 style={styles.title}>받은 요청 (대기 중)</h3>
        <button onClick={load} disabled={loading} style={styles.smallBtn}>새로고침</button>
      </div>

      {!heliosReady && <p style={{ color: '#a60', fontSize: '0.85rem' }}>Helios 동기화 대기 중...</p>}
      {loading    && <p style={{ color: '#888', fontSize: '0.85rem' }}>불러오는 중...</p>}
      {loadError  && <p style={{ color: '#c33', fontSize: '0.85rem' }}>{loadError}</p>}
      {rejectError && <p style={{ color: '#c33', fontSize: '0.85rem' }}>{rejectError}</p>}

      {requests !== null && requests.length === 0 && (
        <p style={{ color: '#888', fontSize: '0.85rem' }}>대기 중인 요청이 없습니다.</p>
      )}

      {requests?.map((req) => {
        const fmt = formatMap.get(req.formatId.toString())
        return (
          <div key={req.id.toString()} style={styles.card}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
              <div>
                <strong>{fmt?.name ?? `형식 #${req.formatId}`}</strong>
                <div style={{ fontSize: '0.8rem', color: '#666', marginTop: '2px' }}>
                  요청자: <code>{req.requester.slice(0, 10)}...</code>
                  &nbsp;· {new Date(Number(req.createdAt) * 1000).toLocaleString()}
                </div>
                <div style={{ fontSize: '0.75rem', color: '#888', marginTop: '2px' }}>
                  DID: {req.subjectDid.slice(0, 24)}...
                </div>
              </div>
              <div style={{ display: 'flex', gap: '0.4rem' }}>
                <button onClick={() => openApprove(req)} style={styles.approveBtn}>승인</button>
                <button
                  onClick={() => setConfirmReject(req)}
                  disabled={rejectLoading === req.id}
                  style={styles.rejectBtn}
                >
                  거절
                </button>
              </div>
            </div>
          </div>
        )
      })}

      {/* ── Approve modal ── */}
      {approveReq && (
        <div style={styles.overlay} onClick={() => !approving && setApproveReq(null)}>
          <div style={styles.modal} onClick={(e) => e.stopPropagation()}>
            <h3 style={{ margin: '0 0 1rem' }}>VC 발급 승인</h3>

            {doneVc ? (
              <div>
                <p style={{ color: '#2a6' }}>✓ 발급이 완료되었습니다!</p>
                <p style={{ fontSize: '0.85rem', color: '#555' }}>
                  다운로드된 파일을 요청자에게 직접 전달하세요.
                </p>
                <div style={{ display: 'flex', gap: '0.5rem', marginTop: '1rem' }}>
                  <button onClick={downloadAgain} style={styles.smallBtn}>재다운로드</button>
                  <button onClick={() => setApproveReq(null)} style={styles.approveBtn}>닫기</button>
                </div>
              </div>
            ) : (
              <>
                <p style={{ fontSize: '0.85rem', marginBottom: '1rem' }}>
                  발급을 위해 Passkey(지문) 인증이 한 번 더 필요합니다.
                </p>
                <div style={{ marginBottom: '0.75rem' }}>
                  <label style={{ display: 'block', fontSize: '0.85rem', marginBottom: '4px' }}>
                    세부사항 (≤100 bytes)
                  </label>
                  <textarea
                    value={details}
                    onChange={(e) => setDetails(e.target.value)}
                    rows={3}
                    style={{ ...styles.textarea, borderColor: detailTooLong ? '#c33' : '#ccc' }}
                    disabled={approving}
                  />
                  <div style={{ fontSize: '0.75rem', color: detailTooLong ? '#c33' : '#888' }}>
                    {detailBytes}/100 bytes
                  </div>
                </div>

                {approveStep && <p style={{ color: '#a60', fontSize: '0.85rem' }}>{approveStep}</p>}
                {approveErr  && (
                  <p style={{ color: '#c33', fontSize: '0.85rem' }}>
                    {approveErr}
                  </p>
                )}

                {pendingVc && approveErr && (
                  <div style={{ marginTop: '0.5rem' }}>
                    <p style={{ fontSize: '0.8rem', color: '#555' }}>
                      서명은 완료됐으나 온체인 기록에 실패했습니다. 재시도하세요.
                    </p>
                    <button onClick={handleRetry} disabled={approving} style={styles.approveBtn}>
                      재시도
                    </button>
                  </div>
                )}

                {!pendingVc && (
                  <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.75rem' }}>
                    <button
                      onClick={handleApprove}
                      disabled={approving || detailEmpty || detailTooLong}
                      style={styles.approveBtn}
                    >
                      {approving ? '처리 중...' : '발급'}
                    </button>
                    <button
                      onClick={() => setApproveReq(null)}
                      disabled={approving}
                      style={{ ...styles.smallBtn }}
                    >
                      취소
                    </button>
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      )}

      {/* ── Reject confirm ── */}
      {confirmReject && (
        <div style={styles.overlay} onClick={() => !rejectLoading && setConfirmReject(null)}>
          <div style={styles.modal} onClick={(e) => e.stopPropagation()}>
            <h3 style={{ margin: '0 0 1rem' }}>요청 거절</h3>
            <p style={{ fontSize: '0.9rem' }}>정말로 이 요청을 거절하시겠습니까?</p>
            <p style={{ fontSize: '0.8rem', color: '#888' }}>거절 후에는 같은 요청을 다시 승인할 수 없습니다.</p>
            <div style={{ display: 'flex', gap: '0.5rem', marginTop: '1rem' }}>
              <button
                onClick={() => handleReject(confirmReject)}
                disabled={rejectLoading === confirmReject.id}
                style={styles.rejectBtn}
              >
                {rejectLoading === confirmReject.id ? '처리 중...' : '거절 확인'}
              </button>
              <button onClick={() => setConfirmReject(null)} style={styles.smallBtn}>취소</button>
            </div>
          </div>
        </div>
      )}
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
  approveBtn: {
    padding: '0.3rem 0.7rem',
    fontFamily: 'monospace',
    fontSize: '0.8rem',
    background: '#222',
    color: '#fff',
    border: '1px solid #222',
    borderRadius: '4px',
    cursor: 'pointer',
    whiteSpace: 'nowrap' as const,
  } as React.CSSProperties,
  rejectBtn: {
    padding: '0.3rem 0.7rem',
    fontFamily: 'monospace',
    fontSize: '0.8rem',
    background: '#fff',
    color: '#c33',
    border: '1px solid #c33',
    borderRadius: '4px',
    cursor: 'pointer',
    whiteSpace: 'nowrap' as const,
  } as React.CSSProperties,
  smallBtn: {
    padding: '0.3rem 0.7rem',
    fontFamily: 'monospace',
    fontSize: '0.8rem',
    background: '#fff',
    color: '#333',
    border: '1px solid #ccc',
    borderRadius: '4px',
    cursor: 'pointer',
  } as React.CSSProperties,
  textarea: {
    width: '100%',
    fontFamily: 'monospace',
    fontSize: '0.85rem',
    padding: '0.4rem 0.6rem',
    border: '1px solid #ccc',
    borderRadius: '4px',
    boxSizing: 'border-box' as const,
    resize: 'vertical' as const,
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
    minWidth: '340px',
    maxWidth: '500px',
    fontFamily: 'monospace',
  } as React.CSSProperties,
}
