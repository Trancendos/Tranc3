#!/usr/bin/env node
/**
 * scripts/lighthouse-audit.mjs
 * ─────────────────────────────────────────────────────────────────────────────
 * Run a Lighthouse accessibility + performance audit against the Tranc3 web app.
 *
 * Usage:
 *   node scripts/lighthouse-audit.mjs              # uses built app on :4173
 *   node scripts/lighthouse-audit.mjs --url http://localhost:3000
 *   node scripts/lighthouse-audit.mjs --build      # build first, then audit
 *   node scripts/lighthouse-audit.mjs --ci         # exit 1 if a11y score < 90
 *
 * Outputs:
 *   reports/lighthouse.html         — full HTML report
 *   reports/lighthouse.json         — raw Lighthouse JSON
 *   reports/a11y-summary.json       — machine-readable a11y summary for CI
 *
 * The --ci flag is used by the Forgejo production-gate to enforce the
 * accessibility score threshold before any deploy.
 * ─────────────────────────────────────────────────────────────────────────────
 */

import { execSync, spawn } from 'child_process'
import { existsSync, mkdirSync, writeFileSync } from 'fs'
import { join, dirname } from 'path'
import { fileURLToPath, pathToFileURL } from 'url'
import { createRequire } from 'module'

const __dirname = dirname(fileURLToPath(import.meta.url))
const ROOT      = join(__dirname, '..')
const WEB_DIR   = join(ROOT, 'web')
const REPORTS   = join(ROOT, 'reports')

// ── CLI args ──────────────────────────────────────────────────────────────────
const args       = process.argv.slice(2)
const CI_MODE    = args.includes('--ci')
const BUILD_FIRST = args.includes('--build')
const urlIdx     = args.indexOf('--url')
const TARGET_URL = urlIdx !== -1 ? args[urlIdx + 1] : null

const A11Y_THRESHOLD = 90   // minimum Lighthouse accessibility score (0–100)

// ── Colours ───────────────────────────────────────────────────────────────────
const C = {
  reset:  '\x1b[0m',
  bold:   '\x1b[1m',
  red:    '\x1b[31m',
  green:  '\x1b[32m',
  yellow: '\x1b[33m',
  cyan:   '\x1b[36m',
}
const ok   = (s) => console.log(`${C.green}✓${C.reset}  ${s}`)
const warn = (s) => console.log(`${C.yellow}⚠${C.reset}  ${s}`)
const fail = (s) => console.error(`${C.red}✗${C.reset}  ${s}`)
const info = (s) => console.log(`${C.cyan}→${C.reset}  ${s}`)

mkdirSync(REPORTS, { recursive: true })

// ── Step 1: Optionally build the web app ──────────────────────────────────────
if (BUILD_FIRST) {
  info('Building web app (npm run build)…')
  execSync('npm run build', { cwd: WEB_DIR, stdio: 'inherit' })
  ok('Build complete.')
}

// ── Step 2: Start a preview server if no explicit URL given ───────────────────
let previewProc = null
let auditUrl    = TARGET_URL

if (!auditUrl) {
  const distExists = existsSync(join(WEB_DIR, 'dist', 'index.html'))
  if (!distExists) {
    info('No dist/ found — building first…')
    execSync('npm run build', { cwd: WEB_DIR, stdio: 'inherit' })
    ok('Build complete.')
  }

  const PORT = 4173
  auditUrl   = `http://localhost:${PORT}`

  info(`Starting preview server on ${auditUrl}…`)
  previewProc = spawn('npm', ['run', 'preview', '--', '--port', String(PORT), '--host', 'localhost'], {
    cwd:   WEB_DIR,
    stdio: 'pipe',
    detached: false,
  })

  // Wait for server to be ready (max 15s)
  await new Promise((resolve, reject) => {
    const timeout = setTimeout(() => reject(new Error('Preview server did not start within 15s')), 15000)
    const check = setInterval(async () => {
      try {
        const { default: http } = await import('http')
        const req = http.get(auditUrl, (res) => {
          if (res.statusCode < 500) {
            clearInterval(check)
            clearTimeout(timeout)
            resolve()
          }
        })
        req.on('error', () => {}) // ignore — server not up yet
        req.end()
      } catch {}
    }, 500)
  })
  ok(`Preview server ready at ${auditUrl}`)
}

