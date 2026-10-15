import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { schedulingClient, renderScheduling } from './scheduling-helpers'
import type { Appointment } from '../src/features/scheduling/api'
import shared from '../../../dev/fixtures/telelink.json'
import { AppointmentSchedule } from '../src/features/appointments/AppointmentSchedule'
import { AppointmentDetails } from '../src/features/appointments/AppointmentDetails'
import {
  appointmentDates,
  dateInSingapore,
  dayCells,
  previewContexts,
  scopedAppointments,
} from '../src/features/appointments/fixtures'

test('appointment previews respect own patient, assigned active doctor and clinic scope', () => {
  for (const context of previewContexts('patient')) {
    assert.ok(
      scopedAppointments('patient', context.id).every(
        (item) => item.patient_id === context.id,
      ),
    )
  }
  for (const context of previewContexts('doctor')) {
    assert.ok(
      scopedAppointments('doctor', context.id).every(
        (item) =>
          item.doctor_id === context.id &&
          shared.memberships.some(
            (member) =>
              member.subject_id === context.id &&
              member.tenant_id === item.tenant_id &&
              member.roles.includes('doctor') &&
              member.status === 'active',
          ),
      ),
    )
  }
  for (const context of previewContexts('clinic_admin')) {
    assert.ok(
      scopedAppointments('clinic_admin', context.id).every(
        (item) => item.tenant_id === context.id,
      ),
    )
  }
  const former = shared.subjects.find(
    (item) => item.display_name === 'Demo Former Doctor',
  )!
  assert.deepEqual(scopedAppointments('doctor', former.subject_id), [])
  const sharedDoctor = shared.subjects.find(
    (item) => item.display_name === 'Demo Shared Doctor',
  )!
  const clinic = shared.clinics[1].tenant_id
  assert.ok(
    scopedAppointments('doctor', sharedDoctor.subject_id, clinic).every(
      (item) => item.tenant_id === clinic,
    ),
  )
})

test('half-hour cells preserve reallocated-slot history and offset-start appointments', () => {
  const clinic = shared.clinics[0].tenant_id
  const cells = dayCells(
    scopedAppointments('clinic_admin', clinic),
    '2026-10-13',
  )
  const reallocated = cells.find(
    (cell) => cell.startsAt === '2026-10-13T07:00:00.000Z',
  )!
  assert.deepEqual(
    reallocated.appointments.map((item) => item.status),
    ['expired', 'held'],
  )
  assert.ok(
    cells.every(
      (cell) => Date.parse(cell.endsAt) - Date.parse(cell.startsAt) === 1800000,
    ),
  )
  const inProgress = shared.appointments.find(
    (item) => item.status === 'in_progress',
  )!
  assert.equal(
    dayCells([inProgress], '2026-10-13').filter(
      (cell) => cell.appointments.length,
    ).length,
    2,
  )
  const late = shared.appointments.find((item) =>
    item.doctor_id.endsWith('024'),
  )!
  assert.ok(
    dayCells([late], '2026-10-12').some((cell) =>
      cell.appointments.includes(late),
    ),
  )
})

test('dates use Singapore time and include an empty preview day', () => {
  assert.equal(dateInSingapore('2026-10-13T18:00:00Z'), '2026-10-14')
  const dates = appointmentDates(shared.appointments)
  assert.deepEqual(dates, ['2026-10-12', '2026-10-13', '2026-10-14'])
  assert.ok(
    dayCells(shared.appointments, dates[2]).every(
      (cell) => !cell.appointments.length,
    ),
  )
  assert.equal(appointmentDates([]).length, 1)
})

test('role views render server appointments and no demo identities', () => {
  for (const role of ['patient', 'doctor', 'clinic_admin'] as const) {
    const appointment = shared.appointments[0]
    const subject =
      role === 'patient' ? appointment.patient_id : appointment.doctor_id
    const tenantId = appointment.tenant_id
    const client = schedulingClient({
      subject_id: subject,
      global_roles: ['patient'],
      memberships: [
        {
          tenant_id: tenantId,
          roles: ['doctor', 'clinic_admin'],
          status: 'active',
        },
      ],
    })
    client.setQueryData(
      [
        'scheduling',
        'appointments',
        's07-test',
        role === 'clinic_admin' ? tenantId : undefined,
      ],
      {
        pages: [{ items: [appointment], next_cursor: null }],
        pageParams: [null],
      },
    )
    const markup = renderScheduling(
      client,
      createElement(AppointmentSchedule, { role }),
    )
    assert.doesNotMatch(
      markup,
      /Fixture preview|Demo patient|Demo doctor|Demo clinic/,
    )
    assert.match(markup, /Date<select/)
    assert.match(markup, /30-minute appointment cells/)
    assert.match(markup, /Singapore time/)
    assert.match(markup, /aria-pressed="false"/)
    client.clear()
  }
})

test('detail view exposes trusted fixture status and refund resolution separately', () => {
  const appointment = shared.appointments.find(
    (item) => item.payment_resolution === 'refund_required',
  )!
  const markup = renderToStaticMarkup(
    createElement(AppointmentDetails, {
      appointment: appointment as Appointment,
      onClose: () => {},
    }),
  )
  assert.match(markup, /Appointment details/)
  assert.match(markup, /expired/)
  assert.match(markup, /refund required/)
  assert.match(markup, /refund review/)
  assert.match(markup, /Close details/)
  assert.match(markup, /\$25.00/)
  assert.match(markup, new RegExp(appointment.appointment_id))
})
