/**
 * CompileBot — Compilation Bot for The Lab
 *
 * Identity:  NID-LAB-COMPILE
 * Tier:      5 (Stateless Nanoservice / Function)
 * Parent:    TheLabAI (AID-LAB)
 *
 * Responsibilities:
 *   - Compile/transpile code from source to target
 *   - Detect compilation errors with precise locations
 *   - Report compilation warnings and diagnostics
 *   - Track compilation time and output metadata
 */

import { Bot, Logger } from '../../../core/definitions';

// ─────────────────────────────────────────────────────────────
// Domain Types
// ─────────────────────────────────────────────────────────────

export interface CompileInput {
  operation: 'COMPILE';
  code: string;
  language: string;
  filePath: string;
  options: Record<string, unknown>;
}

export interface CompileError {
  type: 'error' | 'warning';
  code: string;
  message: string;
  line: number;
  column: number;
  endLine?: number;
  endColumn?: number;
  category: 'syntax' | 'type' | 'reference' | 'semantic' | 'other';
}

export interface CompileResult {
  success: boolean;
  filePath: string;
  language: string;
  targetLanguage: string;
  errors: CompileError[];
  warnings: CompileError[];
  output?: string;
  sourceMap?: Record<string, unknown>;
  compilationTime: number;
  metadata: {
    inputLines: number;
    outputLines: number;
    imports: string[];
    exports: string[];
  };
}

// ─────────────────────────────────────────────────────────────
// CompileBot Implementation
// ─────────────────────────────────────────────────────────────

export class CompileBot extends Bot {
  private readonly log: Logger;

  constructor() {
    const handler = async (input: CompileInput): Promise<unknown> => {
      return this.process(input);
    };

    super(
      'NID-LAB-COMPILE',
      'Compile',
      handler,
      'Code compilation/transpilation with error detection'
    );

    this.log = new Logger('CompileBot');
  }

  private async process(input: CompileInput): Promise<CompileResult> {
    switch (input.operation) {
      case 'COMPILE':
        return this.compile(input);
      default:
        throw new Error(`CompileBot: Unknown operation "${(input as any).operation}"`);
    }
  }

  // ─────────────────────────────────────────────────────────────
  // COMPILE
  // ─────────────────────────────────────────────────────────────

  private compile(input: CompileInput): CompileResult {
    const startTime = Date.now();
    const { code, language, filePath, options } = input;
    const lines = code.split('\n');

    // Phase 1: Syntax check
    const syntaxErrors = this.checkSyntax(code, lines, language);
    if (syntaxErrors.length > 0) {
      return {
        success: false,
        filePath,
        language,
        targetLanguage: this.getTargetLanguage(language, options),
        errors: syntaxErrors,
        warnings: [],
        compilationTime: Date.now() - startTime,
        metadata: {
          inputLines: lines.length,
          outputLines: 0,
          imports: [],
          exports: [],
        },
      };
    }

    // Phase 2: Type checking (TypeScript)
    const typeErrors = this.checkTypes(code, lines, language);
    const typeWarnings = typeErrors.filter((e) => e.type === 'warning');
    const typeErrorsStrict = typeErrors.filter((e) => e.type === 'error');

    if (typeErrorsStrict.length > 0) {
      return {
        success: false,
        filePath,
        language,
        targetLanguage: this.getTargetLanguage(language, options),
        errors: typeErrorsStrict,
        warnings: typeWarnings,
        compilationTime: Date.now() - startTime,
        metadata: {
          inputLines: lines.length,
          outputLines: 0,
          imports: [],
          exports: [],
        },
      };
    }

    // Phase 3: Reference checking
    const refErrors = this.checkReferences(code, lines, language);
    const allErrors = [...refErrors.filter((e) => e.type === 'error')];
    const allWarnings = [
      ...typeWarnings,
      ...refErrors.filter((e) => e.type === 'warning'),
    ];

    // Phase 4: Generate output (simulated transpilation)
    const output = this.transpile(code, lines, language, options);
    const imports = this.extractImports(lines, language);
    const exports_ = this.extractExports(lines, language);

    const result: CompileResult = {
      success: allErrors.length === 0,
      filePath,
      language,
      targetLanguage: this.getTargetLanguage(language, options),
      errors: allErrors,
      warnings: allWarnings,
      output: output.code,
      sourceMap: options.sourceMap ? { version: 3, file: filePath } : undefined,
      compilationTime: Date.now() - startTime,
      metadata: {
        inputLines: lines.length,
        outputLines: output.code.split('\n').length,
        imports,
        exports: exports_,
      },
    };

    this.log.info('Compilation complete', {
      filePath,
      success: result.success,
      errors: allErrors.length,
      warnings: allWarnings.length,
      time: result.compilationTime,
    });

    return result;
  }

