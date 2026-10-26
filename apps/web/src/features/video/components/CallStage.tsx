import type { LocalMedia } from '@/features/video/hooks/useLocalMedia'
import type { CallState } from '@/features/video/media/connection'
import { CameraOff, Video, WifiOff } from 'lucide-react'
import type { Ref } from 'react'
import { useEffect, useRef, useState } from 'react'

function RemoteVideo({ stream, peer }: { stream: MediaStream; peer: string }) {
  const video = useRef<HTMLVideoElement>(null)
  const [blocked, setBlocked] = useState(false)
  const play = () => {
    void video.current
      ?.play()
      .then(() => setBlocked(false))
      .catch(() => setBlocked(true))
  }
  useEffect(() => {
    const element = video.current
    if (!element) return
    element.srcObject = stream
    void element.play().catch(() => setBlocked(true))
    return () => {
      element.srcObject = null
    }
  }, [stream])
  return (
    <>
      <video
        ref={video}
        autoPlay
        playsInline
        aria-label={`Remote ${peer} video`}
        className="absolute inset-0 h-full w-full object-contain"
      />
      {blocked && (
        <button
          type="button"
          onClick={play}
          className="relative z-10 rounded-lg bg-teal-400 p-3 text-slate-950"
        >
          Play call audio and video
        </button>
      )}
    </>
  )
}

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
  state: CallState
  expanded: boolean
  media: LocalMedia
  joinButton: Ref<HTMLButtonElement>
  join: () => void
  remote: MediaStream | null
  live: boolean
}

export function CallStage({
  peer,
  state,
  expanded,
  media,
  joinButton,
  join,
  remote,
  live,
}: CallStageProps) {
  const waiting = state === 'waiting'
  return (
    <div
      className={`relative flex flex-1 items-center justify-center px-6 pt-10 pb-48 ${expanded ? 'min-h-[260px]' : 'min-h-[420px] sm:min-h-[520px]'}`}
    >
      {remote && <RemoteVideo stream={remote} peer={peer} />}
      {!remote && (
        <div className="max-w-md text-center">
          <div className="mx-auto flex size-20 items-center justify-center rounded-full bg-slate-800 text-teal-300">
            {state === 'disconnected' ? (
              <WifiOff size={30} aria-hidden="true" />
            ) : (
              <Video size={30} aria-hidden="true" />
            )}
          </div>
          <h2 className="mt-5 text-xl font-medium">
            {state === 'joining' || state === 'connecting'
              ? 'Connecting your call'
              : waiting
                ? `Waiting for your ${peer}`
                : state === 'left'
                  ? 'You have left the room'
                  : 'Your connection was interrupted'}
          </h2>
          <p className="mt-3 text-sm leading-6 text-slate-400">
            {state === 'joining' || state === 'connecting'
              ? 'Please wait while the call connects.'
              : waiting
                ? live
                  ? 'The other participant will appear here when connected.'
                  : 'Open a booked appointment to join a live consultation.'
                : 'Rejoin when you are ready. Your camera and microphone will be requested again.'}
          </p>
          {!expanded && (
            <button
              ref={joinButton}
              type="button"
              className="mt-5 rounded-lg bg-teal-400 px-5 py-3 font-medium text-slate-950"
              onClick={join}
            >
              {live
                ? waiting
                  ? 'Join consultation'
                  : 'Rejoin consultation'
                : waiting
                  ? 'Expand camera check'
                  : 'Reopen camera check'}
            </button>
          )}
        </div>
      )}
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
