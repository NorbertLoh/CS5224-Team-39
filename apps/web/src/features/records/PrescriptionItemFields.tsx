import type { Medication, PrescriptionInput } from './types'
const field = 'rounded border px-3 py-2'
export function PrescriptionItemFields({
  item,
  index,
  medications,
  onChange,
  onRemove,
}: {
  item: PrescriptionInput
  index: number
  medications: Medication[]
  onChange: (change: Partial<PrescriptionInput>) => void
  onRemove: () => void
}) {
  return (
    <fieldset className="space-y-3 rounded border p-4">
      <legend className="px-1">Medication {index + 1}</legend>
      <label className="flex flex-col gap-2">
        Medication
        <select
          className={field}
          required
          value={item.medication_id}
          onChange={(event) => onChange({ medication_id: event.target.value })}
        >
          <option value="">Choose from clinic catalogue</option>
          {item.medication_id &&
            !medications.some(
              (medication) => medication.medication_id === item.medication_id,
            ) && (
              <option value={item.medication_id}>
                Unavailable medication — choose a replacement
              </option>
            )}
          {medications.map((medication) => (
            <option
              key={medication.medication_id}
              value={medication.medication_id}
            >
              {medication.display_name} ({medication.unit_label})
            </option>
          ))}
        </select>
      </label>
      <label className="flex flex-col gap-2">
        Quantity (dispensing units)
        <input
          className={field}
          type="number"
          min="1"
          max="10000"
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
          maxLength={20000}
          onChange={(event) => onChange({ instructions: event.target.value })}
        />
      </label>
      <button
        type="button"
        className="rounded border px-4 py-2"
        onClick={onRemove}
      >
        Remove medication {index + 1}
      </button>
    </fieldset>
  )
}
