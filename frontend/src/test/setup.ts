import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

// Remove rendered components between tests so they do not leak into each other.
afterEach(() => {
  cleanup()
})
