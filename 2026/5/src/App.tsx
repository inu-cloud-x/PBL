import { useState, useEffect } from 'react'
import { getMissingEnvKeys } from './config'
import { getLastUsedKey, setLastUsedId } from './lib/passkey'
import { createSmartWalletClient } from './lib/wallet'
import Login from './components/Login'
import DataEditor from './components/DataEditor'
import DataViewer from './components/DataViewer'
import ENSRegistrar from './components/ENSRegistrar'
import CreateProposal from './components/CreateProposal'
import ProposalList from './components/ProposalList'
import VCTab from './components/vc/VCTab'
import Nav, { type Tab } from './components/Nav'
import type { SmartWalletClient } from './lib/wallet'

export default function App() {
  const missing = getMissingEnvKeys()
  const [client,       setClient]       = useState<SmartWalletClient | null>(null)
  const [refreshTrigger, setRefreshTrigger] = useState(0)
  const [voteRefresh,  setVoteRefresh]  = useState(0)
  const [tab,          setTab]          = useState<Tab>('data')
  // true while attempting silent auto-login from stored key (session already authenticated this tab)
  const [autoLogging,  setAutoLogging]  = useState(
    () => !!sessionStorage.getItem('dapp_session') && getLastUsedKey() !== null,
  )

  useEffect(() => {
    if (!sessionStorage.getItem('dapp_session')) {
      setAutoLogging(false)
      return
    }
    const key = getLastUsedKey()
    if (!key) {
      sessionStorage.removeItem('dapp_session')
      setAutoLogging(false)
      return
    }
    createSmartWalletClient(key)
      .then((c) => {
        setLastUsedId(key.authenticatorId)
        setClient(c)
      })
      .catch(() => {
        sessionStorage.removeItem('dapp_session')
      })
      .finally(() => setAutoLogging(false))
  }, [])

  if (missing.length > 0) {
    return (
      <div style={{ padding: '2rem', fontFamily: 'monospace' }}>
        <h1>Trustless dApp PoC</h1>
        <div style={{ background: '#fff3cd', border: '1px solid #856404', padding: '1rem', borderRadius: '4px', marginTop: '1rem' }}>
          <strong>미설정 환경변수 ({missing.length}개)</strong>
          <ul style={{ margin: '0.5rem 0 0', paddingLeft: '1.5rem' }}>
            {missing.map((k) => (
              <li key={k} style={{ color: '#856404' }}>{k}</li>
            ))}
          </ul>
          <p style={{ margin: '0.5rem 0 0', fontSize: '0.85rem' }}>
            .env.example을 참고해 .env 파일에 값을 채워주세요.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div style={{ padding: '2rem', maxWidth: '600px', fontFamily: 'monospace' }}>
      <h1>Trustless dApp PoC</h1>

      {autoLogging ? (
        <p style={{ color: '#888', marginTop: '1.5rem' }}>자동 로그인 중...</p>
      ) : !client ? (
        <Login onLogin={setClient} />
      ) : (
        <>
          <div style={{ fontSize: '0.85rem', color: '#555', marginBottom: '0.5rem' }}>
            AA 주소: <code style={{ wordBreak: 'break-all' }}>{client.account.address}</code>
          </div>
          <button
            onClick={() => { sessionStorage.removeItem('dapp_session'); setClient(null) }}
            style={{ fontSize: '0.8rem', background: '#eee', color: '#333', padding: '0.2rem 0.6rem', marginBottom: '1.25rem' }}
          >
            로그아웃
          </button>

          <Nav tab={tab} onTabChange={setTab} />

          {tab === 'data' && (
            <>
              <DataEditor
                client={client}
                onSuccess={() => setRefreshTrigger((n) => n + 1)}
              />
              <hr style={{ margin: '1.5rem 0', borderColor: '#eee' }} />
              <DataViewer
                client={client}
                refreshTrigger={refreshTrigger}
              />
            </>
          )}

          {tab === 'ens' && (
            <ENSRegistrar client={client} />
          )}

          {tab === 'vote' && (
            <>
              <CreateProposal
                client={client}
                onSuccess={() => setVoteRefresh((n) => n + 1)}
              />
              <ProposalList
                client={client}
                refreshTrigger={voteRefresh}
              />
            </>
          )}

          {tab === 'vc' && (
            <VCTab client={client} />
          )}
        </>
      )}
    </div>
  )
}
