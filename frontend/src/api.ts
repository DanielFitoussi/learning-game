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

export const MESSAGES = {
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
  if (status === 422) return MESSAGES.badInput
  if (status === 502) return MESSAGES.generationFailed
  // When the backend is not running, the Vite dev proxy answers with a 500.
  if (status === 500) return MESSAGES.serverDown
  return MESSAGES.unknown
}

/** Ask the backend to generate questions from the material and save a new game. */
export async function createGame(request: CreateGameRequest): Promise<CreateGameResponse> {
  let response: Response
  try {
    response = await fetch('/api/games', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
    })
  } catch {
    throw new ApiError(MESSAGES.serverDown, null)
  }

  if (!response.ok) {
    throw new ApiError(messageForStatus(response.status), response.status)
  }
  return (await response.json()) as CreateGameResponse
}
