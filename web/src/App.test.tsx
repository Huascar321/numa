import { ReactNode } from "react";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AppRoutes } from "./App";

type TestPlan = {
  id: string;
  name: string;
  reporting_currency_code: string;
  created_at: string;
  updated_at: string;
};

type TestAccount = {
  id: string;
  plan_id: string;
  name: string;
  account_type: "Bank" | "Cash" | "Wallet" | "Credit Card" | "Crypto" | "Other";
  currency_code: string;
  status: "active" | "archived";
  balance: { amount: string; currency: string };
  created_at: string;
  updated_at: string;
};

const timestamp = "2026-08-13T00:00:00Z";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function createServer() {
  const plans: TestPlan[] = [];
  const accounts = new Map<string, TestAccount>();
  const getAccountRequests: string[] = [];

  const fetchMock = vi.fn(async (
    input: RequestInfo | URL,
    init?: RequestInit,
  ): Promise<Response> => {
    const url = typeof input === "string" ? input : input.toString();
    const path = new URL(url, "http://localhost").pathname;
    const method = init?.method ?? "GET";
    const body = init?.body ? JSON.parse(String(init.body)) as Record<string, string> : {};

    if (path === "/currencies" && method === "GET") {
      return jsonResponse([
        { code: "BOB", decimal_places: 2 },
        { code: "USDT", decimal_places: 6 },
      ]);
    }
    if (path === "/plans" && method === "GET") return jsonResponse(plans);
    if (path === "/plans" && method === "POST") return jsonResponse({}, 405);

    const accountMatch = path.match(/^\/plans\/([^/]+)\/accounts(?:\/([^/]+)(?:\/archive)?)?$/);
    if (accountMatch) {
      const [, planId, accountId] = accountMatch;
      if (method === "GET" && !accountId) {
        getAccountRequests.push(planId);
        return jsonResponse(plans.some((plan) => plan.id === planId)
          ? [...accounts.values()].filter((account) => account.plan_id === planId)
          : []);
      }
      if (method === "PUT" && accountId) {
        const account: TestAccount = {
          id: accountId,
          plan_id: planId,
          name: body.name,
          account_type: body.account_type as TestAccount["account_type"],
          currency_code: body.currency_code,
          status: "active",
          balance: {
            amount: body.currency_code === "USDT" ? "0.000000" : "0.00",
            currency: body.currency_code,
          },
          created_at: timestamp,
          updated_at: timestamp,
        };
        accounts.set(accountId, account);
        return jsonResponse(account, 201);
      }
      if (method === "PATCH" && accountId) {
        const account = accounts.get(accountId);
        if (!account || account.status === "archived") return jsonResponse({}, 409);
        account.name = body.name;
        return jsonResponse(account);
      }
      if (method === "POST" && accountId && path.endsWith("/archive")) {
        const account = accounts.get(accountId);
        if (!account) return jsonResponse({}, 404);
        account.status = "archived";
        return jsonResponse(account);
      }
    }

    const planMatch = path.match(/^\/plans\/([^/]+)$/);
    if (planMatch) {
      const [, planId] = planMatch;
      if (method === "PUT") {
        const plan: TestPlan = {
          id: planId,
          name: body.name,
          reporting_currency_code: body.reporting_currency_code,
          created_at: timestamp,
          updated_at: timestamp,
        };
        plans.push(plan);
        return jsonResponse(plan, 201);
      }
      const plan = plans.find((item) => item.id === planId);
      if (!plan) return jsonResponse({}, 404);
      if (method === "GET") return jsonResponse(plan);
      if (method === "PATCH") {
        plan.name = body.name;
        return jsonResponse(plan);
      }
    }

    return jsonResponse({}, 404);
  });

  vi.stubGlobal("fetch", fetchMock);
  return {
    fetchMock,
    getAccountRequests,
    seedPlan(plan: TestPlan) {
      plans.push(plan);
    },
  };
}

