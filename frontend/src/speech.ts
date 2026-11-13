// Reading questions aloud with the browser's speech. Speech is a bonus:
// nothing here may throw, and the screen works the same without it.

/** The question text as it should be spoken: math signs become Hebrew words. */
export function textForSpeech(prompt: string): string {
  return (
    prompt
      .replace(/\+/g, ' ועוד ')
      // A minus only between numbers (5-3, 5 - 3), so hyphenated words stay as they are.
      .replace(/(\d)\s*-\s*(?=\d)/g, '$1 פחות ')
      .replace(/\s+/g, ' ')
      .trim()
  )
}

/** Whether this browser can read text aloud. */
export function canSpeak(): boolean {
  try {
    return (
      typeof window !== 'undefined' &&
      'speechSynthesis' in window &&
      typeof window.SpeechSynthesisUtterance === 'function'
    )
  } catch {
    return false
  }
}

/** Read the text aloud in Hebrew, stopping anything already being read. Never throws. */
export function speak(text: string): void {
  if (!canSpeak()) return
  try {
    window.speechSynthesis.cancel()
    const utterance = new window.SpeechSynthesisUtterance(textForSpeech(text))
    utterance.lang = 'he-IL'
    window.speechSynthesis.speak(utterance)
  } catch {
    // Speech failed; the child can still read the question.
  }
}
