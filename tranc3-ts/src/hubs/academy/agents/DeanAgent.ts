/**
 * DeanAgent — Academic Administration Agent for The Academy
 *
 * Identity:  SID-ACADEMY-DEAN
 * Tier:      4 (Autonomous Microservice)
 * Parent:    TheAcademyAI (AID-ACADEMY)
 *
 * Responsibilities:
 *   - Enroll:    Process student enrolments, verify prerequisites,
 *                manage student records and admissions
 *   - Schedule:  Build and manage course schedules, resolve conflicts,
 *                allocate resources and time slots
 *   - Graduate:  Process graduation applications, verify degree requirements,
 *                issue diplomas and honours
 *   - Accredit:  Manage institutional accreditation, quality assurance,
 *                curriculum standards, and external reviews
 *
 * Philosophy: The Dean ensures the machinery of education runs smoothly.
 *             Behind every great scholar is an administrative foundation
 *             that made their journey possible. The DeanAgent is that
 *             foundation — methodical, fair, and unwavering.
 */

import { Agent, Logger, AuditLedger } from '../../../core/definitions'

const auditLedger = new AuditLedger();

// ─────────────────────────────────────────────────────────────────────
// Input / Output Types
// ─────────────────────────────────────────────────────────────────────

export interface DeanInput {
  operation: 'enroll' | 'schedule' | 'graduate' | 'accredit';
  studentId?: string;
  courseId?: string;
  term?: string;
  studentName?: string;
  level?: 'novice' | 'apprentice' | 'journeyman' | 'expert' | 'master';
  degreeProgram?: string;
  accreditingBody?: string;
  reviewScope?: string;
}

export interface EnrolmentResult {
  studentId: string;
  status: 'enrolled' | 'waitlisted' | 'rejected' | 'deferred';
  reason: string;
  prerequisitesMet: boolean;
  missingPrerequisites: string[];
  assignedAdvisor: string;
  initialCourses: string[];
  enrolmentDate: number;
}

export interface ScheduleEntry {
  courseId: string;
  title: string;
  instructor: string;
  timeSlot: string;
  room: string;
  enrolled: number;
  capacity: number;
  conflicts: string[];
}

export interface ScheduleResult {
  term: string;
  entries: ScheduleEntry[];
  totalCourses: number;
  totalEnrolments: number;
  conflicts: ScheduleConflict[];
  roomUtilization: number;
  generatedAt: number;
}

export interface ScheduleConflict {
  type: 'time_overlap' | 'room_overlap' | 'instructor_overlap' | 'prerequisite_chain';
  entities: string[];
  description: string;
  resolution?: string;
}

export interface GraduationResult {
  studentId: string;
  status: 'approved' | 'pending' | 'denied';
  degree: string;
  honours: 'none' | 'cum_laude' | 'magna_cum_laude' | 'summa_cum_laude';
  creditsCompleted: number;
  creditsRequired: number;
  gpa: number;
  requirementsMet: boolean;
  outstandingRequirements: string[];
  graduationDate?: number;
  diplomaId?: string;
}

export interface AccreditationResult {
  id: string;
  accreditingBody: string;
  scope: string;
  status: 'accredited' | 'probationary' | 'pending_review' | 'revoked';
  score: number;
  criteria: AccreditationCriterion[];
  validFrom: number;
  validUntil: number;
  recommendations: string[];
  nextReview: number;
}

export interface AccreditationCriterion {
  name: string;
  score: number;
  maxScore: number;
  status: 'pass' | 'warning' | 'fail';
  notes: string;
}

// ─────────────────────────────────────────────────────────────────────
// Perception / Decision / Action Types
// ─────────────────────────────────────────────────────────────────────

export interface DeanPerception {
  operation: DeanInput['operation'];
  studentId?: string;
  term?: string;
  scope: string;
  urgency: 'routine' | 'priority' | 'critical';
  estimatedWorkload: 'light' | 'moderate' | 'heavy';
}

export interface DeanDecision {
  operation: DeanInput['operation'];
  strategy: 'standard' | 'expedited' | 'comprehensive' | 'provisional';
  verificationDepth: number;
  crossCheckRecords: boolean;
  notifyStakeholders: boolean;
}

