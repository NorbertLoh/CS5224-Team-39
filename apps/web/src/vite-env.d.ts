/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_USE_AWS?: 'true' | 'false'
  readonly VITE_LOCAL_API_BASE_URL?: string
  readonly VITE_AWS_API_BASE_URL?: string
  readonly VITE_COGNITO_CLIENT_ID?: string
  readonly VITE_COGNITO_ISSUER?: string
  readonly VITE_COGNITO_OAUTH_BASE_URL?: string
  readonly VITE_COGNITO_API_URL?: string
  readonly VITE_AWS_COGNITO_CLIENT_ID?: string
  readonly VITE_AWS_COGNITO_ISSUER?: string
  readonly VITE_AWS_COGNITO_OAUTH_BASE_URL?: string
  readonly VITE_AWS_COGNITO_API_URL?: string
}
