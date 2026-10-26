import { useEffect } from 'react'

export type RecordFormState = { dirty: boolean; busy: boolean }
export type RecordFormStateChange = (state: RecordFormState) => void

export function useRecordFormState(
  dirty: boolean,
  busy: boolean,
  onChange?: RecordFormStateChange,
) {
  useEffect(() => {
    onChange?.({ dirty, busy })
  }, [dirty, busy, onChange])
}
