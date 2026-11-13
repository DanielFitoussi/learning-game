// Values the create-game screen and its tests share.

export const MAX_MATERIAL_CHARS = 20_000

export const LOADING_TEXT = 'בונים את המשחק...'
export const STATUS_LINES = ['קוראים את החומר...', 'בונים שאלות...', 'בודקים כל שאלה...']
export const STATUS_INTERVAL_MS = 2500

export const MODE_LEGEND = 'סוג המשחק'

/** The modes the creator can pick, in the order they are shown. */
export const MODE_OPTIONS = [
  { value: 'learning', label: 'תרגול', hint: 'הילד רואה אחרי כל שאלה אם צדק.' },
  { value: 'test', label: 'מבחן', hint: 'בלי משוב במהלך המשחק. התוצאות מוצגות רק בסוף.' },
] as const
