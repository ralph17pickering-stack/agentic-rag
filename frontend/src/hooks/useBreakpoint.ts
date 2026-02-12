import { useState, useEffect } from "react"

export type Breakpoint = "mobile" | "tablet" | "desktop"

function getBreakpoint(): Breakpoint {
  if (typeof window === "undefined") return "desktop"
  const w = window.innerWidth
  if (w < 768) return "mobile"
  if (w < 1024) return "tablet"
  return "desktop"
}

export function useBreakpoint(): Breakpoint {
  const [bp, setBp] = useState<Breakpoint>(getBreakpoint)

  useEffect(() => {
    const mobileQuery = window.matchMedia("(max-width: 767px)")
    const tabletQuery = window.matchMedia("(min-width: 768px) and (max-width: 1023px)")

    const update = () => setBp(getBreakpoint())

    mobileQuery.addEventListener("change", update)
    tabletQuery.addEventListener("change", update)
    return () => {
      mobileQuery.removeEventListener("change", update)
      tabletQuery.removeEventListener("change", update)
    }
  }, [])

  return bp
}
