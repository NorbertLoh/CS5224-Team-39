import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { saveNote, recordsError } from './api'
import type { Note } from './types'
import { ErrorState } from '../../components/ErrorState'
import { FilePenLine } from 'lucide-react'
import { Button } from '../../components/ui/button'
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
    mutationFn: () => saveNote(appointmentId, text),
    onSuccess: (result) => {
      setText(result.text)
      setSavedText(result.text)
    },
    onError: onFailure,
    retry: false,
    gcTime: 0,
  })
  const dirty = text.trim() !== savedText
  useRecordFormState(dirty, save.isPending, onStateChange)
  return (
    <form
      className="space-y-4 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"
      onSubmit={(event) => {
        event.preventDefault()
        if (editable && !save.isPending && text.trim()) save.mutate()
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
            save.reset()
          }}
          required
          maxLength={20000}
          rows={5}
          disabled={!editable || save.isPending}
        />
      </label>
      <Button
        className="h-10 px-4"
        disabled={
          !editable ||
          save.isPending ||
          !text.trim() ||
          text.trim() === savedText
        }
      >
        {save.isPending ? 'Saving note...' : 'Save note'}
      </Button>
      {dirty && (
        <p className="text-xs text-amber-800" role="status">
          Note has unsaved changes.
        </p>
      )}
      {save.isSuccess && (
        <p role="status" className="text-sm text-teal-800">
          Note saved.
        </p>
      )}
      {save.isError && <ErrorState message={recordsError(save.error)} />}
    </form>
  )
}
