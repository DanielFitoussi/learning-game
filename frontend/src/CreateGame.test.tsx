import { act, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { MESSAGES } from './api.ts'
import CreateGame from './CreateGame.tsx'
import {
  LOADING_TEXT,
  MODE_LEGEND,
  MODE_OPTIONS,
  STATUS_INTERVAL_MS,
  STATUS_LINES,
} from './createGameSettings.ts'

function fakeResponse(status: number, body: unknown = {}): Response {
  return { ok: status >= 200 && status < 300, status, json: async () => body } as Response
}

function renderCreateGame(): void {
  render(
    <MemoryRouter>
      <CreateGame />
    </MemoryRouter>,
  )
}

/** The radio button of a mode, found by its visible name ("תרגול" / "מבחן"). */
function modeRadio(label: string): HTMLElement {
  return screen.getByRole('radio', { name: new RegExp(`^${label}`) })
}

/** Fill the text fields only; the mode is picked separately. */
function fillFields(): void {
  fireEvent.change(screen.getByLabelText('נושא'), { target: { value: 'מדעים' } })
  fireEvent.change(screen.getByLabelText('פרק'), { target: { value: 'מחזור המים' } })
  fireEvent.change(screen.getByLabelText('כיתה'), { target: { value: '2' } })
  fireEvent.change(screen.getByLabelText('מספר שאלות'), { target: { value: '3' } })
  fireEvent.change(screen.getByLabelText('חומר הלימוד'), {
    target: { value: 'המים מתאדים מהים ויורדים כגשם.' },
  })
}

function fillForm(modeLabel = 'מבחן'): void {
  fillFields()
  fireEvent.click(modeRadio(modeLabel))
}

function submit(): void {
  fireEvent.click(screen.getByRole('button', { name: 'צור משחק' }))
}

afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

describe('CreateGame', () => {
  it('sends what the teacher typed and the chosen mode, with the grade as a number', async () => {
    const fetchMock = vi.fn().mockResolvedValue(fakeResponse(201, { game_id: 1, question_count: 3, rejected: 0 }))
    vi.stubGlobal('fetch', fetchMock)
    renderCreateGame()

    fillForm()
    submit()

    await screen.findByText('המשחק מוכן! 🎉')
    const body = JSON.parse(fetchMock.mock.calls[0][1].body as string)
    expect(body).toEqual({
      subject: 'מדעים',
      chapter: 'מחזור המים',
      grade: 2,
      mode: 'test',
      material: 'המים מתאדים מהים ויורדים כגשם.',
      count: 3,
    })
  })

  it('sends "learning" when the practice mode is picked', async () => {
    const fetchMock = vi.fn().mockResolvedValue(fakeResponse(201, { game_id: 1, question_count: 3, rejected: 0 }))
    vi.stubGlobal('fetch', fetchMock)
    renderCreateGame()

    fillForm('תרגול')
    submit()

    await screen.findByText('המשחק מוכן! 🎉')
    expect(JSON.parse(fetchMock.mock.calls[0][1].body as string)).toMatchObject({ mode: 'learning' })
  })

  it('keeps the create button disabled until a mode is picked', () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    renderCreateGame()

    fillFields()
    expect(modeRadio('תרגול')).not.toBeChecked()
    expect(modeRadio('מבחן')).not.toBeChecked()
    expect(screen.getByRole('button', { name: 'צור משחק' })).toBeDisabled()
    submit()
    expect(fetchMock).not.toHaveBeenCalled()

    fireEvent.click(modeRadio('תרגול'))
    expect(screen.getByRole('button', { name: 'צור משחק' })).toBeEnabled()
  })

  it('shows the two modes as one group, each with its explanation', () => {
    renderCreateGame()

    expect(screen.getByRole('group', { name: MODE_LEGEND })).toBeInTheDocument()
    for (const option of MODE_OPTIONS) {
      expect(screen.getByText(option.hint)).toBeInTheDocument()
      expect(modeRadio(option.label)).toHaveAccessibleDescription(option.hint)
    }
  })

  it('disables the button and shows the loading text while waiting', () => {
    vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>(() => {})))
    renderCreateGame()

    fillForm()
    submit()

    expect(screen.getByRole('button', { name: 'צור משחק' })).toBeDisabled()
    expect(screen.getByText(LOADING_TEXT)).toBeInTheDocument()
  })

  it('changes the status line every few seconds while waiting', () => {
    vi.useFakeTimers()
    vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>(() => {})))
    renderCreateGame()

    fillForm()
    submit()
    expect(screen.getByText(STATUS_LINES[0])).toBeInTheDocument()

    act(() => {
      vi.advanceTimersByTime(STATUS_INTERVAL_MS)
    })
    expect(screen.getByText(STATUS_LINES[1])).toBeInTheDocument()
  })

  it('shows the game number and question count on success', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(fakeResponse(201, { game_id: 42, question_count: 3, rejected: 0 })),
    )
    renderCreateGame()

    fillForm()
    submit()

    expect(await screen.findByText('42')).toBeInTheDocument()
    expect(screen.getByText('נוצרו 3 שאלות.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'צור משחק' })).toBeEnabled()
    expect(screen.queryByText(LOADING_TEXT)).not.toBeInTheDocument()
  })

  it.each([
    ['bad input (422)', () => Promise.resolve(fakeResponse(422)), MESSAGES.badInput],
    ['AI failure (502)', () => Promise.resolve(fakeResponse(502)), MESSAGES.generationFailed],
    ['proxy with no backend (500)', () => Promise.resolve(fakeResponse(500)), MESSAGES.serverDown],
    ['network error', () => Promise.reject(new TypeError('Failed to fetch')), MESSAGES.serverDown],
  ])('shows the message for %s and keeps what was typed', async (_name, respond, message) => {
    vi.stubGlobal('fetch', vi.fn(respond))
    renderCreateGame()

    fillForm()
    submit()

    expect(await screen.findByRole('alert')).toHaveTextContent(message)
    expect(screen.getByLabelText('נושא')).toHaveValue('מדעים')
    expect(screen.getByLabelText('פרק')).toHaveValue('מחזור המים')
    expect(screen.getByLabelText('כיתה')).toHaveValue('2')
    expect(screen.getByLabelText('מספר שאלות')).toHaveValue('3')
    expect(screen.getByLabelText('חומר הלימוד')).toHaveValue('המים מתאדים מהים ויורדים כגשם.')
    expect(modeRadio('מבחן')).toBeChecked()
    expect(screen.getByRole('button', { name: 'צור משחק' })).toBeEnabled()
  })

  it('counts the characters in the material', () => {
    renderCreateGame()

    fireEvent.change(screen.getByLabelText('חומר הלימוד'), { target: { value: 'שלום' } })

    expect(screen.getByText('4 / 20,000 תווים')).toBeInTheDocument()
  })

  it('links to the play screen of the new game', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(fakeResponse(201, { game_id: 42, question_count: 3, rejected: 0 })),
    )
    renderCreateGame()

    fillForm()
    submit()

    expect(await screen.findByRole('link', { name: 'למשחק' })).toHaveAttribute('href', '/play/42')
  })

  it('copies the full play link', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    vi.stubGlobal('navigator', { ...navigator, clipboard: { writeText } })
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(fakeResponse(201, { game_id: 42, question_count: 3, rejected: 0 })),
    )
    renderCreateGame()

    fillForm()
    submit()
    fireEvent.click(await screen.findByRole('button', { name: 'העתק קישור' }))

    expect(await screen.findByText('הקישור הועתק!')).toBeInTheDocument()
    expect(writeText).toHaveBeenCalledWith(`${window.location.origin}/play/42`)
  })

  it('shows the link when copying fails', async () => {
    const writeText = vi.fn().mockRejectedValue(new Error('denied'))
    vi.stubGlobal('navigator', { ...navigator, clipboard: { writeText } })
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(fakeResponse(201, { game_id: 42, question_count: 3, rejected: 0 })),
    )
    renderCreateGame()

    fillForm()
    submit()
    fireEvent.click(await screen.findByRole('button', { name: 'העתק קישור' }))

    expect(await screen.findByText(`${window.location.origin}/play/42`)).toBeInTheDocument()
  })
})
