/**
 * ChunkedGrid — Miller's Law + Gestalt Proximity + Common Region
 *
 * Splits items into cognitive chunks of ≤ 7 (default), wraps each
 * chunk in a clearly bounded Common Region group.
 */
import React from 'react'
import { useMiller } from '../../hooks/useUxLaws'

interface ChunkedGridProps<T> {
  items: T[]
  renderItem: (item: T, index: number) => React.ReactNode
  chunkSize?: number
  chunkLabel?: (chunkIndex: number, total: number) => string
  className?: string
  itemClassName?: string
  keyExtractor?: (item: T, index: number) => string | number
}

export function ChunkedGrid<T>({
  items, renderItem, chunkSize = 7, chunkLabel, className = '', itemClassName = '', keyExtractor
}: ChunkedGridProps<T>) {
  const chunks = useMiller(items, chunkSize)

  if (chunks.length === 1) {
    return (
      <div className={`ux-miller-chunk ${className}`} role="list">
        {items.map((item, i) => (
          <div key={keyExtractor ? keyExtractor(item, i) : i} className={`ux-miller-chunk-item ${itemClassName}`} role="listitem">
            {renderItem(item, i)}
          </div>
        ))}
      </div>
    )
  }

  return (
    <div className={`ux-flex-col ux-gap-8 ${className}`}>
      {chunks.map((chunk, ci) => (
        <section key={ci} className="ux-common-region" aria-label={chunkLabel?.(ci, chunks.length)}>
          {chunkLabel && (
            <h3 className="ux-attention-meta" style={{ marginBottom: 'var(--ux-space-4)' }}>
              {chunkLabel(ci, chunks.length)}
            </h3>
          )}
          <div className="ux-miller-chunk" role="list">
            {chunk.map((item, i) => {
              const globalIdx = ci * chunkSize + i
              return (
                <div key={keyExtractor ? keyExtractor(item, globalIdx) : globalIdx} className={`ux-miller-chunk-item ${itemClassName}`} role="listitem">
                  {renderItem(item, globalIdx)}
                </div>
              )
            })}
          </div>
        </section>
      ))}
    </div>
  )
}
