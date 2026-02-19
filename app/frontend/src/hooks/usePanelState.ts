import { useState, useCallback, useEffect } from "react"
import type { Breakpoint } from "./useBreakpoint"

export type LeftPanelState = "collapsed" | "open-overlay" | "open-pinned"
export type RightPanelState = "hidden" | "open-overlay"

interface PanelActions {
  leftPanel: LeftPanelState
  rightPanel: RightPanelState
  toggleLeftPanel: () => void
  pinLeftPanel: () => void
  unpinLeftPanel: () => void
  closeLeftPanel: () => void
  openRightPanel: () => void
  closeRightPanel: () => void
  closeAllOverlays: () => void
}

export function usePanelState(breakpoint: Breakpoint): PanelActions {
  const [leftPanel, setLeftPanel] = useState<LeftPanelState>("collapsed")
  const [rightPanel, setRightPanel] = useState<RightPanelState>("hidden")

  // On mobile, force panels closed
  useEffect(() => {
    if (breakpoint === "mobile") {
      setLeftPanel("collapsed")
      setRightPanel("hidden")
    }
    // Tablet: unpin if pinned
    if (breakpoint === "tablet" && leftPanel === "open-pinned") {
      setLeftPanel("open-overlay")
    }
  }, [breakpoint, leftPanel])

  const toggleLeftPanel = useCallback(() => {
    setLeftPanel(prev => {
      if (prev === "collapsed") return "open-overlay"
      if (prev === "open-overlay") return "collapsed"
      // If pinned, unpin and collapse
      return "collapsed"
    })
  }, [])

  const pinLeftPanel = useCallback(() => {
    if (breakpoint === "desktop") {
      setLeftPanel("open-pinned")
      // Auto-close right panel when pinning left on narrower screens
      setRightPanel("hidden")
    }
  }, [breakpoint])

  const unpinLeftPanel = useCallback(() => {
    setLeftPanel("collapsed")
  }, [])

  const closeLeftPanel = useCallback(() => {
    setLeftPanel(prev => (prev === "open-pinned" ? "open-pinned" : "collapsed"))
  }, [])

  const openRightPanel = useCallback(() => {
    setRightPanel("open-overlay")
  }, [])

  const closeRightPanel = useCallback(() => {
    setRightPanel("hidden")
  }, [])

  const closeAllOverlays = useCallback(() => {
    setLeftPanel(prev => (prev === "open-pinned" ? "open-pinned" : "collapsed"))
    setRightPanel("hidden")
  }, [])

  // Keyboard shortcuts
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        // Close overlays (not pinned)
        closeAllOverlays()
      }
      if ((e.ctrlKey || e.metaKey) && e.key === "b") {
        e.preventDefault()
        toggleLeftPanel()
      }
    }
    window.addEventListener("keydown", handler)
    return () => window.removeEventListener("keydown", handler)
  }, [closeAllOverlays, toggleLeftPanel])

  return {
    leftPanel,
    rightPanel,
    toggleLeftPanel,
    pinLeftPanel,
    unpinLeftPanel,
    closeLeftPanel,
    openRightPanel,
    closeRightPanel,
    closeAllOverlays,
  }
}
