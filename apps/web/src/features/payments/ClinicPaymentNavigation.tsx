export function ClinicPaymentNavigation({ tenantId }: { tenantId: string }) {
  return (
    <nav
      aria-label="Clinic management"
      className="flex flex-wrap gap-5 text-sm underline"
    >
      <a href="/clinic-admin">Your clinics</a>
      <a href={`/clinic-admin/clinics/${tenantId}/profile`}>Clinic profile</a>
      <a href={`/clinic-admin/clinics/${tenantId}/staff`}>Staff</a>
      <a
        href={`/clinic-admin/clinics/${tenantId}/payments`}
        aria-current="page"
      >
        Payments
      </a>
    </nav>
  )
}
