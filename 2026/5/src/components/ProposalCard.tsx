import { useState } from 'react'
import { CHOICE_COLOR, type Proposal } from '../lib/voting'
import { useENSName } from '../hooks/useENSName'
import VotePanel from './VotePanel'
import type { SmartWalletClient } from '../lib/wallet'

type Props = {
  proposal: Proposal
  client: SmartWalletClient
  heliosReady: boolean
  onVoted: () => void
}

function formatDeadline(deadline: number): string {
  return new Intl.DateTimeFormat('ko-KR', {
    year: 'numeric', month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit',
  }).format(new Date(deadline * 1000))
}

function formatAddress(addr: string): string {
  return `${addr.slice(0, 6)}…${addr.slice(-4)}`
}

function VoteBar({ yes, no, abstain }: { yes: number; no: number; abstain: number }) {
  const total = yes + no + abstain
  if (total === 0) {
    return <span style={{ fontSize: '0.8rem', color: '#aaa' }}>투표 없음</span>
  }
  return (
    <div>
      <div style={{ display: 'flex', height: '8px', borderRadius: '4px', overflow: 'hidden', margin: '0.3rem 0' }}>
        {yes     > 0 && <div style={{ width: `${(yes     / total) * 100}%`, background: CHOICE_COLOR[0] }} />}
        {no      > 0 && <div style={{ width: `${(no      / total) * 100}%`, background: CHOICE_COLOR[1] }} />}
        {abstain > 0 && <div style={{ width: `${(abstain / total) * 100}%`, background: CHOICE_COLOR[2] }} />}
      </div>
      <div style={{ display: 'flex', gap: '0.75rem', fontSize: '0.78rem' }}>
        <span style={{ color: CHOICE_COLOR[0] }}>Yes {yes}</span>
        <span style={{ color: CHOICE_COLOR[1] }}>No {no}</span>
        <span style={{ color: CHOICE_COLOR[2] }}>기권 {abstain}</span>
        <span style={{ color: '#888' }}>합계 {total}</span>
      </div>
    </div>
  )
}

export default function ProposalCard({ proposal, client, heliosReady, onVoted }: Props) {
  const [expanded, setExpanded] = useState(false)
  const creatorName = useENSName(proposal.creator, heliosReady)
  const isOpen = Date.now() < proposal.deadline * 1000

  return (
    <li style={{
      border: '1px solid #ddd',
      borderRadius: '4px',
      padding: '0.75rem 1rem',
      marginBottom: '0.6rem',
      background: '#fafafa',
    }}>
      {/* Header row */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '0.5rem' }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
            <span
              style={{
                fontSize: '0.7rem',
                padding: '0.1rem 0.45rem',
                borderRadius: '10px',
                background: isOpen ? '#e8f5e9' : '#f5f5f5',
                color: isOpen ? '#2a6' : '#888',
                border: `1px solid ${isOpen ? '#4caf50' : '#ccc'}`,
                whiteSpace: 'nowrap',
              }}
            >
              {isOpen ? '진행 중' : '종료'}
            </span>
            <span style={{ fontSize: '0.75rem', color: '#888' }}>#{proposal.id}</span>
          </div>
          <div style={{ fontWeight: 'bold', fontSize: '0.95rem', marginTop: '0.25rem', wordBreak: 'break-word' }}>
            {proposal.title}
          </div>
          <div style={{ fontSize: '0.78rem', color: '#888', marginTop: '0.2rem' }}>
            제안자: {creatorName ?? formatAddress(proposal.creator)}
            {' · '}
            마감: {formatDeadline(proposal.deadline)}
          </div>
        </div>
        <button
          onClick={() => setExpanded((v) => !v)}
          style={{ fontSize: '0.8rem', padding: '0.2rem 0.5rem', background: '#eee', color: '#333', whiteSpace: 'nowrap' }}
        >
          {expanded ? '접기' : '펼치기'}
        </button>
      </div>

      {/* Vote bar — always visible */}
      <div style={{ marginTop: '0.6rem' }}>
        <VoteBar yes={proposal.yesVotes} no={proposal.noVotes} abstain={proposal.abstainVotes} />
      </div>

      {/* Expanded content */}
      {expanded && (
        <div style={{ marginTop: '0.75rem', paddingTop: '0.75rem', borderTop: '1px solid #eee' }}>
          {proposal.description ? (
            <pre style={{ margin: '0 0 0.75rem', fontFamily: 'monospace', fontSize: '0.85rem', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
              {proposal.description}
            </pre>
          ) : (
            <p style={{ margin: '0 0 0.75rem', color: '#aaa', fontSize: '0.85rem', fontStyle: 'italic' }}>설명 없음</p>
          )}
          <VotePanel proposal={proposal} client={client} onVoted={onVoted} />
        </div>
      )}
    </li>
  )
}
