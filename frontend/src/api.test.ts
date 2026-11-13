import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  ApiError,
  MESSAGES,
  createGame,
  getQuestions,
  messageForStatus,
  sendAnswer,
  startSession,
  type CreateGameRequest,
} from './api.ts'

const REQUEST: CreateGameRequest = {
  subject: 'מדעים',
  chapter: 'מחזור המים',
  grade: 2,
  material: 'המים מתאדים מהים ויורדים כגשם.',
  count: 5,
}

function fakeResponse(status: number, body: unknown = {}): Response {
  return { ok: status >= 200 && status < 300, status, json: async () => body } as Response
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('messageForStatus', () => {
  it.each([
    [422, MESSAGES.badInput],
    [502, MESSAGES.generationFailed],
    [500, MESSAGES.serverDown],
    [404, MESSAGES.gameNotFound],
    [418, MESSAGES.unknown],
  ])('maps %i to its Hebrew message', (status, message) => {
    expect(messageForStatus(status)).toBe(message)
  })
})

describe('createGame', () => {
  it('posts the request to /api/games and returns the new game', async () => {
    const body = { game_id: 7, question_count: 5, rejected: 0 }
    const fetchMock = vi.fn().mockResolvedValue(fakeResponse(201, body))
    vi.stubGlobal('fetch', fetchMock)

    await expect(createGame(REQUEST)).resolves.toEqual(body)

    expect(fetchMock).toHaveBeenCalledWith('/api/games', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(REQUEST),
    })
  })

  it.each([
    [422, MESSAGES.badInput],
    [502, MESSAGES.generationFailed],
    [500, MESSAGES.serverDown],
  ])('throws an ApiError for status %i', async (status, message) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(fakeResponse(status)))

    const error = await createGame(REQUEST).catch((e: unknown) => e)

    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({ message, status })
  })

  it('throws the server-down message when the server cannot be reached', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))

    await expect(createGame(REQUEST)).rejects.toThrow(MESSAGES.serverDown)
  })
})

describe('startSession', () => {
  it('posts the name and mode to the game and returns the session', async () => {
    const fetchMock = vi.fn().mockResolvedValue(fakeResponse(201, { session_id: 3 }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(startSession(7, 'נועה', 'learning')).resolves.toEqual({ session_id: 3 })

    expect(fetchMock).toHaveBeenCalledWith('/api/games/7/sessions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ player_name: 'נועה', mode: 'learning' }),
    })
  })

  it('throws the not-found message for a missing game', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(fakeResponse(404)))

    await expect(startSession(99, 'נועה', 'learning')).rejects.toThrow(MESSAGES.gameNotFound)
  })
})

describe('getQuestions', () => {
  it('gets the questions of the game', async () => {
    const questions = [{ id: 1, prompt: '2 + 2', options: ['4', '5'] }]
    const fetchMock = vi.fn().mockResolvedValue(fakeResponse(200, questions))
    vi.stubGlobal('fetch', fetchMock)

    await expect(getQuestions(7)).resolves.toEqual(questions)

    expect(fetchMock).toHaveBeenCalledWith('/api/games/7/questions', undefined)
  })

  it('throws the not-found message for a missing game', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(fakeResponse(404)))

    await expect(getQuestions(99)).rejects.toThrow(MESSAGES.gameNotFound)
  })

  it('throws the server-down message when the server cannot be reached', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))

    await expect(getQuestions(7)).rejects.toThrow(MESSAGES.serverDown)
  })
})

describe('sendAnswer', () => {
  it('posts the answer with snake_case fields and returns whether it was right', async () => {
    const fetchMock = vi.fn().mockResolvedValue(fakeResponse(201, { is_correct: true }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(sendAnswer(3, 11, '4', 2500)).resolves.toEqual({ is_correct: true })

    expect(fetchMock).toHaveBeenCalledWith('/api/sessions/3/answers', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question_id: 11, chosen_text: '4', time_ms: 2500 }),
    })
  })

  it('keeps the status on the error so callers can spot a 409', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(fakeResponse(409)))

    const error = await sendAnswer(3, 11, '4', 2500).catch((e: unknown) => e)

    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({ status: 409 })
  })
})
