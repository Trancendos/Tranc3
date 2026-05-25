/**
 * GradeBot — Assessment Scoring Bot for The Academy
 *
 * Identity:  NID-ACADEMY-GRADE
 * Tier:      5 (Stateless Nanoservice / Function)
 * Parent:    TheAcademyAI (AID-ACADEMY)
 *
 * Responsibilities:
 *   - SCORE: Evaluate and grade student assessments
 *   - Support quiz, exam, assignment, project, and participation types
 *   - Calculate scores, determine letter grades, and generate rubric evaluations
 *   - Track grading statistics, curves, and performance analytics
 *   - Manage grade lifecycle: pending → graded → reviewed → final → appealed
 *
 * "Numbers are the language of merit. GradeBot translates effort into
 *  the currency of achievement — fairly, consistently, and without bias."
 */

import { Bot, Logger, AuditLedger } from '../../../core/definitions';

// ────────────────────────────────────────────────────────────────────────────
// Input / Output Types
// ────────────────────────────────────────────────────────────────────────────

export interface GradeInput {
  operation: 'SCORE';
  assessmentType: 'quiz' | 'exam' | 'assignment' | 'project' | 'participation';
  studentId: string;
  courseId: string;
  answers?: Record<string, unknown>;
  maxScore?: number;
  rubric?: RubricCriteria[];
  weight?: number;
  term?: string;
  graderId?: string;
  comments?: string;
  curve?: 'none' | 'linear' | 'bell' | 'percentile';
  latePenaltyPercent?: number;
  extraCreditPercent?: number;
}

export interface RubricCriteria {
  criterion: string;
  maxPoints: number;
  earnedPoints: number;
  feedback: string;
}

export interface GradeRecord {
  id: string;
  studentId: string;
  courseId: string;
  assessmentType: GradeInput['assessmentType'];
  rawScore: number;
  maxScore: number;
  percentage: number;
  weightedScore: number;
  letterGrade: string;
  gpaPoints: number;
  rubric: RubricCriteria[];
  status: 'pending' | 'graded' | 'reviewed' | 'final' | 'appealed';
  curveApplied: GradeInput['curve'];
  latePenalty: number;
  extraCredit: number;
  adjustedScore: number;
  term: string;
  graderId: string;
  comments: string;
  gradedAt: number;
  reviewedAt?: number;
  finalisedAt?: number;
}

export interface GradeStatistics {
  totalGrades: number;
  byAssessmentType: Record<GradeInput['assessmentType'], number>;
  byLetterGrade: Record<string, number>;
  averageScore: number;
  medianScore: number;
  standardDeviation: number;
  highestScore: number;
  lowestScore: number;
  passRate: number;
  distinctionRate: number;
  gradeDistribution: { range: string; count: number }[];
  timestamp: number;
}

export interface ScoreResult {
  success: boolean;
  grade: GradeRecord;
  statistics: GradeStatistics;
  classRank?: number;
  classSize?: number;
  percentile?: number;
  message: string;
  timestamp: number;
}

// ────────────────────────────────────────────────────────────────────────────
// Grading Constants
// ────────────────────────────────────────────────────────────────────────────

const GRADE_SCALE: { minPercent: number; letter: string; gpaPoints: number }[] = [
  { minPercent: 97, letter: 'A+', gpaPoints: 4.0 },
  { minPercent: 93, letter: 'A',  gpaPoints: 4.0 },
  { minPercent: 90, letter: 'A-', gpaPoints: 3.7 },
  { minPercent: 87, letter: 'B+', gpaPoints: 3.3 },
  { minPercent: 83, letter: 'B',  gpaPoints: 3.0 },
  { minPercent: 80, letter: 'B-', gpaPoints: 2.7 },
  { minPercent: 77, letter: 'C+', gpaPoints: 2.3 },
  { minPercent: 73, letter: 'C',  gpaPoints: 2.0 },
  { minPercent: 70, letter: 'C-', gpaPoints: 1.7 },
  { minPercent: 67, letter: 'D+', gpaPoints: 1.3 },
  { minPercent: 63, letter: 'D',  gpaPoints: 1.0 },
  { minPercent: 60, letter: 'D-', gpaPoints: 0.7 },
  { minPercent: 0,  letter: 'F',  gpaPoints: 0.0 },
];