  // ─────────────────────────────────────────────────────────────
  // Syntax Checking
  // ─────────────────────────────────────────────────────────────

  private checkSyntax(code: string, lines: string[], language: string): CompileError[] {
    const errors: CompileError[] = [];

    // Brace matching
    let braceDepth = 0;
    let parenDepth = 0;
    let bracketDepth = 0;

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      const inString = this.isInString(line);

      for (let c = 0; c < line.length; c++) {
        const char = line[c];
        if (inString.has(c)) continue;

        if (char === '{') braceDepth++;
        if (char === '}') braceDepth--;
        if (char === '(') parenDepth++;
        if (char === ')') parenDepth--;
        if (char === '[') bracketDepth++;
        if (char === ']') bracketDepth--;

        if (braceDepth < 0) {
          errors.push({
            type: 'error',
            code: 'SYN-UNMATCHED-BRACE',
            message: 'Unexpected closing brace }',
            line: i + 1,
            column: c + 1,
            category: 'syntax',
          });
          braceDepth = 0;
        }
        if (parenDepth < 0) {
          errors.push({
            type: 'error',
            code: 'SYN-UNMATCHED-PAREN',
            message: 'Unexpected closing parenthesis )',
            line: i + 1,
            column: c + 1,
            category: 'syntax',
          });
          parenDepth = 0;
        }
        if (bracketDepth < 0) {
          errors.push({
            type: 'error',
            code: 'SYN-UNMATCHED-BRACKET',
            message: 'Unexpected closing bracket ]',
            line: i + 1,
            column: c + 1,
            category: 'syntax',
          });
          bracketDepth = 0;
        }
      }
    }

    if (braceDepth > 0) {
      errors.push({
        type: 'error',
        code: 'SYN-MISSING-BRACE',
        message: `Missing ${braceDepth} closing brace(s) }`,
        line: lines.length,
        column: 1,
        category: 'syntax',
      });
    }
    if (parenDepth > 0) {
      errors.push({
        type: 'error',
        code: 'SYN-MISSING-PAREN',
        message: `Missing ${parenDepth} closing parenthesis )`,
        line: lines.length,
        column: 1,
        category: 'syntax',
      });
    }

