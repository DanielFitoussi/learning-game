import { act, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MESSAGES, type PlayQuestion } from './api.ts'
import PlayGame from './PlayGame.tsx'
import { FEEDBACK, FEEDBACK_MS, PLAY_TEXT, finishedText, progressText } from './playSettings.ts'

const QUESTIONS: PlayQuestion[] = [
  { id: 11, prompt: '2 + 2', options: ['4', '5', '6'] },
  { id: 12, prompt: '5 - 3', options: ['2', '1', '3'] },
]

/** The answer key of the fake backend. */
const CORRECT: Record<number, string> = { 11: '4', 12: '2' }

function fakeResponse(status: number, body: unknown = {}): Response {
  return { ok: status >= 200 && status < 300, status, json: async () => body } as Response
}

type Handler = (url: string, init?: RequestInit) => Promise<Response>

/** A fake backend for questions, sessions and answers, with optional overrides. */
function fakeBackend(overrides: { answer?: Handler; questions?: Handler } = {}) {
  return vi.fn(async (url: string, init?: RequestInit): Promise<Response> => {
    if (url.endsWith('/questions')) {
      return overrides.questions ? overrides.questions(url, init) : fakeResponse(200, QUESTIONS)
    }
    if (url.endsWith('/sessions')) return fakeResponse(201, { session_id: 5 })
    if (url.endsWith('/answers')) {
      if (overrides.answer) return overrides.answer(url, init)
      const body = JSON.parse(init?.body as string)
      return fakeResponse(201, { is_correct: CORRECT[body.question_id] === body.chosen_text })
    }
    throw new Error(`unexpected ${url}`)
  })
}

function renderPlay(gameId = '7'): void {
  render(
    <MemoryRouter initialEntries={[`/play/${gameId}`]}>
      <Routes>
        <Route path="/play/:gameId" element={<PlayGame />} />
      </Routes>
    </MemoryRouter>,
  )
}

async function startAs(name: string): Promise<void> {
  fireEvent.change(await screen.findByLabelText(PLAY_TEXT.nameLabel), { target: { value: name } })
  fireEvent.click(screen.getByRole('button', { name: PLAY_TEXT.start }))
  await screen.findByText(progressText(1, QUESTIONS.length))
}

function optionTexts(): string[] {
  return screen
    .getAllByRole('button')
    .filter((b) => b.classList.contains('option-button'))
    .map((b) => b.textContent ?? '')
}

function answerCalls(fetchMock: ReturnType<typeof fakeBackend>) {
  return fetchMock.mock.calls.filter(([url]) => String(url).endsWith('/answers'))
}

