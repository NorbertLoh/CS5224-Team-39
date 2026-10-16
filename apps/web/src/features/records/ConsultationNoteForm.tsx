import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { saveNote, recordsError } from './api'
import type { Note } from './types'
import { ErrorState } from '../../components/ErrorState'

export function ConsultationNoteForm({
  appointmentId,
  note,
  editable,
  onFailure,
}: {
  appointmentId: string
  note: Note | null
  editable: boolean
  onFailure: () => void
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
  return (
    <form
      className="space-y-3"
      onSubmit={(event) => {
        event.preventDefault()
        if (editable && !save.isPending && text.trim()) save.mutate()
      }}
    >
      <label className="flex flex-col gap-2">
        Consultation note
        <textarea
          className="rounded border px-3 py-2"
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
      <button
        className="rounded border px-4 py-2 disabled:opacity-50"
        disabled={
          !editable ||
          save.isPending ||
          !text.trim() ||
          text.trim() === savedText
        }
      >
        {save.isPending ? 'Saving note...' : 'Save note'}
      </button>
      {text.trim() !== savedText && (
        <p className="text-sm text-slate-600">Note has unsaved changes.</p>
      )}
      {save.isSuccess && <p role="status">Note saved.</p>}
      {save.isError && <ErrorState message={recordsError(save.error)} />}
    </form>
  )
}
