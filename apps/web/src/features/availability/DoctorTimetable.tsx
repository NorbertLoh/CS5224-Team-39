import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { SelectionActions } from '@/features/availability/SelectionActions'
import type { Selection } from '@/features/availability/timetable'
import {
  cellsInSelections,
  shiftDate,
  weekStart,
} from '@/features/availability/timetable'
import { TimetableToolbar } from '@/features/availability/TimetableToolbar'
import { WeeklyTimetable } from '@/features/availability/WeeklyTimetable'
import {
  createSlot,
  listSlots,
  removeSlot,
  schedulingError,
} from '@/features/scheduling/api'
import { dayStart, singaporeDate } from '@/features/scheduling/time'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

export function DoctorTimetable({
  tenantId,
  doctorId,
  token,
}: {
  tenantId: string
  doctorId: string
  token?: string
}) {
  const cache = useQueryClient()
  const [week, setWeek] = useState(() => weekStart(singaporeDate()))
  const [selections, setSelections] = useState<Selection[]>([])
  const [message, setMessage] = useState('')
  const dates = Array.from({ length: 7 }, (_, index) => shiftDate(week, index))
  const schedule = useQuery({
    queryKey: ['scheduling', 'availability', token, tenantId, doctorId, week],
    queryFn: ({ signal }) =>
      listSlots(
        tenantId,
        dayStart(week),
        dayStart(shiftDate(week, 7)),
        doctorId,
        signal,
      ),
    refetchOnWindowFocus: true,
  })
  const cells = cellsInSelections(selections, dates)
  const mutation = useMutation({
    mutationFn: async (action: 'add' | 'remove') => {
      if (!schedule.data || schedule.isError)
        throw new Error('Refresh the timetable first.')
      const selected = schedule.data.filter((slot) =>
        cells.some(
          (cell) =>
            Date.parse(slot.starts_at) < cell.start + 1800000 &&
            Date.parse(slot.ends_at) > cell.start,
        ),
      )
      if (cells.some((cell) => cell.start <= Date.now()))
        throw new Error('Choose future times only.')
      if (action === 'add' && selected.length)
        throw new Error(
          'The selection overlaps existing availability. Select empty cells only.',
        )
      if (
        action === 'remove' &&
        (!selected.length ||
          selected.some((slot) => slot.availability !== 'available'))
      )
        throw new Error(
          'Select available slots only. Reserved slots cannot be removed.',
        )
      let completed = 0
      try {
        if (action === 'add') {
          for (const cell of cells) {
            await createSlot(tenantId, new Date(cell.start).toISOString())
            completed++
          }
        } else {
          for (const slot of selected) {
            await removeSlot(slot.slot_id)
            completed++
          }
        }
      } catch (cause) {
        throw new Error(
          `${completed} changes saved before the request stopped. ${schedulingError(cause)} Review the refreshed timetable before retrying.`,
          { cause },
        )
      }
      return completed
    },
    onSuccess: (count) => {
      setMessage(`${count} availability changes saved.`)
      setSelections([])
    },
    onSettled: async () => {
      await cache.invalidateQueries({ queryKey: ['scheduling'] })
    },
    retry: false,
  })
  function clear() {
    setSelections([])
    setMessage('')
    mutation.reset()
  }
  return (
    <>
      <fieldset disabled={mutation.isPending} className="space-y-5">
        <TimetableToolbar
          week={week}
          onWeekChange={(value) => {
            setWeek(value)
            clear()
          }}
        />
        {schedule.isPending ? (
          <LoadingState message="Loading live availability..." />
        ) : schedule.isError ? (
          <ErrorState
            message={schedulingError(schedule.error)}
            onRetry={() => void schedule.refetch()}
          />
        ) : (
          <>
            <WeeklyTimetable
              key={week}
              slots={schedule.data}
              tenantId={tenantId}
              doctorId={doctorId}
              dates={dates}
              selections={selections}
              onChange={(next) => {
                setSelections(next)
                setMessage('')
                mutation.reset()
              }}
            />
            <SelectionActions
              count={cells.length}
              onAdd={() => mutation.mutate('add')}
              onRemove={() => mutation.mutate('remove')}
              onClear={clear}
            />
          </>
        )}
      </fieldset>
      {mutation.isError && <ErrorState message={mutation.error.message} />}
      <p role="status" aria-live="polite">
        {mutation.isPending ? 'Saving availability...' : message}
      </p>
    </>
  )
}
