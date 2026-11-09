import { expect, test } from "@playwright/test";
import { openFirstDraft, registerAndOnboard } from "./helpers";

test("onboarding: sign up, pick a persona, jobs get scouted and analysed @mobile", async ({ page }) => {
  await registerAndOnboard(page);
  await expect(page.getByTestId("job-row").first()).toBeVisible({ timeout: 75_000 });
  await expect(page.getByText(/fit \d\.\d\d/).first()).toBeVisible({ timeout: 75_000 });
});

test("approving a proposal submits it and it reaches the pipeline", async ({ page }) => {
  await registerAndOnboard(page);
  await openFirstDraft(page);
  await expect(page.getByTestId("dry-run")).toContainText("Connects");
  // evidence on hover
  const cite = page.getByTestId("cite").first();
  if (await cite.count()) {
    await cite.hover();
    await expect(page.getByRole("tooltip")).toBeVisible();
  }
  await page.getByTestId("approve").click();
  await expect(page.getByText(/Approved/)).toBeVisible();
  await page.goto("/pipeline");
  await expect(page.getByRole("heading", { name: "Pipeline" })).toBeVisible();
  await expect(page.locator(".col").filter({ hasText: "submitted" }).locator(".kcard").first()).toBeVisible({ timeout: 30_000 });
});

test("rejecting a draft requires a reason and records it", async ({ page }) => {
  await registerAndOnboard(page);
  await openFirstDraft(page);
  await page.getByTestId("reject").click();
  await expect(page.getByTestId("reject-confirm")).toBeDisabled();
  await page.getByTestId("reject-reason").fill("Client is outside my niche");
  await page.getByTestId("reject-confirm").click();
  await expect(page.getByText("Rejected. Reason saved.")).toBeVisible();
  await page.goto("/analytics");
  await expect(page.getByText("Client is outside my niche")).toBeVisible({ timeout: 20_000 });
});

test("editing a draft approves the edited text and records the edit for style memory", async ({ page }) => {
  await registerAndOnboard(page);
  await openFirstDraft(page);
  const editor = page.getByTestId("cover-editor");
  const original = await editor.inputValue();
  const edited = original.split(/(?<=[.!?])\s+/).slice(1).join(" ");
  await editor.fill(edited);
  await expect(page.getByTestId("approve-edited")).toBeVisible();
  await page.getByTestId("approve-edited").click();
  await expect(page.getByText(/Approved/)).toBeVisible();
  await page.goto("/settings");
  await expect(page.getByRole("heading", { name: "What GigBid has learned" })).toBeVisible();
  await expect(page.getByText(/cut_first_sentence|Recent edits/).first()).toBeVisible({ timeout: 20_000 });
});

test("degraded mode: when the marketplace is down the UI says so @mobile", async ({ page }) => {
  await page.route("**/api/health", (route) =>
    route.fulfill({ json: { api: true, marketplace: { ok: false, mode: "gigsim", error: "connection refused" }, model_profile: "heuristic", policy_version: 1 } }));
  await registerAndOnboard(page);
  await expect(page.getByTestId("degraded-banner")).toBeVisible();
  await expect(page.getByTestId("degraded-banner")).toContainText("Marketplace unavailable");
});
