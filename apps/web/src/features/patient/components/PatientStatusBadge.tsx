export function PatientStatusBadge({
  label,
  colour,
}: {
  label: string
  colour: string
}) {
  return (
    <span
      className={`rounded-full px-2.5 py-1 text-xs font-medium capitalize ring-1 ring-inset ${colour}`}
    >
      {label}
    </span>
  )
}
