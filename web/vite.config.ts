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
            // SMS service — Port 8019
            '/sms-svc': {
                target: 'http://localhost:8019',
                changeOrigin: true,
                rewrite: (path) => path.replace(/^\/sms-svc/, ''),
            },
            // Backup service — Port 8039
            '/backup-svc': {
                target: 'http://localhost:8039',
                changeOrigin: true,
                rewrite: (path) => path.replace(/^\/backup-svc/, ''),
            },
            // DevOcity (dev portal) — Port 8062
            '/devocity-svc': {
                target: 'http://localhost:8062',
                changeOrigin: true,
                rewrite: (path) => path.replace(/^\/devocity-svc/, ''),
            },
            // GBrain Bridge (knowledge graph) — Port 8030
            '/gbrain-svc': {
                target: 'http://localhost:8030',
                changeOrigin: true,
                rewrite: (path) => path.replace(/^\/gbrain-svc/, ''),
            },
            // The HIVE (data movement & swarm coordination) — Port 8060
            '/hive-svc': {
                target: 'http://localhost:8060',
                changeOrigin: true,
                rewrite: (path) => path.replace(/^\/hive-svc/, ''),
            },
            // Email service — Port 8018
            '/email-svc': {
                target: 'http://localhost:8018',
                changeOrigin: true,
                rewrite: (path) => path.replace(/^\/email-svc/, ''),
            },
            // Geo service — Port 8027
            '/geo-svc': {
                target: 'http://localhost:8027',
                changeOrigin: true,
                rewrite: (path) => path.replace(/^\/geo-svc/, ''),
            },
            // Gateway Service aggregator — Port 8040
            '/gateway-svc': {
                target: 'http://localhost:8040',
                changeOrigin: true,
                rewrite: (path) => path.replace(/^\/gateway-svc/, ''),
            },
            // Sentinel Station event bus — Port 8041
            '/sentinel-svc': {
                target: 'http://localhost:8041',
                changeOrigin: true,
                rewrite: (path) => path.replace(/^\/sentinel-svc/, ''),
            },
            // Ice Box sandbox isolation — Port 8046
            '/ice-box-svc': {
                target: 'http://localhost:8046',
                changeOrigin: true,
                rewrite: (path) => path.replace(/^\/ice-box-svc/, ''),
            },
            // TranceFlow 3D/games studio — Port 8067
            '/tranceflow-svc': {
                target: 'http://localhost:8067',
                changeOrigin: true,
                rewrite: (path) => path.replace(/^\/tranceflow-svc/, ''),
            },
            // TateKing video creation — Port 8066
            '/tateking-svc': {
                target: 'http://localhost:8066',
                changeOrigin: true,
                rewrite: (path) => path.replace(/^\/tateking-svc/, ''),
            },
            // VRAR3D immersion — Port 8068
            '/vrar3d-svc': {
                target: 'http://localhost:8068',
                changeOrigin: true,
                rewrite: (path) => path.replace(/^\/vrar3d-svc/, ''),
            },
            // Warp Radio music streaming — Port 8057
            '/warp-radio-svc': {
                target: 'http://localhost:8057',
                changeOrigin: true,
                rewrite: (path) => path.replace(/^\/warp-radio-svc/, ''),
            },
            // The Academy LMS — Port 8056
            '/academy-svc': {
                target: 'http://localhost:8056',
                changeOrigin: true,
                rewrite: (path) => path.replace(/^\/academy-svc/, ''),
            },
            // The Studio creativity hub — Port 8069
            '/studio-svc': {
                target: 'http://localhost:8069',
                changeOrigin: true,
                rewrite: (path) => path.replace(/^\/studio-svc/, ''),
            },
            // tAimra digital twin — Port 8065
            '/taimra-svc': {
                target: 'http://localhost:8065',
                changeOrigin: true,
                rewrite: (path) => path.replace(/^\/taimra-svc/, ''),
            },
            // Tranquility wellbeing hub — Port 8058
            '/tranquility-svc': {
                target: 'http://localhost:8058',
                changeOrigin: true,
                rewrite: (path) => path.replace(/^\/tranquility-svc/, ''),
            },
            // Resonate empathy engine — Port 8060 (note: shares port with hive-service)
            '/resonate-svc': {
                target: 'http://localhost:8060',
                changeOrigin: true,
                rewrite: (path) => path.replace(/^\/resonate-svc/, ''),
            },
            // I-Mind emotion engine — Port 8059
            '/imind-svc': {
                target: 'http://localhost:8059',
                changeOrigin: true,
                rewrite: (path) => path.replace(/^\/imind-svc/, ''),
            },
            // Sasha's Photo Studio — Port 8051
            '/photo-svc': {
                target: 'http://localhost:8051',
                changeOrigin: true,
                rewrite: (path) => path.replace(/^\/photo-svc/, ''),
            },
            // Dimensional Nexus service — Port 8050
            '/dnexus-svc': {
                target: 'http://localhost:8050',
                changeOrigin: true,
                rewrite: (path) => path.replace(/^\/dnexus-svc/, ''),
            },
            // Swarm Coordinator service — Port 8053
            '/swarm-svc': {
                target: 'http://localhost:8053',
                changeOrigin: true,
                rewrite: (path) => path.replace(/^\/swarm-svc/, ''),
            },
            // Users service — Port 8006
            '/users-svc': {
                target: 'http://localhost:8006',
                changeOrigin: true,
                rewrite: (path) => path.replace(/^\/users-svc/, ''),
            },
            // Infinity Bridge service — Port 8070
            '/infinity-bridge-svc': {
                target: 'http://localhost:8070',
                changeOrigin: true,
                rewrite: (path) => path.replace(/^\/infinity-bridge-svc/, ''),
            },
            // Infinity Shards service — Port 8045
            '/infinity-shards-svc': {
                target: 'http://localhost:8045',
                changeOrigin: true,
                rewrite: (path) => path.replace(/^\/infinity-shards-svc/, ''),
            },
            // Infinity Admin service — Port 8044
            '/infinity-admin-svc': {
                target: 'http://localhost:8044',
                changeOrigin: true,
                rewrite: (path) => path.replace(/^\/infinity-admin-svc/, ''),
            },
            // Infinity One service — Port 8043
            '/infinity-one-svc': {
                target: 'http://localhost:8043',
                changeOrigin: true,
                rewrite: (path) => path.replace(/^\/infinity-one-svc/, ''),
            },
            // Infinity Portal service — Port 8042
            '/iportal-svc': {
                target: 'http://localhost:8042',
                changeOrigin: true,
                rewrite: (path) => path.replace(/^\/iportal-svc/, ''),
            },
            // CDN service — Port 8028
            '/cdn-svc': {
                target: 'http://localhost:8028',
                changeOrigin: true,
                rewrite: (path) => path.replace(/^\/cdn-svc/, ''),
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