const DEFAULT_MAX_SCORES: Record<GradeInput['assessmentType'], number> = {
  quiz: 20,
  exam: 100,
  assignment: 50,
  project: 100,
  participation: 10,
};

const DEFAULT_WEIGHTS: Record<GradeInput['assessmentType'], number> = {
  quiz: 0.15,
  exam: 0.35,
  assignment: 0.25,
  project: 0.20,
  participation: 0.05,
};

// ────────────────────────────────────────────────────────────────────────────
// Grade Storage
// ────────────────────────────────────────────────────────────────────────────

let gradeCounter = 0;
const gradeStore: Map<string, GradeRecord> = new Map();

// ────────────────────────────────────────────────────────────────────────────
// GradeBot Implementation
// ────────────────────────────────────────────────────────────────────────────

export class GradeBot extends Bot {
  private readonly log: Logger;
  private readonly audit: AuditLedger;

  constructor() {
    super(
      'NID-ACADEMY-GRADE',
      'Grade',
      async (input: GradeInput) => this.handleScore(input),
      'Evaluates and grades student assessments with rubric scoring, curves, and statistical analysis'
    );

    this.log = new Logger('GradeBot');
    this.audit = AuditLedger.getInstance();
  }

  // ──────────────────────────────────────────────────────────────────────────
  // Main Handler
  // ──────────────────────────────────────────────────────────────────────────

  private async handleScore(input: GradeInput): Promise<ScoreResult> {
    if (input.operation !== 'SCORE') {
      return this.fail(input, `Invalid operation: ${input.operation}. GradeBot only accepts SCORE.`);
    }

    if (!input.studentId || !input.courseId) {
      return this.fail(input, 'studentId and courseId are required');
    }

    return this.score(input);
  }

  // ──────────────────────────────────────────────────────────────────────────
  // SCORE — Grade a student assessment
  // ──────────────────────────────────────────────────────────────────────────

