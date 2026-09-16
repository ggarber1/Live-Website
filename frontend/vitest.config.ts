// Separate from vite.config.ts: vitest bundles its own Vite, whose plugin
// types disagree with Vite 8's under `tsc -b`. tsconfig.node.json only checks
// vite.config.ts, so keeping the test config here keeps the build clean.
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    setupFiles: './src/setup.ts',
    globals: true,
  },
})
