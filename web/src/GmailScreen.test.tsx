import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { GmailScreen } from "./GmailScreen";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

function show(planId = "plan-one") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[`/plans/${planId}/gmail`]}>
    <Routes><Route path="/plans/:planId/gmail" element={<GmailScreen />} /></Routes>
  </MemoryRouter></QueryClientProvider>);
  return client;
}

function emptyReviews(path: string) {
  return path.includes("binance-card-reviews")
    ? new Response(JSON.stringify({ candidate_count: 0, needs_review_count: 0, items: [], next_after: null }))
    : null;
}

it("shows Gmail as optional when configuration is absent", async () => {
  const fetch = vi.fn(async (path: string) => emptyReviews(path) ?? new Response(JSON.stringify({ configured: false, configured_senders: [], sources: [] })));
  vi.stubGlobal("fetch", fetch);
  const client = show();
  expect(await screen.findByText("Gmail is not configured on the server yet.")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Connect Gmail" })).toBeDisabled();
  expect(screen.getByText("No allowed senders configured; new connections are disabled.")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "← Accounts" })).toHaveAttribute("href", "/plans/plan-one/accounts");
  expect(document.querySelector('input[type="password"]')).toBeNull();
  client.clear();
});

it("disconnects the selected source and refetches authoritative state", async () => {
  const source = { id: "source-one", email: "me@example.com", status: "active", sync_mode: "history",
    last_synced_at: null, last_error: null, message_count: 7, review_count: 2, allowed_senders: ["saved@example.com"] };
  const fetch = vi.fn(async (path: string, options?: RequestInit) => {
    const reviews = emptyReviews(path);
    if (reviews) return reviews;
    if (options?.method === "POST") {
      expect(path).toBe("/plans/plan-one/gmail/source-one/disconnect");
      source.status = "disconnected";
      return new Response(JSON.stringify(source));
    }
    expect(path).toBe("/plans/plan-one/gmail");
    return new Response(JSON.stringify({ configured: true, configured_senders: ["new@example.com"], sources: [source] }));
  });
  vi.stubGlobal("fetch", fetch);
  const client = show();
  expect(await screen.findByText("7 emails collected · 2 require review")).toBeInTheDocument();
  fireEvent.click(screen.getByText("Connection settings"));
  expect(screen.getByText("saved@example.com")).toBeInTheDocument();
  expect(screen.getByText("new@example.com")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Reconnect" })).toBeEnabled();
  expect(screen.getByText(/Google's permission is mailbox-wide/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Disconnect" }));
  expect(await screen.findByText("Disconnected")).toBeInTheDocument();
  expect(screen.getByText("7 emails collected · 2 require review")).toBeInTheDocument();
  await waitFor(() => expect(fetch.mock.calls.filter(([path]) => !path.includes("binance-card-reviews"))).toHaveLength(3));
  client.clear();
});

it("reports authorization errors without a password form", async () => {
  vi.stubGlobal("fetch", vi.fn(async (path: string, options?: RequestInit) => emptyReviews(path) ?? (options?.method === "POST"
    ? new Response(JSON.stringify({ detail: "Gmail is not configured on the server." }), { status: 503 })
    : new Response(JSON.stringify({ configured: true, configured_senders: ["notice@example.com"], sources: [] })))));
  const client = show();
  await waitFor(() => expect(screen.getByRole("button", { name: "Connect Gmail" })).toBeEnabled());
  fireEvent.click(screen.getByRole("button", { name: "Connect Gmail" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Gmail is not configured on the server.");
  expect(document.querySelector('input[type="password"]')).toBeNull();
  client.clear();
});

it("shows legacy unscoped connections and blocks reconnect without server scope", async () => {
  vi.stubGlobal("fetch", vi.fn(async (path: string) => emptyReviews(path) ?? new Response(JSON.stringify({
    configured: false, configured_senders: [], sources: [{
      id: "legacy", email: "me@example.com", status: "needs_authorization", sync_mode: "full",
      allowed_senders: [], last_synced_at: null, last_error: "ingestion_filter_required",
      message_count: 2, review_count: 0,
    }],
  }))));
  const client = show();
  expect(await screen.findByText("No saved sender scope. Reconnect before collection can resume.")).toBeInTheDocument();
  fireEvent.click(screen.getByText("Connection settings"));
  expect(screen.getByRole("button", { name: "Reconnect" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Disconnect" })).toBeEnabled();
  expect(screen.getByText("2 emails collected · 0 require review")).toBeInTheDocument();
  client.clear();
});
