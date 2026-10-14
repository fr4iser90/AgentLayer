/** Mirrors apps/backend/domain/identity/password_policy.py */

export const MIN_PASSWORD_LENGTH = 12;

const SEQ = [
  "0123456789",
  "9876543210",
  "abcdefghijklmnopqrstuvwxyz",
  "zyxwvutsrqponmlkjihgfedcba",
  "qwertyuiop",
  "asdfghjkl",
  "zxcvbnm"
];

function hasLongSequence(lower: string, run = 4): boolean {
  if (lower.length < run) return false;
  for (const seq of SEQ) {
    for (let i = 0; i <= seq.length - run; i++) {
      if (lower.includes(seq.slice(i, i + run))) return true;
    }
  }
  return false;
}

function hasRepeatedRun(password: string, run = 4): boolean {
  return new RegExp(`(.)\\1{${run - 1},}`).test(password);
}

export type PasswordStrengthLevel = 0 | 1 | 2 | 3;

export type PasswordRejectKey =
  | "atLeast"
  | "lower"
  | "upper"
  | "digit"
  | "symbol"
  | "sequence";

export function passwordRejectionReason(password: string): PasswordRejectKey | null {
  const p = password || "";
  if (p.length < MIN_PASSWORD_LENGTH) return "atLeast";
  if (!/[a-z]/.test(p)) return "lower";
  if (!/[A-Z]/.test(p)) return "upper";
  if (!/\d/.test(p)) return "digit";
  if (!/[^A-Za-z0-9]/.test(p)) return "symbol";
  const lower = p.toLowerCase();
  if (hasLongSequence(lower) || hasRepeatedRun(p)) return "sequence";
  return null;
}

export function passwordStrengthLevel(password: string): PasswordStrengthLevel {
  const p = password || "";
  if (!p) return 0;
  if (passwordRejectionReason(p) !== null) return 1;
  if (p.length >= 16) return 3;
  return 2;
}
