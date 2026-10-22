import { useMutation } from '@tanstack/react-query'
import { openPrescriptionOrder } from './patientMedicines'
import { fulfilmentError } from './api'

export function OpenMedicationOrderButton({
  prescriptionId,
  subject,
  label = 'Review medicines & pay',
  onOpened,
}: {
  prescriptionId: string
  subject: string
  label?: string
  onOpened?: (id: string) => void
}) {
  const open = useMutation({
    mutationFn: () => openPrescriptionOrder(prescriptionId, subject),
    retry: false,
    onSuccess: (order) => {
      if (onOpened) onOpened(order.order_id)
      else
        window.location.assign(
          `/patient/medication-orders?order_id=${encodeURIComponent(order.order_id)}`,
        )
    },
  })
  return (
    <div className="space-y-2">
      <button
        type="button"
        className="rounded-lg bg-teal-800 px-5 py-3 font-medium text-white disabled:opacity-50"
        disabled={open.isPending}
        onClick={() => open.mutate()}
      >
        {open.isPending ? 'Opening your medicines...' : label}
      </button>
      {open.isError && (
        <p role="alert" className="text-sm text-red-700">
          {fulfilmentError(open.error)}
        </p>
      )}
    </div>
  )
}
