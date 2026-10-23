import { useState } from 'react'

export function App() {
  const [count, setCount] = useState(0)

  return (
    <div style={{
      maxWidth: '600px',
      margin: '0 auto',
      padding: '2.5rem',
      borderRadius: '16px',
      background: 'rgba(255, 255, 255, 0.03)',
      border: '1px solid rgba(255, 255, 255, 0.08)',
      boxShadow: '0 20px 40px rgba(0, 0, 0, 0.4)',
      backdropFilter: 'blur(10px)',
    }}>
      <h1 style={{
        fontSize: '2.5rem',
        margin: '0 0 0.5rem',
        background: 'linear-gradient(135deg, #60a5fa 0%, #a855f7 100%)',
        WebkitBackgroundClip: 'text',
        WebkitTextFillColor: 'transparent',
      }}>
        Nexus
      </h1>
      <p style={{ color: '#94a3b8', fontSize: '1.1rem', margin: '0 0 2rem' }}>
        Next-generation full-stack platform
      </p>

      <button
        type="button"
        onClick={() => setCount((c) => c + 1)}
        style={{
          padding: '0.75rem 1.75rem',
          fontSize: '1rem',
          fontWeight: 600,
          color: '#ffffff',
          backgroundColor: '#3b82f6',
          border: 'none',
          borderRadius: '8px',
          cursor: 'pointer',
          transition: 'all 0.2s ease',
        }}
        onMouseOver={(e) => (e.currentTarget.style.backgroundColor = '#2563eb')}
        onMouseOut={(e) => (e.currentTarget.style.backgroundColor = '#3b82f6')}
      >
        Count is {count}
      </button>
    </div>
  )
}

export default App
