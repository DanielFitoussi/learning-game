// Math inside a Hebrew prompt must read left to right, or "16 - 7" shows as "7 - 16".

export type PromptPart = {
  text: string
  isMath: boolean
}

/**
 * A math expression: numbers joined by + - − × ÷ or =, with or without spaces,
 * plus an optional trailing "=" with a blank (?, _, __ or ☐), as in "7 + 5 = ?".
 */
const MATH_EXPRESSION = /\d+(?:\s*[+\-−×÷=]\s*\d+)+(?:\s*=\s*(?:\?|_+|☐))?/g

/** Split a prompt into plain text and math parts. Joining the parts gives the prompt back. */
export function splitMath(prompt: string): PromptPart[] {
  const parts: PromptPart[] = []
  let last = 0
  for (const match of prompt.matchAll(MATH_EXPRESSION)) {
    const start = match.index
    if (start > last) parts.push({ text: prompt.slice(last, start), isMath: false })
    parts.push({ text: match[0], isMath: true })
    last = start + match[0].length
  }
  if (last < prompt.length) parts.push({ text: prompt.slice(last), isMath: false })
  return parts
}
