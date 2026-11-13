import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import App from './App.tsx'

describe('App', () => {
  it('shows the main heading', () => {
    render(<App />)

    expect(screen.getByRole('heading', { level: 1, name: 'משחק למידה' })).toBeInTheDocument()
  })

  it('shows the create-game screen', () => {
    render(<App />)

    expect(screen.getByRole('heading', { level: 2, name: 'יצירת משחק חדש' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'צור משחק' })).toBeInTheDocument()
  })
})
