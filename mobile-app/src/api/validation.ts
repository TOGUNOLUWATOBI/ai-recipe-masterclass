/**
 * Client-side input validation. The backend doesn't enforce length/count limits itself,
 * so these exist purely to protect the app: without them, a user (or a bug) could send
 * an empty/absurdly large payload that wastes a slow LLM call for nothing, or a runaway
 * ingredient list. This is a UX/robustness guard, not a security boundary — the
 * backend must not be assumed safe merely because the app validates first.
 */
import { getLanguage } from "../i18n/language";
import { translations } from "../i18n/translations";

export const MAX_QUESTION_LENGTH = 500;
export const MAX_INGREDIENT_LENGTH = 100;
export const MAX_INGREDIENT_COUNT = 20;

export class ValidationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ValidationError";
  }
}

export function sanitizeQuestion(raw: string): string {
  const t = translations[getLanguage()];
  const trimmed = raw.trim().replace(/\s+/g, " ");
  if (trimmed.length === 0) {
    throw new ValidationError(t.validationEnterQuestion);
  }
  if (trimmed.length > MAX_QUESTION_LENGTH) {
    throw new ValidationError(t.validationQuestionTooLong(MAX_QUESTION_LENGTH));
  }
  return trimmed;
}

export function sanitizeIngredients(raw: string[]): string[] {
  const t = translations[getLanguage()];
  const cleaned = raw
    .map((item) => item.trim().replace(/\s+/g, " "))
    .filter((item) => item.length > 0);

  if (cleaned.length === 0) {
    throw new ValidationError(t.validationEnterIngredient);
  }
  if (cleaned.length > MAX_INGREDIENT_COUNT) {
    throw new ValidationError(t.validationTooManyIngredients(MAX_INGREDIENT_COUNT));
  }
  const tooLong = cleaned.find((item) => item.length > MAX_INGREDIENT_LENGTH);
  if (tooLong) {
    throw new ValidationError(t.validationIngredientTooLong(tooLong, MAX_INGREDIENT_LENGTH));
  }
  return cleaned;
}
