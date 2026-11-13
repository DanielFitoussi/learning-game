import { useEffect, useRef, useState, type FormEvent } from 'react'
import { useParams } from 'react-router-dom'
import { ApiError, MESSAGES, getQuestions, sendAnswer, startSession, type PlayQuestion } from './api.ts'
import {
  FEEDBACK,
  FEEDBACK_MS,
  PLAY_MODE,
  PLAY_TEXT,
  finishedText,
  progressText,
} from './playSettings.ts'
import { splitMath } from './mathText.ts'
import { shuffle } from './shuffle.ts'
import { canSpeak, speak } from './speech.ts'

type LoadState =
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'ready'; questions: PlayQuestion[] }

type Phase = 'name' | 'playing' | 'finished'

type Feedback = 'correct' | 'wrong' | null

/** A 409 means the server already has this answer (e.g. the first reply was lost). */
function isAlreadyAnswered(error: unknown): boolean {
  return error instanceof ApiError && error.status === 409
}

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : MESSAGES.unknown
}

/** The game ID from the URL, or null when it is not a positive whole number. */
function parseGameId(raw: string | undefined): number | null {
  const id = Number(raw)
  return Number.isInteger(id) && id > 0 ? id : null
}

function PlayGame() {
  const gameId = parseGameId(useParams().gameId)

  const [load, setLoad] = useState<LoadState>({ kind: 'loading' })
  const [phase, setPhase] = useState<Phase>('name')
  const [name, setName] = useState('')
  const [starting, setStarting] = useState(false)
  const [startError, setStartError] = useState<string | null>(null)
  const [sessionId, setSessionId] = useState<number | null>(null)
  const [index, setIndex] = useState(0)
  const [correctCount, setCorrectCount] = useState(0)
  const [locked, setLocked] = useState(false)
  const [feedback, setFeedback] = useState<Feedback>(null)
  const [answerError, setAnswerError] = useState<string | null>(null)
  const [speechAvailable] = useState(canSpeak)

  // A ref, not state, so a second click in the same moment is already blocked.
  const lockRef = useRef(false)
  const shownAtRef = useRef(0)
  const nextTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Load the questions as soon as the screen opens, so a wrong link shows at once.
  // The screen is keyed by game ID (see App.tsx), so this runs once per game.
  useEffect(() => {
    if (gameId === null) return
    let cancelled = false
    getQuestions(gameId)
      .then((questions) => {
        if (cancelled) return
        // Shuffle each question's options once, here, so re-renders never reorder them.
        const shuffled = questions.map((q) => ({ ...q, options: shuffle(q.options) }))
        setLoad({ kind: 'ready', questions: shuffled })
      })
      .catch((error: unknown) => {
        if (!cancelled) setLoad({ kind: 'error', message: errorMessage(error) })
      })
    return () => {
      cancelled = true
    }
  }, [gameId])

  // Start the clock whenever a new question appears.
  useEffect(() => {
    if (phase === 'playing') shownAtRef.current = performance.now()
  }, [phase, index])

  useEffect(() => {
    return () => {
      if (nextTimerRef.current !== null) clearTimeout(nextTimerRef.current)
    }
  }, [])

  if (gameId === null) {
    return (
      <section className="card play-card">
        <p role="alert" className="message message-error play-message">
          {MESSAGES.gameNotFound}
        </p>
      </section>
    )
  }

  if (load.kind === 'loading') {
    return (
      <section className="card play-card">
        <p role="status" className="play-loading">
          {PLAY_TEXT.loading}
        </p>
      </section>
    )
  }

  if (load.kind === 'error') {
    return (
      <section className="card play-card">
        <p role="alert" className="message message-error play-message">
          {load.message}
        </p>
      </section>
    )
  }

  const questions = load.questions
  const total = questions.length

  if (total === 0) {
    return (
      <section className="card play-card">
        <p className="play-message">{PLAY_TEXT.noQuestions}</p>
      </section>
    )
  }

  async function handleStart(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault()
    const playerName = name.trim()
    if (gameId === null || playerName === '' || starting) return
    setStarting(true)
    setStartError(null)
    try {
      const session = await startSession(gameId, playerName, PLAY_MODE)
      setSessionId(session.session_id)
      setPhase('playing')
    } catch (error) {
      setStartError(errorMessage(error))
    } finally {
      setStarting(false)
    }
  }

  function goToNextQuestion(): void {
    nextTimerRef.current = null
    setFeedback(null)
    if (index + 1 >= total) {
      setPhase('finished')
      return
    }
    setIndex(index + 1)
    lockRef.current = false
    setLocked(false)
  }

  async function handleAnswer(option: string): Promise<void> {
    if (lockRef.current || sessionId === null) return
    lockRef.current = true
    setLocked(true)
    setAnswerError(null)

    const timeMs = Math.max(0, Math.round(performance.now() - shownAtRef.current))
    try {
      const result = await sendAnswer(sessionId, questions[index].id, option, timeMs)
      if (result.is_correct) setCorrectCount((count) => count + 1)
      setFeedback(result.is_correct ? 'correct' : 'wrong')
      nextTimerRef.current = setTimeout(goToNextQuestion, FEEDBACK_MS)
    } catch (error) {
      if (isAlreadyAnswered(error)) {
        // Saved on an earlier try; we don't know if it was right, so no message.
        goToNextQuestion()
        return
      }
      setAnswerError(errorMessage(error))
      lockRef.current = false
      setLocked(false)
    }
  }

  if (phase === 'name') {
    return (
      <section className="card play-card" aria-labelledby="play-title">
        <h2 id="play-title" className="play-title">
          {PLAY_TEXT.title}
        </h2>
        <form className="play-name-form" onSubmit={handleStart}>
          <label htmlFor="player-name" className="play-label">
            {PLAY_TEXT.nameLabel}
          </label>
          <input
            id="player-name"
            type="text"
            className="play-input"
            autoComplete="off"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <button
            type="submit"
            className="primary-button play-start"
            disabled={name.trim() === '' || starting}
          >
            {PLAY_TEXT.start}
          </button>
        </form>
        {startError !== null && (
          <p role="alert" className="message message-error play-message">
            {startError}
          </p>
        )}
      </section>
    )
  }

  if (phase === 'finished') {
    return (
      <section className="card play-card play-finished">
        <p className="play-finished-text">{finishedText(correctCount, total)}</p>
      </section>
    )
  }

  const question = questions[index]

  return (
    <section className="card play-card" aria-labelledby="question-prompt">
      <p className="play-progress">{progressText(index + 1, total)}</p>
      <div className="play-question">
        <h2 id="question-prompt" className="play-prompt" dir="auto">
          <PromptText prompt={question.prompt} />
        </h2>
        {speechAvailable && (
          <button
            type="button"
            className="speak-button"
            aria-label={PLAY_TEXT.readAloud}
            onClick={() => speak(question.prompt)}
          >
            🔊
          </button>
        )}
      </div>

      <div className="play-options" key={question.id}>
        {question.options.map((option) => (
          <button
            key={option}
            type="button"
            className="option-button"
            dir="auto"
            disabled={locked}
            onClick={() => void handleAnswer(option)}
          >
            {option}
          </button>
        ))}
      </div>

      <div role="status" aria-live="polite" className="play-feedback-slot">
        {feedback !== null && (
          <p className={`play-feedback play-feedback-${feedback}`}>{FEEDBACK[feedback]}</p>
        )}
      </div>
      {answerError !== null && (
        <p role="alert" className="message message-error play-message">
          {answerError}
        </p>
      )}
    </section>
  )
}

/** The prompt, with each math expression kept left to right inside Hebrew text. */
function PromptText({ prompt }: { prompt: string }) {
  return (
    <>
      {splitMath(prompt).map((part, i) =>
        part.isMath ? (
          <bdi key={i} dir="ltr">
            {part.text}
          </bdi>
        ) : (
          part.text
        ),
      )}
    </>
  )
}

export default PlayGame
