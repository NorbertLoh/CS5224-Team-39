import { useInfiniteQuery } from '@tanstack/react-query'
import { listClinics } from './api'
import type { Clinic } from './api'
import { consultationPrice } from '@/lib/money'
import { LoadingState } from '@/components/LoadingState'
import { ErrorState } from '@/components/ErrorState'
import { Button } from '@/components/ui/button'

export function ClinicLinks({
  clinics,
  edit = false,
  readinessPreview = false,
}: {
  clinics: Clinic[]
  edit?: boolean
  readinessPreview?: boolean
}) {
  return (
    <div className="mt-5 grid gap-5 sm:grid-cols-2">
      {clinics.map((clinic) => (
        <article
          key={clinic.tenant_id}
          className="rounded-xl border border-t-4 p-6"
          style={{ borderTopColor: clinic.branding.primary_color }}
        >
          <h3 className="text-lg font-semibold">{clinic.name}</h3>
          <p className="mt-2 text-sm text-muted-foreground">
            Consultation -{' '}
            {consultationPrice(
              clinic.consultation_price.amount_minor,
              clinic.consultation_price.currency,
            )}{' '}
            SGD
          </p>
          <div className="mt-5 flex flex-wrap gap-5 text-sm font-medium underline underline-offset-4">
            <a
              href={
                edit
                  ? `/clinic-admin/clinics/${clinic.tenant_id}/profile`
                  : `/clinics/${clinic.slug}`
              }
            >
              {edit ? 'Edit profile' : 'View clinic'}
            </a>
            {edit && (
              <a href={`/clinic-admin/clinics/${clinic.tenant_id}/staff`}>
                Manage staff
              </a>
            )}
            {edit && (
              <a href={`/clinic-admin/clinics/${clinic.tenant_id}/payments`}>
                Payments
              </a>
            )}
            {edit && readinessPreview && (
              <a
                href={`/clinic-admin/clinics/${clinic.tenant_id}/fulfilment-preview`}
              >
                Preview readiness and tracking
              </a>
            )}
          </div>
        </article>
      ))}
    </div>
  )
}

export function ClinicDirectory({ admin = false }: { admin?: boolean }) {
  const query = useInfiniteQuery({
    queryKey: ['clinics', admin],
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) => listClinics(pageParam, admin),
    getNextPageParam: (page) => page.next_cursor ?? undefined,
  })
  if (query.isPending) return <LoadingState message="Loading clinics..." />
  if (query.isError)
    return (
      <ErrorState
        message="Could not load clinics."
        onRetry={() => void query.refetch()}
      />
    )
  const clinics = query.data.pages.flatMap((page) => page.items)
  return (
    <>
      {clinics.length ? (
        <ClinicLinks clinics={clinics} edit={admin} />
      ) : (
        <p className="mt-5 text-muted-foreground">No clinics to display yet.</p>
      )}
      {query.hasNextPage && (
        <Button
          className="mt-5"
          disabled={query.isFetchingNextPage}
          onClick={() => void query.fetchNextPage()}
        >
          Load more clinics
        </Button>
      )}
    </>
  )
}
