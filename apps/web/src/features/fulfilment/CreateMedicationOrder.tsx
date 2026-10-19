import { useMutation, useQuery } from '@tanstack/react-query'
import { createOrder, fulfilmentError } from './api'
import { stableKey } from './checkout'
import { readPrescription } from '../records/api'

export function CreateMedicationOrder({
  prescriptionId,
  subject,
  token,
  onCreated,
}: {
  prescriptionId: string
  subject: string
  token: string
  onCreated: (id: string) => void
}) {
  const prescription = useQuery({
    queryKey: ['fulfilment', 'prescription', token, prescriptionId],
    queryFn: ({ signal }) => readPrescription(prescriptionId, signal),
    retry: false,
    gcTime: 0,
  })
  const create = useMutation({
    mutationFn: async () => {
      const current = await prescription.refetch()
      if (
        current.isError ||
        current.data?.patient_id !== subject ||
        current.data?.prescription_id !== prescriptionId ||
        current.data.status !== 'issued'
      )
        throw new Error('Issued prescription unavailable.')
      const key = stableKey(
        sessionStorage,
        `telelink.order.${subject}.${prescriptionId}`,
      )
      const order = await createOrder(prescriptionId, key)
      if (
        order.patient_id !== subject ||
        order.prescription_id !== prescriptionId
      )
        throw new Error('Order unavailable.')
      // Order POST replay is historical. The selected order is always loaded again by GET.
      return order.order_id
    },
    retry: false,
    onSuccess: onCreated,
  })
  const data = prescription.isError ? undefined : prescription.data
  return (
    <section className="space-y-3 rounded-xl border p-5">
      <h2 className="text-xl font-semibold">
        Order medication from your prescription
      </h2>
      <p className="break-all text-sm">Prescription: {prescriptionId}</p>
      {prescription.isPending ? (
        <p role="status">Checking prescription...</p>
      ) : data?.patient_id !== subject ||
        data.prescription_id !== prescriptionId ? (
        <p role="alert">This prescription is unavailable.</p>
      ) : data.status !== 'issued' ? (
        <p role="status">Only an issued prescription can create an order.</p>
      ) : (
        <button
          className="rounded-lg bg-slate-900 px-4 py-2 text-white disabled:opacity-50"
          disabled={create.isPending || prescription.isFetching}
          onClick={() => create.mutate()}
        >
          {create.isPending
            ? 'Opening medication order...'
            : 'Create or open medication order'}
        </button>
      )}
      {create.isError && (
        <p role="alert" className="text-sm text-red-700">
          {fulfilmentError(create.error)}
        </p>
      )}
    </section>
  )
}
