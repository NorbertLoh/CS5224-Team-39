/** Active and keyboard-focused tabs share one underline, without a second shadow line. */
export function tabClassName(active: boolean) {
  return `inline-flex min-h-11 shrink-0 cursor-pointer items-center justify-center gap-2 rounded-none border-b-2 bg-transparent px-3 py-2.5 text-sm font-medium whitespace-nowrap outline-none transition-colors hover:text-teal-900 focus-visible:border-teal-700 ${active ? 'border-teal-700 text-teal-800' : 'border-transparent text-slate-500'}`
}
