import { useState, useEffect } from 'react'
import { votingVote, votingHasVoted, Choice, CHOICE_LABEL, CHOICE_COLOR, type Proposal, type ChoiceValue } from '../lib/voting'
import type { SmartWalletClient } from '../lib/wallet'

type Props = {
  proposal: Proposal
  client: SmartWalletClient
  onVoted: () => void
}

export default function VotePanel({ proposal, client, onVoted }: Props) {
  // undefined = loading, null = not voted, 0|1|2 = already voted with this choice
  const [myVote,   setMyVote]   = useState<ChoiceValue | null | undefined>(undefined)
  const [loading,  setLoading]  = useState(false)
  const [status,   setStatus]   = useState('')
  const [error,    setError]    = useState('')

  const isOpen = Date.now() < proposal.deadline * 1000
  const voter  = client.account.address

  useEffect(() => {
    let cancelled = false
    votingHasVoted(proposal.id, voter)
      .then((voted) => {
        if (cancelled) return
        // We know they voted but not which choice — show null to allow button display
        // hasVoted only returns bool; the choice is inferred from contract events (out of scope for PoC)
        setMyVote(voted ? -1 as unknown as ChoiceValue : null)
      })
      .catch(() => {
        if (!cancelled) setMyVote(null) // on error, assume not voted — contract will reject if wrong
      })
    return () => { cancelled = true }
  }, [proposal.id, voter])

  async function handleVote(choice: ChoiceValue) {
    if (loading) return
    setError('')
    setStatus('Passkey로 서명 중...')
    setLoading(true)
    try {
      await votingVote(client, proposal.id, choice)
      setStatus('')
      setMyVote(choice)
      onVoted()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      setStatus('')
    } finally {
      setLoading(false)
    }
  }

  if (myVote === undefined) {
    return <p style={{ fontSize: '0.8rem', color: '#888', margin: '0.5rem 0 0' }}>투표 내역 확인 중...</p>
  }

  // Already voted (hasVoted = true, choice unknown)
  if ((myVote as unknown as number) === -1) {
    return (
      <p style={{ fontSize: '0.85rem', color: '#2a6', margin: '0.75rem 0 0' }}>
        이미 투표했습니다.
      </p>
    )
  }

  // Voted in this session (choice is known)
  if (myVote !== null) {
    return (
      <p style={{ fontSize: '0.85rem', color: '#2a6', margin: '0.75rem 0 0' }}>
        내 투표:{' '}
        <strong style={{ color: CHOICE_COLOR[myVote] }}>{CHOICE_LABEL[myVote]}</strong>
      </p>
    )
  }

  // Not yet voted
  if (!isOpen) {
    return <p style={{ fontSize: '0.8rem', color: '#888', margin: '0.75rem 0 0' }}>투표가 마감되었습니다.</p>
  }

  return (
    <div style={{ marginTop: '0.75rem' }}>
      <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
        {([Choice.Yes, Choice.No, Choice.Abstain] as ChoiceValue[]).map((choice) => (
          <button
            key={choice}
            onClick={() => handleVote(choice)}
            disabled={loading}
            style={{
              padding: '0.3rem 0.9rem',
              border: `1px solid ${CHOICE_COLOR[choice]}`,
              color: CHOICE_COLOR[choice],
              background: '#fff',
              fontSize: '0.85rem',
              borderRadius: '4px',
            }}
          >
            {loading ? '...' : CHOICE_LABEL[choice]}
          </button>
        ))}
      </div>
      {status && <p style={{ fontSize: '0.8rem', color: '#888', marginTop: '0.4rem' }}>{status}</p>}
      {error  && <p style={{ fontSize: '0.8rem', color: '#c33', marginTop: '0.4rem' }}>오류: {error}</p>}
    </div>
  )
}