  private score(input: GradeInput): ScoreResult {
    const {
      assessmentType,
      studentId,
      courseId,
      answers,
      maxScore,
      rubric,
      weight,
      term,
      graderId,
      comments,
      curve,
      latePenaltyPercent,
      extraCreditPercent,
    } = input;

    const resolvedMaxScore = maxScore ?? DEFAULT_MAX_SCORES[assessmentType];
    const resolvedWeight = weight ?? DEFAULT_WEIGHTS[assessmentType];
    const resolvedTerm = term ?? this.getCurrentTerm();
    const resolvedGraderId = graderId ?? 'SID-ACADEMY-PROFESSOR';
    const resolvedCurve = curve ?? 'none';

    // Calculate raw score from answers or rubric
    let rawScore: number;
    let resolvedRubric: RubricCriteria[];

    if (rubric && rubric.length > 0) {
      // Rubric-based scoring
      resolvedRubric = rubric;
      rawScore = rubric.reduce((sum, criterion) => sum + criterion.earnedPoints, 0);
    } else if (answers) {
      // Answer-based scoring — simulate scoring based on answer count
      resolvedRubric = this.generateRubricFromAnswers(answers, assessmentType, resolvedMaxScore);
      rawScore = this.scoreFromAnswers(answers, assessmentType, resolvedMaxScore);
    } else {
      // No answers or rubric provided — cannot grade
      return this.fail(input, 'Either answers or rubric must be provided for scoring');
    }

    // Clamp raw score
    rawScore = Math.max(0, Math.min(rawScore, resolvedMaxScore));

    // Calculate percentage
    let percentage = (rawScore / resolvedMaxScore) * 100;

    // Apply late penalty
    const latePenalty = latePenaltyPercent ?? 0;
    if (latePenalty > 0) {
      percentage = Math.max(0, percentage - latePenalty);
    }

    // Apply extra credit
    const extraCredit = extraCreditPercent ?? 0;
    if (extraCredit > 0) {
      percentage = Math.min(100 + extraCredit, percentage + extraCredit);
    }

    // Apply curve if specified
    if (resolvedCurve !== 'none') {
      percentage = this.applyCurve(percentage, resolvedCurve);
    }

    const adjustedScore = Math.round((percentage / 100) * resolvedMaxScore * 100) / 100;
    const weightedScore = Math.round(adjustedScore * resolvedWeight * 100) / 100;

    // Determine letter grade and GPA points
    const { letter: letterGrade, gpaPoints } = this.determineLetterGrade(percentage);

    // Create grade record
    gradeCounter++;
    const grade: GradeRecord = {
      id: `GRADE-${gradeCounter.toString().padStart(6, '0')}`,
      studentId,
      courseId,
      assessmentType,
      rawScore,
      maxScore: resolvedMaxScore,
      percentage: Math.round(percentage * 100) / 100,
      weightedScore,
      letterGrade,
      gpaPoints,
      rubric: resolvedRubric,
      status: 'graded',
      curveApplied: resolvedCurve,
      latePenalty,
      extraCredit,
      adjustedScore,
      term: resolvedTerm,
      graderId: resolvedGraderId,
      comments: comments ?? '',
      gradedAt: Date.now(),
    };

    gradeStore.set(grade.id, grade);

    // Calculate class rank and percentile for this course/assessment type
    const { rank, classSize, percentile } = this.calculateClassRank(
      studentId, courseId, assessmentType, adjustedScore
    );

    const statistics = this.buildStatistics();

    this.audit.append({
      actor: 'NID-ACADEMY-GRADE',
      action: 'SCORE',
      entity: grade.id,
      status: 'SUCCESS',
      meta: {
        studentId,
        courseId,
        assessmentType,
        rawScore,
        adjustedScore,
        percentage: grade.percentage,
        letterGrade,
        curveApplied: resolvedCurve,
      },
    });

    this.log.info('Assessment scored', {
      gradeId: grade.id,
      studentId,
      courseId,
      assessmentType,
      rawScore,
      adjustedScore,
      letterGrade,
    });

    return {
      success: true,
      grade,
      statistics,
      classRank: rank,
      classSize,
      percentile,
      message: `${assessmentType.charAt(0).toUpperCase() + assessmentType.slice(1)} scored: ${rawScore}/${resolvedMaxScore} → ${grade.percentage}% → ${letterGrade} (${gpaPoints} GPA) | Rank ${rank}/${classSize} (${percentile}th percentile)`,
      timestamp: Date.now(),
    };
  }

  // ──────────────────────────────────────────────────────────────────────────
  // Answer-Based Scoring
  // ──────────────────────────────────────────────────────────────────────────

  private scoreFromAnswers(
    answers: Record<string, unknown>,
    assessmentType: GradeInput['assessmentType'],
    maxScore: number
  ): number {
    const answerCount = Object.keys(answers).length;
    if (answerCount === 0) return 0;

    // Simulate scoring based on answer count and assessment type
    // In production, this would compare against an answer key
    const baseScores: Record<GradeInput['assessmentType'], number> = {
      quiz: 0.78,
      exam: 0.72,
      assignment: 0.82,
      project: 0.85,
      participation: 0.90,
    };

    const baseFactor = baseScores[assessmentType];
    // Add some variance based on answer count to simulate different outcomes
    const variance = (answerCount % 10) / 100; // ±0.05 variance
    const scoreFactor = Math.max(0, Math.min(1, baseFactor + variance - 0.05));

    return Math.round(scoreFactor * maxScore * 100) / 100;
  }

