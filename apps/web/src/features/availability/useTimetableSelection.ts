import { useRef } from 'react'
import type { KeyboardEvent, MouseEvent, PointerEvent } from 'react'
import { applyDragSelection, deselectCell, updateSelections } from './timetable'
import type { Cell, Selection } from './timetable'

const arrowOffsets: Record<string, [number, number]> = {
  ArrowUp: [0, -1],
  ArrowDown: [0, 1],
  ArrowLeft: [-1, 0],
  ArrowRight: [1, 0],
}

export function useTimetableSelection(
  selections: Selection[],
  onChange: (selections: Selection[]) => void,
) {
  const anchor = useRef<Cell | null>(null)
  const dragging = useRef(false)
  const extending = useRef(false)
  const beforeDrag = useRef<Selection[]>([])

  function startDrag(
    event: PointerEvent<HTMLButtonElement>,
    cell: Cell,
    selected: boolean,
  ) {
    if (event.button !== 0) return
    event.preventDefault()
    event.currentTarget.focus()
    beforeDrag.current = selections
    anchor.current = cell
    dragging.current = true
    extending.current = !selected
    event.currentTarget.closest('table')!.setPointerCapture(event.pointerId)
    onChange(applyDragSelection(beforeDrag.current, { from: cell, to: cell }))
  }

  function moveDrag(event: PointerEvent<HTMLTableElement>) {
    if (!dragging.current || !anchor.current) return
    const target = document
      .elementFromPoint(event.clientX, event.clientY)
      ?.closest<HTMLElement>('[data-day][data-row]')
    if (!target || !event.currentTarget.contains(target)) return
    const cell = {
      day: Number(target.dataset.day),
      row: Number(target.dataset.row),
    }
    onChange(
      applyDragSelection(beforeDrag.current, {
        from: anchor.current,
        to: cell,
      }),
    )
  }

  function endDrag() {
    dragging.current = false
  }

  function cancelDrag() {
    endDrag()
    onChange(beforeDrag.current)
  }

  function clearWithEscape(event: KeyboardEvent<HTMLTableElement>) {
    if (event.key !== 'Escape') return
    endDrag()
    anchor.current = null
    onChange([])
  }

  function toggleCell(
    event: MouseEvent<HTMLButtonElement>,
    cell: Cell,
    selected: boolean,
  ) {
    // Pointer gestures already update selection; only handle keyboard activation here.
    if (event.detail !== 0) return
    if (selected && !event.shiftKey) {
      extending.current = false
      anchor.current = cell
      onChange(deselectCell(selections, cell))
      return
    }

    const from = event.shiftKey && anchor.current ? anchor.current : cell
    onChange(
      updateSelections(
        selections,
        { from, to: cell },
        event.shiftKey && extending.current,
      ),
    )
    if (!event.shiftKey || !anchor.current) anchor.current = cell
    extending.current = true
  }

  function moveFocus(event: KeyboardEvent<HTMLButtonElement>, cell: Cell) {
    const offset = arrowOffsets[event.key]
    if (!offset) return
    event.preventDefault()
    const next = {
      day: Math.max(0, Math.min(6, cell.day + offset[0])),
      row: Math.max(0, Math.min(47, cell.row + offset[1])),
    }
    event.currentTarget
      .closest('table')
      ?.querySelector<HTMLButtonElement>(
        `[data-day="${next.day}"][data-row="${next.row}"]`,
      )
      ?.focus()

    if (event.shiftKey) {
      if (!anchor.current) anchor.current = cell
      onChange(
        updateSelections(
          selections,
          { from: anchor.current, to: next },
          extending.current,
        ),
      )
      extending.current = true
    } else {
      anchor.current = next
      extending.current = false
    }
  }

  return {
    startDrag,
    toggleCell,
    moveFocus,
    tableHandlers: {
      onPointerMove: moveDrag,
      onPointerUp: endDrag,
      onLostPointerCapture: endDrag,
      onPointerCancel: cancelDrag,
      onKeyDown: clearWithEscape,
    },
  }
}