function renderApp(initialEntry: string) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>{children}</MemoryRouter>
    </QueryClientProvider>
  );
  return { queryClient, ...render(<AppRoutes />, { wrapper }) };
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("minimal authoritative client flows", () => {
  it("creates and selects a Plan using server responses", async () => {
    createServer();
    renderApp("/plans");

    expect(await screen.findByRole("heading", { name: "Plans" })).toBeInTheDocument();
    await screen.findByRole("option", { name: "BOB" });
    const name = screen.getByLabelText("Name");
    fireEvent.change(name, { target: { value: "Personal Plan" } });
    fireEvent.click(screen.getByRole("button", { name: "Create Plan" }));

    expect(await screen.findByRole("heading", { name: "Accounts" })).toBeInTheDocument();
    expect(screen.getByText("Personal Plan")).toBeInTheDocument();
  });

  it("lists and renames a selected Plan without changing its currency", async () => {
    const server = createServer();
    server.seedPlan({
      id: "plan-existing",
      name: "Existing Plan",
      reporting_currency_code: "USDT",
      created_at: timestamp,
      updated_at: timestamp,
    });
    renderApp("/plans");

    expect(await screen.findByText("Existing Plan")).toBeInTheDocument();
    expect(screen.getByText(/Reporting currency:/)).toHaveTextContent("USDT");
    fireEvent.click(screen.getByRole("button", { name: "Rename" }));
    fireEvent.change(screen.getByLabelText("New name"), {
      target: { value: "Renamed Plan" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByText("Renamed Plan")).toBeInTheDocument();
    expect(screen.getByText(/Reporting currency:/)).toHaveTextContent("USDT");
    expect(server.fetchMock).toHaveBeenCalledWith(
      "/plans",
      expect.anything(),
    );
  });

  it("creates, renames, archives, and refetches Accounts with exact balances", async () => {
    const server = createServer();
    const planId = "plan-accounts";
    const plan: TestPlan = {
      id: planId,
      name: "Accounts Plan",
      reporting_currency_code: "BOB",
      created_at: timestamp,
      updated_at: timestamp,
    };
    server.seedPlan(plan);
    renderApp(`/plans/${planId}/accounts`);

    expect(await screen.findByRole("heading", { name: "Accounts" })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "USDT wallet" } });
    fireEvent.change(screen.getByLabelText("Type"), { target: { value: "Crypto" } });
    fireEvent.change(screen.getByLabelText("Currency"), { target: { value: "USDT" } });
    fireEvent.click(screen.getByRole("button", { name: "Create Account" }));

    expect(await screen.findByText("USDT wallet")).toBeInTheDocument();
    expect(screen.getByText("0.000000 USDT")).toBeInTheDocument();
    const accountCard = () => screen.getByText(/USDT wallet|Renamed wallet/).closest("article") as HTMLElement;

    fireEvent.click(within(accountCard()).getByRole("button", { name: "Rename" }));
    fireEvent.change(screen.getByLabelText("New name"), { target: { value: "Renamed wallet" } });
    fireEvent.click(within(accountCard()).getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Renamed wallet")).toBeInTheDocument();

    fireEvent.click(within(accountCard()).getByRole("button", { name: "Archive" }));
    const archivedCard = await screen.findByText("Renamed wallet");
    const archivedArticle = archivedCard.closest("article") as HTMLElement;
    await waitFor(() => expect(within(archivedArticle).getByText("archived"))
      .toBeInTheDocument());
    expect(within(archivedArticle).queryByRole("button", { name: "Rename" }))
      .not.toBeInTheDocument();
    expect(within(archivedArticle).queryByRole("button", { name: "Archive" }))
      .not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /transactions/i }))
      .not.toBeInTheDocument();
    expect(document.querySelector('link[rel="manifest"]')).not.toBeInTheDocument();
    await waitFor(() => expect(server.getAccountRequests.length).toBeGreaterThanOrEqual(4));
  });
});
