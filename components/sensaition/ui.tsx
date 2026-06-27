"use client"

import type { CSSProperties, ReactNode } from "react"
import { theme } from "@/lib/theme"

export const cardStyle: CSSProperties = {
  background: theme.surface,
  border: `1px solid ${theme.border}`,
  borderRadius: 10,
  overflow: "hidden",
}

export const labelStyle: CSSProperties = {
  fontSize: 15,
  fontWeight: 700,
  letterSpacing: "0.13em",
  textTransform: "uppercase",
  color: theme.sub,
}

export const primaryButton = (background: string, color: string): CSSProperties => ({
  background,
  color,
  border: "none",
  borderRadius: 7,
  padding: "9px 16px",
  fontSize: 19.5,
  fontWeight: 600,
  cursor: "pointer",
})

export const ghostButton: CSSProperties = {
  background: "none",
  color: theme.sub,
  border: `1px solid ${theme.border}`,
  borderRadius: 7,
  padding: "9px 16px",
  fontSize: 19.5,
  fontWeight: 600,
  cursor: "pointer",
}

export function Modal({
  children,
  onClose,
  wide,
}: {
  children: ReactNode
  onClose: () => void
  wide?: boolean
}) {
  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.55)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 1000,
        padding: 20,
      }}
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: theme.surface,
          border: `1px solid ${theme.border}`,
          borderRadius: 12,
          padding: 24,
          width: "100%",
          maxWidth: wide ? 480 : 380,
        }}
      >
        {children}
      </div>
    </div>
  )
}
