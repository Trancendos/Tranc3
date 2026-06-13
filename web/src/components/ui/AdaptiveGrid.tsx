import React, { useRef, useState, useEffect, useCallback } from "react";

interface AdaptiveGridProps {
  children: React.ReactNode;
  minItemWidth?: number;
  gap?: string;
  className?: string;
}

const AdaptiveGrid: React.FC<AdaptiveGridProps> = ({
  children,
  minItemWidth = 250,
  gap = "1rem",
  className = "",
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [columns, setColumns] = useState<number>(1);

  const recalculate = useCallback(() => {
    if (!containerRef.current) return;
    const containerWidth = containerRef.current.offsetWidth;
    // Parse gap to pixels (simplified: assume rem = 16px if not px)
    const gapPx = gap.endsWith("px")
      ? parseFloat(gap)
      : parseFloat(gap) * 16;
    const cols = Math.max(
      1,
      Math.floor((containerWidth + gapPx) / (minItemWidth + gapPx))
    );
    setColumns(cols);
  }, [minItemWidth, gap]);

  useEffect(() => {
    recalculate();
    if (!containerRef.current) return;

    const ro = new ResizeObserver(() => {
      recalculate();
    });
    ro.observe(containerRef.current);
    return () => ro.disconnect();
  }, [recalculate]);

  const gridStyle: React.CSSProperties = {
    display: "grid",
    gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))`,
    gap,
    width: "100%",
    boxSizing: "border-box",
  };

  return (
    <div ref={containerRef} className={className} style={gridStyle}>
      {children}
    </div>
  );
};

export default AdaptiveGrid;
