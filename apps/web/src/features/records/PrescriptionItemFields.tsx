import type { PrescriptionInput } from './fixtures'

const field = 'rounded border px-3 py-2'
const button = 'rounded border px-4 py-2 disabled:opacity-50'

type PrescriptionItemFieldsProps = {
  item: PrescriptionInput
  index: number
  issued: boolean
  onChange: (change: Partial<PrescriptionInput>) => void
  onRemove: () => void
}

export function PrescriptionItemFields({
  item,
  index,
  issued,
  onChange,
  onRemove,
}: PrescriptionItemFieldsProps) {
  return (
    <fieldset className="space-y-3 rounded border p-4" disabled={issued}>
      <legend className="px-1">Medication {index + 1}</legend>
      <label className="flex flex-col gap-2">
        Medication name
        <input
          className={field}
          type="text"
          placeholder="Type medication name"
          required
          value={item.display_name}
          onChange={(event) => onChange({ display_name: event.target.value })}
        />
      </label>
      <label className="flex flex-col gap-2">
        Quantity (dispensing units)
        <input
          className={field}
          type="number"
          min="1"
          step="1"
          required
          value={Number.isNaN(item.quantity) ? '' : item.quantity}
          onChange={(event) =>
            onChange({ quantity: event.target.valueAsNumber })
          }
        />
      </label>
      <label className="flex flex-col gap-2">
        Instructions
        <textarea
          className={field}
          value={item.instructions}
          required
          onChange={(event) => onChange({ instructions: event.target.value })}
        />
      </label>
      {!issued && (
        <button type="button" className={button} onClick={onRemove}>
          Remove medication {index + 1}
        </button>
      )}
    </fieldset>
  )
}