export interface DeanActionResult {
  success: boolean;
  operation: DeanInput['operation'];
  result?: EnrolmentResult | ScheduleResult | GraduationResult | AccreditationResult;
  message: string;
  timestamp: number;
}

// ─────────────────────────────────────────────────────────────────────
// Simulated Academic Data
// ─────────────────────────────────────────────────────────────────────

const ADVISORS = ['Prof. Aldric', 'Dr. Morwenna', 'Prof. Theron', 'Dr. Seraphina', 'Prof. Lucian'];

const DEGREE_REQUIREMENTS: Record<string, {
  credits: number;
  minGPA: number;
  requiredCourses: number;
  honoursThresholds: Record<string, number>;
}> = {
  'general_studies': {
    credits: 120,
    minGPA: 2.0,
    requiredCourses: 10,
    honoursThresholds: { 'cum_laude': 3.5, 'magna_cum_laude': 3.7, 'summa_cum_laude': 3.9 },
  },
  'computer_science': {
    credits: 140,
    minGPA: 2.5,
    requiredCourses: 14,
    honoursThresholds: { 'cum_laude': 3.5, 'magna_cum_laude': 3.7, 'summa_cum_laude': 3.9 },
  },
  'engineering': {
    credits: 150,
    minGPA: 2.5,
    requiredCourses: 15,
    honoursThresholds: { 'cum_laude': 3.5, 'magna_cum_laude': 3.75, 'summa_cum_laude': 3.9 },
  },
  'philosophy': {
    credits: 110,
    minGPA: 2.0,
    requiredCourses: 10,
    honoursThresholds: { 'cum_laude': 3.4, 'magna_cum_laude': 3.7, 'summa_cum_laude': 3.9 },
  },
};

// ─────────────────────────────────────────────────────────────────────
// DeanAgent Implementation
// ─────────────────────────────────────────────────────────────────────

export class DeanAgent extends Agent {
  private readonly log: Logger;
  private readonly audit: AuditLedger;
  private scheduleStore: Map<string, ScheduleResult>;
  private accreditationStore: Map<string, AccreditationResult>;
  private scheduleCounter: number;
  private accreditationCounter: number;

  constructor() {
    super('SID-ACADEMY-DEAN');
    this.log = new Logger('DeanAgent');
    this.audit = auditLedger;
    this.scheduleStore = new Map();
    this.accreditationStore = new Map();
    this.scheduleCounter = 0;
    this.accreditationCounter = 0;
  }

  // ───────────────────────────────────────────────────────────────
  // perceive — Analyse the administrative request
  // ───────────────────────────────────────────────────────────────

  async perceive(input: DeanInput): Promise<DeanPerception> {
    const operation = input.operation;
    const term = input.term ?? 'current';

    // Determine urgency
    const urgency: DeanPerception['urgency'] =
      operation === 'graduate' ? 'priority' :
      operation === 'accredit' ? 'critical' :
      'routine';

    const estimatedWorkload: DeanPerception['estimatedWorkload'] =
      operation === 'schedule' ? 'heavy' :
      operation === 'accredit' ? 'heavy' :
      operation === 'graduate' ? 'moderate' :
      'light';

    return {
      operation,
      studentId: input.studentId,
      term,
      scope: input.reviewScope ?? 'standard',
      urgency,
      estimatedWorkload,
    };
  }

  // ───────────────────────────────────────────────────────────────
  // decide — Choose the administrative strategy
  // ───────────────────────────────────────────────────────────────

  async decide(perception: DeanPerception): Promise<DeanDecision> {
    let strategy: DeanDecision['strategy'] = 'standard';
    let verificationDepth = 2;
    let crossCheckRecords = false;
    let notifyStakeholders = false;

    switch (perception.operation) {
      case 'enroll':
        strategy = 'standard';
        verificationDepth = 1;
        crossCheckRecords = true;
        notifyStakeholders = true;
        break;
      case 'schedule':
        strategy = 'comprehensive';
        verificationDepth = 3;
        crossCheckRecords = true;
        notifyStakeholders = true;
        break;
      case 'graduate':
        strategy = perception.urgency === 'priority' ? 'expedited' : 'comprehensive';
        verificationDepth = 3;
        crossCheckRecords = true;
        notifyStakeholders = true;
        break;
      case 'accredit':
        strategy = 'comprehensive';
        verificationDepth = 4;
        crossCheckRecords = true;
        notifyStakeholders = true;
        break;
    }

    return {
      operation: perception.operation,
      strategy,
      verificationDepth,
      crossCheckRecords,
      notifyStakeholders,
    };
  }

