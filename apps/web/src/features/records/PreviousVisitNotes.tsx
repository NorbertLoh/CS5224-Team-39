import { useState } from 'react'
import { useInfiniteQuery, useQuery } from '@tanstack/react-query'
import { ChevronDown } from 'lucide-react'
import type { Appointment } from '../scheduling/api'
import { nameOrId } from '../appointments/display'
import { previousVisits, readNote, recordsError } from './api'
import { ErrorState } from '../../components/ErrorState'
import { LoadingState } from '../../components/LoadingState'

const visitDate = new Intl.DateTimeFormat('en-SG', {
  timeZone: 'Asia/Singapore',
  dateStyle: 'medium',
  timeStyle: 'short',
})

export function PreviousVisitNotes({
  appointment,
  token,
}: {
  appointment: Appointment
  token: string
}) {
  const history = useInfiniteQuery({
    queryKey: ['records', 'previous-visits', token, appointment.appointment_id],
    initialPageParam: null as string | null,
    queryFn: ({ pageParam, signal }) =>
      previousVisits(appointment, pageParam, signal),
    getNextPageParam: (page) => page.next_cursor ?? undefined,
    retry: false,
    gcTime: 0,
    refetchOnWindowFocus: false,
  })
  const visits = history.data?.pages.flatMap((page) => page.items) ?? []
  return (
    <section
      className="space-y-3 rounded-xl border p-4"
      aria-label="Previous visit notes"
    >
      <h3 className="font-semibold">Previous visit notes</h3>
      <p className="text-sm text-slate-600">
        Earlier completed visits for this patient with you at this clinic,
        newest first. Open a visit to read its saved note.
      </p>
      {history.isPending ? (
        <LoadingState message="Loading previous visits..." />
      ) : (
        <>
          {visits.map((visit) => (
            <VisitNote key={visit.appointment_id} visit={visit} token={token} />
          ))}
          {history.isError ? (
            <ErrorState
              message={recordsError(history.error)}
              onRetry={() =>
                void (history.isFetchNextPageError
                  ? history.fetchNextPage()
                  : history.refetch())
              }
            />
          ) : !visits.length ? (
            <p className="text-sm text-slate-600" role="status">
              No previous completed visits.
            </p>
          ) : null}
          {history.hasNextPage && !history.isError && (
            <button
              type="button"
              className="rounded border px-4 py-2 text-sm"
              disabled={history.isFetchingNextPage}
              onClick={() => void history.fetchNextPage()}
            >
              {history.isFetchingNextPage
                ? 'Loading older visits...'
                : 'Load older visits'}
            </button>
          )}
        </>
      )}
    </section>
  )
}

function VisitNote({ visit, token }: { visit: Appointment; token: string }) {
  const [open, setOpen] = useState(false)
  const note = useQuery({
    queryKey: ['records', 'previous-note', token, visit.appointment_id],
    queryFn: async ({ signal }) => {
      const saved = await readNote(visit.appointment_id, signal)
      if (
        saved &&
        ['appointment_id', 'patient_id', 'tenant_id', 'doctor_id'].some(
          (field) =>
            saved[field as keyof typeof saved] !==
            visit[field as keyof Appointment],
        )
      )
        throw new Error('Invalid previous note context')
      return saved
    },
    enabled: open,
    retry: false,
    gcTime: 0,
    refetchOnWindowFocus: false,
  })
  return (
    <details
      className="group rounded-lg border"
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 rounded-lg p-4 focus-visible:outline-2 focus-visible:outline-offset-2 [&::-webkit-details-marker]:hidden">
        <span>
          <span className="block font-medium">
            {visitDate.format(new Date(visit.starts_at))} SGT
          </span>
          <span className="block text-sm text-slate-600">
            {nameOrId(visit.doctor_name, visit.doctor_id)} · Completed visit
          </span>
        </span>
        <ChevronDown
          aria-hidden="true"
          size={20}
          className="shrink-0 text-slate-500 transition-transform group-open:rotate-180"
        />
      </summary>
      {open && (
        <div className="border-t p-4">
          {note.isPending ? (
            <LoadingState message="Loading saved note..." />
          ) : note.isError ? (
            <ErrorState
              message={recordsError(note.error)}
              onRetry={() => void note.refetch()}
            />
          ) : note.data ? (
            <p className="whitespace-pre-wrap break-words text-sm">
              {note.data.text}
            </p>
          ) : (
            <p className="text-sm text-slate-600">
              No saved note for this visit.
            </p>
          )}
        </div>
      )}
    </details>
  )
}
