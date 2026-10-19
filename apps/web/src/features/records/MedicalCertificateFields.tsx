export function MedicalCertificateFields({
  start,
  days,
  notes,
  end,
  disabled,
  onStartChange,
  onDaysChange,
  onNotesChange,
}: {
  start: string
  days: string
  notes: string
  end: string | null
  disabled: boolean
  onStartChange: (value: string) => void
  onDaysChange: (value: string) => void
  onNotesChange: (value: string) => void
}) {
  return (
    <>
      <label className="flex flex-col gap-2">
        MC start date (Singapore)
        <input
          className="rounded border px-3 py-2"
          type="date"
          min="0001-01-01"
          max="9999-12-31"
          required
          disabled={disabled}
          value={start}
          onChange={(event) => onStartChange(event.target.value)}
        />
      </label>
      <label className="flex flex-col gap-2">
        Number of days
        <input
          className="rounded border px-3 py-2"
          type="number"
          min="1"
          step="1"
          required
          disabled={disabled}
          value={days}
          onChange={(event) => onDaysChange(event.target.value)}
        />
      </label>
      <p role="status">
        {end
          ? `Inclusive end date: ${end}`
          : 'Enter a valid start date and positive whole number of days.'}
      </p>
      <label className="flex flex-col gap-2">
        Additional notes for the MC (optional)
        <textarea
          className="rounded border px-3 py-2"
          rows={3}
          maxLength={20000}
          disabled={disabled}
          value={notes}
          onChange={(event) => onNotesChange(event.target.value)}
        />
      </label>
    </>
  )
}
