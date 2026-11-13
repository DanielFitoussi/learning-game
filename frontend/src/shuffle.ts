/**
 * A shuffled copy of the items (Fisher–Yates). The input is not changed.
 * `random` returns a number in [0, 1); tests pass a fixed one.
 */
export function shuffle<T>(items: readonly T[], random: () => number = Math.random): T[] {
  const result = [...items]
  for (let i = result.length - 1; i > 0; i--) {
    const j = Math.floor(random() * (i + 1))
    ;[result[i], result[j]] = [result[j], result[i]]
  }
  return result
}
