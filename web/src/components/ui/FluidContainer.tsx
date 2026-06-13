import React from "react";

interface FluidContainerProps {
  children: React.ReactNode;
  minWidth?: string;
  maxWidth?: string;
  padding?: string;
  className?: string;
}

const FluidContainer: React.FC<FluidContainerProps> = ({
  children,
  minWidth = "320px",
  maxWidth = "1200px",
  padding = "clamp(1rem, 4vw, 3rem)",
  className = "",
}) => {
  const style: React.CSSProperties & Record<string, string> = {
    "--fluid-min-width": minWidth,
    "--fluid-max-width": maxWidth,
    "--fluid-padding": padding,
    width: "100%",
    minWidth: "var(--fluid-min-width)",
    maxWidth: "var(--fluid-max-width)",
    marginInline: "auto",
    paddingInline: "var(--fluid-padding)",
    paddingBlock: "var(--fluid-padding)",
    boxSizing: "border-box",
    fontSize: "clamp(0.875rem, 1vw + 0.5rem, 1.125rem)",
    lineHeight: "1.6",
  };

  return (
    <div className={className} style={style}>
      {children}
    </div>
  );
};

export default FluidContainer;