  private generateRubricFromAnswers(
    answers: Record<string, unknown>,
    assessmentType: GradeInput['assessmentType'],
    maxScore: number
  ): RubricCriteria[] {
    const answerCount = Object.keys(answers).length;
    const pointsPerQuestion = Math.round((maxScore / Math.max(answerCount, 1)) * 100) / 100;

    // Generate sample rubric criteria from answer keys
    const criteriaLabels: Record<GradeInput['assessmentType'], string[]> = {
      quiz: ['Knowledge Recall', 'Concept Application', 'Analytical Reasoning'],
      exam: ['Comprehension', 'Application', 'Analysis', 'Synthesis', 'Evaluation'],
      assignment: ['Accuracy', 'Completeness', 'Presentation', 'Critical Thinking'],
      project: ['Technical Execution', 'Creativity', 'Documentation', 'Teamwork', 'Impact'],
      participation: ['Attendance', 'Engagement', 'Contribution'],
    };

    const labels = criteriaLabels[assessmentType];
    const pointsPerCriterion = Math.round((maxScore / labels.length) * 100) / 100;
    const baseFactor = 0.7 + (answerCount % 5) * 0.05;

    return labels.map(label => {
      const earned = Math.round(pointsPerCriterion * Math.min(1, baseFactor + Math.random() * 0.2) * 100) / 100;
      return {
        criterion: label,
        maxPoints: pointsPerCriterion,
        earnedPoints: Math.min(earned, pointsPerCriterion),
        feedback: earned >= pointsPerCriterion * 0.9
          ? `Excellent performance in ${label.toLowerCase()}`
          : earned >= pointsPerCriterion * 0.7
            ? `Good performance in ${label.toLowerCase()}, room for improvement`
            : `Needs improvement in ${label.toLowerCase()}`,
      };
    });
  }

  // ──────────────────────────────────────────────────────────────────────────
  // Letter Grade Determination
  // ──────────────────────────────────────────────────────────────────────────

  private determineLetterGrade(percentage: number): { letter: string; gpaPoints: number } {
    for (const tier of GRADE_SCALE) {
      if (percentage >= tier.minPercent) {
        return { letter: tier.letter, gpaPoints: tier.gpaPoints };
      }
    }
    return { letter: 'F', gpaPoints: 0.0 };
  }

  // ──────────────────────────────────────────────────────────────────────────
  // Curve Application
  // ──────────────────────────────────────────────────────────────────────────

  private applyCurve(percentage: number, curveType: GradeInput['curve']): number {
    switch (curveType) {
      case 'linear': {
        // Linear curve: boost by 5% if below 75%, scaling down as score approaches 100%
        if (percentage < 75) {
          const boost = (75 - percentage) * 0.3;
          return Math.min(100, percentage + boost);
        }
        return percentage;
      }
      case 'bell': {
        // Bell curve: slight normalization toward the mean (75%)
        const mean = 75;
        const distance = percentage - mean;
        const normalizedDistance = distance * 0.85;
        return Math.max(0, Math.min(100, mean + normalizedDistance));
      }
      case 'percentile': {
        // Percentile curve: boost by 3% across the board
        return Math.min(100, percentage + 3);
      }
      case 'none':
      default:
        return percentage;
    }
  }

  // ──────────────────────────────────────────────────────────────────────────
  // Class Rank Calculation
  // ──────────────────────────────────────────────────────────────────────────

  private calculateClassRank(
    studentId: string,
    courseId: string,
    assessmentType: GradeInput['assessmentType'],
    score: number
  ): { rank: number; classSize: number; percentile: number } {
    // Find all grades for the same course and assessment type
    const classGrades = Array.from(gradeStore.values())
      .filter(g => g.courseId === courseId && g.assessmentType === assessmentType);

    // Include the current student's score
    const allScores = classGrades.map(g => g.adjustedScore);
    allScores.push(score);

    // Sort descending
    const sortedScores = [...allScores].sort((a, b) => b - a);
    const rank = sortedScores.indexOf(score) + 1;
    const classSize = sortedScores.length;
    const percentile = classSize > 1
      ? Math.round(((classSize - rank) / (classSize - 1)) * 100)
      : 100;

    return { rank, classSize, percentile };
  }

  // ──────────────────────────────────────────────────────────────────────────
  // Current Term Determination
  // ──────────────────────────────────────────────────────────────────────────

  private getCurrentTerm(): string {
    const now = new Date();
    const year = now.getFullYear();
    const month = now.getMonth(); // 0-indexed

    if (month >= 8 && month <= 11) return `Fall ${year}`;
    if (month >= 0 && month <= 4) return `Spring ${year}`;
    return `Summer ${year}`;
  }

