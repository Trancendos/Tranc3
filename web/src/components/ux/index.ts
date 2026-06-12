/**
 * Tranc3 UX Component Cell Library — Laws of UX as modular, composable components.
 *
 * All 30 Laws of UX encoded as reactive React cells:
 *   Fitts, Hick, Miller, Zeigarnik, Goal-Gradient, Peak-End, Jakob,
 *   Gestalt (Proximity, Common Region, Similarity, Uniform Connectedness,
 *   Prägnanz), Aesthetic-Usability, Doherty, Tesler, Postel, Serial Position,
 *   Von Restorff, Selective Attention, Working Memory, Cognitive Load,
 *   Cognitive Bias, Flow, Pareto, Parkinson, Occam's Razor, Mental Model.
 */

// ── Primitive cells ──────────────────────────────────────────────────────────
export { ProgressBar }        from './ProgressBar'        // Zeigarnik + Goal-Gradient
export { StepIndicator }      from './StepIndicator'      // Goal-Gradient + Serial Position
export { SkeletonCell }       from './SkeletonCell'        // Doherty Threshold
export { ChoiceGroup }        from './ChoiceGroup'         // Hick's Law + Choice Overload
export { ChunkedGrid }        from './ChunkedGrid'         // Miller's Law + Common Region
export { SmartField }         from './SmartField'          // Tesler's Law + Postel's Law
export { CelebrationWrapper } from './CelebrationWrapper'  // Peak-End Rule
export { SelectiveList }      from './SelectiveList'       // Selective Attention + Serial + Von Restorff
export { HierarchyBadge }     from './HierarchyBadge'      // Similarity + Von Restorff
export { AdaptiveButton }     from './AdaptiveButton'      // Fitts's Law + Aesthetic-Usability

// ── Cluster components ───────────────────────────────────────────────────────
export { AccordionCluster }   from './AccordionCluster'   // Cognitive Load + Hick + Jakob
export { FlowZone }           from './FlowZone'           // Flow + Working Memory
export { ParetoInsight }      from './ParetoInsight'      // Pareto + Von Restorff
export { StatusIndicator }    from './StatusIndicator'    // Nielsen #1: Visibility of System Status

// ── Figma Design Principles — Fluidic / Adaptive / Intelligent cells ─────────
export { VisualHierarchy }         from './VisualHierarchy'       // Visual hierarchy + typographic scale
export { ProgressiveDisclosure }   from './ProgressiveDisclosure' // Progressive disclosure (click/scroll/time/hover)
export { AdaptiveGrid, GridCell }  from './AdaptiveGrid'          // Liquid responsive grid (auto-fit/fill/fixed)
export { SmartCard }               from './SmartCard'             // State-machine card (idle→loading→success|error)
export { FocusTrap }               from './FocusTrap'             // ARIA APG dialog focus management
export { ContrastBadge, ContrastPreview } from './ContrastBadge'  // WCAG contrast ratio checker
export { ToastCluster, useToast }  from './ToastCluster'          // Managed toast notifications

// ── Hooks (re-exported for direct use) ──────────────────────────────────────
export {
  useDoherty,
  useFitts,
  useHicks,
  useMiller,
  useGoalGradient,
  useZeigarnik,
  usePeakEnd,
  useAesthetic,
  useSerialPosition,
  useVonRestorff,
  useCognitiveLoad,
  useWorkingMemory,
  useTesler,
  usePostel,
  useSelectiveAttention,
  usePareto,
  useFlow,
  useJakob,
} from '../../hooks/useUxLaws'
