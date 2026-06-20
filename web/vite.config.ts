import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig({
    plugins: [react()],
    resolve: {
        alias: {
            '@': fileURLToPath(new URL('./src', import.meta.url)),
        },
    },
    server: {
        proxy: {
            '/api/ecosystem': {
                target: 'http://localhost:8001',
                changeOrigin: true,
            },
            '/ws': {
                target: 'http://localhost:8004',
                ws: true,
                changeOrigin: true,
            },
            // Health-aggregator (The Observatory) — used by WorkersPage + StatusPage
            '/health-agg': {
                target: 'http://localhost:8029',
                changeOrigin: true,
                rewrite: (path) => path.replace(/^\/health-agg/, ''),
            },
            // Optional/external services proxy — used by ServicesPage
            '/optional-health': {
                target: 'http://localhost:8029',
                changeOrigin: true,
                rewrite: (path) => path.replace(/^\/optional-health/, ''),
            },
            // The Lab (code platform) — Port 8055
            '/lab': {
                target: 'http://localhost:8055',
                changeOrigin: true,
                rewrite: (path) => path.replace(/^\/lab/, ''),
            },
            // The Dutchy (market intelligence) — Port 8061
            '/dutchy': {
                target: 'http://localhost:8061',
                changeOrigin: true,
                rewrite: (path) => path.replace(/^\/dutchy/, ''),
            },
            // Turing's Hub (AI entity builder) — Port 8035
            '/turings': {
                target: 'http://localhost:8035',
                changeOrigin: true,
                rewrite: (path) => path.replace(/^\/turings/, ''),
            },
            // Deep Agents orchestrator — Port 8037
            '/dagents': {
                target: 'http://localhost:8037',
                changeOrigin: true,
                rewrite: (path) => path.replace(/^\/dagents/, ''),
            },
            '/api': {
                target: process.env.VITE_API_URL || 'http://localhost:8000',
                changeOrigin: true,
                rewrite: (path) => path.replace(/^\/api/, ''),
            },
        },
    },
})