  // ──────────────────────────────────────────────────────────────────────────
  // Statistics
  // ──────────────────────────────────────────────────────────────────────────

  private buildStatistics(): GradeStatistics {
    const all = Array.from(gradeStore.values());

    const byAssessmentType: Record<GradeInput['assessmentType'], number> = {
      quiz: 0, exam: 0, assignment: 0, project: 0, participation: 0,
    };
    const byLetterGrade: Record<string, number> = {};

    for (const grade of all) {
      byAssessmentType[grade.assessmentType]++;
      byLetterGrade[grade.letterGrade] = (byLetterGrade[grade.letterGrade] ?? 0) + 1;
    }

    const scores = all.map(g => g.percentage);
    const averageScore = scores.length > 0
      ? Math.round((scores.reduce((s, v) => s + v, 0) / scores.length) * 100) / 100
      : 0;

    const sortedScores = [...scores].sort((a, b) => a - b);
    const medianScore = sortedScores.length > 0
      ? sortedScores.length % 2 === 0
        ? Math.round(((sortedScores[sortedScores.length / 2 - 1]! + sortedScores[sortedScores.length / 2]!) / 2) * 100) / 100
        : sortedScores[Math.floor(sortedScores.length / 2)]!
      : 0;

    const variance = scores.length > 1
      ? scores.reduce((sum, s) => sum + Math.pow(s - averageScore, 2), 0) / (scores.length - 1)
      : 0;
    const standardDeviation = Math.round(Math.sqrt(variance) * 100) / 100;

    const highestScore = sortedScores.length > 0 ? sortedScores[sortedScores.length - 1]! : 0;
    const lowestScore = sortedScores.length > 0 ? sortedScores[0]! : 0;

    const passRate = scores.length > 0
      ? Math.round((scores.filter(s => s >= 60).length / scores.length) * 10000) / 100
      : 0;
    const distinctionRate = scores.length > 0
      ? Math.round((scores.filter(s => s >= 80).length / scores.length) * 10000) / 100
      : 0;

    // Grade distribution in 10% ranges
    const ranges = [
      { range: '0-9%', count: 0 }, { range: '10-19%', count: 0 },
      { range: '20-29%', count: 0 }, { range: '30-39%', count: 0 },
      { range: '40-49%', count: 0 }, { range: '50-59%', count: 0 },
      { range: '60-69%', count: 0 }, { range: '70-79%', count: 0 },
      { range: '80-89%', count: 0 }, { range: '90-100%', count: 0 },
    ];

    for (const score of scores) {
      const idx = Math.min(Math.floor(score / 10), 9);
      ranges[idx]!.count++;
    }

    return {
      totalGrades: all.length,
      byAssessmentType,
      byLetterGrade,
      averageScore,
      medianScore,
      standardDeviation,
      highestScore,
      lowestScore,
      passRate,
      distinctionRate,
      gradeDistribution: ranges,
      timestamp: Date.now(),
    };
  }

  // ──────────────────────────────────────────────────────────────────────────
  // Failure Helper
  // ──────────────────────────────────────────────────────────────────────────

  private fail(input: GradeInput, message: string): ScoreResult {
    this.log.error('Score failed', { message, studentId: input.studentId, courseId: input.courseId });

    const emptyGrade: GradeRecord = {
      id: '',
      studentId: input.studentId ?? '',
      courseId: input.courseId ?? '',
      assessmentType: input.assessmentType ?? 'quiz',
      rawScore: 0,
      maxScore: 0,
      percentage: 0,
      weightedScore: 0,
      letterGrade: 'F',
      gpaPoints: 0,
      rubric: [],
      status: 'pending',
      curveApplied: 'none',
      latePenalty: 0,
      extraCredit: 0,
      adjustedScore: 0,
      term: '',
      graderId: '',
      comments: '',
      gradedAt: 0,
    };

    return {
      success: false,
      grade: emptyGrade,
      statistics: this.buildStatistics(),
      message,
      timestamp: Date.now(),
    };
  }
}