  // ───────────────────────────────────────────────────────────────
  // act — Execute the administrative operation
  // ───────────────────────────────────────────────────────────────

  async act(decision: DeanDecision): Promise<DeanActionResult> {
    this.log.info('Executing dean operation', {
      operation: decision.operation,
      strategy: decision.strategy,
      verificationDepth: decision.verificationDepth,
    });

    let result: EnrolmentResult | ScheduleResult | GraduationResult | AccreditationResult;

    switch (decision.operation) {
      case 'enroll':
        result = this.performEnrolment(decision);
        break;
      case 'schedule':
        result = this.performSchedule(decision);
        break;
      case 'graduate':
        result = this.performGraduation(decision);
        break;
      case 'accredit':
        result = this.performAccreditation(decision);
        break;
      default:
        return {
          success: false,
          operation: decision.operation,
          message: `Unknown operation: ${decision.operation}`,
          timestamp: Date.now(),
        };
    }

    this.audit.append({
      actor: 'DeanAgent',
      action: `DEAN_${decision.operation.toUpperCase()}`,
      entity: 'studentId' in result ? (result as any).studentId ?? 'batch' : 'batch',
      status: 'SUCCESS',
    });

    return {
      success: true,
      operation: decision.operation,
      result,
      message: `Dean ${decision.operation} completed via ${decision.strategy} strategy`,
      timestamp: Date.now(),
    };
  }

  // ───────────────────────────────────────────────────────────────
  // Private: Enrolment Operation
  // ───────────────────────────────────────────────────────────────

  private performEnrolment(decision: DeanDecision): EnrolmentResult {
    const studentId = `STU-${(Math.floor(Math.random() * 50) + 1).toString().padStart(6, '0')}`;
    const prerequisitesMet = Math.random() > 0.2;
    const missingPrerequisites = prerequisitesMet
      ? []
      : [`CRS-${(Math.floor(Math.random() * 10) + 1).toString().padStart(6, '0')}`, `CRS-${(Math.floor(Math.random() * 10) + 11).toString().padStart(6, '0')}`];

    const status: EnrolmentResult['status'] =
      prerequisitesMet ? 'enrolled' :
      missingPrerequisites.length <= 1 ? 'waitlisted' : 'rejected';

    // Assign initial courses
    const initialCourseCount = 3 + Math.floor(Math.random() * 3);
    const initialCourses: string[] = [];
    for (let i = 0; i < initialCourseCount; i++) {
      initialCourses.push(`CRS-${(i + 1).toString().padStart(6, '0')}`);
    }

    const result: EnrolmentResult = {
      studentId,
      status,
      reason: status === 'enrolled'
        ? 'All prerequisites met. Student enrolled successfully.'
        : status === 'waitlisted'
        ? `Missing prerequisite: ${missingPrerequisites[0]}. Student placed on waitlist.`
        : `Missing ${missingPrerequisites.length} prerequisites. Enrolment deferred.`,
      prerequisitesMet,
      missingPrerequisites,
      assignedAdvisor: ADVISORS[Math.floor(Math.random() * ADVISORS.length)],
      initialCourses: status === 'enrolled' ? initialCourses : [],
      enrolmentDate: Date.now(),
    };

    this.log.info('Enrolment processed', {
      studentId,
      status,
      prerequisitesMet,
      advisor: result.assignedAdvisor,
    });

    return result;
  }

  // ───────────────────────────────────────────────────────────────
  // Private: Schedule Operation
  // ───────────────────────────────────────────────────────────────

