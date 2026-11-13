// Texts and timing for the child's play screen.

/** Learning mode: how long the right/wrong feedback stays before the next question. */
export const FEEDBACK_MS = 1500

/** Test mode: how long the neutral "saved" note stays before the next question. */
export const SAVED_MS = 700

/** Test mode: shown after each answer instead of right/wrong. */
export const SAVED_TEXT = 'התשובה נשמרה'

export const FEEDBACK = {
  correct: 'כל הכבוד! ⭐',
  wrong: 'לא נורא, ממשיכים 💪',
} as const

export const PLAY_TEXT = {
  title: 'בואו נשחק!',
  loading: 'טוען את המשחק...',
  nameLabel: 'איך קוראים לך?',
  start: 'מתחילים!',
  readAloud: 'הקראת השאלה',
  noQuestions: 'אין עדיין שאלות במשחק הזה.',
  resultsTitle: 'התשובות שלך',
} as const

/** Test mode end screen: the mark next to each question. */
export const RESULT_MARK = {
  correct: '✅',
  wrong: '❌',
  // A 409: the answer was saved on an earlier try, so we don't know if it was right.
  unknown: '—',
} as const

export const RESULT_LABEL = {
  correct: 'נכון',
  wrong: 'לא נכון',
  unknown: 'לא ידוע',
} as const

export function progressText(current: number, total: number): string {
  return `שאלה ${current} מתוך ${total}`
}

export function finishedText(correct: number, total: number): string {
  return `סיימת! ענית נכון על ${correct} מתוך ${total}`
}
