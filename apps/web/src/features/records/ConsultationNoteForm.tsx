import { useState } from 'react'

export function ConsultationNoteForm({
  onStatus,
}: {
  onStatus: (message: string) => void
}) {
  const [text, setText] = useState('')
  const [savedText, setSavedText] = useState('')
  const field = 'rounded border px-3 py-2'
  const button = 'rounded border px-4 py-2 disabled:opacity-50'
  return (
    <form
      className="space-y-3"
      onSubmit={(event) => {
        event.preventDefault()
        setSavedText(text.trim())
        onStatus('Note saved in this preview.')
      }}
    >
      <label className="flex flex-col gap-2">
        Consultation note
        <textarea
          className={field}
          value={text}
          onChange={(event) => setText(event.target.value)}
          required
          rows={5}
        />
      </label>
      <button
        className={button}
        disabled={!text.trim() || text.trim() === savedText}
      >
        Save preview note
      </button>
      {text.trim() !== savedText && (
        <p className="text-sm text-slate-600">Note has unsaved changes.</p>
      )}
    </form>
  )
}
