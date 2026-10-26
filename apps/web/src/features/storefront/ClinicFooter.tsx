export function ClinicFooter({ name }: { name: string }) {
  return (
    <footer className="border-t border-slate-200 bg-white">
      <div className="mx-auto flex max-w-6xl flex-wrap justify-between gap-3 px-6 py-6 text-xs text-slate-500 sm:px-8">
        <span>{name}</span>
        <span>
          Powered by{' '}
          <a
            href="/"
            className="font-medium text-slate-700 underline-offset-4 hover:underline"
          >
            TeleLink Health
          </a>
        </span>
      </div>
    </footer>
  )
}
