import React, { useRef, useState } from "react";

interface LiquidCardProps {
  children: React.ReactNode;
  elevated?: boolean;
  onClick?: () => void;
  className?: string;
  morphOnHover?: boolean;
}

const LiquidCard: React.FC<LiquidCardProps> = ({
  children,
  elevated = false,
  onClick,
  className = "",
  morphOnHover = true,
}) => {
  const [hovered, setHovered] = useState(false);
  const cardRef = useRef<HTMLDivElement>(null);

  const baseRadius = "1rem";
  const hoveredRadius = morphOnHover ? "1.5rem 0.75rem 1.5rem 0.75rem" : baseRadius;

  const baseShadow = elevated
    ? "0 8px 24px rgba(0,0,0,0.12), 0 2px 6px rgba(0,0,0,0.08)"
    : "0 1px 4px rgba(0,0,0,0.08)";

  const hoveredShadow = elevated
    ? "0 16px 40px rgba(0,0,0,0.16), 0 4px 12px rgba(0,0,0,0.10)"
    : "0 6px 20px rgba(0,0,0,0.12), 0 2px 6px rgba(0,0,0,0.07)";

  const style: React.CSSProperties = {
    borderRadius: hovered ? hoveredRadius : baseRadius,
    boxShadow: hovered ? hoveredShadow : baseShadow,
    background: hovered
      ? "linear-gradient(135deg, #ffffff 0%, #f8faff 100%)"
      : "#ffffff",
    padding: "1.25rem",
    transform: hovered ? "translateY(-2px) scale(1.005)" : "translateY(0) scale(1)",
    transition:
      "border-radius 0.4s cubic-bezier(0.34, 1.56, 0.64, 1), " +
      "box-shadow 0.3s ease, " +
      "background 0.3s ease, " +
      "transform 0.3s cubic-bezier(0.34, 1.56, 0.64, 1)",
    cursor: onClick ? "pointer" : "default",
    outline: "none",
    border: "1px solid rgba(0,0,0,0.06)",
    overflow: "hidden",
    position: "relative",
    willChange: "transform, box-shadow, border-radius",
  };

  // Ripple/shimmer overlay on hover
  const overlayStyle: React.CSSProperties = {
    position: "absolute",
    inset: 0,
    background: "linear-gradient(135deg, rgba(255,255,255,0.3) 0%, transparent 60%)",
    opacity: hovered ? 1 : 0,
    transition: "opacity 0.3s ease",
    pointerEvents: "none",
    borderRadius: "inherit",
  };

  return (
    <div
      ref={cardRef}
      className={className}
      style={style}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      onClick={onClick}
      role={onClick ? "button" : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={
        onClick
          ? (e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onClick();
              }
            }
          : undefined
      }
    >
      <div style={overlayStyle} aria-hidden="true" />
      <div style={{ position: "relative", zIndex: 1 }}>{children}</div>
    </div>
  );
};

export default LiquidCard;
