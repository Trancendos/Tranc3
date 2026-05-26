/**
 * TokenBot — Cryptographic Token Generation & Verification Bot for Infinity
 *
 * Identity:  NID-INFINITY-TOKEN
 * Tier:      5 (Stateless Nanoservice / Function)
 * Parent:    GuardianAI (AID-GUARDIAN)
 *
 * Responsibilities:
 *   - GENERATE: Create cryptographic tokens (access, refresh, API, service)
 *   - VERIFY:   Validate token integrity, expiry, and signature
 *   - REFRESH:  Issue new tokens from valid refresh tokens
 *   - REVOKE:   Mark tokens as revoked in the denial list
 *   - INSPECT:  Decode token claims without verification (debug)
 *
 * "The token is the atom of trust — a quantum of identity sealed in
 *  cryptographic certainty. Every token carries within it the weight
 *  of the authority that issued it, and the expiry of its mandate."
 */

import { Bot, Logger, AuditLedger } from '../../../core/definitions'
import { randomBytes, createHmac } from 'crypto'

const auditLedger = new AuditLedger();

// ─────────────────────────────────────────────────────────────────────────────
// Input / Output Types
// ─────────────────────────────────────────────────────────────────────────────

export interface TokenInput {
  operation: 'GENERATE' | 'VERIFY' | 'REFRESH' | 'REVOKE' | 'INSPECT';
  userId?: string;
  type?: 'access' | 'refresh' | 'api' | 'service';
  token?: string;
  refreshToken?: string;
  scopes?: string[];
  expiresIn?: number;
  issuer?: string;
  audience?: string;
}

export interface TokenClaims {
  sub: string;
  iss: string;
  aud: string;
  iat: number;
  exp: number;
  jti: string;
  type: TokenInput['type'];
  scopes: string[];
  sid: string;
}

export interface GeneratedToken {
  token: string;
  type: TokenInput['type'];
  claims: TokenClaims;
  expiresAt: Date;
  createdAt: Date;
}

export interface VerificationResult {
  valid: boolean;
  claims: TokenClaims | null;
  reason: string | null;
  expiresAt: Date | null;
  verifiedAt: Date;
}

export interface TokenResult {
  success: boolean;
  operation: TokenInput['operation'];
  generated?: GeneratedToken;
  verification?: VerificationResult;
  revoked?: boolean;
  message: string;
  timestamp: Date;
}

// ─────────────────────────────────────────────────────────────────────────────
// Token Storage (Zero-Cost In-Memory)
// ─────────────────────────────────────────────────────────────────────────────

let tokenCounter = 0;
const revokedTokens: Set<string> = new Set();
const HMAC_SECRET = randomBytes(32).toString('hex');

// ─────────────────────────────────────────────────────────────────────────────
// TokenBot Implementation
// ─────────────────────────────────────────────────────────────────────────────

export class TokenBot extends Bot {
  private readonly log: Logger;
  private readonly audit: AuditLedger;

  constructor() {
    super(
      'NID-INFINITY-TOKEN',
      'Token',
      async (input: TokenInput) => this.handleOperation(input),
      'Generates, verifies, refreshes, and revokes cryptographic tokens for the Infinity auth system'
    );

    this.log = new Logger('TokenBot');
    this.audit = auditLedger;
  }

  private async handleOperation(input: TokenInput): Promise<TokenResult> {
    switch (input.operation) {
      case 'GENERATE':
        return this.generateToken(input);
      case 'VERIFY':
        return this.verifyToken(input);
      case 'REFRESH':
        return this.refreshToken(input);
      case 'REVOKE':
        return this.revokeToken(input);
      case 'INSPECT':
        return this.inspectToken(input);
      default:
        return {
          success: false,
          operation: input.operation,
          message: `Unknown operation: ${input.operation}`,
          timestamp: new Date(),
        };
    }
  }

  // ─────────────────────────────────────────────────────────────────────────
  // GENERATE
  // ─────────────────────────────────────────────────────────────────────────

  private generateToken(input: TokenInput): TokenResult {
    tokenCounter++;
    const now = new Date();
    const expiresIn = input.expiresIn ?? 3600;
    const type = input.type ?? 'access';
    const issuer = input.issuer ?? 'tranc3-infinity';
    const audience = input.audience ?? 'tranc3-ecosystem';
    const userId = input.userId ?? `USR-${tokenCounter}`;
    const jti = `TKN-${tokenCounter.toString().padStart(8, '0')}`;
    const sid = `SES-${tokenCounter.toString().padStart(8, '0')}`;

    const claims: TokenClaims = {
      sub: userId,
      iss: issuer,
      aud: audience,
      iat: Math.floor(now.getTime() / 1000),
      exp: Math.floor(now.getTime() / 1000) + expiresIn,
      jti,
      type,
      scopes: input.scopes ?? [],
      sid,
    };

    // Create signed token (HMAC-SHA256)
    const payload = Buffer.from(JSON.stringify(claims)).toString('base64url');
    const signature = createHmac('sha256', HMAC_SECRET).update(payload).digest('base64url');
    const token = `${payload}.${signature}`;

    const generated: GeneratedToken = {
      token,
      type,
      claims,
      expiresAt: new Date(now.getTime() + expiresIn * 1000),
      createdAt: now,
    };

    this.audit.append({
      actor: 'NID-INFINITY-TOKEN',
      action: 'GENERATE_TOKEN',
      entity: jti,
      status: 'SUCCESS',
      details: { type, userId, scopes: claims.scopes },
    });

    return {
      success: true,
      operation: 'GENERATE',
      generated,
      message: `${type} token generated for ${userId} — expires in ${expiresIn}s`,
      timestamp: now,
    };
  }

