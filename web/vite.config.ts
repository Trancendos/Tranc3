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
            // Analytics service — Port 8016
            '/analytics': {
                target: 'http://localhost:8016',
                changeOrigin: true,
                rewrite: (path) => path.replace(/^\/analytics/, ''),
            },
            // Vault service (The Void) — Port 8038
            '/vault': {
                target: 'http://localhost:8038',
                changeOrigin: true,
                rewrite: (path) => path.replace(/^\/vault/, ''),
            },
            // Topology service — Port 8031
            '/topo': {
                target: 'http://localhost:8031',
                changeOrigin: true,
                rewrite: (path) => path.replace(/^\/topo/, ''),
            },
            // Ledger service (Royal Bank) — Port 8032
            '/ledger': {
                target: 'http://localhost:8032',
                changeOrigin: true,
                rewrite: (path) => path.replace(/^\/ledger/, ''),
            },
            // Model Router service — Port 8033
            '/mrouter': {
                target: 'http://localhost:8033',
                changeOrigin: true,
                rewrite: (path) => path.replace(/^\/mrouter/, ''),
            },
            // LangChain integration service — Port 8036
            '/lchain': {
                target: 'http://localhost:8036',
                changeOrigin: true,
                rewrite: (path) => path.replace(/^\/lchain/, ''),
            },
            // Audit service (The Observatory trail) — Port 8017
            '/audit': {
                target: 'http://localhost:8017',
                changeOrigin: true,
                rewrite: (path) => path.replace(/^\/audit/, ''),
            },
            // Geo service — Port 8027
            '/geo-svc': {
                target: 'http://localhost:8027',
                changeOrigin: true,
                rewrite: (path) => path.replace(/^\/geo-svc/, ''),
            },
            // Rate limit service — Port 8026
            '/rlimit': {
                target: 'http://localhost:8026',
                changeOrigin: true,
                rewrite: (path) => path.replace(/^\/rlimit/, ''),
            },
            // Cache service — Port 8023
            '/cache-svc': {
                target: 'http://localhost:8023',
                changeOrigin: true,
                rewrite: (path) => path.replace(/^\/cache-svc/, ''),
            },
            // Cron service (ChronosSphere) — Port 8021
            '/cron-svc': {
                target: 'http://localhost:8021',
                changeOrigin: true,
                rewrite: (path) => path.replace(/^\/cron-svc/, ''),
            },
            // Config service — Port 8024
            '/config-svc': {
                target: 'http://localhost:8024',
                changeOrigin: true,
                rewrite: (path) => path.replace(/^\/config-svc/, ''),
            },
            '/api': {
                target: process.env.VITE_API_URL || 'http://localhost:8000',
                changeOrigin: true,
                rewrite: (path) => path.replace(/^\/api/, ''),
            },
        },
    },
})
