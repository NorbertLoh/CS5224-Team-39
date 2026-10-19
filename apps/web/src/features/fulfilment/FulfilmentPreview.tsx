import { useState } from 'react'
import { demoPatientId, fixtureOrders } from './fixtures'
import type { Example } from './fixtures'
import { markReady, visibleOrders } from './model'
import type { PreviewContext } from './model'
import { TrackingControls } from './TrackingControls'
import { TrackingOrderList } from './TrackingOrderList'
import { TrackingOrderDetails } from './TrackingOrderDetails'

type Props = { role: 'patient' } | { role: 'clinic_admin'; tenantId: string }

export function FulfilmentPreview(props: Props) {
  const context: PreviewContext =
    props.role === 'patient'
      ? { role: 'patient', patientId: demoPatientId }
      : { role: 'clinic_admin', tenantId: props.tenantId }
  const [example, setExample] = useState<Example>('active')
  const [orders, setOrders] = useState(() =>
    fixtureOrders(
      'active',
      props.role === 'clinic_admin' ? props.tenantId : undefined,
    ),
  )
  const [selectedId, setSelectedId] = useState<string | null>(
    orders[0]?.order_id ?? null,
  )
  const [checked, setChecked] = useState(false)
  const scoped = visibleOrders(orders, context)
  const selected = scoped.find((order) => order.order_id === selectedId)
  function changeExample(next: Example) {
    const nextOrders = fixtureOrders(
      next,
      props.role === 'clinic_admin' ? props.tenantId : undefined,
    )
    setExample(next)
    setOrders(nextOrders)
    setSelectedId(nextOrders[0]?.order_id ?? null)
    setChecked(false)
  }
  return (
    <main className="mx-auto max-w-5xl space-y-6 px-4 py-8 sm:px-6">
      <a
        className="text-sm underline"
        href={props.role === 'patient' ? '/patient' : '/clinic-admin'}
      >
        {props.role === 'patient'
          ? 'Back to patient dashboard'
          : 'Back to your clinics'}
      </a>
      <h1 className="text-3xl font-semibold">
        {props.role === 'patient'
          ? 'Medication delivery tracking'
          : 'Medicine readiness and delivery tracking'}
      </h1>
      {props.role === 'clinic_admin' && (
        <p className="break-all text-sm text-slate-600">
          Synthetic examples for selected clinic {props.tenantId}
        </p>
      )}
      <TrackingControls
        example={example}
        onExampleChange={changeExample}
        refreshingExample={example === 'loading'}
        onRefresh={() => {
          if (example === 'error') changeExample('active')
          else setChecked(true)
        }}
      />
      {checked && (
        <p role="status" className="text-sm">
          Demo status checked. The current snapshot is unchanged.
        </p>
      )}
      {example === 'loading' ? (
        <p role="status" aria-busy="true">
          Loading medication orders...
        </p>
      ) : example === 'error' ? (
        <div role="alert" className="space-y-3 rounded-xl border p-5">
          <p>Medication orders are unavailable. Try loading them again.</p>
          <button
            className="rounded border px-4 py-2"
            onClick={() => changeExample('active')}
          >
            Retry demo orders
          </button>
        </div>
      ) : (
        <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
          <TrackingOrderList
            orders={scoped}
            selectedId={selectedId}
            onSelect={(id) => {
              setSelectedId(id)
              setChecked(false)
            }}
          />
          {selected && (
            <TrackingOrderDetails
              key={`${example}:${selected.order_id}`}
              order={selected}
              context={context}
              onReady={() => {
                setChecked(false)
                setOrders((current) =>
                  current.map((order) =>
                    order.order_id === selected.order_id
                      ? markReady(order, context)
                      : order,
                  ),
                )
              }}
            />
          )}
        </div>
      )}
    </main>
  )
}