/** Click an option, wait for the reply, then skip the feedback pause. */
async function answer(text: string, feedback: string): Promise<void> {
  fireEvent.click(screen.getByRole('button', { name: text }))
  await screen.findByText(feedback)
  act(() => {
    vi.advanceTimersByTime(FEEDBACK_MS)
  })
}

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true })
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('PlayGame', () => {
  it('starts a learning session with the trimmed name', async () => {
    const fetchMock = fakeBackend()
    vi.stubGlobal('fetch', fetchMock)
    renderPlay()

    await startAs('  נועה ')

    const call = fetchMock.mock.calls.find(([url]) => String(url).endsWith('/sessions'))!
    expect(call[0]).toBe('/api/games/7/sessions')
    expect(JSON.parse(call[1]!.body as string)).toEqual({ player_name: 'נועה', mode: 'learning' })
  })

  it('keeps the start button disabled until a name is typed', async () => {
    vi.stubGlobal('fetch', fakeBackend())
    renderPlay()

    expect(await screen.findByRole('button', { name: PLAY_TEXT.start })).toBeDisabled()
    fireEvent.change(screen.getByLabelText(PLAY_TEXT.nameLabel), { target: { value: '   ' } })
    expect(screen.getByRole('button', { name: PLAY_TEXT.start })).toBeDisabled()
  })

  it('shows the questions in order with shuffled options', async () => {
    // random() = 0 turns [a, b, c] into [b, c, a].
    vi.spyOn(Math, 'random').mockReturnValue(0)
    vi.stubGlobal('fetch', fakeBackend())
    renderPlay()
    await startAs('נועה')

    expect(screen.getByRole('heading', { name: '2 + 2' })).toBeInTheDocument()
    expect(optionTexts()).toEqual(['5', '6', '4'])

    await answer('4', FEEDBACK.correct)

    expect(screen.getByText(progressText(2, 2))).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '5 - 3' })).toBeInTheDocument()
    expect(optionTexts()).toEqual(['1', '3', '2'])
  })

  it('shows option text with dir="auto" so English reads left to right', async () => {
    vi.stubGlobal('fetch', fakeBackend())
    renderPlay()
    await startAs('נועה')

    expect(screen.getByRole('button', { name: '4' })).toHaveAttribute('dir', 'auto')
  })

  it('sends the answer with the time since the question was shown', async () => {
    const fetchMock = fakeBackend()
    vi.stubGlobal('fetch', fetchMock)
    const now = vi.spyOn(performance, 'now').mockReturnValue(1000)
    renderPlay()
    await startAs('נועה')

    now.mockReturnValue(3400)
    fireEvent.click(screen.getByRole('button', { name: '5' }))
    await screen.findByText(FEEDBACK.wrong)

    const [url, init] = answerCalls(fetchMock)[0]
    expect(url).toBe('/api/sessions/5/answers')
    expect(JSON.parse(init!.body as string)).toEqual({ question_id: 11, chosen_text: '5', time_ms: 2400 })
  })

  it('sends only one answer on a double click', async () => {
    const fetchMock = fakeBackend()
    vi.stubGlobal('fetch', fetchMock)
    renderPlay()
    await startAs('נועה')

    const button = screen.getByRole('button', { name: '4' })
    fireEvent.click(button)
    fireEvent.click(button)
    fireEvent.click(screen.getByRole('button', { name: '5' }))

    await screen.findByText(FEEDBACK.correct)
    expect(answerCalls(fetchMock)).toHaveLength(1)
    for (const text of ['4', '5', '6']) {
      expect(screen.getByRole('button', { name: text })).toBeDisabled()
    }
  })

  it('shows how many answers were right at the end', async () => {
    vi.stubGlobal('fetch', fakeBackend())
    renderPlay()
    await startAs('נועה')

    await answer('4', FEEDBACK.correct)
    await answer('3', FEEDBACK.wrong)

    expect(screen.getByText(finishedText(1, 2))).toBeInTheDocument()
  })

  it('moves on without an error when the answer was already saved (409)', async () => {
    vi.stubGlobal('fetch', fakeBackend({ answer: async () => fakeResponse(409) }))
    renderPlay()
    await startAs('נועה')

    fireEvent.click(screen.getByRole('button', { name: '4' }))

    expect(await screen.findByText(progressText(2, 2))).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '2' })).toBeEnabled()
  })

  it('shows an error and lets the child try again when sending fails', async () => {
    let fail = true
    vi.stubGlobal(
      'fetch',
      fakeBackend({
        answer: async () => {
          if (fail) throw new TypeError('Failed to fetch')
          return fakeResponse(201, { is_correct: true })
        },
      }),
    )
    renderPlay()
    await startAs('נועה')

    fireEvent.click(screen.getByRole('button', { name: '4' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(MESSAGES.serverDown)
    expect(screen.getByText(progressText(1, 2))).toBeInTheDocument()

    fail = false
    fireEvent.click(screen.getByRole('button', { name: '4' }))
    expect(await screen.findByText(FEEDBACK.correct)).toBeInTheDocument()
  })

  it('shows the not-found message for a missing game', async () => {
    vi.stubGlobal('fetch', fakeBackend({ questions: async () => fakeResponse(404) }))
    renderPlay('99')

    expect(await screen.findByRole('alert')).toHaveTextContent(MESSAGES.gameNotFound)
    expect(screen.queryByLabelText(PLAY_TEXT.nameLabel)).not.toBeInTheDocument()
  })

  it('shows the not-found message for a game ID that is not a number', async () => {
    const fetchMock = fakeBackend()
    vi.stubGlobal('fetch', fetchMock)
    renderPlay('abc')

    expect(await screen.findByRole('alert')).toHaveTextContent(MESSAGES.gameNotFound)
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('hides the read-aloud button and still plays when the browser has no speech', async () => {
    // jsdom has no speechSynthesis.
    vi.stubGlobal('fetch', fakeBackend())
    renderPlay()
    await startAs('נועה')

    expect(screen.queryByRole('button', { name: PLAY_TEXT.readAloud })).not.toBeInTheDocument()
    await answer('4', FEEDBACK.correct)
    expect(screen.getByText(progressText(2, 2))).toBeInTheDocument()
  })

  it('reads the question aloud in Hebrew when speech exists', async () => {
    const synth = { speak: vi.fn(), cancel: vi.fn() }
    vi.stubGlobal('speechSynthesis', synth)
    vi.stubGlobal(
      'SpeechSynthesisUtterance',
      class {
        text: string
        lang = ''
        constructor(text: string) {
          this.text = text
        }
      },
    )
    vi.stubGlobal('fetch', fakeBackend())
    renderPlay()
    await startAs('נועה')

    fireEvent.click(screen.getByRole('button', { name: PLAY_TEXT.readAloud }))

    expect(synth.speak).toHaveBeenCalledWith(expect.objectContaining({ text: '2 ועוד 2', lang: 'he-IL' }))
  })

  it('shows math in the prompt left to right, with the Hebrew and "?" outside', async () => {
    vi.stubGlobal(
      'fetch',
      fakeBackend({
        questions: async () => fakeResponse(200, [{ id: 21, prompt: 'כמה הם 16 - 7?', options: ['9', '8'] }]),
      }),
    )
    renderPlay()
    fireEvent.change(await screen.findByLabelText(PLAY_TEXT.nameLabel), { target: { value: 'נועה' } })
    fireEvent.click(screen.getByRole('button', { name: PLAY_TEXT.start }))

    const heading = await screen.findByRole('heading', { name: 'כמה הם 16 - 7?' })
    const bdi = heading.querySelector('bdi')
    expect(bdi).toHaveAttribute('dir', 'ltr')
    expect(bdi).toHaveTextContent(/^16 - 7$/)
  })

  it('keeps a trailing "= ?" inside the left-to-right part', async () => {
    vi.stubGlobal(
      'fetch',
      fakeBackend({
        questions: async () => fakeResponse(200, [{ id: 22, prompt: 'פִּתְרוּ: 7 + 5 = ?', options: ['12', '11'] }]),
      }),
    )
    renderPlay()
    fireEvent.change(await screen.findByLabelText(PLAY_TEXT.nameLabel), { target: { value: 'נועה' } })
    fireEvent.click(screen.getByRole('button', { name: PLAY_TEXT.start }))

    const heading = await screen.findByRole('heading', { name: 'פִּתְרוּ: 7 + 5 = ?' })
    expect(heading.querySelector('bdi')).toHaveTextContent(/^7 \+ 5 = \?$/)
  })
})
