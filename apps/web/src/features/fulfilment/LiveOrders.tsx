import { useSchedulingIdentity } from '../scheduling/useSchedulingIdentity'
import type { OrderContext } from './model'
import { OrderWorkspace } from './OrderWorkspace'

type Props = { role: 'patient' } | { role: 'clinic_admin'; tenantId: string }
export function LiveOrders(props: Props) {
  const identity = useSchedulingIdentity()
  if (identity.isError)
    return (
      <p role="alert" className="p-6">
        Could not verify order access. Refresh your session and try again.
      </p>
    )
  if (!identity.data || !identity.token)
    return (
      <p role="status" className="p-6">
        Checking order access...
      </p>
    )
  const context: OrderContext =
    props.role === 'patient'
      ? { role: 'patient', patientId: identity.data.subject_id }
      : { role: 'clinic_admin', tenantId: props.tenantId }
  return (
    <OrderWorkspace
      key={`${identity.token}:${props.role}:${props.role === 'clinic_admin' ? props.tenantId : ''}`}
      context={context}
      token={identity.token}
    />
  )
}
