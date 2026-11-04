/** Active and keyboard-focused tabs share one underline, without a second shadow line. */
export function tabClassName(
  active: boolean,
  attention?: 'danger' | 'waiting',
) {
  const color =
    attention === 'danger'
      ? `text-red-700 hover:text-red-900 focus-visible:border-red-700 ${active ? 'border-red-700' : 'border-transparent'}`
      : attention === 'waiting'
        ? `text-amber-800 hover:text-amber-900 focus-visible:border-amber-700 ${active ? 'border-amber-700' : 'border-transparent'}`
        : `hover:text-teal-900 focus-visible:border-teal-700 ${active ? 'border-teal-700 text-teal-800' : 'border-transparent text-slate-500'}`
  return `inline-flex min-h-11 shrink-0 cursor-pointer items-center justify-center gap-2 rounded-none border-b-2 bg-transparent px-3 py-2.5 text-sm font-medium whitespace-nowrap outline-none transition-colors ${color}`
}
