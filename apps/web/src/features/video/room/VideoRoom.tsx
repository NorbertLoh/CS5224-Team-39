import type { RecordFormState } from '@/features/records/hooks/useRecordFormState'
import { DoctorRecordForm } from '@/features/records/prescriptions/DoctorRecordForm'
import { RecordWorkspace } from '@/features/records/workspace/RecordWorkspace'
import { CallControls } from '@/features/video/components/CallControls'
import { CallStage } from '@/features/video/components/CallStage'
import { useExpandedRoom } from '@/features/video/hooks/useExpandedRoom'
import { useLocalMedia } from '@/features/video/hooks/useLocalMedia'
import { useRemoteCall } from '@/features/video/hooks/useRemoteCall'
import type {
  CallState,
  RoomConnection,
} from '@/features/video/media/connection'
import type { CSSProperties, ReactNode } from 'react'
import { useEffect, useRef, useState } from 'react'

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
  endActions?: (
    blocked: boolean,
    onPendingChange: (pending: boolean) => void,
  ) => ReactNode
}) {
  const media = useLocalMedia()
  const call = useRemoteCall(connection, role, media)
  const [expanded, setExpanded] = useState(false)
  const [finishing, setFinishing] = useState(false)
  const [cameraPaneSize, setCameraPaneSize] = useState(58)
  const doctorLayout = useRef<HTMLDivElement>(null)
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
  const cameraPaneLimits = () => {
    const availableWidth =
      (doctorLayout.current?.getBoundingClientRect().width ?? 0) - 24
    const min = Math.max(35, (360 / availableWidth) * 100)
    const max = Math.max(min, Math.min(70, 100 - (320 / availableWidth) * 100))
    return { min, max }
  }
  const resizeCameraPane = (clientX: number) => {
    const bounds = doctorLayout.current?.getBoundingClientRect()
    if (!bounds) return

    const availableWidth = bounds.width - 24
    const cameraWidth = clientX - bounds.left - 12
    const { min, max } = cameraPaneLimits()
    setCameraPaneSize(
      Math.min(max, Math.max(min, (cameraWidth / availableWidth) * 100)),
    )
  }

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
        ref={doctor ? doctorLayout : undefined}
        style={
          doctor
            ? ({
                '--camera-size': `${cameraPaneSize}fr`,
                '--notes-size': `${100 - cameraPaneSize}fr`,
              } as CSSProperties)
            : undefined
        }
        className={`grid grid-cols-1 gap-6 ${expanded ? 'min-h-full lg:h-full lg:min-h-0' : 'mt-6 items-start'} ${doctor ? 'lg:grid-cols-[minmax(0,var(--camera-size))_24px_minmax(0,var(--notes-size))] lg:gap-0' : expanded ? 'h-full' : ''}`}
      >
        <div
          className={`relative min-w-0 ${expanded ? 'min-h-0 lg:h-full' : ''}`}
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
            <div
              role="separator"
              aria-label="Resize video and notes panels"
              aria-orientation="vertical"
              aria-valuemin={35}
              aria-valuemax={70}
              aria-valuenow={Math.round(cameraPaneSize)}
              aria-valuetext={`Video ${Math.round(cameraPaneSize)}%, notes ${Math.round(100 - cameraPaneSize)}%`}
              tabIndex={0}
              className="group absolute inset-y-0 left-full hidden w-6 touch-none cursor-col-resize items-center justify-center rounded-full outline-none focus-visible:ring-2 focus-visible:ring-teal-600 focus-visible:ring-offset-2 lg:flex"
              onPointerDown={(event) => {
                event.currentTarget.setPointerCapture(event.pointerId)
                resizeCameraPane(event.clientX)
              }}
              onPointerMove={(event) => {
                if (event.currentTarget.hasPointerCapture(event.pointerId))
                  resizeCameraPane(event.clientX)
              }}
              onKeyDown={(event) => {
                if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
                  event.preventDefault()
                  const { min, max } = cameraPaneLimits()
                  setCameraPaneSize((size) =>
                    Math.min(
                      max,
                      Math.max(
                        min,
                        size + (event.key === 'ArrowRight' ? 5 : -5),
                      ),
                    ),
                  )
                }
                if (event.key === 'Home')
                  setCameraPaneSize(cameraPaneLimits().min)
                if (event.key === 'End')
                  setCameraPaneSize(cameraPaneLimits().max)
              }}
            >
              <span className="h-full w-1 rounded-full bg-slate-300 transition-colors group-hover:bg-teal-500" />
            </div>
          )}
        </div>
        {doctor && (
          <aside
            aria-label="Doctor workspace"
            className={`min-w-0 lg:col-start-3 [&_select]:w-full [&_select]:min-w-0 ${expanded ? 'min-h-0 lg:h-full lg:overflow-y-auto' : ''}`}
          >
            {actions && <div className="mb-5">{actions}</div>}
            <fieldset disabled={finishing} className="min-w-0">
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
            </fieldset>
            {endActions && (
              <div className="mt-6">
                {endActions(formState.dirty || formState.busy, setFinishing)}
              </div>
            )}
          </aside>
        )}
      </div>
    </main>
  )
}
