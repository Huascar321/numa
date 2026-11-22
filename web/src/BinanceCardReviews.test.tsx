import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BinanceCardReviews } from "./BinanceCardReviews";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

function show(planId = "plan-one") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const view = render(<QueryClientProvider client={client}><BinanceCardReviews planId={planId} /></QueryClientProvider>);
  return { client, view };
}

const candidate = {
  id: 1, disposition: "candidate", reason: "settlement_unresolved",
  reported_amount: "99999999999999999999.90", reported_currency: "USD",
  merchant: "SYNTHETIC.MERCHANT <script>not executable</script>",
  event_at: "2026-01-01T10:00:00+00:00", notification_at: "2026-01-01T10:00:15+00:00",
  settlement_amount: null, settlement_currency: null, account_id: null,
  provenance: { source_id: "source-one", source_email: "synthetic@example.invalid", gmail_message_id: "synthetic-message",
    header_message_id: "<synthetic@example.invalid>", parser_version: "binance-card-usd-review-v1",
    ingested_at: "2026-01-01T10:01:00Z", processed_at: "2026-01-01T10:02:00Z", sender_authentication: "not_verified_by_parser" },
};

it("shows exact reported USD, unresolved settlement and safe source text without posting actions", async () => {
  const fetch = vi.fn(async (path: string, options?: RequestInit) => {
    expect(path).toBe("/plans/plan-one/gmail/binance-card-reviews?after=0&limit=25");
    expect(options?.method).toBeUndefined();
    return new Response(JSON.stringify({ candidate_count: 1, needs_review_count: 0, items: [candidate], next_after: null }));
  });
  vi.stubGlobal("fetch", fetch);
  const { client } = show();
  expect(await screen.findByText("99999999999999999999.90 USD")).toBeInTheDocument();
  expect(screen.getByText("Settlement unresolved · not posted")).toBeInTheDocument();
  expect(screen.getByText("2026-01-01 10:00:00 UTC")).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: candidate.merchant })).toBeInTheDocument();
  expect(document.querySelector("script")).toBeNull();
  expect(screen.queryByRole("button", { name: /post|approve|confirm/i })).toBeNull();
  fireEvent.click(screen.getByText("Source evidence"));
  expect(screen.getByText("synthetic-message")).toBeInTheDocument();
  expect(screen.getByText(/Sender matching is not authentication/)).toBeInTheDocument();
  client.clear();
});

it("loads the next cursor page without duplicating previous items or inferring unsupported amounts", async () => {
  const unsupported = { ...candidate, id: 2, disposition: "needs_review", reason: "unsupported_currency",
    reported_amount: null, reported_currency: null, merchant: null, event_at: null, notification_at: null };
  const fetch = vi.fn(async (path: string) => new Response(JSON.stringify({
    candidate_count: 1, needs_review_count: 1,
    items: path.includes("after=1") ? [unsupported] : [candidate], next_after: path.includes("after=1") ? null : 1,
  })));
  vi.stubGlobal("fetch", fetch);
  const { client } = show();
  fireEvent.click(await screen.findByRole("button", { name: "Load more notices" }));
  expect(await screen.findByText("Reported currency is outside the validated USD template.")).toBeInTheDocument();
  expect(screen.getAllByText("99999999999999999999.90 USD")).toHaveLength(1);
  expect(screen.getByText("No financial amount inferred · not posted")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Load more notices" })).toBeNull();
  expect(fetch.mock.calls[1][0]).toContain("after=1&limit=25");
  client.clear();
});

it("isolates query data when switching plans and explains an empty review list", async () => {
  vi.stubGlobal("fetch", vi.fn(async (path: string) => new Response(JSON.stringify({
    candidate_count: path.includes("plan-one") ? 1 : 0, needs_review_count: 0,
    items: path.includes("plan-one") ? [candidate] : [], next_after: null,
  }))));
  const { client, view } = show();
  await screen.findByText("99999999999999999999.90 USD");
  view.rerender(<QueryClientProvider client={client}><BinanceCardReviews planId="plan-two" /></QueryClientProvider>);
  expect(screen.queryByText("99999999999999999999.90 USD")).toBeNull();
  expect(await screen.findByText(/No Binance notices to inspect yet/)).toBeInTheDocument();
  client.clear();
});

it("exposes a retryable read error without obscuring existing finances", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ detail: "unavailable" }), { status: 503 })));
  const { client } = show();
  expect(await screen.findByRole("alert")).toHaveTextContent("Existing financial records are unchanged.");
  expect(within(screen.getByRole("region", { name: "Binance Card review" })).getByRole("button", { name: "Retry loading notices" })).toBeEnabled();
  client.clear();
});
