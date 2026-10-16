import type { Prescription } from './types'
export function PrescriptionSummary({
  prescription,
  selected,
  onToggle,
}: {
  prescription: Prescription
  selected: boolean
  onToggle: () => void
}) {
  return (
    <button
      type="button"
      className="w-full rounded border p-4 text-left"
      onClick={onToggle}
      aria-expanded={selected}
    >
      <span className="block font-medium">
        Prescription · {prescription.status}
      </span>
      <span className="block text-sm">
        {new Intl.DateTimeFormat('en-SG', {
          timeZone: 'Asia/Singapore',
          dateStyle: 'medium',
        }).format(
          new Date(prescription.issued_at ?? prescription.created_at),
        )}{' '}
        · {prescription.items.length} medication(s) ·{' '}
        {selected ? 'Hide details' : 'View details'}
      </span>
      <span className="block break-all text-sm">
        Clinic: {prescription.tenant_id}
      </span>
    </button>
  )
}
