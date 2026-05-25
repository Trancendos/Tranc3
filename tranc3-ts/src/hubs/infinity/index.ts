/**
 * Infinity — Barrel Exports
 *
 * Hub:      Infinity
 * Pillar:   The Guardian (Anchor: Orb of Orisis)
 * Identity: AID-GUARDIAN
 */

// ── Lead AI ────────────────────────────────────────────────────────────────
export { GuardianAI } from './GuardianAI';
export type {
  GuardianUser,
  OAuthSession,
  SSOConnection,
  IAMPolicy,
  ZeroTrustAssessment,
} from './GuardianAI';

// ── Agents ─────────────────────────────────────────────────────────────────
export { AuthAgent } from './agents/AuthAgent';
export type {
  AuthInput,
  AuthPerception,
  AuthDecision,
  AuthenticationResult,
  AuthorizationResult,
  ProvisionResult,
  RevokeResult,
  AuthActionResult,
} from './agents/AuthAgent';

// ── Bots ───────────────────────────────────────────────────────────────────
export { TokenBot } from './bots/TokenBot';
export type {
  TokenInput,
  TokenClaims,
  GeneratedToken,
  VerificationResult,
  TokenResult,
} from './bots/TokenBot';
