import { expect, type Page } from "@playwright/test";

export const PASSWORD = "e2e-password-123";

export async function registerAndOnboard(page: Page, persona = "AI/ML engineer") {
  const email = `e2e-${Date.now()}-${Math.floor(Math.random() * 1e6)}@gigbid-e2e.dev`;
  await page.goto("/login");
  await page.getByRole("tab", { name: "Create account" }).click();
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByRole("heading", { name: "Set up GigBid" })).toBeVisible();
  await page.getByText(persona).click();
  await page.getByRole("button", { name: "Start scouting" }).click();
  await expect(page.getByRole("heading", { name: "Job inbox" })).toBeVisible();
  return email;
}

/** Waits until the worker has produced at least one draft waiting for approval, then opens it. */
export async function openFirstDraft(page: Page) {
  const review = page.getByRole("link", { name: "Review draft" }).first();
  await expect(review).toBeVisible({ timeout: 75_000 });
  await review.click();
  await expect(page.getByTestId("cover-editor")).toBeVisible();
}