  private performSchedule(decision: DeanDecision): ScheduleResult {
    this.scheduleCounter++;

    const terms = ['Fall 2025', 'Spring 2026', 'Summer 2026'];
    const term = terms[this.scheduleCounter % terms.length];

    const timeSlots = ['09:00-10:30', '10:45-12:15', '13:00-14:30', '14:45-16:15', '16:30-18:00'];
    const rooms = ['Lecture Hall A', 'Lecture Hall B', 'Seminar Room 1', 'Lab 101', 'Lab 202', 'Auditorium'];

    const entries: ScheduleEntry[] = [];
    const conflicts: ScheduleConflict[] = [];

    for (let i = 0; i < 12; i++) {
      const timeSlot = timeSlots[i % timeSlots.length];
      const room = rooms[i % rooms.length];
      const enrolled = 10 + Math.floor(Math.random() * 25);
      const capacity = 30 + Math.floor(Math.random() * 20);

      entries.push({
        courseId: `CRS-${(i + 1).toString().padStart(6, '0')}`,
        title: `Course ${i + 1}`,
        instructor: ADVISORS[i % ADVISORS.length],
        timeSlot,
        room,
        enrolled,
        capacity,
        conflicts: [],
      });
    }

    // Detect conflicts (simulated)
    for (let i = 0; i < entries.length; i++) {
      for (let j = i + 1; j < entries.length; j++) {
        if (entries[i].timeSlot === entries[j].timeSlot && entries[i].room === entries[j].room) {
          const conflict: ScheduleConflict = {
            type: 'room_overlap',
            entities: [entries[i].courseId, entries[j].courseId],
            description: `${entries[i].courseId} and ${entries[j].courseId} share room ${entries[i].room} at ${entries[i].timeSlot}`,
            resolution: `Move ${entries[j].courseId} to ${rooms[(rooms.indexOf(entries[j].room) + 1) % rooms.length]}`,
          };
          conflicts.push(conflict);
          entries[i].conflicts.push(entries[j].courseId);
          entries[j].conflicts.push(entries[i].courseId);
        }
      }
    }

    const totalEnrolments = entries.reduce((sum, e) => sum + e.enrolled, 0);
    const roomUtilization = entries.filter(e => e.enrolled > 0).length / entries.length;

    const result: ScheduleResult = {
      term,
      entries,
      totalCourses: entries.length,
      totalEnrolments,
      conflicts,
      roomUtilization: Math.round(roomUtilization * 100) / 100,
      generatedAt: Date.now(),
    };

    this.scheduleStore.set(`${term}-${this.scheduleCounter}`, result);
    this.log.info('Schedule generated', { term, courses: entries.length, conflicts: conflicts.length });

    return result;
  }

  // ───────────────────────────────────────────────────────────────
  // Private: Graduation Operation
  // ───────────────────────────────────────────────────────────────

  private performGraduation(decision: DeanDecision): GraduationResult {
    const studentId = `STU-${(Math.floor(Math.random() * 50) + 1).toString().padStart(6, '0')}`;
    const degreeProgram = Object.keys(DEGREE_REQUIREMENTS)[Math.floor(Math.random() * Object.keys(DEGREE_REQUIREMENTS).length)] ?? 'general_studies';
    const requirements = DEGREE_REQUIREMENTS[degreeProgram] ?? DEGREE_REQUIREMENTS['general_studies'];

    const gpa = 2.0 + Math.random() * 2.0;
    const creditsCompleted = Math.floor(requirements.credits * (0.6 + Math.random() * 0.45));
    const completedCourses = Math.floor(requirements.requiredCourses * (0.5 + Math.random() * 0.55));

    const requirementsMet = gpa >= requirements.minGPA &&
      creditsCompleted >= requirements.credits &&
      completedCourses >= requirements.requiredCourses;

    const outstanding: string[] = [];
    if (gpa < requirements.minGPA) outstanding.push(`GPA below minimum: ${gpa.toFixed(2)} < ${requirements.minGPA}`);
    if (creditsCompleted < requirements.credits) outstanding.push(`${requirements.credits - creditsCompleted} credits remaining`);
    if (completedCourses < requirements.requiredCourses) outstanding.push(`${requirements.requiredCourses - completedCourses} required courses remaining`);

    // Determine honours
    let honours: GraduationResult['honours'] = 'none';
    if (requirementsMet && gpa >= requirements.honoursThresholds['summa_cum_laude']) honours = 'summa_cum_laude';
    else if (requirementsMet && gpa >= requirements.honoursThresholds['magna_cum_laude']) honours = 'magna_cum_laude';
    else if (requirementsMet && gpa >= requirements.honoursThresholds['cum_laude']) honours = 'cum_laude';

    const status: GraduationResult['status'] =
      requirementsMet ? 'approved' :
      outstanding.length <= 1 ? 'pending' : 'denied';

    const result: GraduationResult = {
      studentId,
      status,
      degree: degreeProgram.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()),
      honours,
      creditsCompleted,
      creditsRequired: requirements.credits,
      gpa: Math.round(gpa * 100) / 100,
      requirementsMet,
      outstandingRequirements: outstanding,
      graduationDate: status === 'approved' ? Date.now() : undefined,
      diplomaId: status === 'approved' ? `DIP-${Date.now()}` : undefined,
    };

