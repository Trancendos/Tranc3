/**
 * UX Laws Showcase — living reference for the Tranc3 UX System
 *
 * Demonstrates every Law of UX component in context.
 * Route: /ux-showcase (dev/admin only)
 */
import React, { useState } from 'react'
import {
  ProgressBar,
  StepIndicator,
  SkeletonCell,
  ChoiceGroup,
  ChunkedGrid,
  SmartField,
  CelebrationWrapper,
  SelectiveList,
  HierarchyBadge,
  AdaptiveButton,
  AccordionCluster,
  FlowZone,
  ParetoInsight,
} from '../components/ux'

/* ── Demo data ──────────────────────────────────────────────────────────── */
const STEPS = [
  { id: 'account',  label: 'Account'  },
  { id: 'profile',  label: 'Profile'  },
  { id: 'services', label: 'Services' },
  { id: 'confirm',  label: 'Confirm'  },
]

const CHOICES = [
  { id: 'spark',    label: 'The Spark',    description: 'MCP tool registry'          },
  { id: 'grid',     label: 'The Digital Grid', description: 'Workflow DAG engine'    },
  { id: 'hive',     label: 'The HIVE',     description: 'Data transport hub'         },
  { id: 'nexus',    label: 'The Nexus',    description: 'WebSocket comms'            },
  { id: 'void',     label: 'The Void',     description: 'Encrypted vault'            },
  { id: 'obs',      label: 'The Observatory', description: 'Audit + metrics'         },
  { id: 'ws',       label: 'The Workshop', description: 'CI/CD Forgejo'              },
  { id: 'luminous', label: 'Luminous',     description: 'AI orchestration brain'     },
  { id: 'citadel',  label: 'The Citadel',  description: 'DevOps fortress'            },
]

const GRID_ITEMS = Array.from({ length: 9 }, (_, i) => ({
  id: String(i),
  title: `Entity ${i + 1}`,
  status: i % 3 === 0 ? 'online' : i % 3 === 1 ? 'building' : 'planned',
}))

const LIST_ITEMS = [
  { id: 'a', label: 'The Spark',     meta: 'Port 8001', featured: true  },
  { id: 'b', label: 'Luminous',      meta: 'Port 8009'                   },
  { id: 'c', label: 'The Nexus',     meta: 'Port 8004'                   },
  { id: 'd', label: 'The HIVE',      meta: 'Port 8060'                   },
  { id: 'e', label: 'The Citadel',   meta: 'Docker'                      },
]

const PARETO_ITEMS = [
  { id: 'a', label: 'AI Gateway',       value: 8420, unit: 'req/hr' },
  { id: 'b', label: 'Auth Service',     value: 5210, unit: 'req/hr' },
  { id: 'c', label: 'MCP Tools',        value: 3100, unit: 'req/hr' },
  { id: 'd', label: 'Workflow Engine',  value: 980,  unit: 'req/hr' },
  { id: 'e', label: 'Notifications',   value: 310,  unit: 'req/hr' },
  { id: 'f', label: 'Audit Log',        value: 120,  unit: 'req/hr' },
]

const ACCORDION_ITEMS = [
  {
    id: 'fitts',
    title: "Fitts's Law",
    badge: 'Interaction',
    children: <p>Time to acquire a target is a function of the distance to and size of the target. Make important actions large and close to the user's current position.</p>,
  },
  {
    id: 'hicks',
    title: "Hick's Law",
    badge: 'Cognition',
    children: <p>The time it takes to make a decision increases with the number and complexity of choices. Reduce options, use progressive disclosure, highlight recommendations.</p>,
  },
  {
    id: 'peak',
    title: 'Peak-End Rule',
    badge: 'Memory',
    children: <p>People judge an experience largely based on how they felt at its most intense point and at its end. Design memorable peaks and positive endings intentionally.</p>,
  },
  {
    id: 'zeigarnik',
    title: 'Zeigarnik Effect',
    badge: 'Memory',
    children: <p>People remember uncompleted tasks better than completed ones. Use progress indicators to drive engagement and signal incomplete states clearly.</p>,
  },
]

/* ── Section wrapper ─────────────────────────────────────────────────────── */
function Section({ title, law, children }: { title: string; law: string; children: React.ReactNode }) {
  return (
    <section style={{ marginBottom: 'var(--ux-space-16)' }}>
      <div className="ux-flex ux-items-center ux-gap-4" style={{ marginBottom: 'var(--ux-space-6)' }}>
        <h2 className="ux-attention-primary">{title}</h2>
        <HierarchyBadge label={law} variant="primary" dot />
      </div>
      {children}
    </section>
  )
}

