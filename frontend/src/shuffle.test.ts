import { describe, expect, it } from 'vitest'
import { shuffle } from './shuffle.ts'

describe('shuffle', () => {
  it('keeps exactly the same items', () => {
    const items = ['א', 'ב', 'ג', 'ד', 'ה']

    expect([...shuffle(items)].sort()).toEqual([...items].sort())
  })

  it('does not change the input', () => {
    const items = [1, 2, 3, 4]

    shuffle(items, () => 0)

    expect(items).toEqual([1, 2, 3, 4])
  })

  it('gives a fixed order for a fixed random source', () => {
    // random() = 0 always swaps with the first item: [1,2,3,4] -> [2,3,4,1].
    expect(shuffle([1, 2, 3, 4], () => 0)).toEqual([2, 3, 4, 1])
    // random() close to 1 always swaps an item with itself: order unchanged.
    expect(shuffle([1, 2, 3, 4], () => 0.999)).toEqual([1, 2, 3, 4])
  })

  it('handles empty and single-item lists', () => {
    expect(shuffle([])).toEqual([])
    expect(shuffle(['x'])).toEqual(['x'])
  })
})
