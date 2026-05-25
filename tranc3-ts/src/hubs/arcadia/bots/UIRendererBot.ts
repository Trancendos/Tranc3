/**
 * UIRenderer Bot — Arcadia Tier 5 Bot (NID-ARCADIA-UI-RENDERER)
 *
 * Renders UI components with provided data.
 * Handles component lookup, data injection, and render output generation.
 * This is a server-side rendering scaffold — in production it would
 * use a real SSR framework (Next.js, Remix, etc.)
 */

import { Bot, Logger } from '../../../core/definitions';

const logger = new Logger('UIRendererBot');

/** Supported UI component types */
export type UIComponent =
  | 'forum-thread-list'
  | 'forum-post'
  | 'user-profile'
  | 'campaign-card'
  | 'mail-inbox'
  | 'notification-badge'
  | 'sidebar-nav'
  | 'dashboard-widget';

/** Render request */
export interface RenderRequest {
  component: string;
  data: Record<string, any>;
  locale?: string;
  theme?: 'light' | 'dark' | 'auto';
}

/** Render result */
export interface RenderResult {
  component: string;
  html: string;
  renderTimeMs: number;
  cacheable: boolean;
  dataHash: string;
}

export class UIRendererBot extends Bot {
  /** Simple template cache */
  private readonly templateCache: Map<string, string> = new Map();

  constructor() {
    super(
      'UIRenderer',
      async (request: RenderRequest): Promise<RenderResult> => {
        const startTime = Date.now();

        // Generate data hash for cache key
        const dataHash = simpleHash(JSON.stringify(request.data));

        // Check template cache
        const cacheKey = `${request.component}:${dataHash}`;
        const cached = this.templateCache.get(cacheKey);

        if (cached) {
          logger.debug('UI rendered from cache', { component: request.component });
          return {
            component: request.component,
            html: cached,
            renderTimeMs: Date.now() - startTime,
            cacheable: true,
            dataHash,
          };
        }

        // Render component
        const html = renderComponent(request.component as UIComponent, request.data, request.theme || 'dark');

        // Cache the result
        this.templateCache.set(cacheKey, html);

        // Limit cache size
        if (this.templateCache.size > 1000) {
          const firstKey = this.templateCache.keys().next().value;
          if (firstKey) this.templateCache.delete(firstKey);
        }

        const renderTimeMs = Date.now() - startTime;
        logger.debug('UI rendered', { component: request.component, renderTimeMs });

        return {
          component: request.component,
          html,
          renderTimeMs,
          cacheable: true,
          dataHash,
        };
      },
      'Renders UI components with data injection and template caching',
    );
  }
}

/** Simple string hash for cache keys */
function simpleHash(str: string): string {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    const char = str.charCodeAt(i);
    hash = ((hash << 5) - hash) + char;
    hash = hash & hash; // Convert to 32-bit integer
  }
  return Math.abs(hash).toString(36);
}

/** Render a component to HTML (scaffold) */
function renderComponent(component: UIComponent, data: Record<string, any>, theme: string): string {
  const themeClass = theme === 'dark' ? 'theme-dark' : 'theme-light';

  switch (component) {
    case 'forum-thread-list':
      return `<div class="${themeClass} forum-threads">${(data.threads || [])
        .map((t: any) => `<div class="thread"><h3>${t.title || 'Untitled'}</h3><span>${t.author || 'Unknown'}</span></div>`)
        .join('')}</div>`;

    case 'forum-post':
      return `<div class="${themeClass} forum-post"><h2>${data.title || ''}</h2><p>${data.content || ''}</p><span class="author">${data.author || ''}</span></div>`;

    case 'user-profile':
      return `<div class="${themeClass} user-profile"><h2>${data.username || 'User'}</h2><p>${data.bio || ''}</p></div>`;

    case 'campaign-card':
      return `<div class="${themeClass} campaign-card"><h3>${data.name || ''}</h3><p>${data.description || ''}</p><span class="status">${data.status || ''}</span></div>`;

    case 'mail-inbox':
      return `<div class="${themeClass} mail-inbox">${(data.mails || [])
        .map((m: any) => `<div class="mail-item"><span class="from">${m.from || ''}</span><span class="subject">${m.subject || ''}</span></div>`)
        .join('')}</div>`;

    case 'notification-badge':
      return `<span class="${themeClass} notification-badge">${data.count || 0}</span>`;

    case 'sidebar-nav':
      return `<nav class="${themeClass} sidebar-nav">${(data.items || [])
        .map((item: any) => `<a href="${item.href || '#'}">${item.label || ''}</a>`)
        .join('')}</nav>`;

    case 'dashboard-widget':
      return `<div class="${themeClass} dashboard-widget"><h4>${data.title || ''}</h4><div class="value">${data.value || '—'}</div></div>`;

    default:
      return `<div class="${themeClass} unknown-component">Component not found: ${component}</div>`;
  }
}