/* ── Page ────────────────────────────────────────────────────────────────── */
export default function UxShowcasePage() {
  const [step, setStep]       = useState(1)
  const [loading, setLoading] = useState(false)
  const [selected, setSelected] = useState<string | null>('spark')
  const [celebrated, setCelebrated] = useState(false)

  function simulateLoad() {
    setLoading(true)
    setTimeout(() => setLoading(false), 2000)
  }

  return (
    <FlowZone
      contextLabel="UX Laws Showcase"
      contextMeta={<HierarchyBadge label="30 Laws" variant="success" dot />}
    >
      <div
        style={{
          maxWidth: '900px',
          margin: '0 auto',
          padding: 'var(--ux-space-12) var(--ux-space-6)',
        }}
      >
        <header style={{ marginBottom: 'var(--ux-space-16)' }}>
          <h1 className="ux-attention-primary" style={{ fontSize: 'var(--ux-text-3xl)', marginBottom: 'var(--ux-space-4)' }}>
            Tranc3 UX System
          </h1>
          <p className="ux-flow-prose">
            Every component below is a living implementation of one or more Laws of UX —
            fluidic, adaptive, reactive, and ARIA-complete. The system is built from
            CSS custom-property DNA tokens, composable React hooks, and modular cell
            components that cluster into intelligent, proactive interfaces.
          </p>
        </header>

        {/* ── Doherty Threshold ──────────────────────────────────────────── */}
        <Section title="Doherty Threshold" law="< 400 ms">
          <p className="ux-attention-secondary" style={{ marginBottom: 'var(--ux-space-4)' }}>
            Skeleton only appears after 100 ms — no flash on fast responses.
          </p>
          <SkeletonCell isLoading={loading} variant="list" rows={3}>
            <SelectiveList items={LIST_ITEMS} label="Platform services" />
          </SkeletonCell>
          <div style={{ marginTop: 'var(--ux-space-4)' }}>
            <AdaptiveButton importance="secondary" loading={loading} onClick={simulateLoad}>
              {loading ? 'Loading…' : 'Simulate 2 s load'}
            </AdaptiveButton>
          </div>
        </Section>

        {/* ── Goal-Gradient + Zeigarnik ──────────────────────────────────── */}
        <Section title="Goal-Gradient + Zeigarnik" law="Progress">
          <p className="ux-attention-secondary" style={{ marginBottom: 'var(--ux-space-4)' }}>
            Progress accelerates near completion; celebrates at 100%.
          </p>
          <ProgressBar current={step} total={STEPS.length} label="Onboarding" />
          <StepIndicator steps={STEPS} currentStep={step} className="ux-mt-4" />
          <div className="ux-flex ux-gap-2" style={{ marginTop: 'var(--ux-space-4)' }}>
            <AdaptiveButton importance="secondary" onClick={() => setStep(s => Math.max(0, s - 1))} disabled={step === 0}>
              Back
            </AdaptiveButton>
            <AdaptiveButton importance="primary" onClick={() => setStep(s => Math.min(STEPS.length, s + 1))} disabled={step === STEPS.length}>
              {step === STEPS.length - 1 ? 'Finish' : 'Next'}
            </AdaptiveButton>
          </div>
        </Section>

        {/* ── Peak-End Rule ─────────────────────────────────────────────── */}
        <Section title="Peak-End Rule" law="Delight">
          <p className="ux-attention-secondary" style={{ marginBottom: 'var(--ux-space-4)' }}>
            Celebration animation fires at the peak moment of task completion.
          </p>
          <CelebrationWrapper
            triggerOn={celebrated}
            message="Task complete — great work!"
            className="ux-surface-card ux-p-6"
          >
            <p className="ux-attention-secondary">Your deployment is ready.</p>
          </CelebrationWrapper>
          <AdaptiveButton
            importance="primary"
            onClick={() => { setCelebrated(false); setTimeout(() => setCelebrated(true), 50) }}
            style={{ marginTop: 'var(--ux-space-4)' }}
          >
            Trigger peak moment
          </AdaptiveButton>
        </Section>

        {/* ── Hick's Law + Choice Overload ──────────────────────────────── */}
        <Section title="Hick's Law + Choice Overload" law="≤ 7 choices">
          <p className="ux-attention-secondary" style={{ marginBottom: 'var(--ux-space-4)' }}>
            9 services — only 7 shown, 2 hidden behind "Show more".
          </p>
          <ChoiceGroup
            choices={CHOICES}
            selected={selected}
            onSelect={setSelected}
            label="Select a platform service"
            maxVisible={7}
          />
        </Section>

        {/* ── Miller's Law + Chunking ────────────────────────────────────── */}
        <Section title="Miller's Law + Chunking" law="7 ± 2">
          <p className="ux-attention-secondary" style={{ marginBottom: 'var(--ux-space-4)' }}>
            9 items chunked into groups of 3 — each group is a Common Region.
          </p>
          <ChunkedGrid
            items={GRID_ITEMS}
            chunkSize={3}
            chunkLabel={(i, total) => `Group ${i + 1} of ${total}`}
            renderItem={(item) => (
              <div>
                <div className="ux-attention-secondary" style={{ fontWeight: 600 }}>{item.title}</div>
                <HierarchyBadge
                  label={item.status}
                  variant={item.status === 'online' ? 'success' : item.status === 'building' ? 'warning' : 'muted'}
                  dot
                />
              </div>
            )}
          />
        </Section>

        {/* ── Tesler's Law + Postel's Law ────────────────────────────────── */}
        <Section title="Tesler's Law + Postel's Law" law="Smart Forms">
          <p className="ux-attention-secondary" style={{ marginBottom: 'var(--ux-space-4)' }}>
            Complexity absorbed by the system — validation, normalisation, ARIA all automatic.
          </p>
          <div className="ux-flex-col ux-gap-4" style={{ maxWidth: '480px' }}>
            <SmartField
              label="Email address"
              type="email"
              hint="We'll only use this for critical alerts"
              required
              validate={v => v.includes('@') ? null : 'Must be a valid email address'}
              autoComplete="email"
            />
            <SmartField
              label="API key prefix"
              hint="Enter the first 8 characters of your key"
              validate={v => v.length >= 8 ? null : 'Must be at least 8 characters'}
            />
          </div>
        </Section>

        {/* ── Pareto Principle ──────────────────────────────────────────── */}
        <Section title="Pareto Principle" law="80 / 20">
          <ParetoInsight items={PARETO_ITEMS} title="Service request distribution" />
        </Section>

        {/* ── Cognitive Load + Hick + Jakob (Accordion) ─────────────────── */}
        <Section title="Cognitive Load — Progressive Disclosure" law="Accordion">
          <AccordionCluster
            items={ACCORDION_ITEMS}
            label="UX Laws reference"
            defaultOpen={['fitts']}
          />
        </Section>

        {/* ── Von Restorff + Similarity + Badges ────────────────────────── */}
        <Section title="Von Restorff + Law of Similarity" law="Badges">
          <p className="ux-attention-secondary" style={{ marginBottom: 'var(--ux-space-4)' }}>
            Consistent badge family (Similarity) + amber Highlight breaks the pattern (Von Restorff).
          </p>
          <div className="ux-flex ux-gap-2" style={{ flexWrap: 'wrap' }}>
            <HierarchyBadge label="Online"    variant="success"   dot />
            <HierarchyBadge label="Building"  variant="warning"   dot />
            <HierarchyBadge label="Planned"   variant="muted"     dot />
            <HierarchyBadge label="Critical"  variant="danger"    dot />
            <HierarchyBadge label="Featured"  variant="highlight" />
            <HierarchyBadge label="AI-Powered" variant="primary"  dot />
          </div>
        </Section>

        {/* ── Fitts's Law — Button sizes ─────────────────────────────────── */}
        <Section title="Fitts's Law — Adaptive Buttons" law="Target size">
          <p className="ux-attention-secondary" style={{ marginBottom: 'var(--ux-space-4)' }}>
            Primary = 52 px min-height. Secondary = 48 px. Tertiary = 44 px (WCAG minimum).
          </p>
          <div className="ux-flex ux-gap-4 ux-items-center" style={{ flexWrap: 'wrap' }}>
            <AdaptiveButton importance="primary">Deploy to Production</AdaptiveButton>
            <AdaptiveButton importance="secondary">Review Changes</AdaptiveButton>
            <AdaptiveButton importance="tertiary">Dismiss</AdaptiveButton>
          </div>
        </Section>

      </div>
    </FlowZone>
  )
}
