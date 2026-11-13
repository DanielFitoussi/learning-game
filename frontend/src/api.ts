// Calls to the backend. In development Vite forwards /api/... to the backend.

export type Grade = 1 | 2 | 3

export type CreateGameRequest = {
  subject: string
  chapter: string
  grade: Grade
  material: string
  count: number
}

export type CreateGameResponse = {
  game_id: number
  question_count: number
  rejected: number
}

export type PlayMode = 'learning' | 'test'

export type StartSessionResponse = {
  session_id: number
}

/** A question as the child sees it: option texts only, never which is correct. */
export type PlayQuestion = {
  id: number
  prompt: string
  options: string[]
}

export type AnswerResponse = {
  is_correct: boolean
}

export const MESSAGES = {
  gameNotFound: 'המשחק לא נמצא',
  badInput: 'חלק מהפרטים חסרים או לא תקינים. בדקו את הטופס ונסו שוב.',
  generationFailed: 'לא הצלחנו ליצור שאלות מהחומר. נסו שוב בעוד רגע.',
  serverDown: 'אין חיבור לשרת. ודאו שהשרת פועל ונסו שוב.',
  unknown: 'משהו השתבש. נסו שוב.',
} as const

/** An error whose message is short, in Hebrew, and safe to show to a teacher. */
export class ApiError extends Error {
  readonly status: number | null

  constructor(message: string, status: number | null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

/** The Hebrew message for a failed HTTP status. */
export function messageForStatus(status: number): string {
  if (status === 404) return MESSAGES.gameNotFound
  if (status === 422) return MESSAGES.badInput
  if (status === 502) return MESSAGES.generationFailed
  // When the backend is not running, the Vite dev proxy answers with a 500.
  if (status === 500) return MESSAGES.serverDown
  return MESSAGES.unknown
}

/** Fetch a JSON endpoint; any failure becomes an ApiError with a Hebrew message. */
async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(url, init)
  } catch {
    throw new ApiError(MESSAGES.serverDown, null)
  }

  if (!response.ok) {
    throw new ApiError(messageForStatus(response.status), response.status)
  }
  return (await response.json()) as T
}

function postJson<T>(url: string, body: unknown): Promise<T> {
  return requestJson<T>(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

/** Ask the backend to generate questions from the material and save a new game. */
export function createGame(request: CreateGameRequest): Promise<CreateGameResponse> {
  return postJson<CreateGameResponse>('/api/games', request)
}

/** Start a session of one child playing one game. */
export function startSession(
  gameId: number,
  playerName: string,
  mode: PlayMode,
): Promise<StartSessionResponse> {
  return postJson<StartSessionResponse>(`/api/games/${gameId}/sessions`, {
    player_name: playerName,
    mode,
  })
}

/** The game's questions, in order. */
export function getQuestions(gameId: number): Promise<PlayQuestion[]> {
  return requestJson<PlayQuestion[]>(`/api/games/${gameId}/questions`)
}

/** Save the child's answer to one question. */
export function sendAnswer(
  sessionId: number,
  questionId: number,
  chosenText: string,
  timeMs: number,
): Promise<AnswerResponse> {
  return postJson<AnswerResponse>(`/api/sessions/${sessionId}/answers`, {
    question_id: questionId,
    chosen_text: chosenText,
    time_ms: timeMs,
  })
}
