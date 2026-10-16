import { Button } from '../../components/ui/button'

type SelectionActionsProps = {
  count: number
  onAdd: () => void
  onRemove: () => void
  onClear: () => void
}

export function SelectionActions({
  count,
  onAdd,
  onRemove,
  onClear,
}: SelectionActionsProps) {
  const summary = count
    ? `${count} ${count === 1 ? 'slot' : 'slots'} selected · ${count / 2} ${count === 2 ? 'hour' : 'hours'}`
    : 'Select times on the timetable to get started.'

  return (
    <div className="flex flex-wrap items-center justify-between gap-4 rounded-xl border bg-slate-50 p-4">
      <p className="text-sm" role="status">
        {summary}
      </p>
      <div className="flex flex-wrap gap-2">
        <Button disabled={!count} onClick={onAdd}>
          Add availability
        </Button>
        <Button variant="outline" disabled={!count} onClick={onRemove}>
          Remove availability
        </Button>
        <Button variant="ghost" disabled={!count} onClick={onClear}>
          Clear selection
        </Button>
      </div>
    </div>
  )
}
