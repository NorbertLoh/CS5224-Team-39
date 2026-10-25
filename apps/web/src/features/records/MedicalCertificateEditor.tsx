import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { saveMedicalCertificate, recordsError } from './api'
import { mcEndDate, type MedicalCertificate } from './medicalCertificate'
import { MedicalCertificateFields } from './MedicalCertificateFields'
import { ErrorState } from '../../components/ErrorState'
import { FileCheck2 } from 'lucide-react'
import { Button } from '../../components/ui/button'
import {
  useRecordFormState,
  type RecordFormStateChange,
} from './useRecordFormState'

export function MedicalCertificateEditor({
  appointmentId,
  draft,
  editable,
  onStateChange,
}: {
  appointmentId: string
  draft: MedicalCertificate | null
  editable: boolean
  onStateChange?: RecordFormStateChange
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
  useRecordFormState(current !== saved, mutation.isPending, onStateChange)
  return (
    <form
      className="space-y-4 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"
      aria-label="Medical certificate"
      onSubmit={(event) => {
        event.preventDefault()
        if (!locked && (!selected || end)) mutation.mutate()
      }}
    >
      <div className="flex items-center gap-3">
        <span className="rounded-lg bg-teal-50 p-2 text-teal-800">
          <FileCheck2 aria-hidden="true" size={18} />
        </span>
        <h3 className="font-semibold">Medical certificate</h3>
        <span className="ml-auto rounded-full bg-slate-100 px-2 py-1 text-xs text-slate-600">
          Optional
        </span>
      </div>
      <p className="text-sm text-slate-600">
        Save your selection before completing the visit. The MC is issued after
        completion; private visit notes are excluded.
      </p>
      <label className="flex items-center gap-3 rounded-xl bg-slate-50 p-3 text-sm font-medium">
        <input
          type="checkbox"
          className="size-4 accent-teal-700"
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
        <Button
          className="h-10 px-4"
          disabled={locked || current === saved || (selected && !end)}
        >
          {mutation.isPending ? 'Saving MC draft...' : 'Save MC draft'}
        </Button>
      )}
      {current !== saved && (
        <p role="status" className="text-xs text-amber-800">
          MC has unsaved changes.
        </p>
      )}
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
