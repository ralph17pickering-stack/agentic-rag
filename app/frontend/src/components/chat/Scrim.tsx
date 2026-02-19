interface ScrimProps {
  visible: boolean
  onClick: () => void
}

export function Scrim({ visible, onClick }: ScrimProps) {
  if (!visible) return null

  return (
    <div
      className="absolute inset-0 z-20 bg-black/30 animate-in fade-in duration-200"
      onClick={onClick}
      aria-hidden="true"
    />
  )
}
