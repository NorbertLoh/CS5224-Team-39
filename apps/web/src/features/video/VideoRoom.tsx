import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { CallStage } from './CallStage'
import { CallControls } from './CallControls'
import { useExpandedRoom } from './useExpandedRoom'
import { DoctorRecordForm } from '../records/DoctorRecordForm'
import { RecordWorkspace } from '../records/RecordWorkspace'
import { useLocalMedia } from './useLocalMedia'
import { useRemoteCall } from './useRemoteCall'
import type { CallState, RoomConnection } from './connection'
import type { RecordFormState } from '../records/useRecordFormState'

export function VideoRoom({
  role,
  connection,
  appointmentId,
  token,
  subjectId,
  actions,
  endActions,
}: {
  role: 'patient' | 'doctor'
  connection?: RoomConnection
  appointmentId?: string
  token?: string
  subjectId?: string
  actions?: ReactNode
  endActions?: (blocked: boolean) => ReactNode
}) {
  const media = useLocalMedia()
  const call = useRemoteCall(connection, role, media)
  const [expanded, setExpanded] = useState(false)
  const [formState, setFormState] = useState<RecordFormState>({
    dirty: false,
    busy: false,
  })
  const [previewState, setPreviewState] = useState<CallState>('waiting')
  const doctor = role === 'doctor'
  const peer = doctor ? 'patient' : 'doctor'
  const state = connection ? call.state : previewState
  const leave = () => {
    call.leave()
    setPreviewState('left')
    setExpanded(false)
  }
  const join = () => {
    setPreviewState('waiting')
    setExpanded(true)
    if (connection) void call.join()
  }

  useEffect(() => {
    if (call.state === 'disconnected') setExpanded(false)
  }, [call.state])

  const { room, joinButton, leaveButton, handleKeyDown } = useExpandedRoom(
    expanded,
    leave,
  )

  return (
    <main
      ref={room}
      role={expanded ? 'dialog' : undefined}
      aria-modal={expanded || undefined}
      aria-label={
        expanded
          ? `${doctor ? 'Doctor' : 'Patient'} consultation room`
          : undefined
      }
      className={
        expanded
          ? 'fixed inset-0 z-50 overflow-y-auto bg-white p-3 sm:p-5'
          : 'mx-auto max-w-[1600px] px-4 py-8 sm:px-8'
      }
      onKeyDown={handleKeyDown}
    >
      <div hidden={expanded}>
        <a
          className="text-sm text-slate-600 underline underline-offset-4"
          href={`/${role}`}
        >
          Back to {role} dashboard
        </a>
        <div className="mt-5 flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="text-xs font-semibold tracking-widest text-teal-700 uppercase">
              TeleLink consultation
            </p>
            <h1 className="mt-2 text-3xl font-semibold">
              {doctor ? 'Doctor consultation room' : 'Your video consultation'}
            </h1>
          </div>
          <span className="rounded-full border border-amber-200 bg-amber-50 px-4 py-2 text-sm text-amber-900">
            {connection ? 'Video consultation' : 'Camera check'}
          </span>
        </div>
        <p className="mt-4 max-w-4xl text-sm leading-6 text-slate-600">
          {connection
            ? 'Join when you are ready to speak with the other participant.'
            : 'Check your camera and microphone here. Choose a booked appointment to start your consultation.'}
          {doctor &&
            ' The records workspace saves real records for the appointment you select.'}
        </p>
      </div>
      <div
        className={`grid grid-cols-1 gap-6 ${expanded ? 'min-h-full lg:h-full lg:min-h-0' : 'mt-6 items-start'} ${doctor ? 'lg:grid-cols-[minmax(0,1.4fr)_minmax(320px,1fr)]' : expanded ? 'h-full' : ''}`}
      >
        <section
          aria-label="Video call"
          className={`flex min-w-0 flex-col overflow-hidden rounded-2xl bg-slate-950 text-white shadow-lg ${expanded ? 'min-h-[calc(100dvh-1.5rem)] sm:min-h-[calc(100dvh-2.5rem)] lg:h-full lg:min-h-0' : ''}`}
        >
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 px-5 py-4">
            <span className="text-sm font-medium">
              Consultation · {doctor ? 'Doctor' : 'Patient'} view
            </span>
            <span role="status" className="text-sm text-slate-300">
              {state === 'connected'
                ? 'Connected'
                : state === 'joining' || state === 'connecting'
                  ? 'Connecting'
                  : state === 'waiting'
                    ? 'Waiting room'
                    : state === 'left'
                      ? 'You left the room'
                      : 'Disconnected'}
            </span>
          </div>
          <CallStage
            peer={peer}
            state={state}
            expanded={expanded}
            media={media}
            joinButton={joinButton}
            join={join}
            remote={call.remote}
            live={Boolean(connection)}
          />
          <CallControls
            state={state}
            media={media}
            leaveButton={leaveButton}
            leave={leave}
            live={Boolean(connection)}
            error={call.error}
          />
        </section>
        {doctor && (
          <aside
            aria-label="Doctor workspace"
            className={`min-w-0 [&_select]:w-full [&_select]:min-w-0 ${expanded ? 'min-h-0 lg:h-full lg:overflow-y-auto' : ''}`}
          >
            {actions && <div className="mb-5">{actions}</div>}
            {appointmentId && token && subjectId ? (
              <RecordWorkspace
                appointmentId={appointmentId}
                token={token}
                subjectId={subjectId}
                onStateChange={setFormState}
              />
            ) : (
              <DoctorRecordForm />
            )}
            {endActions && (
              <div className="mt-6">
                {endActions(formState.dirty || formState.busy)}
              </div>
            )}
          </aside>
        )}
      </div>
    </main>
  )
}
