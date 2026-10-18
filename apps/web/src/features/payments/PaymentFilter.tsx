export function PaymentFilter({
  label,
  value,
  options,
  onChange,
}: {
  label: string
  value: string
  options: Record<string, string>
  onChange: (value: string) => void
}) {
  return (
    <label className="block max-w-sm text-sm font-medium">
      {label}
      <select
        className="mt-2 block w-full rounded-lg border bg-white p-3"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      >
        {Object.entries(options).map(([key, optionLabel]) => (
          <option key={key} value={key}>
            {optionLabel}
          </option>
        ))}
      </select>
    </label>
  )
}