  // ─────────────────────────────────────────────────────────────────────────
  // VERIFY
  // ─────────────────────────────────────────────────────────────────────────

  private verifyToken(input: TokenInput): TokenResult {
    const token = input.token ?? '';
    const now = new Date();

    if (revokedTokens.has(token)) {
      return {
        success: false,
        operation: 'VERIFY',
        verification: {
          valid: false,
          claims: null,
          reason: 'Token has been revoked',
          expiresAt: null,
          verifiedAt: now,
        },
        message: 'Token verification failed — token revoked',
        timestamp: now,
      };
    }

    try {
      const [payload, signature] = token.split('.');
      if (!payload || !signature) throw new Error('Malformed token');

      // Verify HMAC signature
      const expectedSig = createHmac('sha256', HMAC_SECRET).update(payload).digest('base64url');
      if (signature !== expectedSig) {
        return {
          success: false,
          operation: 'VERIFY',
          verification: {
            valid: false,
            claims: null,
            reason: 'Invalid signature',
            expiresAt: null,
            verifiedAt: now,
          },
          message: 'Token verification failed — invalid signature',
          timestamp: now,
        };
      }

      const claims: TokenClaims = JSON.parse(Buffer.from(payload, 'base64url').toString('utf-8'));

      // Check expiry
      if (claims.exp < Math.floor(now.getTime() / 1000)) {
        return {
          success: false,
          operation: 'VERIFY',
          verification: {
            valid: false,
            claims,
            reason: 'Token expired',
            expiresAt: new Date(claims.exp * 1000),
            verifiedAt: now,
          },
          message: 'Token verification failed — expired',
          timestamp: now,
        };
      }

      return {
        success: true,
        operation: 'VERIFY',
        verification: {
          valid: true,
          claims,
          reason: null,
          expiresAt: new Date(claims.exp * 1000),
          verifiedAt: now,
        },
        message: `Token verified for ${claims.sub} (${claims.type})`,
        timestamp: now,
      };
    } catch (err) {
      return {
        success: false,
        operation: 'VERIFY',
        verification: {
          valid: false,
          claims: null,
          reason: 'Malformed token',
          expiresAt: null,
          verifiedAt: now,
        },
        message: 'Token verification failed — malformed',
        timestamp: now,
      };
    }
  }

  // ─────────────────────────────────────────────────────────────────────────
  // REFRESH / REVOKE / INSPECT
  // ─────────────────────────────────────────────────────────────────────────

  private refreshToken(input: TokenInput): TokenResult {
    // Verify the refresh token first, then issue a new access token
    const verifyResult = this.verifyToken({ operation: 'VERIFY', token: input.refreshToken });

    if (!verifyResult.success || !verifyResult.verification?.valid) {
      return {
        success: false,
        operation: 'REFRESH',
        message: 'Refresh token invalid or expired',
        timestamp: new Date(),
      };
    }

    const oldClaims = verifyResult.verification.claims!;
    return this.generateToken({
      operation: 'GENERATE',
      userId: oldClaims.sub,
      type: 'access',
      scopes: oldClaims.scopes,
    });
  }

  private revokeToken(input: TokenInput): TokenResult {
    const token = input.token ?? '';
    revokedTokens.add(token);

    this.audit.append({
      actor: 'NID-INFINITY-TOKEN',
      action: 'REVOKE_TOKEN',
      entity: 'token',
      status: 'SUCCESS',
    });

    return {
      success: true,
      operation: 'REVOKE',
      revoked: true,
      message: 'Token revoked successfully',
      timestamp: new Date(),
    };
  }

  private inspectToken(input: TokenInput): TokenResult {
    const token = input.token ?? '';

    try {
      const [payload] = token.split('.');
      const claims: TokenClaims = JSON.parse(Buffer.from(payload, 'base64url').toString('utf-8'));

      return {
        success: true,
        operation: 'INSPECT',
        verification: {
          valid: false,
          claims,
          reason: 'Inspection mode — signature not verified',
          expiresAt: new Date(claims.exp * 1000),
          verifiedAt: new Date(),
        },
        message: `Token inspected — subject: ${claims.sub}, type: ${claims.type}`,
        timestamp: new Date(),
      };
    } catch {
      return {
        success: false,
        operation: 'INSPECT',
        message: 'Cannot inspect — malformed token',
        timestamp: new Date(),
      };
    }
  }
}
