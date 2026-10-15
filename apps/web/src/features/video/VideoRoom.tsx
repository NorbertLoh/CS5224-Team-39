import { useState } from 'react'
import { CallStage } from './CallStage'
import { CallControls } from './CallControls'
import { useExpandedRoom } from './useExpandedRoom'
import { DoctorRecordForm } from '../records/DoctorRecordForm'
import { useLocalMedia } from './useLocalMedia'

export function VideoRoom({ role }: { role: 'patient' | 'doctor' }) {
  const media = useLocalMedia()
  const [expanded, setExpanded] = useState(false)
  const [state, setState] = useState<'waiting' | 'disconnected' | 'left'>(
    'waiting',
  )
  const doctor = role === 'doctor'
  const peer = doctor ? 'patient' : 'doctor'
  const waiting = state === 'waiting'
  const leave = (next: 'left' | 'disconnected') => {
    media.stop()
    setState(next)
    setExpanded(false)
  }
  const join = () => {
    setState('waiting')
    setExpanded(true)
  }

  const { room, joinButton, leaveButton, handleKeyDown } = useExpandedRoom(
    expanded,
    () => leave('left'),
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
            Synthetic preview
          </span>
        </div>
        <p className="mt-4 max-w-4xl text-sm leading-6 text-slate-600">
          Check your camera and microphone here. The other participant is a
          placeholder; no remote call is connected and your media stays in this
          browser.
        </p>
      </div>
      <div
        className={`grid gap-6 ${expanded ? 'min-h-full lg:h-full lg:min-h-0' : 'mt-6 items-start'} ${doctor ? 'lg:grid-cols-[minmax(0,1.4fr)_minmax(320px,1fr)]' : expanded ? 'h-full' : ''}`}
      >
        <section
          aria-label="Video call"
          className={`flex min-w-0 flex-col overflow-hidden rounded-2xl bg-slate-950 text-white shadow-lg ${expanded ? 'min-h-[calc(100dvh-1.5rem)] sm:min-h-[calc(100dvh-2.5rem)] lg:h-full lg:min-h-0' : ''}`}
        >
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 px-5 py-4">
            <span className="text-sm font-medium">
              Consultation preview · {doctor ? 'Doctor' : 'Patient'} view
            </span>
            <span role="status" className="text-sm text-slate-300">
              {waiting
                ? 'Waiting room'
                : state === 'left'
                  ? 'You left the preview'
                  : 'Disconnected preview'}
            </span>
          </div>
          <CallStage
            peer={peer}
            state={state}
            expanded={expanded}
            media={media}
            joinButton={joinButton}
            join={join}
          />
          <CallControls
            state={state}
            media={media}
            leaveButton={leaveButton}
            leave={leave}
          />
        </section>
        {doctor && (
          <aside
            aria-label="Doctor workspace"
            className={expanded ? 'min-h-0 lg:h-full lg:overflow-y-auto' : ''}
          >
            <DoctorRecordForm />
          </aside>
        )}
      </div>
    </main>
  )
}
