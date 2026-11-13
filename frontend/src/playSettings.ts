// Texts and timing for the child's play screen.

export const PLAY_MODE = 'learning' as const

/** How long the feedback stays on screen before the next question. */
export const FEEDBACK_MS = 1500

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
} as const

export function progressText(current: number, total: number): string {
  return `שאלה ${current} מתוך ${total}`
}

export function finishedText(correct: number, total: number): string {
  return `סיימת! ענית נכון על ${correct} מתוך ${total}`
}
