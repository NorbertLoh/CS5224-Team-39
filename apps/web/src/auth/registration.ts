import type { AuthConfig } from './session'

const errors: Record<string, string> = {
  UsernameExistsException:
    'An account with this email already exists. Sign in, or choose “I have a verification code” to finish verifying it.',
  InvalidPasswordException:
    'Choose a stronger password that meets the account password requirements.',
  CodeMismatchException:
    'That code does not match. Check your email and try again.',
  ExpiredCodeException: 'That code has expired. Request a new code below.',
  TooManyRequestsException:
    'Too many attempts. Please wait a moment and try again.',
  LimitExceededException:
    'The verification limit was reached. Wait a while, then request a new code.',
  NotAuthorizedException:
    'Registration is unavailable or this account is already confirmed. Try signing in.',
  InvalidParameterException:
    'Check your details and try again. Your password must meet the account requirements.',
  CodeDeliveryFailureException:
    'The verification email could not be delivered. Check the email address and request a new code.',
}

async function request(config: AuthConfig, action: string, values: object) {
  let response: Response
  try {
    response = await fetch(config.apiUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-amz-json-1.1',
        'X-Amz-Target': `AWSCognitoIdentityProviderService.${action}`,
      },
      body: JSON.stringify({ ClientId: config.clientId, ...values }),
      credentials: 'omit',
      cache: 'no-store',
      redirect: 'error',
      signal: AbortSignal.timeout(15000),
    })
  } catch {
    throw new Error('Unable to reach account services. Please try again.')
  }
  const result = await response.json().catch(() => null)
  if (!response.ok) {
    const code =
      String(result?.__type || result?.code || '')
        .split('#')
        .pop() || ''
    throw new Error(
      errors[code] || 'Unable to complete registration. Please try again.',
    )
  }
  if (!result || typeof result !== 'object')
    throw new Error(
      'Account services returned an invalid response. Please try again.',
    )
  return result
}

export async function signUp(
  config: AuthConfig,
  name: string,
  email: string,
  password: string,
): Promise<boolean> {
  const result = await request(config, 'SignUp', {
    Username: email.trim(),
    Password: password,
    UserAttributes: [
      { Name: 'email', Value: email.trim() },
      { Name: 'name', Value: name.trim() },
    ],
  })
  if (
    typeof result.UserConfirmed !== 'boolean' ||
    typeof result.UserSub !== 'string'
  )
    throw new Error(
      'Account creation could not be confirmed. Try signing in or verifying your email.',
    )
  return result.UserConfirmed
}

export async function confirmSignUp(
  config: AuthConfig,
  email: string,
  code: string,
) {
  await request(config, 'ConfirmSignUp', {
    Username: email.trim(),
    ConfirmationCode: code.trim(),
    ForceAliasCreation: false,
  })
}

export async function resendSignUpCode(config: AuthConfig, email: string) {
  await request(config, 'ResendConfirmationCode', { Username: email.trim() })
}
