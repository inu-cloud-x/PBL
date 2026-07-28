import { useState, useEffect, useCallback } from 'react'
import {
  loadAllVcs, saveVc, removeVc, exportVcAsJson, importVcFromFile,
  verifyVcSignature, vcHash, vcListIssuedToMe, isExpired,
  type VerifiableCredential,
} from '../../lib/vc'
import { getConfig } from '../../config'

type Props = {
  address: `0x${string}`
  heliosReady: boolean
}

export default function MyCredentials({ address, heliosReady }: Props) {
  const chainId = getConfig().chainId
  const [vcs,       setVcs]       = useState<VerifiableCredential[]>([])
  const [importing, setImporting] = useState(false)
  const [importErr, setImportErr] = useState<string | null>(null)
  const [toast,     setToast]     = useState<string | null>(null)

  const reload = useCallback(() => {
    setVcs(loadAllVcs(chainId).slice().reverse())
  }, [chainId])

  useEffect(() => { reload() }, [reload])

  function showToast(msg: string) {
    setToast(msg)
    setTimeout(() => setToast(null), 3000)
  }

  async function handleImport(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    e.target.value = ''  // reset input for re-import

    setImportErr(null)
    setImporting(true)
    try {
      const vc = await importVcFromFile(file)

      // 1. Verify signature
      const valid = await verifyVcSignature(vc)
      if (!valid) throw new Error('서명 검증에 실패했습니다. 위조된 VC일 수 있습니다.')

      // 2. Check on-chain hash (must be issued to my address)
      const hash = vcHash(vc)
      if (heliosReady) {
        const issued = await vcListIssuedToMe(address)
        const match = issued.find((i) => i.jsonHash.toLowerCase() === hash.toLowerCase())
        if (!match) {
          throw new Error('이 VC가 내 주소로 발급된 온체인 기록이 없습니다. 다른 주소로 발급된 VC이거나 변조된 파일일 수 있습니다.')
        }
      }

      saveVc(vc, chainId)
      reload()
      showToast('VC가 보관함에 추가되었습니다.')
    } catch (e) {
      setImportErr(e instanceof Error ? e.message : String(e))
    } finally {
      setImporting(false)
    }
  }

  async function handleVerify(vc: VerifiableCredential) {
    const hash = vcHash(vc)
    const sigValid = await verifyVcSignature(vc)

    if (!sigValid) {
      showToast('✗ 서명 검증 실패')
      return
    }

    if (!heliosReady) {
      showToast('✓ 서명 유효 (온체인 검증은 Helios 준비 후 가능)')
      return
    }

    try {
      const issued = await vcListIssuedToMe(address)
      const match = issued.find((i) => i.jsonHash.toLowerCase() === hash.toLowerCase())
      if (match) showToast('✓ 서명 유효 + 온체인 기록 확인됨')
      else        showToast('✓ 서명 유효 (온체인 hash 불일치)')
    } catch {
      showToast('✓ 서명 유효 (온체인 조회 실패)')
    }
  }

  function handleDownload(vc: VerifiableCredential) {
    const { filename, blob } = exportVcAsJson(vc)
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = filename; a.click()
    URL.revokeObjectURL(url)
  }

  function handleDelete(hash: string) {
    if (!confirm('이 VC를 보관함에서 삭제하시겠습니까? 파일이 없으면 복구 불가합니다.')) return
    removeVc(chainId, hash)
    reload()
  }

  return (
    <div>
      {/* ── Import ─────────────────────────────────────── */}
      <section style={styles.card}>
        <h3 style={styles.sectionTitle}>VC 가져오기</h3>
        <p style={{ fontSize: '0.85rem', color: '#555', marginBottom: '0.75rem' }}>
          Issuer로부터 받은 <code>.vc.json</code> 파일을 선택하세요.
          서명 검증 및 온체인 기록 확인 후 보관함에 저장됩니다.
        </p>
        {!heliosReady && (
          <p style={{ fontSize: '0.8rem', color: '#a60', marginBottom: '0.5rem' }}>
            Helios 준비 전 가져오기 시 온체인 검증이 생략됩니다.
          </p>
        )}
        <label style={styles.fileLabel}>
          {importing ? '처리 중...' : '파일 선택'}
          <input
            type="file"
            accept=".vc.json,application/json"
            onChange={handleImport}
            disabled={importing}
            style={{ display: 'none' }}
          />
        </label>
        {importErr && (
          <p style={{ color: '#c33', fontSize: '0.85rem', marginTop: '0.5rem' }}>{importErr}</p>
        )}
      </section>

      {/* ── VC list ────────────────────────────────────── */}
      <section>
        <h3 style={styles.sectionTitle}>내 VC 목록 ({vcs.length})</h3>

        {vcs.length === 0 && (
          <p style={{ color: '#888', fontSize: '0.85rem' }}>저장된 VC가 없습니다.</p>
        )}

        {vcs.map((vc) => {
          const hash    = vcHash(vc)
          const expired = isExpired(vc)
          const vcName  = vc.type[1] ?? 'VerifiableCredential'
          const issuer  = vc.issuer

          return (
            <div key={hash} style={{ ...styles.card, borderLeft: expired ? '3px solid #c33' : '3px solid #2a6' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <div style={{ flex: 1 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <strong style={{ fontSize: '1rem' }}>{vcName}</strong>
                    {expired && (
                      <span style={{ fontSize: '0.7rem', color: '#c33', border: '1px solid #c33', borderRadius: '3px', padding: '1px 4px', fontWeight: 700 }}>
                        EXPIRED
                      </span>
                    )}
                  </div>

                  <div style={{ fontSize: '0.8rem', color: '#555', marginTop: '4px' }}>
                    <div>Issuer: {issuer.name ? `${issuer.name} ` : ''}<code style={{ fontSize: '0.75rem' }}>{issuer.id.slice(0, 24)}...</code></div>
                    <div>세부사항: {vc.credentialSubject.details}</div>
                    <div>
                      발급일: {new Date(vc.issuanceDate).toLocaleDateString()}
                      &nbsp;· 만료일: {new Date(vc.expirationDate).toLocaleDateString()}
                    </div>
                  </div>
                </div>
              </div>

              <div style={{ display: 'flex', gap: '0.4rem', marginTop: '0.75rem', flexWrap: 'wrap' }}>
                <button onClick={() => handleVerify(vc)} style={styles.smallBtn}>온체인 검증</button>
                <button onClick={() => handleDownload(vc)} style={styles.smallBtn}>JSON 다운로드</button>
                <button
                  onClick={() => handleDelete(hash)}
                  style={{ ...styles.smallBtn, color: '#c33', borderColor: '#c33' }}
                >
                  삭제
                </button>
              </div>
            </div>
          )
        })}
      </section>

      {/* ── Toast ──────────────────────────────────────── */}
      {toast && (
        <div style={styles.toast}>{toast}</div>
      )}
    </div>
  )
}

const styles = {
  sectionTitle: { margin: '0 0 0.75rem', fontSize: '1rem' } as React.CSSProperties,
  card: {
    border: '1px solid #ddd',
    borderRadius: '6px',
    padding: '0.75rem 1rem',
    marginBottom: '0.75rem',
    background: '#fafafa',
  } as React.CSSProperties,
  fileLabel: {
    display: 'inline-block',
    padding: '0.4rem 0.9rem',
    fontFamily: 'monospace',
    fontSize: '0.85rem',
    background: '#222',
    color: '#fff',
    borderRadius: '4px',
    cursor: 'pointer',
  } as React.CSSProperties,
  smallBtn: {
    padding: '0.25rem 0.6rem',
    fontFamily: 'monospace',
    fontSize: '0.78rem',
    background: '#fff',
    color: '#333',
    border: '1px solid #ccc',
    borderRadius: '4px',
    cursor: 'pointer',
  } as React.CSSProperties,
  toast: {
    position: 'fixed' as const,
    bottom: '1.5rem',
    right: '1.5rem',
    background: '#222',
    color: '#fff',
    padding: '0.6rem 1.2rem',
    borderRadius: '6px',
    fontFamily: 'monospace',
    fontSize: '0.85rem',
    zIndex: 200,
  } as React.CSSProperties,
}
