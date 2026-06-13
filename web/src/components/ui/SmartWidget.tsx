import React, {
  useState,
  useEffect,
  Suspense,
  Component,
  type ErrorInfo,
  type ReactNode,
} from "react";

// ---------------------------------------------------------------------------
// Error Boundary
// ---------------------------------------------------------------------------

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

interface ErrorBoundaryProps {
  fallback?: ReactNode;
  children: ReactNode;
}

class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error("[SmartWidget] Uncaught error:", error, info);
  }

  render(): ReactNode {
    if (this.state.hasError) {
      return (
        this.props.fallback ?? (
          <div
            style={{
              padding: "1rem",
              color: "#b91c1c",
              background: "#fef2f2",
              borderRadius: "0.5rem",
              fontSize: "0.875rem",
            }}
          >
            Something went wrong: {this.state.error?.message ?? "Unknown error"}
          </div>
        )
      );
    }
    return this.props.children;
  }
}

// ---------------------------------------------------------------------------
// Loading skeleton
// ---------------------------------------------------------------------------

const Skeleton: React.FC = () => (
  <div
    style={{
      display: "flex",
      flexDirection: "column",
      gap: "0.75rem",
      padding: "1rem",
    }}
  >
    {[80, 60, 90].map((w, i) => (
      <div
        key={i}
        style={{
          height: "1rem",
          width: `${w}%`,
          background: "linear-gradient(90deg, #e5e7eb 25%, #f3f4f6 50%, #e5e7eb 75%)",
          backgroundSize: "200% 100%",
          borderRadius: "0.25rem",
          animation: "smartwidget-shimmer 1.5s infinite",
        }}
      />
    ))}
    <style>{`
      @keyframes smartwidget-shimmer {
        0% { background-position: 200% 0; }
        100% { background-position: -200% 0; }
      }
    `}</style>
  </div>
);

// ---------------------------------------------------------------------------
// Inner widget (handles async data load)
// ---------------------------------------------------------------------------

interface InnerWidgetProps {
  loadData?: () => Promise<unknown>;
  children?: ReactNode;
}

const InnerWidget: React.FC<InnerWidgetProps> = ({ loadData, children }) => {
  const [data, setData] = useState<unknown>(null);
  const [loading, setLoading] = useState<boolean>(!!loadData);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    if (!loadData) return;
    let cancelled = false;
    setLoading(true);
    loadData()
      .then((result) => {
        if (!cancelled) {
          setData(result);
          setLoading(false);
        }
      })
      .catch((err: Error) => {
        if (!cancelled) {
          setError(err);
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [loadData]);

  if (loading) return <Skeleton />;
  if (error) throw error; // bubble up to ErrorBoundary

  return (
    <>
      {children}
      {data !== null && (
        <pre
          style={{
            fontSize: "0.75rem",
            overflowX: "auto",
            padding: "0.5rem",
            background: "#f8fafc",
            borderRadius: "0.25rem",
          }}
        >
          {JSON.stringify(data, null, 2)}
        </pre>
      )}
    </>
  );
};

// ---------------------------------------------------------------------------
// SmartWidget
// ---------------------------------------------------------------------------

interface SmartWidgetProps {
  title?: string;
  loadData?: () => Promise<unknown>;
  fallback?: ReactNode;
  className?: string;
  children?: ReactNode;
}

const SmartWidget: React.FC<SmartWidgetProps> = ({
  title,
  loadData,
  fallback,
  className = "",
  children,
}) => {
  const containerStyle: React.CSSProperties = {
    border: "1px solid #e5e7eb",
    borderRadius: "0.75rem",
    overflow: "hidden",
    background: "#ffffff",
    boxShadow: "0 1px 3px rgba(0,0,0,0.08)",
  };

  const titleStyle: React.CSSProperties = {
    padding: "0.75rem 1rem",
    borderBottom: "1px solid #f3f4f6",
    fontWeight: 600,
    fontSize: "0.9375rem",
    color: "#111827",
  };

  const bodyStyle: React.CSSProperties = {
    padding: "1rem",
  };

  return (
    <div className={className} style={containerStyle}>
      {title && <div style={titleStyle}>{title}</div>}
      <div style={bodyStyle}>
        <ErrorBoundary fallback={fallback}>
          <Suspense fallback={<Skeleton />}>
            <InnerWidget loadData={loadData}>{children}</InnerWidget>
          </Suspense>
        </ErrorBoundary>
      </div>
    </div>
  );
};

export default SmartWidget;
