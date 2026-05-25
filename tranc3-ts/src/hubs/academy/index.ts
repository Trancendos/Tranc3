/**
 * The Academy — Barrel Exports
 *
 * Hub:      The Academy
 * Pillar:   The Doctor
 * Identity: AID-ACADEMY
 *
 * All types, agents, bots, and the Lead AI are re-exported here
 * for clean upstream imports.
 */

// ─── Lead AI ────────────────────────────────────────────────────────────────
export { TheAcademyAI } from './TheAcademyAI';
export type {
  Student as AIStudent,
  Course as AICourse,
  Certification as AICertification,
  AcademicRecord as AIAcademicRecord,
  Curriculum as AICurriculum,
} from './TheAcademyAI';

// ─── Agents ─────────────────────────────────────────────────────────────────
export { ProfessorAgent } from './agents/ProfessorAgent';
export type {
  ProfessorInput,
  LectureContent,
  AssessmentPaper,
  AssessmentQuestion,
  MentorshipReport,
  CertificationRecommendation,
  ProfessorPerception,
  ProfessorDecision,
  ProfessorActionResult,
} from './agents/ProfessorAgent';

export { DeanAgent } from './agents/DeanAgent';
export type {
  DeanInput,
  EnrolmentResult,
  ScheduleEntry,
  ScheduleResult,
  ScheduleConflict,
  GraduationResult,
  AccreditationResult,
  AccreditationCriterion,
  DeanPerception,
  DeanDecision,
  DeanActionResult,
} from './agents/DeanAgent';

// ─── Bots ───────────────────────────────────────────────────────────────────
export { ChalkBot } from './bots/ChalkBot';
export type {
  ChalkInput,
  ChalkDocument,
  ChalkRevision,
  ChalkStats,
  ScribeResult,
} from './bots/ChalkBot';

export { GradeBot } from './bots/GradeBot';
export type {
  GradeInput,
  RubricCriteria,
  GradeRecord,
  GradeStatistics,
  ScoreResult,
} from './bots/GradeBot';

export { BellBot } from './bots/BellBot';
export type {
  BellInput,
  BellSignal,
  BellSchedule,
  BellHistory,
  BellStats,
  RingResult,
} from './bots/BellBot';
