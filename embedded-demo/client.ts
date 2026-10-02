/*
 * Licensed to the Apache Software Foundation (ASF) under one or more
 * contributor license agreements. See the NOTICE file distributed with
 * this work for additional information regarding copyright ownership.
 * The ASF licenses this file to You under the Apache License, Version 2.0
 * (the "License"); you may not use this file except in compliance with
 * the License. You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

import { embedDashboard } from "@superset-ui/embedded-sdk";

type Viewer = { id: string; label: string; country: string };
const mount = document.querySelector<HTMLDivElement>("#dashboard")!;
const status = document.querySelector<HTMLElement>("#status")!;
const identity = document.querySelector<HTMLElement>("#identity")!;
const logout = document.querySelector<HTMLButtonElement>("#logout")!;
const retry = document.querySelector<HTMLButtonElement>("#retry")!;
let embedded: Awaited<ReturnType<typeof embedDashboard>> | undefined;
let busy = false;

async function request<T>(url: string, body?: object): Promise<T> {
  const response = await fetch(url, {
    method: body ? "POST" : "GET",
    credentials: "same-origin",
    cache: "no-store",
    ...(body
      ? {
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        }
      : {}),
  });
  if (!response.ok) {
    throw new Error(
      response.status === 401
        ? "Your demo session ended. Choose a viewer to continue."
        : "Unable to load analytics. Check that FocalBI is running, then retry.",
    );
  }
  return response.status === 204
    ? (undefined as T)
    : (response.json() as Promise<T>);
}

function clearDashboard(): void {
  embedded?.unmount();
  embedded = undefined;
  mount.replaceChildren();
}

async function showDashboard(viewer: Viewer | null): Promise<void> {
  clearDashboard();
  retry.hidden = true;
  logout.hidden = !viewer;
  identity.textContent = viewer
    ? `${viewer.label} · ${viewer.country} data only`
    : "No demo viewer selected";
  document
    .querySelectorAll<HTMLButtonElement>("[data-viewer]")
    .forEach((button) => {
      button.setAttribute(
        "aria-pressed",
        String(button.dataset.viewer === viewer?.id),
      );
    });
  mount.hidden = !viewer;
  if (!viewer) {
    status.textContent =
      "Choose a demo viewer to open the interactive dashboard.";
    return;
  }
  status.textContent = "Opening dashboard…";
  const config = await request<{
    dashboardUuid: string;
    supersetDomain: string;
  }>("/api/analytics/config");
  embedded = await embedDashboard({
    id: config.dashboardUuid,
    supersetDomain: config.supersetDomain,
    mountPoint: mount,
    fetchGuestToken: async () => {
      try {
        const result = await request<{ token: string; issuedAt: string }>(
          "/api/analytics/guest-token",
        );
        status.textContent = `Access renewed at ${new Date(result.issuedAt).toLocaleTimeString()}. Use the dashboard filters and tabs below.`;
        return result.token;
      } catch (error) {
        status.textContent =
          error instanceof Error ? error.message : "Session expired.";
        retry.hidden = false;
        clearDashboard();
        throw error;
      }
    },
    dashboardUiConfig: {
      hideTitle: false,
      hideTab: false,
      hideChartControls: false,
      filters: { visible: true, expanded: true },
    },
    referrerPolicy: "strict-origin-when-cross-origin",
    iframeTitle: "Interactive sales dashboard",
  });
}

async function run(action: () => Promise<void>): Promise<void> {
  if (busy) return;
  busy = true;
  document.querySelectorAll<HTMLButtonElement>("button").forEach((button) => {
    button.disabled = true;
  });
  try {
    await action();
  } catch (error) {
    status.textContent =
      error instanceof Error ? error.message : "Unable to open the dashboard.";
    retry.hidden = false;
  } finally {
    busy = false;
    document.querySelectorAll<HTMLButtonElement>("button").forEach((button) => {
      button.disabled = false;
    });
  }
}
document
  .querySelectorAll<HTMLButtonElement>("[data-viewer]")
  .forEach((button) => {
    button.addEventListener(
      "click",
      () =>
        void run(async () => {
          clearDashboard();
          await request("/api/demo/session", { viewer: button.dataset.viewer });
          // SDK 0.3.0 does not cancel renewal timers in unmount(). A document
          // reload disposes the old viewer's timers as well as its iframe.
          window.location.reload();
        }),
    );
  });
logout.addEventListener(
  "click",
  () =>
    void run(async () => {
      await request("/api/logout", {});
      clearDashboard();
      window.location.reload();
    }),
);
async function restore(): Promise<void> {
  const result = await request<{ viewer: Viewer | null }>("/api/session");
  await showDashboard(result.viewer);
}
retry.addEventListener("click", () => window.location.reload());
window.addEventListener("pagehide", clearDashboard);
void run(restore);
