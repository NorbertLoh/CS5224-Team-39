import type { Prescription } from './fixtures'

type PrescriptionSummaryProps = {
  prescription: Prescription
  selected: boolean
  onToggle: () => void
}

export function PrescriptionSummary({
  prescription,
  selected,
  onToggle,
}: PrescriptionSummaryProps) {
  return (
    <ul>
      <li>
        <button
          type="button"
          className="w-full rounded border p-4 text-left"
          onClick={onToggle}
          aria-expanded={selected}
        >
          <span className="block font-medium">
            Issued prescription · Demo clinic
          </span>
          <span className="block text-sm">
            12 Oct 2026 · {prescription.items.length} medication ·{' '}
            {selected ? 'Hide details' : 'View details'}
          </span>
        </button>
      </li>
    </ul>
  )
}
