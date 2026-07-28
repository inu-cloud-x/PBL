import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import wasm from 'vite-plugin-wasm'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const beaconTarget = env.VITE_CONSENSUS_RPC_URL || 'https://lodestar-sepolia.chainsafe.io'

  return {
    plugins: [react(), wasm()],
    resolve: {
      alias: {
        events: 'events',
      },
    },
    optimizeDeps: {
      include: ['events'],
      exclude: ['@a16z/helios'],
    },
    server: {
      proxy: {
        '/api/beacon-proxy': {
          target: beaconTarget,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api\/beacon-proxy/, '') || '/',
        },
      },
    },
  }
})
