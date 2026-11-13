import { afterEach, describe, expect, it, vi } from 'vitest'
import { canSpeak, speak, textForSpeech } from './speech.ts'

class FakeUtterance {
  text: string
  lang = ''
  constructor(text: string) {
    this.text = text
  }
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('textForSpeech', () => {
  it.each([
    ['2 + 3', '2 ועוד 3'],
    ['2+3', '2 ועוד 3'],
    ['7 - 4', '7 פחות 4'],
    ['7-4', '7 פחות 4'],
    ['כמה זה 5 + 2 - 1?', 'כמה זה 5 ועוד 2 פחות 1?'],
  ])('reads %s as %s', (prompt, spoken) => {
    expect(textForSpeech(prompt)).toBe(spoken)
  })

  it('leaves a hyphen between words alone', () => {
    expect(textForSpeech('well-known')).toBe('well-known')
  })
})

describe('canSpeak', () => {
  it('is false when the browser has no speech', () => {
    // jsdom has no speechSynthesis.
    expect(canSpeak()).toBe(false)
  })

  it('is true when speech exists', () => {
    vi.stubGlobal('speechSynthesis', { speak: vi.fn(), cancel: vi.fn() })
    vi.stubGlobal('SpeechSynthesisUtterance', FakeUtterance)

    expect(canSpeak()).toBe(true)
  })
})

describe('speak', () => {
  it('speaks the converted text in Hebrew', () => {
    const synth = { speak: vi.fn(), cancel: vi.fn() }
    vi.stubGlobal('speechSynthesis', synth)
    vi.stubGlobal('SpeechSynthesisUtterance', FakeUtterance)

    speak('2 + 3')

    expect(synth.cancel).toHaveBeenCalled()
    expect(synth.speak).toHaveBeenCalledWith(expect.objectContaining({ text: '2 ועוד 3', lang: 'he-IL' }))
  })

  it('does nothing without speech', () => {
    expect(() => speak('2 + 3')).not.toThrow()
  })

  it('does not throw when the browser speech fails', () => {
    vi.stubGlobal('speechSynthesis', {
      cancel: vi.fn(),
      speak: vi.fn(() => {
        throw new Error('not allowed')
      }),
    })
    vi.stubGlobal('SpeechSynthesisUtterance', FakeUtterance)

    expect(() => speak('2 + 3')).not.toThrow()
  })
})
