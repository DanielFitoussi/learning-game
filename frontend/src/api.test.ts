import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, MESSAGES, createGame, messageForStatus, type CreateGameRequest } from './api.ts'

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
    [404, MESSAGES.unknown],
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
