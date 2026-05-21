# TRANC3 — Zero Cost Hosting & Deployment Guide
**Version:** 1.0.0 | **Total Monthly Cost: £0**

---

## Stack Overview

| Layer | Service | Free Tier | Upgrade Path |
|-------|---------|-----------|--------------|
| API Hosting | Render.com | 750 hrs/mo, 512MB RAM | $7/mo for always-on |
| ML Inference | Hugging Face Spaces | Free CPU, free GPU (limited) | $9/mo for persistent GPU |
| Frontend | Vercel | Unlimited deploys, 100GB bandwidth | $20/mo Pro |
| Database | Supabase | 500MB, 2 projects | $25/mo Pro |
| Cache | Upstash Redis | 10k commands/day, 256MB | $0.2 per 100k commands |
| Vector DB | Pinecone | 1 index, 100k vectors | $70/mo Starter |
| CI/CD | GitHub Actions | 2000 min/mo | $4/mo for 3000 min |
| Container Registry | GitHub Packages | 500MB free | $4/mo |
| Monitoring | Grafana Cloud | 10k metrics, 50GB logs | $29/mo |
| Auth | Supabase Auth | Unlimited users | Included in DB tier |
| Payments | Stripe | No monthly fee | 2.9% + 30p per transaction |
| DNS + CDN + Edge | Cloudflare | Unlimited requests | $20/mo Pro |
| Secrets | GitHub Secrets | Unlimited | Free |
| Docs | GitHub Pages | Unlimited | Free |

---

## Deployment Steps

### 1. Database (Supabase)
```bash
# 1. Create account at supabase.com
# 2. New project → copy DATABASE_URL
# 3. Run migrations
alembic upgrade head
```

### 2. Cache (Upstash)
```bash
# 1. Create account at upstash.com
# 2. Create Redis database → copy REDIS_URL
# 3. Add to .env
```

### 3. API (Render)
```bash
# 1. Connect GitHub repo at render.com
# 2. New Web Service → select repo
# 3. Build command: pip install -r requirements.txt
# 4. Start command: uvicorn api:app --host 0.0.0.0 --port $PORT
# 5. Add all .env variables in Render dashboard
```

### 4. ML Inference (Hugging Face Spaces)
```bash
# 1. Create Space at huggingface.co/spaces
# 2. Select FastAPI SDK
# 3. Push inference-only api.py
# 4. Free T4 GPU available via ZeroGPU (apply for access)
```

### 5. Frontend (Vercel)
```bash
# 1. Connect GitHub repo at vercel.com
# 2. Framework: React (Vite)
# 3. Root directory: web/
# 4. Add VITE_API_URL env var pointing to Render URL
```

### 6. Monitoring (Grafana Cloud)
```bash
# 1. Create account at grafana.com
# 2. Create stack → copy OTEL endpoint + API key
# 3. Add to .env
# 4. Prometheus metrics auto-exposed at /metrics
```

### 7. Payments (Stripe)
```bash
# 1. Create account at stripe.com
# 2. Create products + prices for Pro and Business tiers
# 3. Copy price IDs to .env
# 4. Set up webhook → /billing/webhook
```

---

## Revenue Activation Checklist

- [ ] Stripe account created and verified
- [ ] Pro tier price created (£29/mo)
- [ ] Business tier price created (£149/mo)
- [ ] Webhook endpoint configured
- [ ] Free tier rate limits enforced
- [ ] Upgrade prompts in frontend when limits hit
- [ ] RapidAPI listing created (API marketplace)
- [ ] GitHub Sponsors profile set up
- [ ] Affiliate programme page live

---

## Scaling Path (When Revenue Justifies It)

| MRR | Action |
|-----|--------|
| £0–£500 | Stay on free tiers |
| £500–£2k | Upgrade Render ($7) + Supabase ($25) |
| £2k–£10k | Move to GKE Autopilot, add Pinecone Starter |
| £10k+ | Multi-region, dedicated GPU, enterprise SLA |
