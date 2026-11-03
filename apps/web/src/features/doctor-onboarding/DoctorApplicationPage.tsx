import { readSession } from '@/auth/session'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { myApplication } from './api'
import { DoctorApplicationForm } from './DoctorApplicationForm'
import { useQuery } from '@tanstack/react-query'

export function DoctorApplicationPage() {
  const application = useQuery({
    queryKey: ['doctor-application', readSession()?.accessToken],
    queryFn: ({ signal }) => myApplication(signal),
    refetchInterval: 30000,
  })
  return (
    <main className="mx-auto max-w-3xl px-6 py-10">
      <p className="text-sm font-medium text-teal-700">
        Professional registration
      </p>
      <h1 className="mt-2 text-3xl font-semibold">Join as a doctor</h1>
      <p className="mt-3 text-slate-600">
        Submit your professional details for platform review. You can join a
        clinic before approval; clinical access starts once you are approved and
        your clinic membership is active.
      </p>
      {application.isPending ? (
        <LoadingState message="Loading your application..." />
      ) : application.isError ? (
        <ErrorState
          message="Could not load your application."
          onRetry={() => void application.refetch()}
        />
      ) : (
        <DoctorApplicationForm
          key={`${application.data?.revision ?? 0}:${application.data?.status ?? 'new'}`}
          application={application.data}
        />
      )}
    </main>
  )
}
