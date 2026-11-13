import { describe, expect, it } from 'vitest'
import { splitMath } from './mathText.ts'

const text = (t: string) => ({ text: t, isMath: false })
const math = (t: string) => ({ text: t, isMath: true })

describe('splitMath', () => {
  it('wraps addition and keeps the Hebrew and question mark outside', () => {
    expect(splitMath('כמה הם 8 + 6?')).toEqual([text('כמה הם '), math('8 + 6'), text('?')])
  })

  it.each([
    ['כמה הם 16 - 7?', '16 - 7'],
    ['כמה הם 16-7?', '16-7'],
    ['כמה הם 9 − 4?', '9 − 4'],
    ['כמה הם 3 × 4?', '3 × 4'],
    ['כמה הם 12 ÷ 3?', '12 ÷ 3'],
    ['האם 3 + 4 = 7?', '3 + 4 = 7'],
  ])('finds the expression in %s', (prompt, expression) => {
    expect(splitMath(prompt)).toContainEqual(math(expression))
  })

  it.each([
    ['פִּתְרוּ: 7 + 5 = ?', '7 + 5 = ?'],
    ['פִּתְרוּ: 7 + 5 = _', '7 + 5 = _'],
    ['פִּתְרוּ: 7 + 5 = __', '7 + 5 = __'],
    ['פִּתְרוּ: 7 + 5 = ☐', '7 + 5 = ☐'],
  ])('includes a trailing "=" with its blank in %s', (prompt, expression) => {
    expect(splitMath(prompt)).toEqual([text('פִּתְרוּ: '), math(expression)])
  })

  it('does not take a question mark that has no "=" before it', () => {
    expect(splitMath('כמה הם 8 + 6 ?')).toEqual([text('כמה הם '), math('8 + 6'), text(' ?')])
  })

  it('finds two expressions in one prompt', () => {
    expect(splitMath('מה גדול יותר, 5 + 2 או 9-1?')).toEqual([
      text('מה גדול יותר, '),
      math('5 + 2'),
      text(' או '),
      math('9-1'),
      text('?'),
    ])
  })

  it('leaves a prompt with no math as one plain part', () => {
    expect(splitMath('איזו חיה נותנת חלב?')).toEqual([text('איזו חיה נותנת חלב?')])
  })

  it('does not wrap a lone number or a hyphen after a Hebrew letter', () => {
    expect(splitMath('כמה רגליים יש ל-4 כלבים?')).toEqual([text('כמה רגליים יש ל-4 כלבים?')])
  })

  it('always gives back the original prompt when the parts are joined', () => {
    for (const prompt of ['כמה הם 8 + 6?', 'פִּתְרוּ: 7 + 5 = ?', '2+2', '', 'שלום']) {
      expect(
        splitMath(prompt)
          .map((p) => p.text)
          .join(''),
      ).toBe(prompt)
    }
  })
})
