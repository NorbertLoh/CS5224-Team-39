import { useCallback, useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { saveMedicalCertificate, recordsError } from './api'
import { mcEndDate, type MedicalCertificate } from './medicalCertificate'
import { MedicalCertificateFields } from './MedicalCertificateFields'
import { ErrorState } from '../../components/ErrorState'
import { FileCheck2 } from 'lucide-react'
import { Button } from '../../components/ui/button'
import { useDraftAutosave } from './useDraftAutosave'
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
  const fingerprint = (
    chosen: boolean,
    date: string,
    duration: string,
    text: string,
  ) =>
    JSON.stringify([
      chosen,
      chosen ? date : '',
      chosen ? String(Number(duration)) : '',
      text.trim(),
    ])
  const [saved, setSaved] = useState(fingerprint(selected, start, days, notes))
  const end = mcEndDate(start, days)
  const current = fingerprint(selected, start, days, notes)
  const mutation = useMutation({
    mutationFn: (submitted: Parameters<typeof saveMedicalCertificate>[1]) =>
      saveMedicalCertificate(appointmentId, submitted),
    onSuccess: (result) => {
      setSaved(
        fingerprint(
          result.selected,
          result.start_date ?? '',
          String(result.duration_days ?? ''),
          result.additional_notes,
        ),
      )
    },
    retry: false,
    gcTime: 0,
  })
  const locked = !editable || Boolean(draft?.finalized_at)
  const queueSave = useCallback(
    () =>
      mutation.mutate({
        selected,
        start_date: selected ? start || null : null,
        duration_days: selected && days ? Number(days) : null,
        additional_notes: notes,
      }),
    [mutation.mutate, selected, start, days, notes],
  )
  useDraftAutosave(
    !locked &&
      !mutation.isPending &&
      current !== saved &&
      (!selected || Boolean(end)) &&
      !mutation.isError,
    current,
    queueSave,
  )
  useRecordFormState(current !== saved, mutation.isPending, onStateChange)
  return (
    <form
      className="space-y-4 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"
      aria-label="Medical certificate"
      onSubmit={(event) => {
        event.preventDefault()
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
        Your valid MC draft saves automatically. Wait for Saved before
        completing the visit. The MC is issued after completion.
      </p>
      <label className="flex items-center gap-3 rounded-xl bg-slate-50 p-3 text-sm font-medium">
        <input
          type="checkbox"
          className="size-4 accent-teal-700"
          checked={selected}
          disabled={locked}
          onChange={(event) => {
            setSelected(event.target.checked)
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
          }}
          onDaysChange={(value) => {
            setDays(value)
          }}
          onNotesChange={(value) => {
            setNotes(value)
          }}
        />
      )}
      {!draft?.finalized_at && (
        <p role="status" className="text-xs text-amber-800">
          {mutation.isError
            ? 'MC draft not saved.'
            : mutation.isPending
              ? 'Saving MC draft…'
              : current !== saved
                ? selected && !end
                  ? 'Complete a valid start date and duration to autosave.'
                  : 'Waiting to autosave…'
                : mutation.isSuccess || draft
                  ? selected
                    ? 'MC draft saved. Will issue after consultation completion.'
                    : 'MC draft saved. No MC will be issued.'
                  : 'MC draft autosave is on.'}
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
          message={`${recordsError(mutation.error)} Your MC fields are preserved.`}
        />
      )}
      {mutation.isError && (
        <Button
          type="button"
          variant="outline"
          disabled={locked || (selected && !end)}
          onClick={() => mutation.reset()}
        >
          Retry autosave
        </Button>
      )}
    </form>
  )
}
