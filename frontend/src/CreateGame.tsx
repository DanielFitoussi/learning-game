import { useEffect, useState, type CSSProperties, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { ApiError, MESSAGES, createGame, type CreateGameResponse, type Grade } from './api.ts'
import {
  LOADING_TEXT,
  MAX_MATERIAL_CHARS,
  STATUS_INTERVAL_MS,
  STATUS_LINES,
} from './createGameSettings.ts'

const QUESTION_COUNTS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
const DEFAULT_COUNT = 5

const GRADE_OPTIONS: { value: Grade; label: string }[] = [
  { value: 1, label: 'א' },
  { value: 2, label: 'ב' },
  { value: 3, label: 'ג' },
]

type Status =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'success'; result: CreateGameResponse }
  | { kind: 'error'; message: string }

function CreateGame() {
  const [subject, setSubject] = useState('')
  const [chapter, setChapter] = useState('')
  const [grade, setGrade] = useState<Grade>(1)
  const [count, setCount] = useState(DEFAULT_COUNT)
  const [material, setMaterial] = useState('')
  const [status, setStatus] = useState<Status>({ kind: 'idle' })

  const isLoading = status.kind === 'loading'

  async function handleSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault()
    setStatus({ kind: 'loading' })
    try {
      const result = await createGame({ subject, chapter, grade, material, count })
      setStatus({ kind: 'success', result })
    } catch (error) {
      const message = error instanceof ApiError ? error.message : MESSAGES.unknown
      setStatus({ kind: 'error', message })
    }
  }

  return (
    <section className="card" aria-labelledby="create-game-title">
      <h2 id="create-game-title">יצירת משחק חדש</h2>
      <p className="card-intro">הדביקו את חומר הלימוד, ואנחנו נהפוך אותו למשחק שאלות.</p>

      <form className="create-form" onSubmit={handleSubmit}>
        <div className="field-row">
          <div className="field">
            <label htmlFor="subject">נושא</label>
            <input
              id="subject"
              type="text"
              required
              placeholder="למשל: מדעים"
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="chapter">פרק</label>
            <input
              id="chapter"
              type="text"
              required
              placeholder="למשל: מחזור המים"
              value={chapter}
              onChange={(e) => setChapter(e.target.value)}
            />
          </div>
        </div>

        <div className="field-row">
          <div className="field">
            <label htmlFor="grade">כיתה</label>
            <select
              id="grade"
              value={grade}
              onChange={(e) => setGrade(Number(e.target.value) as Grade)}
            >
              {GRADE_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="count">מספר שאלות</label>
            <select id="count" value={count} onChange={(e) => setCount(Number(e.target.value))}>
              {QUESTION_COUNTS.map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="field">
          <label htmlFor="material">חומר הלימוד</label>
          <textarea
            id="material"
            required
            rows={10}
            maxLength={MAX_MATERIAL_CHARS}
            placeholder="הדביקו כאן את הטקסט שהתלמידים לומדים"
            value={material}
            onChange={(e) => setMaterial(e.target.value)}
            aria-describedby="material-counter"
          />
          <p id="material-counter" className="counter">
            {material.length.toLocaleString('en-US')} / {MAX_MATERIAL_CHARS.toLocaleString('en-US')}{' '}
            תווים
          </p>
        </div>

        <button type="submit" className="primary-button" disabled={isLoading}>
          צור משחק
        </button>
      </form>

      <div role="status" aria-live="polite">
        {isLoading && <MagicLoader />}
      </div>
      {status.kind === 'error' && (
        <p role="alert" className="message message-error">
          {status.message}
        </p>
      )}
      {status.kind === 'success' && <SuccessCard result={status.result} />}
    </section>
  )
}

/** A wand with sparkles and a status line that changes every few seconds. */
function MagicLoader() {
  const [lineIndex, setLineIndex] = useState(0)

  useEffect(() => {
    const timer = setInterval(() => {
      setLineIndex((index) => (index + 1) % STATUS_LINES.length)
    }, STATUS_INTERVAL_MS)
    return () => clearInterval(timer)
  }, [])

  return (
    <div className="loader">
      <svg className="wand" viewBox="0 0 64 64" width="64" height="64" aria-hidden="true">
        <rect
          x="8"
          y="38"
          width="40"
          height="7"
          rx="3.5"
          transform="rotate(-40 28 41)"
          fill="var(--wand)"
        />
        <rect
          x="38"
          y="38"
          width="10"
          height="7"
          rx="3.5"
          transform="rotate(-40 28 41)"
          fill="var(--accent)"
        />
        <path className="sparkle sparkle-1" d="M48 6 l2.5 6 6 2.5 -6 2.5 -2.5 6 -2.5 -6 -6 -2.5 6 -2.5z" />
        <path className="sparkle sparkle-2" d="M58 26 l1.5 3.5 3.5 1.5 -3.5 1.5 -1.5 3.5 -1.5 -3.5 -3.5 -1.5 3.5 -1.5z" />
        <path className="sparkle sparkle-3" d="M32 4 l1.5 3.5 3.5 1.5 -3.5 1.5 -1.5 3.5 -1.5 -3.5 -3.5 -1.5 3.5 -1.5z" />
      </svg>
      <div>
        <p className="loader-title">{LOADING_TEXT}</p>
        <p key={lineIndex} className="loader-line">
          {STATUS_LINES[lineIndex]}
        </p>
      </div>
    </div>
  )
}

const CONFETTI_COLORS = ['var(--confetti-1)', 'var(--confetti-2)', 'var(--confetti-3)', 'var(--confetti-4)']
const CONFETTI_PIECES = Array.from({ length: 18 }, (_, i) => ({
  left: `${(i * 37) % 100}%`,
  delay: `${(i % 6) * 0.08}s`,
  color: CONFETTI_COLORS[i % CONFETTI_COLORS.length],
}))

type CopyState = 'idle' | 'copied' | 'failed'

/** The full link a child opens to play the game. */
function playLink(gameId: number): string {
  return `${window.location.origin}/play/${gameId}`
}

function SuccessCard({ result }: { result: CreateGameResponse }) {
  const [copy, setCopy] = useState<CopyState>('idle')
  const link = playLink(result.game_id)

  async function handleCopy(): Promise<void> {
    try {
      await navigator.clipboard.writeText(link)
      setCopy('copied')
    } catch {
      // No clipboard (or permission denied): show the link so it can be copied by hand.
      setCopy('failed')
    }
  }

  return (
    <div className="success-card">
      <div className="confetti" aria-hidden="true">
        {CONFETTI_PIECES.map((piece, i) => (
          <span
            key={i}
            style={
              {
                '--left': piece.left,
                '--delay': piece.delay,
                '--color': piece.color,
              } as CSSProperties
            }
          />
        ))}
      </div>
      <p className="success-title">המשחק מוכן! 🎉</p>
      <p>
        מספר המשחק: <strong className="game-number">{result.game_id}</strong>
      </p>
      <p>נוצרו {result.question_count} שאלות.</p>
      {result.rejected > 0 && (
        <p className="success-note">{result.rejected} שאלות לא עברו את הבדיקה ולא נכללו.</p>
      )}
      <div className="success-actions">
        <Link className="primary-button play-link" to={`/play/${result.game_id}`}>
          למשחק
        </Link>
        <button type="button" className="secondary-button" onClick={() => void handleCopy()}>
          העתק קישור
        </button>
      </div>
      <div role="status" aria-live="polite">
        {copy === 'copied' && <p className="success-note">הקישור הועתק!</p>}
        {copy === 'failed' && (
          <p className="success-note">
            העתיקו את הקישור: <span dir="ltr">{link}</span>
          </p>
        )}
      </div>
    </div>
  )
}

export default CreateGame
