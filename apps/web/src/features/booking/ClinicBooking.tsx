import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { BookingFlow } from '@/features/booking/BookingFlow'
import { clinicDoctors, publicClinic } from '@/features/clinics/api'
import { useInfiniteQuery, useQuery } from '@tanstack/react-query'

export function ClinicBooking({ slug }: { slug: string }) {
  const clinic = useQuery({
    queryKey: ['public-clinic', slug],
    queryFn: () => publicClinic(slug),
  })
  const tenantId = clinic.data?.tenant_id
  const doctors = useInfiniteQuery({
    queryKey: ['clinic-doctors', tenantId],
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) => clinicDoctors(tenantId!, pageParam),
    enabled: Boolean(tenantId && clinic.data?.status === 'active'),
    getNextPageParam: (page) => page.next_cursor ?? undefined,
  })
  if (clinic.isPending) return <LoadingState message="Loading clinic..." />
  if (clinic.isError)
    return (
      <ErrorState
        message="Could not load the clinic."
        onRetry={() => void clinic.refetch()}
      />
    )
  if (clinic.data.status !== 'active')
    return <ErrorState message="This clinic is not accepting bookings." />
  if (doctors.isPending)
    return <LoadingState message="Loading consultation times..." />
  if (doctors.isError)
    return (
      <ErrorState
        message="Could not load clinic doctors."
        onRetry={() => void doctors.refetch()}
      />
    )
  return (
    <main className="mx-auto max-w-4xl space-y-6 px-6 py-10">
      <a
        href={`/clinics/${encodeURIComponent(slug)}`}
        className="text-sm underline"
      >
        Back to clinic
      </a>
      <h1 className="text-3xl font-semibold">Book at {clinic.data.name}</h1>
      <BookingFlow
        key={clinic.data.tenant_id}
        clinic={clinic.data}
        doctors={doctors.data.pages.flatMap((page) => page.items)}
      />
      {doctors.hasNextPage && (
        <button
          type="button"
          disabled={doctors.isFetchingNextPage}
          onClick={() => void doctors.fetchNextPage()}
          className="rounded border px-4 py-2"
        >
          Load more doctors' times
        </button>
      )}
    </main>
  )
}
