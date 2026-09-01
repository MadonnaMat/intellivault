import type { CDPSession, Page } from "@playwright/test";

export interface VirtualAuthenticator {
  client: CDPSession;
  id: string;
  /** Detach this authenticator — models the device no longer being present. */
  remove(): Promise<void>;
}

/**
 * Attach a CDP virtual authenticator to the page's context. `usb` transport is
 * used because Chromium allows several of them per browser (only one `internal`).
 * With `automaticPresenceSimulation` the ceremony completes with no user prompt.
 */
export async function addVirtualAuthenticator(page: Page): Promise<VirtualAuthenticator> {
  const client = await page.context().newCDPSession(page);
  await client.send("WebAuthn.enable");
  const { authenticatorId } = await client.send("WebAuthn.addVirtualAuthenticator", {
    options: {
      protocol: "ctap2",
      transport: "usb",
      hasResidentKey: true,
      hasUserVerification: true,
      isUserVerified: true,
      automaticPresenceSimulation: true,
    },
  });
  return {
    client,
    id: authenticatorId,
    remove: () =>
      client
        .send("WebAuthn.removeVirtualAuthenticator", { authenticatorId })
        .then(() => undefined),
  };
}
