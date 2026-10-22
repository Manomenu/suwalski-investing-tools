// The signals tool against a real server with an empty database: every check is on the board
// even before the job ever ran, and a check's page is reachable by its address (Discord links).
import { expect, test } from "@playwright/test";

test("the board lists the checks and says the job has not run yet", async ({ page }) => {
    await page.goto("/signals");

    await expect(page.getByRole("button", { name: "A1 Chmura hamuje przy rosnącym capeksie", exact: true })).toBeVisible();
    await expect(page.getByText("Job jeszcze nie biegł", { exact: false })).toBeVisible();
});

test("a check's address opens its panel, and closing it returns to the board", async ({ page }) => {
    await page.goto("/signals/A2");

    await expect(page.getByRole("heading", { name: "ARR labów stoi w miejscu", exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Zamknij", exact: true }).click();
    await expect(page).toHaveURL(/\/signals$/);
});

test("the timeline is one click away", async ({ page }) => {
    await page.goto("/signals");

    await page.getByText("Oś czasu", { exact: true }).click();

    await expect(page).toHaveURL(/\/signals\/feed$/);
    await expect(page.getByText("Nic takiego jeszcze nie było.", { exact: true })).toBeVisible();
});
