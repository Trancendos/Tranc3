import * as React from "react"
import { cn } from "@/lib/utils"
import { Badge } from "./badge"

export interface DocumentCardProps extends React.HTMLAttributes<HTMLDivElement> {
  title: string
  filename: string
  contentType?: string
  status?: "pending" | "processing" | "indexed" | "error"
  fileSize?: number
  createdAt?: string
  tags?: string[]
  onDownload?: () => void
  onDelete?: () => void
  variant?: "default" | "glass" | "fluid"
}

const statusConfig = {
  pending: { label: "Pending", variant: "outline" as const },
  processing: { label: "Processing", variant: "fluid" as const },
  indexed: { label: "Indexed", variant: "default" as const },
  error: { label: "Error", variant: "destructive" as const },
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1048576).toFixed(1)} MB`
}

function fileIcon(contentType: string): string {
  if (contentType.includes("pdf")) return "📄"
  if (contentType.includes("image")) return "🖼️"
  if (contentType.includes("word") || contentType.includes("document")) return "📝"
  if (contentType.includes("spreadsheet") || contentType.includes("excel")) return "📊"
  if (contentType.includes("zip") || contentType.includes("compressed")) return "🗜️"
  return "📁"
}

export function DocumentCard({
  title,
  filename,
  contentType = "application/octet-stream",
  status = "pending",
  fileSize,
  createdAt,
  tags = [],
  onDownload,
  onDelete,
  variant = "default",
  className,
  ...props
}: DocumentCardProps) {
  const { label, variant: badgeVariant } = statusConfig[status]

  return (
    <div
      className={cn(
        "rounded-xl border p-4 transition-all duration-200",
        variant === "glass" && "glass glow",
        variant === "fluid" && "fluid-gradient cell-border",
        variant === "default" && "bg-card border-border hover:border-primary/40",
        "group",
        className,
      )}
      {...props}
    >
      <div className="flex items-start gap-3">
        <span className="text-2xl shrink-0 mt-0.5">{fileIcon(contentType)}</span>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="font-semibold text-sm text-foreground truncate max-w-[180px]">
              {title}
            </h3>
            <Badge variant={badgeVariant} className="text-xs shrink-0">
              {label}
            </Badge>
          </div>

          <p className="text-xs text-muted-foreground truncate mt-0.5">{filename}</p>

          <div className="flex items-center gap-3 mt-2 text-xs text-muted-foreground">
            {fileSize !== undefined && <span>{formatBytes(fileSize)}</span>}
            {createdAt && (
              <span>{new Date(createdAt).toLocaleDateString("en-GB")}</span>
            )}
          </div>

          {tags.length > 0 && (
            <div className="flex flex-wrap gap-1 mt-2">
              {tags.map((tag) => (
                <Badge key={tag} variant="cell" className="text-xs">
                  {tag}
                </Badge>
              ))}
            </div>
          )}
        </div>

        <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
          {onDownload && (
            <button
              onClick={onDownload}
              className="p-1.5 rounded-md hover:bg-primary/10 text-muted-foreground hover:text-primary transition-colors"
              aria-label="Download"
            >
              ↓
            </button>
          )}
          {onDelete && (
            <button
              onClick={onDelete}
              className="p-1.5 rounded-md hover:bg-destructive/10 text-muted-foreground hover:text-destructive transition-colors"
              aria-label="Delete"
            >
              ✕
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
