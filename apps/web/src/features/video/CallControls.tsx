import type { Ref } from 'react'
import { Camera, CameraOff, Mic, MicOff, PhoneOff } from 'lucide-react'
import type { LocalMedia } from './useLocalMedia'

const control =
  'inline-flex items-center justify-center gap-2 rounded-xl border border-slate-600 px-4 py-3 text-sm font-medium transition hover:bg-slate-700 disabled:opacity-40 focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-teal-300'

type CallControlsProps = {
  state: 'waiting' | 'disconnected' | 'left'
  media: LocalMedia
  leaveButton: Ref<HTMLButtonElement>
  leave: (next: 'left' | 'disconnected') => void
}

export function CallControls({
  state,
  media,
  leaveButton,
  leave,
}: CallControlsProps) {
  const waiting = state === 'waiting'
  return (
    <div className="space-y-4 border-t border-slate-800 p-5">
      {media.error && (
        <p
          role="alert"
          className="rounded-lg bg-amber-100 p-3 text-sm text-amber-950"
        >
          {media.error}
        </p>
      )}
      {waiting && !media.stream && (
        <div className="text-center">
          <button
            type="button"
            disabled={media.pending}
            className="rounded-lg bg-teal-400 px-5 py-3 text-sm font-medium text-slate-950 disabled:opacity-50"
            onClick={() => void media.start()}
          >
            {media.pending
              ? 'Waiting for device permission…'
              : media.error
                ? 'Retry camera and microphone'
                : 'Enable camera and microphone'}
          </button>
        </div>
      )}
      <div className="flex flex-wrap justify-center gap-3">
        <button
          type="button"
          className={control}
          disabled={!media.stream}
          aria-label={
            media.microphone ? 'Mute microphone' : 'Unmute microphone'
          }
          aria-pressed={!media.microphone}
          onClick={media.toggleMicrophone}
        >
          {media.microphone ? <Mic size={18} /> : <MicOff size={18} />}
          {media.microphone ? 'Mute' : 'Unmute'}
        </button>
        <button
          type="button"
          className={control}
          disabled={!media.stream}
          aria-label={media.camera ? 'Turn camera off' : 'Turn camera on'}
          aria-pressed={!media.camera}
          onClick={media.toggleCamera}
        >
          {media.camera ? <Camera size={18} /> : <CameraOff size={18} />}
          {media.camera ? 'Camera off' : 'Camera on'}
        </button>
        <button
          ref={leaveButton}
          type="button"
          className={`${control} border-red-600 bg-red-600 hover:bg-red-700`}
          disabled={state === 'left'}
          onClick={() => leave('left')}
        >
          <PhoneOff size={18} />
          Leave preview
        </button>
      </div>
      {waiting && (
        <div className="text-center">
          <button
            type="button"
            className="text-xs text-slate-400 underline underline-offset-4"
            onClick={() => leave('disconnected')}
          >
            Test disconnected preview
          </button>
        </div>
      )}
      <p className="text-center text-xs text-slate-400">
        {media.stream
          ? 'Local devices enabled. No media is being transmitted.'
          : 'Your camera and microphone are off.'}
      </p>
    </div>
  )
}
