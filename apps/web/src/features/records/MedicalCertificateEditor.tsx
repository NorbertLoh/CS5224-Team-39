import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { saveMedicalCertificate, recordsError } from './api'
import { mcEndDate, type MedicalCertificate } from './medicalCertificate'
import { MedicalCertificateFields } from './MedicalCertificateFields'
import { ErrorState } from '../../components/ErrorState'

export function MedicalCertificateEditor({
  appointmentId,
  draft,
  editable,
}: {
  appointmentId: string
  draft: MedicalCertificate | null
  editable: boolean
}) {
  const [selected, setSelected] = useState(draft?.selected ?? false)
  const [start, setStart] = useState(draft?.start_date ?? '')
  const [days, setDays] = useState(String(draft?.duration_days ?? ''))
  const [notes, setNotes] = useState(draft?.additional_notes ?? '')
  const [saved, setSaved] = useState(
    JSON.stringify([selected, start, days, notes]),
  )
  const end = mcEndDate(start, days)
  const current = JSON.stringify([selected, start, days, notes])
  const mutation = useMutation({
    mutationFn: () =>
      saveMedicalCertificate(appointmentId, {
        selected,
        start_date: start || null,
        duration_days: days ? Number(days) : null,
        additional_notes: notes,
      }),
    onSuccess: (result) => {
      const values = [
        result.selected,
        result.start_date ?? '',
        String(result.duration_days ?? ''),
        result.additional_notes,
      ]
      setSelected(result.selected)
      setStart(result.start_date ?? '')
      setDays(String(result.duration_days ?? ''))
      setNotes(result.additional_notes)
      setSaved(JSON.stringify(values))
    },
    retry: false,
    gcTime: 0,
  })
  const locked = !editable || Boolean(draft?.finalized_at) || mutation.isPending
  return (
    <form
      className="space-y-3 rounded border p-4"
      aria-label="Medical certificate"
      onSubmit={(event) => {
        event.preventDefault()
        if (!locked && (!selected || end)) mutation.mutate()
      }}
    >
      <h3 className="font-semibold">Medical certificate</h3>
      <p className="text-sm text-slate-600">
        Save this draft before completing the consultation. Only the saved
        selection is issued after completion succeeds. Private consultation
        notes are excluded.
      </p>
      <label className="flex items-center gap-2">
        <input
          type="checkbox"
          checked={selected}
          disabled={locked}
          onChange={(event) => {
            setSelected(event.target.checked)
            mutation.reset()
          }}
        />
        Issue MC
      </label>
      {selected && (
        <MedicalCertificateFields
          start={start}
          days={days}
          notes={notes}
          end={end}
          disabled={locked}
          onStartChange={(value) => {
            setStart(value)
            mutation.reset()
          }}
          onDaysChange={(value) => {
            setDays(value)
            mutation.reset()
          }}
          onNotesChange={(value) => {
            setNotes(value)
            mutation.reset()
          }}
        />
      )}
      {!draft?.finalized_at && (
        <button
          className="rounded border px-4 py-2 disabled:opacity-50"
          disabled={locked || current === saved || (selected && !end)}
        >
          {mutation.isPending ? 'Saving MC draft...' : 'Save MC draft'}
        </button>
      )}
      {current !== saved && <p role="status">MC has unsaved changes.</p>}
      {mutation.isSuccess && (
        <p role="status">
          MC draft saved.{' '}
          {selected
            ? 'Will issue after consultation completion.'
            : 'No MC will be issued.'}
        </p>
      )}
      {draft?.finalized_at && (
        <p role="status">
          {draft.issued_at
            ? 'MC issued. Check Documents for PDF preparation or download.'
            : 'Consultation completed without an MC.'}
        </p>
      )}
      {mutation.isError && (
        <ErrorState
          message={`${recordsError(mutation.error)} Your MC fields are preserved; retry saving or reload to check the last outcome.`}
        />
      )}
    </form>
  )
}
