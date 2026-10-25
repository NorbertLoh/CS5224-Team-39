import { useCallback, useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { saveNote, recordsError } from './api'
import type { Note } from './types'
import { ErrorState } from '../../components/ErrorState'
import { FilePenLine } from 'lucide-react'
import { useDraftAutosave } from './useDraftAutosave'
import {
  useRecordFormState,
  type RecordFormStateChange,
} from './useRecordFormState'

export function ConsultationNoteForm({
  appointmentId,
  note,
  editable,
  onFailure,
  onStateChange,
}: {
  appointmentId: string
  note: Note | null
  editable: boolean
  onFailure: () => void
  onStateChange?: RecordFormStateChange
}) {
  const [text, setText] = useState(note?.text ?? '')
  const [savedText, setSavedText] = useState(note?.text ?? '')
  const save = useMutation({
    mutationFn: (submitted: string) => saveNote(appointmentId, submitted),
    onSuccess: (result, submitted) => {
      setText((current) =>
        current.trim() === submitted.trim() ? result.text : current,
      )
      setSavedText(result.text)
    },
    onError: onFailure,
    retry: false,
    gcTime: 0,
  })
  const dirty = text.trim() !== savedText
  const queueSave = useCallback(() => save.mutate(text), [save.mutate, text])
  useDraftAutosave(
    editable &&
      dirty &&
      Boolean(text.trim()) &&
      !save.isPending &&
      !save.isError,
    text,
    queueSave,
  )
  useRecordFormState(dirty, save.isPending, onStateChange)
  return (
    <form
      className="space-y-4 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"
      onSubmit={(event) => {
        event.preventDefault()
      }}
    >
      <div className="flex items-center gap-3">
        <span className="rounded-lg bg-teal-50 p-2 text-teal-800">
          <FilePenLine aria-hidden="true" size={18} />
        </span>
        <h3 className="font-semibold">Consultation note</h3>
      </div>
      <p className="text-sm text-slate-600">
        Record your assessment and care plan for this visit.
      </p>
      <label className="flex flex-col gap-2">
        <span className="sr-only">Consultation note</span>
        <textarea
          className="min-h-36 rounded-xl border border-slate-200 bg-slate-50/50 px-3 py-3 text-sm leading-6 outline-none focus:border-teal-600 focus:ring-2 focus:ring-teal-600/15 disabled:opacity-60"
          value={text}
          onChange={(event) => {
            setText(event.target.value)
          }}
          required
          maxLength={20000}
          rows={5}
          disabled={!editable}
        />
      </label>
      <p
        role="status"
        className={`text-xs ${dirty ? 'text-amber-800' : 'text-teal-800'}`}
      >
        {save.isError
          ? 'Not saved. Your text is preserved.'
          : save.isPending
            ? 'Saving note…'
            : dirty
              ? text.trim()
                ? 'Waiting to autosave…'
                : 'A saved note cannot be empty. Add text to save your changes.'
              : savedText
                ? 'Note saved.'
                : 'Your note saves automatically after you pause typing.'}
      </p>
      {save.isError && <ErrorState message={recordsError(save.error)} />}
    </form>
  )
}
