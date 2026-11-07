import * as React from "react"
import { cn } from "@/lib/utils"

export interface UploadZoneProps {
  onFiles?: (files: File[]) => void
  accept?: string
  maxSizeMB?: number
  multiple?: boolean
  disabled?: boolean
  className?: string
  variant?: "default" | "fluid" | "glass"
}

export function UploadZone({
  onFiles,
  accept = "*/*",
  maxSizeMB = 50,
  multiple = true,
  disabled = false,
  variant = "fluid",
  className,
}: UploadZoneProps) {
  const [dragging, setDragging] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const inputRef = React.useRef<HTMLInputElement>(null)

  const handleFiles = React.useCallback(
    (files: FileList | null) => {
      if (!files) return
      setError(null)
      const valid: File[] = []
      for (const file of Array.from(files)) {
        if (file.size > maxSizeMB * 1024 * 1024) {
          setError(`"${file.name}" exceeds ${maxSizeMB} MB limit`)
          return
        }
        valid.push(file)
      }
      onFiles?.(valid)
    },
    [maxSizeMB, onFiles],
  )

  const onDrop = React.useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      setDragging(false)
      if (!disabled) handleFiles(e.dataTransfer.files)
    },
    [disabled, handleFiles],
  )

  return (
    <div
      className={cn(
        "relative rounded-xl border-2 border-dashed p-8 text-center transition-all duration-200 cursor-pointer select-none",
        dragging && "border-primary scale-[1.01]",
        !dragging && variant === "fluid" && "border-primary/30 hover:border-primary/60",
        !dragging && variant === "glass" && "glass border-white/20 hover:border-white/40",
        !dragging && variant === "default" && "border-border hover:border-primary/40",
        disabled && "opacity-50 cursor-not-allowed",
        className,
      )}
      onDragOver={(e) => {
        e.preventDefault()
        if (!disabled) setDragging(true)
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={onDrop}
      onClick={() => !disabled && inputRef.current?.click()}
      role="button"
      tabIndex={0}
      aria-disabled={disabled}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") inputRef.current?.click()
      }}
    >
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        multiple={multiple}
        className="sr-only"
        onChange={(e) => handleFiles(e.target.files)}
        disabled={disabled}
      />

      <div className="flex flex-col items-center gap-2 pointer-events-none">
        <div
          className={cn(
            "text-4xl transition-transform duration-200",
            dragging && "scale-110",
          )}
        >
          {dragging ? "📥" : "☁️"}
        </div>
        <p className="font-semibold text-sm text-foreground">
          {dragging ? "Drop files here" : "Drag & drop files or click to browse"}
        </p>
        <p className="text-xs text-muted-foreground">
          Max {maxSizeMB} MB per file
          {accept !== "*/*" && ` · ${accept}`}
        </p>
      </div>

      {error && (
        <p className="absolute bottom-3 left-0 right-0 text-xs text-destructive px-4">
          {error}
        </p>
      )}
    </div>
  )
}
