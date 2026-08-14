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
import type { Category, CategoryGroup, Tag } from "./api";

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

function createLedgerServer() {
  const planId = "plan-ledger";
  const accountId = "account-ledger";
  const pendingId = "category-pending";
  const categoryId = "category-groceries";
  const groupId = "group-needs";
  const tagId = "tag-recurring";
  const plan: TestPlan & { budget_timezone: string } = {
    id: planId,
    name: "Ledger Plan",
    reporting_currency_code: "BOB",
    budget_timezone: "America/La_Paz",
    created_at: timestamp,
    updated_at: timestamp,
  };
  const accounts: TestAccount[] = [{
    id: accountId,
    plan_id: planId,
    name: "Main account",
    account_type: "Bank",
    currency_code: "BOB",
    status: "active",
    balance: { amount: "0.00", currency: "BOB" },
    created_at: timestamp,
    updated_at: timestamp,
  }, {
    id: "account-usdt",
    plan_id: planId,
    name: "USDT wallet",
    account_type: "Crypto",
    currency_code: "USDT",
    status: "active",
    balance: { amount: "0.000000", currency: "USDT" },
    created_at: timestamp,
    updated_at: timestamp,
  }];
  const categories: Category[] = [
    {
      id: pendingId,
      plan_id: planId,
      group_id: null,
      name: "Pendientes",
      is_pending: true,
      status: "active" as const,
      created_at: timestamp,
      updated_at: timestamp,
    },
    {
      id: categoryId,
      plan_id: planId,
      group_id: null,
      name: "Groceries",
      is_pending: false,
      status: "active" as const,
      created_at: timestamp,
      updated_at: timestamp,
    },
  ];
  const groups: CategoryGroup[] = [{
    id: groupId,
    plan_id: planId,
    name: "Needs",
    status: "active" as const,
    created_at: timestamp,
    updated_at: timestamp,
  }];
  const tags: Tag[] = [{
    id: tagId,
    plan_id: planId,
    name: "Recurring",
    status: "active" as const,
    created_at: timestamp,
    updated_at: timestamp,
  }];
  const transactions: Array<Record<string, unknown>> = [];
  const corrections = new Map<string, Array<Record<string, unknown>>>();
  const assignments: Array<Record<string, unknown>> = [];
  const transfers: Array<Record<string, unknown>> = [];
  const fetchMock = vi.fn(async (
    input: RequestInfo | URL,
    init?: RequestInit,
  ): Promise<Response> => {
    const url = typeof input === "string" ? input : input.toString();
    const path = new URL(url, "http://localhost").pathname;
    const method = init?.method ?? "GET";
    const body = init?.body
      ? JSON.parse(String(init.body)) as Record<string, unknown>
      : {};
    if (path === "/currencies" && method === "GET") {
      return jsonResponse([
        { code: "BOB", decimal_places: 2 },
        { code: "USDT", decimal_places: 6 },
      ]);
    }
    if (path === `/plans/${planId}` && method === "GET") return jsonResponse(plan);
    if (path === `/plans/${planId}/accounts` && method === "GET") return jsonResponse(accounts);
    if (path === `/plans/${planId}/categories` && method === "GET") return jsonResponse(categories);
    if (path === `/plans/${planId}/category-groups` && method === "GET") return jsonResponse(groups);
    if (path === `/plans/${planId}/tags` && method === "GET") return jsonResponse(tags);

    const groupPut = path.match(new RegExp(`^/plans/${planId}/category-groups/([^/]+)$`));
    if (groupPut && method === "PUT") {
      const group = {
        id: groupPut[1], plan_id: planId, name: String(body.name), status: "active" as const,
        created_at: timestamp, updated_at: timestamp,
      };
      groups.push(group);
      return jsonResponse(group, 201);
    }
    const groupArchive = path.match(new RegExp(`^/plans/${planId}/category-groups/([^/]+)/archive$`));
    if (groupArchive && method === "POST") {
      const group = groups.find((item) => item.id === groupArchive[1]);
      if (!group) return jsonResponse({}, 404);
      group.status = "archived";
      return jsonResponse(group);
    }
    const categoryPut = path.match(new RegExp(`^/plans/${planId}/categories/([^/]+)$`));
    if (categoryPut && method === "PUT") {
      const category = {
        id: categoryPut[1], plan_id: planId, group_id: (body.group_id as string | null) ?? null,
        name: String(body.name), is_pending: false, status: "active" as const,
        created_at: timestamp, updated_at: timestamp,
      };
      categories.push(category);
      return jsonResponse(category, 201);
    }
    const categoryArchive = path.match(new RegExp(`^/plans/${planId}/categories/([^/]+)/archive$`));
    if (categoryArchive && method === "POST") {
      const category = categories.find((item) => item.id === categoryArchive[1]);
      if (!category || category.is_pending) return jsonResponse({}, 409);
      category.status = "archived";
      return jsonResponse(category);
    }
    const tagPut = path.match(new RegExp(`^/plans/${planId}/tags/([^/]+)$`));
    if (tagPut && method === "PUT") {
      const tag = {
        id: tagPut[1], plan_id: planId, name: String(body.name), status: "active" as const,
        created_at: timestamp, updated_at: timestamp,
      };
      tags.push(tag);
      return jsonResponse(tag, 201);
    }
    const tagArchive = path.match(new RegExp(`^/plans/${planId}/tags/([^/]+)/archive$`));
    if (tagArchive && method === "POST") {
      const tag = tags.find((item) => item.id === tagArchive[1]);
      if (!tag) return jsonResponse({}, 404);
      tag.status = "archived";
      return jsonResponse(tag);
    }

    if (path === `/plans/${planId}/transactions` && method === "GET") {
      return jsonResponse(transactions);
    }
    if (path === `/plans/${planId}/transfers` && method === "GET") return jsonResponse(transfers);
    const transferPut = path.match(new RegExp(`^/plans/${planId}/transfers/([^/]+)$`));
    if (transferPut && method === "PUT") {
      const transfer = {
        id: transferPut[1], plan_id: planId, source_account_id: body.source_account_id,
        destination_account_id: body.destination_account_id, outbound_amount: body.outbound_amount,
        outbound_currency_code: "BOB", inbound_amount: body.inbound_amount,
        inbound_currency_code: "USDT", event_at: body.event_at, rate: "10.00000000000000000000000000000000000000",
        rate_source: body.rate_source, memo: body.memo ?? null, reversal_reason: null,
        provenance: body.provenance ?? {}, reverses_transfer_id: null, created_at: timestamp,
        legs: [{ id: "leg-out", role: "outbound", transaction_id: "transaction-out", movement_id: "movement-out" }, { id: "leg-in", role: "inbound", transaction_id: "transaction-in", movement_id: "movement-in" }],
      };
      transfers.push(transfer);
      transactions.push(transfer);
      return jsonResponse(transfer, 201);
    }
    const reversalPut = path.match(new RegExp(`^/plans/${planId}/transfers/([^/]+)/reversals/([^/]+)$`));
    if (reversalPut && method === "PUT") {
      const parent = transfers.find((transfer) => transfer.id === reversalPut[1]);
      if (!parent) return jsonResponse({}, 404);
      const reversal = { ...parent, id: reversalPut[2], event_at: body.event_at, memo: body.memo ?? null,
        reversal_reason: body.reversal_reason, reverses_transfer_id: parent.id, rate_source: "reversal" };
      transfers.push(reversal);
      transactions.push(reversal);
      return jsonResponse(reversal, 201);
    }
    const transactionPut = path.match(new RegExp(`^/plans/${planId}/transactions/([^/]+)$`));
    if (transactionPut && method === "PUT") {
      const transaction = {
        id: transactionPut[1], plan_id: planId, account_id: String(body.account_id),
        type: body.type, amount: String(body.amount), currency_code: String(body.currency_code),
        event_at: String(body.event_at), category_id: (body.category_id as string | undefined) ?? pendingId,
        merchant: (body.merchant as string | undefined) ?? null,
        memo: (body.memo as string | undefined) ?? null, photo_reference: null, location: null,
        tags: (body.tags as string[] | undefined) ?? [], source: "manual", source_metadata: {},
        provenance: {}, created_at: timestamp, updated_at: timestamp,
      };
      transactions.push(transaction);
      const account = accounts.find((item) => item.id === transaction.account_id);
      if (account) account.balance.amount = `-${transaction.amount as string}`;
      return jsonResponse(transaction, 201);
    }
    const correctionsPath = path.match(new RegExp(`^/plans/${planId}/transactions/([^/]+)/corrections$`));
    if (correctionsPath && method === "GET") return jsonResponse(corrections.get(correctionsPath[1]) ?? []);
    const correctionPut = path.match(new RegExp(`^/plans/${planId}/transactions/([^/]+)/corrections/([^/]+)$`));
    if (correctionPut && method === "PUT") {
      const transaction = transactions.find((item) => item.id === correctionPut[1]);
      if (!transaction) return jsonResponse({}, 404);
      const transactionKey = String(transaction.id);
      const history = corrections.get(transactionKey) ?? [];
      const before = { ...transaction };
      if (body.amount !== undefined) transaction.amount = String(body.amount);
      const after = { ...transaction };
      const correction = {
        id: correctionPut[2], plan_id: planId, transaction_id: transaction.id,
        correction_sequence: history.length + 1, before_snapshot: before,
        after_snapshot: after, provenance: {}, created_at: timestamp,
      };
      history.push(correction);
      corrections.set(transactionKey, history);
      const account = accounts.find((item) => item.id === String(transaction.account_id));
      if (account) account.balance.amount = `-${transaction.amount as string}`;
      return jsonResponse(correction, 201);
    }

    const summaryPath = path.match(new RegExp(`^/plans/${planId}/budget/months/([^/]+)$`));
    if (summaryPath && method === "GET") {
      const amount = transactions[0]?.amount === "15.00" ? "-15.00" : transactions.length ? "-12.00" : "0.00";
      const assigned = assignments.reduce((sum, item) => sum + Number(item.amount), 0);
      return jsonResponse({
        plan_id: planId, month: summaryPath[1], currency: "BOB", ready_to_assign: "0.00",
        assigned_total: assigned.toFixed(2), activity_total: amount,
        available_total: (assigned + Number(amount)).toFixed(2),
        unconverted_by_currency: [{ currency: "USDT", income: "0.000000", expense: "-1.000000", amount: "-1.000000", movement_ids: ["movement-usdt"], transaction_ids: ["transaction-usdt"] }],
        categories: [{ plan_id: planId, category_id: categoryId, month: summaryPath[1], currency: "BOB", assigned: assigned.toFixed(2), activity: amount, available: (assigned + Number(amount)).toFixed(2), unconverted_by_currency: [{ currency: "USDT", income: "0.000000", expense: "-1.000000", amount: "-1.000000", movement_ids: ["movement-usdt"], transaction_ids: ["transaction-usdt"] }] }],
      });
    }
    const assignmentPut = path.match(new RegExp(`^/plans/${planId}/budget-assignments/([^/]+)$`));
    if (assignmentPut && method === "PUT") {
      const assignment = { id: assignmentPut[1], plan_id: planId, category_id: body.category_id, month_key: body.month, amount: body.amount, currency_code: "BOB", source: "manual", provenance: {}, created_at: timestamp };
      assignments.push(assignment);
      return jsonResponse(assignment, 201);
    }
    return jsonResponse({}, 404);
  });
  vi.stubGlobal("fetch", fetchMock);
  return { planId, accountId, fetchMock };
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

    expect(await screen.findByRole("heading", { level: 1, name: "Accounts" })).toBeInTheDocument();
    expect(await screen.findByText("Personal Plan")).toBeInTheDocument();
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

  it("protects Pendientes and creates and archives taxonomy resources", async () => {
    createLedgerServer();
    renderApp("/plans/plan-ledger/ledger");

    expect(await screen.findByRole("heading", { name: "Ledger" })).toBeInTheDocument();
    const pendingLabel = await screen.findByText("Pendientes", { selector: "strong" });
    const pending = pendingLabel.closest(".taxonomy-item") as HTMLElement;
    expect(within(pending).queryByRole("button", { name: "Rename" })).not.toBeInTheDocument();
    expect(within(pending).queryByRole("button", { name: "Archive" })).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Category Group"), { target: { value: "Optional" } });
    fireEvent.click(screen.getByRole("button", { name: "Add Group" }));
    expect(await screen.findByText("Optional")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Category", { selector: "input" }), { target: { value: "Dining" } });
    fireEvent.click(screen.getByRole("button", { name: "Add Category" }));
    const dining = await screen.findByText("Dining");
    expect(dining).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Tag"), { target: { value: "Travel" } });
    fireEvent.click(screen.getByRole("button", { name: "Add Tag" }));
    expect(await screen.findByText("Travel")).toBeInTheDocument();

    const groceries = screen.getAllByText("Groceries", { selector: "strong" })[0]
      .closest(".taxonomy-item") as HTMLElement;
    fireEvent.click(within(groceries).getByRole("button", { name: "Archive" }));
    await waitFor(() => expect(within(groceries).getByText("archived")).toBeInTheDocument());
  });

  it("posts, corrects, assigns, and refetches authoritative ledger projections", async () => {
    const server = createLedgerServer();
    renderApp("/plans/plan-ledger/ledger");

    expect(await screen.findByRole("heading", { name: "Ledger" })).toBeInTheDocument();
    expect((await screen.findAllByRole("option", { name: /Main account/ })).length).toBeGreaterThan(0);
    fireEvent.change(screen.getByLabelText("Amount (exact decimal string)"), {
      target: { value: "12.00" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Post" }));
    expect(await screen.findByText((text) => text.includes("expense 12.00 BOB"))).toBeInTheDocument();
    expect(await screen.findByText((text) => text.includes("-12.00 BOB"))).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "View detail and correct" }));
    const correctionInput = await screen.findByLabelText("Replacement amount");
    fireEvent.change(correctionInput, { target: { value: "15.00" } });
    fireEvent.click(screen.getByRole("button", { name: "Save correction" }));
    expect(await screen.findByText((text) => text.includes("expense 15.00 BOB"))).toBeInTheDocument();
    expect(await screen.findByText((text) => text.includes("-15.00 BOB"))).toBeInTheDocument();
    expect(await screen.findByText("#1: 12.00 → 15.00")).toBeInTheDocument();

    const assignmentCategory = screen.getAllByLabelText("Category").at(-1);
    expect(assignmentCategory).toBeDefined();
    fireEvent.change(assignmentCategory as HTMLSelectElement, { target: { value: "category-groceries" } });
    fireEvent.change(screen.getByLabelText("Assignment (exact decimal string)"), {
      target: { value: "20.00" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Assign" }));
    expect(await screen.findByText(/Assigned 20\.00/)).toBeInTheDocument();
    expect(screen.getAllByText(/Unconverted USDT: -1\.000000/).length).toBeGreaterThan(0);
    expect(server.fetchMock.mock.calls.some(([path]) => String(path).includes("/budget/months/"))).toBe(true);
  });

  it("posts an exact cross-currency Transfer, renders grouped facts, and refetches after reversal", async () => {
    const server = createLedgerServer();
    renderApp("/plans/plan-ledger/ledger");

    await screen.findByLabelText("Sent (exact)");
    fireEvent.change(screen.getByLabelText("Sent (exact)"), { target: { value: "99999999999999999999.99" } });
    fireEvent.change(screen.getByLabelText("Received (exact)"), { target: { value: "10.000000" } });
    fireEvent.change(screen.getByLabelText("Rate source evidence"), { target: { value: "bank receipt" } });
    fireEvent.click(screen.getByRole("button", { name: "Create Transfer" }));

    expect(await screen.findByText(/Transfer 99999999999999999999\.99 BOB/)).toBeInTheDocument();
    expect(screen.getByText(/Event 2026-/)).toBeInTheDocument();
    expect(screen.getByText(/outbound leg leg-out, transaction transaction-out/)).toBeInTheDocument();
    const transferCard = screen.getByText(/Transfer 99999999999999999999\.99 BOB/).closest("article") as HTMLElement;
    expect(within(transferCard).queryByRole("button", { name: /correct|delete|unlink|edit/i })).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Reversal reason"), { target: { value: "duplicate" } });
    fireEvent.click(screen.getByRole("button", { name: "Reverse transfer" }));
    expect(await screen.findByText("Reversal reason: duplicate")).toBeInTheDocument();
    await waitFor(() => expect(server.fetchMock.mock.calls.filter(([path]) => String(path).includes("/transfers")).length).toBeGreaterThan(2));
  });
});
