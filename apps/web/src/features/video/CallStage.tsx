import { useEffect, useRef } from 'react'
import type { Ref } from 'react'
import { CameraOff, Video, WifiOff } from 'lucide-react'
import type { LocalMedia } from './useLocalMedia'

function LocalVideo({
  stream,
  camera,
}: {
  stream: MediaStream
  camera: boolean
}) {
  const video = useRef<HTMLVideoElement>(null)
  useEffect(() => {
    const element = video.current
    if (!element) return
    element.srcObject = stream
    return () => {
      element.srcObject = null
    }
  }, [stream])
  return (
    <video
      ref={video}
      autoPlay
      playsInline
      muted
      aria-label="Your local camera preview"
      className={`h-full w-full -scale-x-100 object-cover ${camera ? '' : 'invisible'}`}
    />
  )
}

type CallStageProps = {
  peer: 'patient' | 'doctor'
  state: 'waiting' | 'disconnected' | 'left'
  expanded: boolean
  media: LocalMedia
  joinButton: Ref<HTMLButtonElement>
  join: () => void
}

export function CallStage({
  peer,
  state,
  expanded,
  media,
  joinButton,
  join,
}: CallStageProps) {
  const waiting = state === 'waiting'
  return (
    <div
      className={`relative flex flex-1 items-center justify-center px-6 pt-10 pb-48 ${expanded ? 'min-h-[260px]' : 'min-h-[420px] sm:min-h-[520px]'}`}
    >
      <div className="max-w-md text-center">
        <div className="mx-auto flex size-20 items-center justify-center rounded-full bg-slate-800 text-teal-300">
          {state === 'disconnected' ? (
            <WifiOff size={30} aria-hidden="true" />
          ) : (
            <Video size={30} aria-hidden="true" />
          )}
        </div>
        <h2 className="mt-5 text-xl font-medium">
          {waiting
            ? `Waiting for your ${peer}`
            : state === 'left'
              ? 'You have left the preview'
              : 'Your connection was interrupted'}
        </h2>
        <p className="mt-3 text-sm leading-6 text-slate-400">
          {waiting
            ? 'Remote video will appear here once live calling is available.'
            : 'This is a preview state. Rejoin to return to the waiting room, then enable your camera and microphone when ready.'}
        </p>
        {!expanded && (
          <button
            ref={joinButton}
            type="button"
            className="mt-5 rounded-lg bg-teal-400 px-5 py-3 font-medium text-slate-950"
            onClick={join}
          >
            {waiting ? 'Join preview' : 'Rejoin preview'}
          </button>
        )}
      </div>
      <div className="absolute right-5 bottom-5 h-32 w-44 overflow-hidden rounded-xl border border-slate-600 bg-slate-800 sm:h-36 sm:w-52">
        {media.stream && (
          <LocalVideo stream={media.stream} camera={media.camera} />
        )}
        {(!media.stream || !media.camera) && (
          <div className="absolute inset-0 flex items-center justify-center text-slate-400">
            <CameraOff size={24} aria-hidden="true" />
          </div>
        )}
        <span className="absolute bottom-2 left-2 rounded bg-slate-950/80 px-2 py-1 text-xs">
          You{media.stream && !media.microphone ? ' · Mic off' : ''}
        </span>
      </div>
    </div>
  )
}
