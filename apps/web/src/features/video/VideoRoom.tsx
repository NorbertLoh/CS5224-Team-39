import { useEffect, useRef, useState } from 'react'
import { Camera, CameraOff, Mic, MicOff, PhoneOff, Video, WifiOff } from 'lucide-react'
import { DoctorRecordForm } from '../records/DoctorRecordForm'
import { useLocalMedia } from './useLocalMedia'

const control = 'inline-flex items-center justify-center gap-2 rounded-xl border border-slate-600 px-4 py-3 text-sm font-medium transition hover:bg-slate-700 disabled:opacity-40 focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-teal-300'

function LocalVideo({ stream, camera }: { stream: MediaStream; camera: boolean }) {
  const video = useRef<HTMLVideoElement>(null)
  useEffect(() => {
    const element = video.current
    if (!element) return
    element.srcObject = stream
    return () => { element.srcObject = null }
  }, [stream])
  return <video ref={video} autoPlay playsInline muted aria-label="Your local camera preview" className={`h-full w-full -scale-x-100 object-cover ${camera ? '' : 'invisible'}`} />
}

export function VideoRoom({ role }: { role: 'patient' | 'doctor' }) {
  const media = useLocalMedia()
  const [state, setState] = useState<'waiting' | 'disconnected' | 'left'>('waiting')
  const doctor = role === 'doctor'
  const peer = doctor ? 'patient' : 'doctor'
  const waiting = state === 'waiting'
  const leave = (next: 'left' | 'disconnected') => { media.stop(); setState(next) }
  const rejoin = () => { setState('waiting'); void media.start() }

  return <main className="mx-auto max-w-[1600px] px-4 py-8 sm:px-8">
    <a className="text-sm text-slate-600 underline underline-offset-4" href={`/${role}`}>Back to {role} dashboard</a>
    <div className="mt-5 flex flex-wrap items-center justify-between gap-4">
      <div><p className="text-xs font-semibold tracking-widest text-teal-700 uppercase">TeleLink consultation</p><h1 className="mt-2 text-3xl font-semibold">{doctor ? 'Doctor consultation room' : 'Your video consultation'}</h1></div>
      <span className="rounded-full border border-amber-200 bg-amber-50 px-4 py-2 text-sm text-amber-900">Synthetic preview</span>
    </div>
    <p className="mt-4 max-w-4xl text-sm leading-6 text-slate-600">Check your camera and microphone here. The other participant is a placeholder; no remote call is connected and your media stays in this browser.</p>
    <div className={`mt-6 grid items-start gap-6 ${doctor ? 'xl:grid-cols-[minmax(0,1.4fr)_minmax(360px,1fr)]' : ''}`}>
      <section aria-label="Video call" className="min-w-0 overflow-hidden rounded-2xl bg-slate-950 text-white shadow-lg">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 px-5 py-4"><span className="text-sm font-medium">Consultation preview · {doctor ? 'Doctor' : 'Patient'} view</span><span role="status" className="text-sm text-slate-300">{waiting ? 'Waiting room' : state === 'left' ? 'You left the preview' : 'Disconnected preview'}</span></div>
        <div className="relative flex min-h-[420px] items-center justify-center px-6 pt-10 pb-48 sm:min-h-[520px]">
          <div className="max-w-md text-center">
            <div className="mx-auto flex size-20 items-center justify-center rounded-full bg-slate-800 text-teal-300">{state === 'disconnected' ? <WifiOff size={30} aria-hidden="true" /> : <Video size={30} aria-hidden="true" />}</div>
            <h2 className="mt-5 text-xl font-medium">{waiting ? `Waiting for your ${peer}` : state === 'left' ? 'You have left the preview' : 'Your connection was interrupted'}</h2>
            <p className="mt-3 text-sm leading-6 text-slate-400">{waiting ? 'Remote video will appear here once live calling is available.' : 'This is a preview state. Rejoin to restart your local camera and microphone.'}</p>
            {!waiting && <button type="button" className="mt-5 rounded-lg bg-teal-400 px-5 py-3 font-medium text-slate-950" onClick={rejoin}>Rejoin preview</button>}
          </div>
          <div className="absolute right-5 bottom-5 h-32 w-44 overflow-hidden rounded-xl border border-slate-600 bg-slate-800 sm:h-36 sm:w-52">
            {media.stream && <LocalVideo stream={media.stream} camera={media.camera} />}
            {(!media.stream || !media.camera) && <div className="absolute inset-0 flex items-center justify-center text-slate-400"><CameraOff size={24} aria-hidden="true" /></div>}
            <span className="absolute bottom-2 left-2 rounded bg-slate-950/80 px-2 py-1 text-xs">You{media.stream && !media.microphone ? ' · Mic off' : ''}</span>
          </div>
        </div>
        <div className="space-y-4 border-t border-slate-800 p-5">
          {media.error && <p role="alert" className="rounded-lg bg-amber-100 p-3 text-sm text-amber-950">{media.error}</p>}
          {waiting && !media.stream && <div className="text-center"><button type="button" disabled={media.pending} className="rounded-lg bg-teal-400 px-5 py-3 text-sm font-medium text-slate-950 disabled:opacity-50" onClick={() => void media.start()}>{media.pending ? 'Waiting for device permission…' : media.error ? 'Retry camera and microphone' : 'Enable camera and microphone'}</button></div>}
          <div className="flex flex-wrap justify-center gap-3">
            <button type="button" className={control} disabled={!media.stream} aria-label={media.microphone ? 'Mute microphone' : 'Unmute microphone'} aria-pressed={!media.microphone} onClick={media.toggleMicrophone}>{media.microphone ? <Mic size={18} /> : <MicOff size={18} />}{media.microphone ? 'Mute' : 'Unmute'}</button>
            <button type="button" className={control} disabled={!media.stream} aria-label={media.camera ? 'Turn camera off' : 'Turn camera on'} aria-pressed={!media.camera} onClick={media.toggleCamera}>{media.camera ? <Camera size={18} /> : <CameraOff size={18} />}{media.camera ? 'Camera off' : 'Camera on'}</button>
            <button type="button" className={`${control} border-red-600 bg-red-600 hover:bg-red-700`} disabled={state === 'left'} onClick={() => leave('left')}><PhoneOff size={18} />Leave preview</button>
          </div>
          {waiting && <div className="text-center"><button type="button" className="text-xs text-slate-400 underline underline-offset-4" onClick={() => leave('disconnected')}>Test disconnected preview</button></div>}
          <p className="text-center text-xs text-slate-400">{media.stream ? 'Local devices enabled. No media is being transmitted.' : 'Your camera and microphone are off.'}</p>
        </div>
      </section>
      {doctor && <aside aria-label="Doctor workspace"><DoctorRecordForm /></aside>}
    </div>
  </main>
}
