import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from './App.tsx'
import { PLAY_TEXT } from './playSettings.ts'

function renderAt(path: string): void {
  render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('App routing', () => {
  it('shows the teacher screen at /', () => {
    renderAt('/')

    expect(screen.getByRole('heading', { level: 1, name: 'משחק למידה' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 2, name: 'יצירת משחק חדש' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'צור משחק' })).toBeInTheDocument()
  })

  it('shows the play screen for /play/:gameId and loads that game', async () => {
    const questions = [{ id: 1, prompt: '1 + 1', options: ['2', '3'] }]
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => questions })
    vi.stubGlobal('fetch', fetchMock)

    renderAt('/play/7')

    expect(await screen.findByRole('heading', { name: PLAY_TEXT.title })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'צור משחק' })).not.toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith('/api/games/7/questions', undefined)
  })
})
