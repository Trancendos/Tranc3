/**
 * Wireframe Bot — Studio Tier 5 Bot (NID-STUDIO-WIREFRAME)
 *
 * Layout structure and wireframe generation.
 * Generates UI/UX wireframes with component placement,
 * responsive grid systems, and layout templates.
 */

import { Bot, Logger } from '../../../core/definitions';

const logger = new Logger('WireframeBot');

export interface WireframeRequest {
  layout: 'desktop' | 'tablet' | 'mobile' | 'responsive';
  components: string[];
  gridSize?: number;
  spacing?: number;
}

export interface WireframeResult {
  wireframeId: string;
  layout: string;
  dimensions: { width: number; height: number };
  components: ComponentPlacement[];
  gridSystem: GridSystem;
  responsiveBreakpoints: Breakpoint[];
}

export interface ComponentPlacement {
  name: string;
  x: number;
  y: number;
  width: number;
  height: number;
  type: string;
}

export interface GridSystem {
  columns: number;
  gutterWidth: number;
  marginWidth: number;
}

export interface Breakpoint {
  name: string;
  minWidth: number;
  maxWidth: number;
  columns: number;
}

export class WireframeBot extends Bot {
  constructor() {
    super(
      'Wireframe',
      async (request: WireframeRequest): Promise<WireframeResult> => {
        const wireframeId = `WF-${Date.now()}`;
        const gridSize = request.gridSize || 12;
        const spacing = request.spacing || 16;

        const { width, height, columns } = getLayoutDimensions(request.layout);
        const gridSystem: GridSystem = {
          columns,
          gutterWidth: spacing,
          marginWidth: spacing * 2,
        };

        // Auto-place components in a grid layout
        const components = autoPlaceComponents(request.components, columns, width, height, spacing);

        const responsiveBreakpoints: Breakpoint[] = [
          { name: 'mobile', minWidth: 0, maxWidth: 767, columns: 4 },
          { name: 'tablet', minWidth: 768, maxWidth: 1023, columns: 8 },
          { name: 'desktop', minWidth: 1024, maxWidth: 9999, columns: 12 },
        ];

        logger.debug('Wireframe generated', { layout: request.layout, components: components.length });

        return {
          wireframeId,
          layout: request.layout,
          dimensions: { width, height },
          components,
          gridSystem,
          responsiveBreakpoints,
        };
      },
      'Generates UI wireframes with component placement and responsive grid systems',
    );
  }
}

/** Get dimensions and columns for a layout type */
function getLayoutDimensions(layout: string): { width: number; height: number; columns: number } {
  switch (layout) {
    case 'desktop': return { width: 1440, height: 900, columns: 12 };
    case 'tablet': return { width: 768, height: 1024, columns: 8 };
    case 'mobile': return { width: 375, height: 812, columns: 4 };
    case 'responsive': return { width: 1440, height: 900, columns: 12 };
    default: return { width: 1440, height: 900, columns: 12 };
  }
}

/** Auto-place components in a vertical flow layout */
function autoPlaceComponents(
  componentNames: string[],
  columns: number,
  canvasWidth: number,
  canvasHeight: number,
  spacing: number,
): ComponentPlacement[] {
  const placements: ComponentPlacement[] = [];
  let currentY = spacing;

  const componentTypes: Record<string, { widthRatio: number; height: number; type: string }> = {
    'header': { widthRatio: 1, height: 64, type: 'navigation' },
    'nav': { widthRatio: 1, height: 48, type: 'navigation' },
    'sidebar': { widthRatio: 0.25, height: 400, type: 'navigation' },
    'hero': { widthRatio: 1, height: 300, type: 'content' },
    'content': { widthRatio: 0.75, height: 400, type: 'content' },
    'card': { widthRatio: 0.33, height: 200, type: 'content' },
    'footer': { widthRatio: 1, height: 80, type: 'navigation' },
    'form': { widthRatio: 0.5, height: 300, type: 'interactive' },
    'button': { widthRatio: 0.15, height: 40, type: 'interactive' },
    'image': { widthRatio: 0.5, height: 250, type: 'media' },
    'video': { widthRatio: 0.75, height: 400, type: 'media' },
    'text': { widthRatio: 0.5, height: 100, type: 'content' },
  };

  for (const name of componentNames) {
    const config = componentTypes[name.toLowerCase()] || { widthRatio: 0.5, height: 150, type: 'content' };
    const componentWidth = Math.floor(canvasWidth * config.widthRatio);
    const componentHeight = config.height;

    placements.push({
      name,
      x: spacing,
      y: currentY,
      width: componentWidth,
      height: componentHeight,
      type: config.type,
    });

    currentY += componentHeight + spacing;
  }

  return placements;
}