    // String literal checks
    for (let i = 0; i < lines.length; i++) {
      const trimmed = lines[i].trim();

      // Unterminated string (simplified)
      const singleQuotes = (trimmed.match(/'/g) || []).length;
      const doubleQuotes = (trimmed.match(/(?<!\\)"/g) || []).length;
      const templateQuotes = (trimmed.match(/(?<!\\)`/g) || []).length;

      if (singleQuotes % 2 !== 0 && !trimmed.includes('//')) {
        errors.push({
          type: 'error',
          code: 'SYN-UNTERMINATED-STRING',
          message: 'Unterminated string literal',
          line: i + 1,
          column: 1,
          category: 'syntax',
        });
      }
    }

    // TypeScript-specific: check for type annotations in JS
    if (language.toLowerCase() === 'javascript') {
      for (let i = 0; i < lines.length; i++) {
        if (/:\s*(?:string|number|boolean|any|void|never)\b/.test(lines[i]) && !lines[i].includes('//')) {
          errors.push({
            type: 'error',
            code: 'SYN-TYPE-IN-JS',
            message: 'Type annotations can only be used in TypeScript files',
            line: i + 1,
            column: 1,
            category: 'syntax',
          });
        }
      }
    }

    return errors;
  }

  // ─────────────────────────────────────────────────────────────
  // Type Checking (Simplified)
  // ─────────────────────────────────────────────────────────────

  private checkTypes(code: string, lines: string[], language: string): CompileError[] {
    const errors: CompileError[] = [];

    if (language.toLowerCase() !== 'typescript') return errors;

    // Check for implicit any
    for (let i = 0; i < lines.length; i++) {
      const trimmed = lines[i].trim();

      // Function parameter without type
      const funcParamMatch = trimmed.match(/function\s+\w+\s*\(([^)]*)\)/);
      if (funcParamMatch) {
        const params = funcParamMatch[1];
        if (params) {
          const paramList = params.split(',');
          for (const param of paramList) {
            const trimmedParam = param.trim();
            if (trimmedParam && !trimmedParam.includes(':') && !trimmedParam.startsWith('...')) {
              errors.push({
                type: 'warning',
                code: 'TYP-IMPLICIT-ANY',
                message: `Parameter '${trimmedParam}' implicitly has an 'any' type`,
                line: i + 1,
                column: trimmed.indexOf(trimmedParam) + 1,
                category: 'type',
              });
            }
          }
        }
      }
    }

    return errors;
  }

  // ─────────────────────────────────────────────────────────────
  // Reference Checking
  // ─────────────────────────────────────────────────────────────

  private checkReferences(code: string, lines: string[], language: string): CompileError[] {
    const errors: CompileError[] = [];

    // Check for imports that don't match exports (simplified)
    const importNames = new Set<string>();
    const declaredNames = new Set<string>();

    for (let i = 0; i < lines.length; i++) {
      const trimmed = lines[i].trim();

      // Collect imported names
      const importMatch = trimmed.match(/import\s+(?:\{([^}]+)\}|(\w+))\s+from/);
      if (importMatch) {
        if (importMatch[1]) {
          importMatch[1].split(',').forEach((name) => {
            importNames.add(name.trim().split(/\s+as\s+/)[0].trim());
          });
        }
        if (importMatch[2]) {
          importNames.add(importMatch[2]);
        }
      }

      // Collect declared names
      const constMatch = trimmed.match(/(?:export\s+)?(?:const|let|var|function|class|interface|type|enum)\s+(\w+)/);
      if (constMatch) {
        declaredNames.add(constMatch[1]);
      }
    }

    // Check for potentially unresolved references (very simplified)
    // In practice, this would use a full symbol table
    const identifiers = code.match(/\b[A-Z]\w*\b/g) ?? [];
    const knownGlobals = new Set(['Object', 'Array', 'String', 'Number', 'Boolean', 'Promise', 'Map', 'Set', 'Date', 'Error', 'JSON', 'Math', 'console', 'process', 'Buffer', 'RegExp', 'Symbol', 'BigInt', 'undefined', 'NaN', 'Infinity']);

    for (const id of [...new Set(identifiers)]) {
      if (!declaredNames.has(id) && !importNames.has(id) && !knownGlobals.has(id)) {
        // This is a very rough heuristic — in practice would need full scope analysis
        // Only warn for names that look like they should be imported
        if (id.length > 3 && /^[A-Z]/.test(id)) {
          // Could be a class/type that's not imported
          // Don't flag as error, just informational
        }
      }
    }

    return errors;
  }

  // ─────────────────────────────────────────────────────────────
  // Transpilation (Simulated)
  // ─────────────────────────────────────────────────────────────

  private transpile(
    code: string,
    lines: string[],
    language: string,
    options: Record<string, unknown>
  ): { code: string } {
    const target = this.getTargetLanguage(language, options);

    switch (language.toLowerCase()) {
      case 'typescript':
        return this.transpileTypeScript(code, options);
      case 'javascript':
        return { code: this.minifyJs(code, options) };
      default:
        return { code }; // pass-through for unsupported languages
    }
  }

  private transpileTypeScript(code: string, options: Record<string, unknown>): { code: string } {
    let output = code;

    // Remove type annotations (very simplified)
    // In production, would use the TypeScript compiler API
    output = output.replace(/:\s*(?:string|number|boolean|any|void|never|undefined|null|object|unknown|never)\b/g, '');
    output = output.replace(/:\s*[A-Z]\w*(?:<[^>]+>)?/g, ''); // custom type annotations
    output = output.replace(/<[^>]+>/g, ''); // generic type parameters
    output = output.replace(/interface\s+\w+\s*\{[^}]*\}/g, ''); // remove interfaces
    output = output.replace(/type\s+\w+\s*=\s*[^;]+;/g, ''); // remove type aliases
    output = output.replace(/enum\s+\w+\s*\{[^}]*\}/g, ''); // remove enums (simplified)
    output = output.replace(/as\s+(?:string|number|boolean|any|unknown)\b/g, ''); // remove type assertions
    output = output.replace(/!\./g, '.'); // remove non-null assertions
    output = output.replace(/(?:public|private|protected|readonly)\s+/g, ''); // remove access modifiers

    return { code: output };
  }

  private minifyJs(code: string, options: Record<string, unknown>): string {
    const minify = (options.minify as boolean) ?? false;
    if (!minify) return code;

    // Very simplified minification
    let output = code;
    output = output.replace(/\/\*[\s\S]*?\*\//g, ''); // block comments
    output = output.replace(/\/\/.*$/gm, ''); // line comments
    output = output.replace(/^\s+/gm, ''); // leading whitespace
    output = output.replace(/\n+/g, '\n'); // multiple newlines

    return output;
  }

  // ─────────────────────────────────────────────────────────────
  // Utilities
  // ─────────────────────────────────────────────────────────────

  private getTargetLanguage(language: string, options: Record<string, unknown>): string {
    if (options.target) return options.target as string;
    if (language.toLowerCase() === 'typescript') return 'javascript';
    return language;
  }

  private extractImports(lines: string[], language: string): string[] {
    const imports: string[] = [];
    for (const line of lines) {
      const match = line.match(/from\s+['"](.+?)['"]/);
      if (match) imports.push(match[1]);
    }
    return imports;
  }

  private extractExports(lines: string[], language: string): string[] {
    const exports: string[] = [];
    for (const line of lines) {
      const match = line.match(/export\s+(?:const|let|var|function|class|interface|type|enum)\s+(\w+)/);
      if (match) exports.push(match[1]);
    }
    return exports;
  }

  private isInString(line: string): Set<number> {
    const stringPositions = new Set<number>();
    let inSingleQuote = false;
    let inDoubleQuote = false;
    let inTemplate = false;

    for (let i = 0; i < line.length; i++) {
      const char = line[i];
      const prev = i > 0 ? line[i - 1] : '';

      if (prev === '\\') continue; // escaped

      if (char === "'" && !inDoubleQuote && !inTemplate) {
        inSingleQuote = !inSingleQuote;
        if (inSingleQuote) stringPositions.add(i);
      } else if (char === '"' && !inSingleQuote && !inTemplate) {
        inDoubleQuote = !inDoubleQuote;
        if (inDoubleQuote) stringPositions.add(i);
      } else if (char === '`' && !inSingleQuote && !inDoubleQuote) {
        inTemplate = !inTemplate;
        if (inTemplate) stringPositions.add(i);
      }

      if (inSingleQuote || inDoubleQuote || inTemplate) {
        stringPositions.add(i);
      }
    }

    return stringPositions;
  }
}