// ── Step 3: Run Lighthouse ────────────────────────────────────────────────────
let result
try {
  // Resolve from web/node_modules since lighthouse is installed there
  const webRequire = createRequire(join(WEB_DIR, 'package.json'))
  const lighthousePath = webRequire.resolve('lighthouse')
  const chromeLauncherPath = webRequire.resolve('chrome-launcher')
  const { default: lighthouse } = await import(pathToFileURL(lighthousePath).href)
  const chromeLauncher = await import(pathToFileURL(chromeLauncherPath).href)

  info(`Launching Chromium and running Lighthouse audit against ${auditUrl}…`)

  // Discover Chromium — prefer Playwright's bundled binary, then PATH
  const chromePath = (() => {
    // Playwright-installed Chromium (CI and dev containers)
    const pw = join(
      process.env.PLAYWRIGHT_BROWSERS_PATH || '/opt/pw-browsers',
      'chromium-1194', 'chrome-linux', 'chrome'
    )
    if (existsSync(pw)) return pw

    // Fallback: let chrome-launcher auto-detect (requires Chrome/Chromium on PATH)
    return undefined
  })()

  const launchOpts = {
    chromeFlags: [
      '--headless',
      '--no-sandbox',
      '--disable-gpu',
      '--disable-dev-shm-usage',
      '--disable-extensions',
    ],
  }
  if (chromePath) launchOpts.chromePath = chromePath

  const chrome = await chromeLauncher.launch(launchOpts)

  const options = {
    logLevel:  'error',
    output:    ['html', 'json'],
    onlyCategories: ['accessibility', 'best-practices', 'performance', 'seo'],
    port:      chrome.port,
  }

  const runnerResult = await lighthouse(auditUrl, options)
  await chrome.kill()

  const lhr     = runnerResult.lhr
  const reports = runnerResult.report   // [htmlString, jsonString]

  // Write reports
  const htmlPath  = join(REPORTS, 'lighthouse.html')
  const jsonPath  = join(REPORTS, 'lighthouse.json')
  const summPath  = join(REPORTS, 'a11y-summary.json')

  writeFileSync(htmlPath, reports[0])
  writeFileSync(jsonPath, reports[1])
  ok(`HTML report written → ${htmlPath}`)
  ok(`JSON report written → ${jsonPath}`)

  // Extract a11y audit items
  const a11yCat    = lhr.categories.accessibility
  const a11yScore  = Math.round((a11yCat?.score ?? 0) * 100)
  const perfScore  = Math.round((lhr.categories.performance?.score ?? 0) * 100)
  const bpScore    = Math.round((lhr.categories['best-practices']?.score ?? 0) * 100)
  const seoScore   = Math.round((lhr.categories.seo?.score ?? 0) * 100)

  // Gather failing a11y audits
  const a11yAudits = Object.values(lhr.audits).filter(
    (a) => a.scoreDisplayMode === 'binary' && a.score !== null && a.score < 1
       && lhr.categories.accessibility?.auditRefs?.some((r) => r.id === a.id)
  )

  const summary = {
    url:       auditUrl,
    timestamp: new Date().toISOString(),
    scores: {
      accessibility:  a11yScore,
      performance:    perfScore,
      best_practices: bpScore,
      seo:            seoScore,
    },
    a11y_threshold:       A11Y_THRESHOLD,
    a11y_passed:          a11yScore >= A11Y_THRESHOLD,
    failing_a11y_audits:  a11yAudits.map((a) => ({
      id:          a.id,
      title:       a.title,
      description: a.description,
      score:       a.score,
      impact:      a.details?.items?.length ?? 0,
    })),
    reports: {
      html: htmlPath,
      json: jsonPath,
    },
  }

  writeFileSync(summPath, JSON.stringify(summary, null, 2))
  ok(`A11y summary written → ${summPath}`)

  // ── Print scorecard ──────────────────────────────────────────────────────
  console.log('')
  console.log(`${C.bold}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${C.reset}`)
  console.log(`${C.bold}  Lighthouse Audit Results — ${auditUrl}${C.reset}`)
  console.log(`${C.bold}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${C.reset}`)
  const scoreStr = (n) => n >= 90 ? `${C.green}${n}${C.reset}` : n >= 70 ? `${C.yellow}${n}${C.reset}` : `${C.red}${n}${C.reset}`
  console.log(`  Accessibility  : ${scoreStr(a11yScore)} / 100  (threshold: ${A11Y_THRESHOLD})`)
  console.log(`  Performance    : ${scoreStr(perfScore)} / 100`)
  console.log(`  Best Practices : ${scoreStr(bpScore)} / 100`)
  console.log(`  SEO            : ${scoreStr(seoScore)} / 100`)
  console.log('')

  if (a11yAudits.length === 0) {
    ok('No accessibility violations found!')
  } else {
    warn(`${a11yAudits.length} accessibility audit(s) failed:`)
    for (const a of a11yAudits) {
      console.log(`    ${C.red}✗${C.reset} [${a.id}] ${a.title}`)
    }
  }

  console.log(`${C.bold}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${C.reset}`)
  console.log('')

  result = summary

  if (CI_MODE && !summary.a11y_passed) {
    fail(`Accessibility score ${a11yScore} is below threshold ${A11Y_THRESHOLD}`)
    process.exitCode = 1
  }

} finally {
  if (previewProc) {
    previewProc.kill()
  }
}
