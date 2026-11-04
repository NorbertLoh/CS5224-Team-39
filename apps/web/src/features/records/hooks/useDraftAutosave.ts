import { useEffect } from 'react'

// Cancel queued saves when fields change, editing locks or the form unmounts.
export function useDraftAutosave(
  enabled: boolean,
  valueKey: string,
  save: () => void,
) {
  useEffect(() => {
    if (!enabled) return
    const timer = window.setTimeout(save, 1000)
    return () => window.clearTimeout(timer)
  }, [enabled, valueKey, save])
}
