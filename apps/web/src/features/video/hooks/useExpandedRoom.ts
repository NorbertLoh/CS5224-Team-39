import type { KeyboardEvent } from 'react'
import { useEffect, useRef } from 'react'

export function useExpandedRoom(expanded: boolean, onLeave: () => void) {
  const room = useRef<HTMLElement>(null)
  const joinButton = useRef<HTMLButtonElement>(null)
  const leaveButton = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (!expanded) return
    const previousOverflow = document.body.style.overflow
    const previousFocus = document.activeElement as HTMLElement | null
    document.body.style.overflow = 'hidden'
    leaveButton.current?.focus()
    return () => {
      document.body.style.overflow = previousOverflow
      if (room.current) (joinButton.current ?? previousFocus)?.focus()
    }
  }, [expanded])

  const handleKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    if (!expanded) return
    if (event.key === 'Escape') {
      event.preventDefault()
      onLeave()
      return
    }
    if (event.key !== 'Tab') return

    const controls = Array.from(
      room.current?.querySelectorAll<HTMLElement>(
        'a[href], button:not(:disabled), input:not(:disabled), textarea:not(:disabled), select:not(:disabled)',
      ) ?? [],
    ).filter(
      (element) =>
        element.getClientRects().length &&
        !element.closest('fieldset:disabled'),
    )
    const first = controls[0]
    const last = controls[controls.length - 1]
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault()
      last?.focus()
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault()
      first?.focus()
    }
  }

  return { room, joinButton, leaveButton, handleKeyDown }
}
