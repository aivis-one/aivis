// =============================================================================
// AIVIS.ONE Frontend -- The password rule (H44)
// =============================================================================
//
// The same two numbers as the server's NewPassword (backend
// app/modules/users/schemas.py), which every password field there is held
// to: registration, the reset, the first password of an account that has
// none, a new project account. Pydantic's length constraints do not reach
// generated.ts, so the frontend keeps them here, once, and every screen that
// checks a password before sending it reads them from this file. The server
// stays the judge: a password outside the rule is a 422 there whatever this
// file says.
// =============================================================================

export const PASSWORD_MIN_LENGTH = 8
export const PASSWORD_MAX_LENGTH = 128

/** Whether `password` is within the rule's length limits. */
export function passwordWithinRule(password: string): boolean {
  return password.length >= PASSWORD_MIN_LENGTH && password.length <= PASSWORD_MAX_LENGTH
}
