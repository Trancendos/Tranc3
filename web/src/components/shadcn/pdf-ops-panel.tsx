import * as React from "react"
import { cn } from "@/lib/utils"

export type PdfOperation =
  | "merge"
  | "split"
  | "compress"
  | "rotate"
  | "watermark"
  | "ocr"
  | "convert-to-pdf"
  | "pdf-to-images"

interface PdfOp {
  id: PdfOperation
  label: string
  icon: string
  description: string
}

const PDF_OPS: PdfOp[] = [
  { id: "merge", label: "Merge", icon: "🔗", description: "Combine multiple PDFs" },
  { id: "split", label: "Split", icon: "✂️", description: "Split PDF into pages" },
  { id: "compress", label: "Compress", icon: "🗜️", description: "Reduce file size" },
  { id: "rotate", label: "Rotate", icon: "🔄", description: "Rotate pages" },
  { id: "watermark", label: "Watermark", icon: "💧", description: "Add watermark" },
  { id: "ocr", label: "OCR", icon: "🔍", description: "Extract text from scans" },
  { id: "convert-to-pdf", label: "To PDF", icon: "📄", description: "Convert documents to PDF" },
  { id: "pdf-to-images", label: "To Images", icon: "🖼️", description: "Export pages as images" },
]

export interface PdfOpsPanelProps {
  selectedOp?: PdfOperation
  onSelectOp?: (op: PdfOperation) => void
  disabledOps?: PdfOperation[]
  className?: string
}

export function PdfOpsPanel({
  selectedOp,
  onSelectOp,
  disabledOps = [],
  className,
}: PdfOpsPanelProps) {
  return (
    <div className={cn("grid grid-cols-2 sm:grid-cols-4 gap-2", className)}>
      {PDF_OPS.map((op) => {
        const isDisabled = disabledOps.includes(op.id)
        const isSelected = selectedOp === op.id
        return (
          <button
            key={op.id}
            disabled={isDisabled}
            onClick={() => !isDisabled && onSelectOp?.(op.id)}
            className={cn(
              "flex flex-col items-center gap-1.5 rounded-xl border p-3 text-center transition-all duration-150",
              isSelected
                ? "border-primary bg-primary/10 shadow-glow"
                : "border-border bg-card hover:border-primary/50 hover:bg-primary/5",
              isDisabled && "opacity-40 cursor-not-allowed",
            )}
          >
            <span className="text-2xl">{op.icon}</span>
            <span className="text-xs font-semibold text-foreground">{op.label}</span>
            <span className="text-[10px] text-muted-foreground leading-tight">
              {op.description}
            </span>
          </button>
        )
      })}
    </div>
  )
}
