// The shell: which tool opens, the rail of icons, and the address bar following the open tool.
// Nothing here waits for Yahoo or SEC — only what renders without the network.
import { expect, test } from "@playwright/test";

test("/ opens the Signals tool and the URL becomes /signals", async ({ page }) => {
    await page.goto("/");

    await expect(page).toHaveURL(/\/signals$/);
    await expect(page.getByRole("heading", { name: "Sygnały końca hossy na AI", exact: true })).toBeVisible();
});

test("the Reverse DCF icon has a tooltip and opens its tool", async ({ page }) => {
    await page.goto("/");
    const icon = page.getByRole("button", { name: "Reverse DCF", exact: true });

    await icon.hover();
    await expect(page.getByRole("tooltip")).toHaveText("Reverse DCF");

    await icon.click();

    await expect(page).toHaveURL(/\/reverse-dcf$/);
    await expect(page.getByLabel("Ticker", { exact: true })).toBeVisible();
});

test("an unknown path lands on Signals, and Back returns to the previous tool", async ({ page }) => {
    await page.goto("/nowhere");
    await expect(page).toHaveURL(/\/signals$/);

    await page.getByRole("button", { name: "Reverse DCF", exact: true }).click();
    await expect(page).toHaveURL(/\/reverse-dcf$/);

    await page.goBack();
    await expect(page).toHaveURL(/\/signals$/);
    await expect(page.getByRole("heading", { name: "Sygnały końca hossy na AI", exact: true })).toBeVisible();
});
