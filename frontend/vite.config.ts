import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

function vendorChunkName(id: string): string | undefined {
  if (!id.includes('node_modules')) return undefined

  if (id.includes('/@loaders.gl/')) return 'vendor-loaders'
  if (id.includes('/@luma.gl/')) return 'vendor-luma'
  if (id.includes('/@math.gl/')) return 'vendor-mathgl'
  if (id.includes('/probe.gl/')) return 'vendor-probegl'
  if (id.includes('/mjolnir.js/')) return 'vendor-mjolnir'
  if (id.includes('/h3-js/')) return 'vendor-h3'

  if (
    id.includes('/@mapbox/')
    || id.includes('/earcut/')
    || id.includes('/kdbush/')
    || id.includes('/pbf/')
    || id.includes('/supercluster/')
  ) {
    return 'vendor-map-utils'
  }

  if (id.includes('/maplibre-gl/')) return 'vendor-maplibre'
  if (id.includes('/react-map-gl/')) return 'vendor-react-map'

  if (id.includes('/@deck.gl/') || id.includes('/deck.gl/')) {
    return 'vendor-deckgl'
  }

  if (id.includes('/recharts/')) return 'vendor-recharts'
  if (id.includes('/@turf/')) return 'vendor-turf'

  if (id.includes('/framer-motion/') || id.includes('/gsap/') || id.includes('/lenis/')) {
    return 'vendor-motion'
  }

  if (id.includes('/react-router/') || id.includes('/react-router-dom/')) {
    return 'vendor-router'
  }

  if (id.includes('/react/') || id.includes('/react-dom/')) {
    return 'vendor-react'
  }

  return undefined
}

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const devApiTarget = env.VITE_DEV_API_TARGET || 'http://localhost:8000'

  return {
    plugins: [react(), tailwindcss()],
    server: {
      proxy: {
        '/api': {
          target: devApiTarget,
          changeOrigin: true,
        },
        '/docs': {
          target: devApiTarget,
          changeOrigin: true,
        },
        '/openapi.json': {
          target: devApiTarget,
          changeOrigin: true,
        },
      },
    },
    build: {
      chunkSizeWarningLimit: 800,
      rollupOptions: {
        output: {
          manualChunks(id) {
            return vendorChunkName(id)
          },
        },
      },
    },
  }
})