    this.log.info('Graduation processed', {
      studentId,
      status,
      degree: degreeProgram,
      honours,
      gpa: gpa.toFixed(2),
    });

    return result;
  }

  // ───────────────────────────────────────────────────────────────
  // Private: Accreditation Operation
  // ───────────────────────────────────────────────────────────────

  private performAccreditation(decision: DeanDecision): AccreditationResult {
    this.accreditationCounter++;

    const bodies = ['Arcadian Board of Education', 'Global Academic Standards Council', 'Institute of Higher Learning'];
    const accreditingBody = bodies[this.accreditationCounter % bodies.length];

    const criteria: AccreditationCriterion[] = [
      {
        name: 'Curriculum Quality',
        score: 75 + Math.random() * 25,
        maxScore: 100,
        status: 'pass',
        notes: 'Curriculum meets or exceeds standards across all programmes',
      },
      {
        name: 'Faculty Qualifications',
        score: 70 + Math.random() * 30,
        maxScore: 100,
        status: 'pass',
        notes: 'Faculty credentials verified and current',
      },
      {
        name: 'Student Outcomes',
        score: 65 + Math.random() * 35,
        maxScore: 100,
        status: 'pass',
        notes: 'Graduation rates and employment outcomes within acceptable range',
      },
      {
        name: 'Facilities & Resources',
        score: 60 + Math.random() * 40,
        maxScore: 100,
        status: 'pass',
        notes: 'Physical and digital infrastructure meets requirements',
      },
      {
        name: 'Governance & Administration',
        score: 70 + Math.random() * 30,
        maxScore: 100,
        status: 'pass',
        notes: 'Administrative processes are transparent and effective',
      },
      {
        name: 'Research Output',
        score: 50 + Math.random() * 50,
        maxScore: 100,
        status: 'warning',
        notes: 'Research publication volume needs improvement in some departments',
      },
    ];

    // Update status based on score
    for (const criterion of criteria) {
      criterion.score = Math.round(criterion.score * 100) / 100;
      criterion.status = criterion.score >= 70 ? 'pass' : criterion.score >= 50 ? 'warning' : 'fail';
    }

    const totalScore = criteria.reduce((sum, c) => sum + c.score, 0) / criteria.length;
    const hasFailures = criteria.some(c => c.status === 'fail');
    const hasWarnings = criteria.some(c => c.status === 'warning');

    const status: AccreditationResult['status'] =
      totalScore >= 80 && !hasFailures ? 'accredited' :
      totalScore >= 70 && !hasFailures ? 'probationary' :
      hasFailures ? 'pending_review' : 'probationary';

    const result: AccreditationResult = {
      id: `ACC-${this.accreditationCounter.toString().padStart(6, '0')}`,
      accreditingBody,
      scope: decision.verificationDepth >= 3 ? 'comprehensive' : 'standard',
      status,
      score: Math.round(totalScore * 100) / 100,
      criteria,
      validFrom: Date.now(),
      validUntil: Date.now() + (365 * 24 * 60 * 60 * 1000 * (status === 'accredited' ? 5 : status === 'probationary' ? 2 : 1)),
      recommendations: [
        'Strengthen research output across all departments',
        'Implement continuous improvement tracking for flagged criteria',
        'Schedule mid-cycle review for warning areas',
        'Enhance student feedback mechanisms',
      ],
      nextReview: Date.now() + (365 * 24 * 60 * 60 * 1000 * (status === 'accredited' ? 4 : 1)),
    };

    this.accreditationStore.set(result.id, result);
    this.log.info('Accreditation review completed', {
      id: result.id,
      body: accreditingBody,
      status,
      score: totalScore.toFixed(2),
    });

    return result;
  }
}
