// Listing wizard steps (T105), shared by the server page (initial step from `?step=`) and
// the client wizard.
export const STEPS = ["details", "location", "photos", "prices", "rules", "review"] as const;
export type Step = (typeof STEPS)[number];

export function isStep(value: string | undefined): value is Step {
  return STEPS.includes(value as Step);
}
