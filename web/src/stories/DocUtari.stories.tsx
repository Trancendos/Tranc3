import type { Meta, StoryObj } from "@storybook/react"
import { DocumentCard } from "../components/shadcn/document-card"
import { UploadZone } from "../components/shadcn/upload-zone"
import { PdfOpsPanel } from "../components/shadcn/pdf-ops-panel"

// ── DocumentCard ──────────────────────────────────────────────────────────────
const docMeta: Meta<typeof DocumentCard> = {
  title: "DocUtari/DocumentCard",
  component: DocumentCard,
  tags: ["autodocs"],
  args: {
    title: "Annual Report 2025",
    filename: "annual-report-2025.pdf",
    contentType: "application/pdf",
    status: "indexed",
    fileSize: 2_457_600,
    createdAt: "2025-12-01T10:00:00Z",
    tags: ["Finance", "Report"],
  },
}
export default docMeta
type DocStory = StoryObj<typeof DocumentCard>

export const Default: DocStory = {}

export const Glass: DocStory = {
  args: { variant: "glass" },
  parameters: { backgrounds: { default: "dark" } },
}

export const Fluid: DocStory = {
  args: { variant: "fluid" },
}

export const Processing: DocStory = {
  args: { status: "processing", tags: [] },
}

export const Error: DocStory = {
  args: { status: "error", tags: ["Failed"] },
}

// ── UploadZone ────────────────────────────────────────────────────────────────
export const UploadZoneDefault: StoryObj<typeof UploadZone> = {
  render: () => (
    <UploadZone
      onFiles={(files) => console.log("Files:", files.map((f) => f.name))}
    />
  ),
  name: "UploadZone/Default",
}

export const UploadZoneGlass: StoryObj<typeof UploadZone> = {
  render: () => (
    <div className="p-8 bg-slate-900 rounded-xl">
      <UploadZone variant="glass" accept=".pdf,.docx" maxSizeMB={25} />
    </div>
  ),
  name: "UploadZone/Glass",
  parameters: { backgrounds: { default: "dark" } },
}

// ── PdfOpsPanel ───────────────────────────────────────────────────────────────
export const PdfOpsPanelDefault: StoryObj<typeof PdfOpsPanel> = {
  render: () => {
    const [selected, setSelected] =
      // eslint-disable-next-line react-hooks/rules-of-hooks
      React.useState<Parameters<typeof PdfOpsPanel>[0]["selectedOp"]>(undefined)
    return <PdfOpsPanel selectedOp={selected} onSelectOp={setSelected} />
  },
  name: "PdfOpsPanel/Default",
}

import * as React from "react"
