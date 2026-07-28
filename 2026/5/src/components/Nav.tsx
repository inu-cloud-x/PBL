export type Tab = 'data' | 'ens' | 'vote' | 'vc'

type Props = {
  tab: Tab
  onTabChange: (tab: Tab) => void
}

const TABS: { id: Tab; label: string }[] = [
  { id: 'data', label: '데이터' },
  { id: 'ens',  label: 'ENS 이름' },
  { id: 'vote', label: '투표' },
  { id: 'vc',   label: 'VC' },
]

export default function Nav({ tab, onTabChange }: Props) {
  return (
    <nav style={{ display: 'flex', gap: '0.25rem', borderBottom: '1px solid #ddd', marginBottom: '1.5rem' }}>
      {TABS.map(({ id, label }) => (
        <button
          key={id}
          onClick={() => onTabChange(id)}
          style={{
            padding: '0.4rem 1rem',
            fontFamily: 'monospace',
            fontSize: '0.9rem',
            border: '1px solid #ddd',
            borderBottom: tab === id ? '1px solid #fff' : '1px solid #ddd',
            borderRadius: '4px 4px 0 0',
            background: tab === id ? '#fff' : '#f5f5f5',
            color: tab === id ? '#000' : '#555',
            cursor: 'pointer',
            position: 'relative',
            top: '1px',
          }}
        >
          {label}
        </button>
      ))}
    </nav>
  )
}
