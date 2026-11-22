import { ReactNode } from "react";
import {
  act,
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

function createLedgerServer(options: { deferReconciliationPreviews?: boolean } = {}) {
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
  const reconciliations: Array<Record<string, unknown>> = [];
  const pendingReconciliationPreviews: Array<{
    accountId: string;
    release: () => void;
  }> = [];
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
    if (path === `/plans/${planId}/gmail`) return jsonResponse({configured:false,configured_senders:[],sources:[]});
    if (path.includes("binance-card-reviews")) return jsonResponse({candidate_count:0,needs_review_count:0,items:[],next_after:null});


    const reconciliationHistory = path.match(new RegExp(`^/plans/${planId}/accounts/([^/]+)/reconciliations$`));
    if (reconciliationHistory && method === "GET") {
      return jsonResponse(reconciliations.filter((item) => item.account_id === reconciliationHistory[1]));
    }
    const reconciliationPreview = path.match(new RegExp(`^/plans/${planId}/accounts/([^/]+)/reconciliations/([^/]+)/preview$`));
    if (reconciliationPreview && method === "POST") {
      const reconciliationAccount = accounts.find((item) => item.id === reconciliationPreview[1]);
      if (!reconciliationAccount) return jsonResponse({}, 404);
      const statement = String(body.statement_balance);
      const discrepancy = statement === reconciliationAccount.balance.amount ? "0.00" : statement;
      const response = jsonResponse({
        id: reconciliationPreview[2], plan_id: planId, account_id: reconciliationAccount.id,
        statement_balance: { amount: statement, currency: reconciliationAccount.currency_code },
        statement_at: body.statement_at,
        derived_balance: reconciliationAccount.balance,
        discrepancy: { amount: discrepancy, currency: reconciliationAccount.currency_code },
        policy: "warn", tolerance: { amount: "0.00", currency: reconciliationAccount.currency_code },
        requires_warning_acceptance: discrepancy !== "0.00", blocked: false,
      });
      if (options.deferReconciliationPreviews) {
        return new Promise<Response>((resolve) => {
          pendingReconciliationPreviews.push({
            accountId: reconciliationAccount.id,
            release: () => resolve(response),
          });
        });
      }
      return response;
    }
    const reconciliationConfirm = path.match(new RegExp(`^/plans/${planId}/accounts/([^/]+)/reconciliations/([^/]+)$`));
    if (reconciliationConfirm && method === "PUT") {
      const reconciliationAccount = accounts.find((item) => item.id === reconciliationConfirm[1]);
      if (!reconciliationAccount) return jsonResponse({}, 404);
      const statement = String(body.statement_balance);
      const discrepancy = statement === reconciliationAccount.balance.amount ? "0.00" : statement;
      if (discrepancy !== "0.00" && body.warning_accepted !== true) return jsonResponse({ detail: "warning acceptance is required" }, 409);
      const item = {
        id: reconciliationConfirm[2], plan_id: planId, account_id: reconciliationAccount.id,
        statement_balance: { amount: statement, currency: reconciliationAccount.currency_code },
        statement_at: body.statement_at, derived_balance: { ...reconciliationAccount.balance },
        discrepancy: { amount: discrepancy, currency: reconciliationAccount.currency_code },
        policy: "warn", tolerance: { amount: "0.00", currency: reconciliationAccount.currency_code },
        requires_warning_acceptance: discrepancy !== "0.00", blocked: false,
        warning_accepted: body.warning_accepted, confirmed_at: timestamp,
        adjustment_transaction_id: discrepancy === "0.00" ? null : `adjustment-${reconciliationConfirm[2]}`,
        adjustment_movement_id: discrepancy === "0.00" ? null : `movement-${reconciliationConfirm[2]}`,
      };
      if (discrepancy !== "0.00") reconciliationAccount.balance = { amount: statement, currency: reconciliationAccount.currency_code };
      reconciliations.unshift(item);
      return jsonResponse(item, 201);
    }

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
    if (path.includes("/budget-actions/") && method === "PUT") {
      assignments.push({category_id:body.category_id,amount:body.amount});
      return jsonResponse({},201);
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
  return { planId, accountId, fetchMock, pendingReconciliationPreviews };
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
  it("renders the shared Numa brand and home navigation", async () => {
    const server = createServer();
    vi.stubGlobal("fetch", server.fetchMock);
    renderApp("/plans");
    expect(screen.getByRole("link", { name: "Numa home" })).toHaveAttribute("href", "/plans");
    expect(screen.getByText("Personal finance")).toBeInTheDocument();
    expect(await screen.findByText("No Plans yet.")).toBeInTheDocument();
  });

  it("opens activity directly and keeps disclosed evidence in the exact transaction request", async () => {
    const server = createLedgerServer();
    renderApp("/plans/plan-ledger/ledger");
    await screen.findAllByRole("option", { name: /Main account/ });
    expect(screen.queryByRole("region", { name: "Budget month" })).not.toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Transactions" })).toBeInTheDocument();
    expect(within(screen.getByRole("navigation", {name:"Workspace navigation"})).getByRole("link", {name:"All activity"})).toHaveAttribute("aria-current","page");
    expect(screen.getByRole("link", { name: "Activity" })).toHaveAttribute("href", "#transactions-heading");
    fireEvent.click(screen.getByRole("button", {name:"+ Add transaction"}));
    fireEvent.change(screen.getByLabelText("Transaction account"), {target:{value:"account-ledger"}});
    const evidence = screen.getByText("Additional evidence").closest("details");
    expect(evidence).not.toHaveAttribute("open");
    fireEvent.click(screen.getByText("Additional evidence"));
    expect(evidence).toHaveAttribute("open");
    fireEvent.change(screen.getByLabelText("Outflow"), { target: { value: "12.00" } });
    fireEvent.change(screen.getByLabelText("Photo reference (opaque)"), { target: { value: "receipt-reference" } });
    fireEvent.change(screen.getByLabelText("Location JSON"), { target: { value: '{"city":"La Paz"}' } });
    fireEvent.change(screen.getByLabelText("Source metadata JSON"), { target: { value: '{"provider":"manual"}' } });
    fireEvent.change(screen.getByLabelText("Provenance JSON"), { target: { value: '{"note":"user entered"}' } });
    // Disclosure never unmounts or resets the user's draft.
    fireEvent.click(screen.getByText("Additional evidence"));
    fireEvent.click(screen.getByText("Additional evidence"));
    expect(screen.getByLabelText("Photo reference (opaque)")).toHaveValue("receipt-reference");
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Transaction added. Balances and budget have been refreshed.")).toBeInTheDocument();
    const request = server.fetchMock.mock.calls.find(([path, init]) => String(path).includes("/transactions/") && init?.method === "PUT");
    expect(JSON.parse(String(request?.[1]?.body))).toMatchObject({
      amount: "12.00", currency_code: "BOB", photo_reference: "receipt-reference",
      location: { city: "La Paz" }, source_metadata: { provider: "manual" }, provenance: { note: "user entered" },
    });
  });

  it("keeps invalid advanced JSON from submitting financial activity", async () => {
    const server = createLedgerServer();
    renderApp("/plans/plan-ledger/ledger");
    await screen.findAllByRole("option", { name: /Main account/ });
    fireEvent.click(screen.getByRole("button", {name:"+ Add transaction"}));
    fireEvent.change(screen.getByLabelText("Transaction account"), {target:{value:"account-ledger"}});
    fireEvent.click(screen.getByText("Additional evidence"));
    fireEvent.change(screen.getByLabelText("Outflow"), { target: { value: "12.00" } });
    fireEvent.change(screen.getByLabelText("Provenance JSON"), { target: { value: "not json" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Provenance must be valid JSON.");
    expect(server.fetchMock.mock.calls.some(([, init]) => init?.method === "PUT")).toBe(false);
  });

  it("inherits the register account, saves the local date and suggests the last category for a payee", async () => {
    const server = createLedgerServer();
    const local = new Date(2026, 10, 22, 23, 55);
    vi.useFakeTimers({toFake: ["Date"]});
    vi.setSystemTime(local);
    try {
      renderApp("/plans/plan-ledger/ledger?account=account-usdt");
      await screen.findAllByRole("option", {name: /USDT wallet/});
      fireEvent.click(screen.getByRole("button", {name: "+ Add transaction"}));
      const entry = within(await screen.findByRole("form", {name:"Transaction entry"}));
      expect(entry.getByLabelText("Transaction account")).toHaveValue("account-usdt");
      expect(entry.getByLabelText("Date and time")).toHaveValue("2026-11-22T23:55");
      fireEvent.change(entry.getByLabelText("Payee"), {target:{value:"Cafe"}});
      fireEvent.click(entry.getByRole("button", {name:"Category: Pendientes"}));
      fireEvent.change(entry.getByLabelText("Search categories"), {target:{value:"ocer"}});
      fireEvent.click(entry.getByRole("button", {name:"Groceries"}));
      fireEvent.change(entry.getByLabelText("Outflow"), {target:{value:"12,34"}});
      fireEvent.click(entry.getByRole("button", {name:"Save and add another"}));
      await entry.findByText("Transaction saved.");
      const writes = () => server.fetchMock.mock.calls.filter(([path,init]) => String(path).includes("/transactions/") && init?.method==="PUT");
      expect(JSON.parse(String(writes()[0][1]?.body))).toMatchObject({amount:"12.34",account_id:"account-usdt",category_id:"category-groceries",event_at:local.toISOString()});
      expect(entry.getByLabelText("Outflow")).toHaveValue("");
      expect(entry.getByLabelText("Transaction account")).toHaveValue("account-usdt");
      fireEvent.change(entry.getByLabelText("Payee"), {target:{value:" CAFE "}});
      expect(entry.getByRole("button", {name:"Category: Groceries"})).toBeInTheDocument();
      fireEvent.click(entry.getByRole("button", {name:"Category: Groceries"}));
      fireEvent.click(entry.getByRole("button", {name:"Pendientes"}));
      fireEvent.change(entry.getByLabelText("Payee"), {target:{value:"Cafe"}});
      expect(entry.getByRole("button", {name:"Category: Pendientes"})).toBeInTheDocument();
      fireEvent.click(entry.getByRole("button", {name:"Cancel"}));
      expect(writes()).toHaveLength(1);
    } finally {
      vi.useRealTimers();
    }
  });

  it("offers recent alternatives for the same payee and keeps an explicit category", async () => {
    const server = createLedgerServer();
    const path = "/plans/plan-ledger";
    const put = (resource: string, data: object) =>
      server.fetchMock(path + resource, {method: "PUT", body: JSON.stringify(data)});
    await put("/categories/transport", {name: "Transport"});
    // The real ledger returns effective transactions newest first.
    for (const [day, category] of [["03", "category-groceries"], ["02", "transport"], ["01", "transport"]]) {
      await put("/transactions/demo-" + day, {
        type: "expense", amount: "10.00", currency_code: "BOB", account_id: "account-ledger",
        event_at: "2026-11-" + day + "T12:00:00Z", category_id: category, merchant: "Local shop",
      });
    }
    renderApp(path + "/ledger?account=account-ledger");
    await screen.findAllByRole("option", {name: /Main account/});
    fireEvent.click(screen.getByRole("button", {name: "+ Add transaction"}));
    const entry = within(await screen.findByRole("form", {name: "Transaction entry"}));
    fireEvent.change(entry.getByLabelText("Payee"), {target: {value: "local shop"}});
    fireEvent.click(await entry.findByRole("button", {name: "Category: Groceries"}));
    const recents = within(entry.getByRole("group", {name: "Recent categories for this payee"}));
    expect(recents.getAllByRole("button")).toHaveLength(1);
    fireEvent.click(recents.getByRole("button", {name: "Transport"}));
    fireEvent.change(entry.getByLabelText("Outflow"), {target: {value: "8.00"}});
    fireEvent.click(entry.getByRole("button", {name: "Save"}));
    await screen.findByText("Transaction added. Balances and budget have been refreshed.");
    const writes = server.fetchMock.mock.calls.filter(([url, init]) => String(url).includes("/transactions/") && init?.method === "PUT");
    expect(JSON.parse(String(writes[writes.length - 1]?.[1]?.body)).category_id).toBe("transport");
  });

  it("requires an account in All activity and reuses the transaction ID after a lost response", async () => {
    const server = createLedgerServer();
    const ids: string[] = [];
    vi.stubGlobal("fetch", async (path: RequestInfo | URL, init?: RequestInit) => {
      const result = await server.fetchMock(path, init);
      if (init?.method === "PUT" && String(path).includes("/transactions/")) {
        ids.push(String(path));
        if (ids.length === 1) throw new TypeError("Response lost");
      }
      return result;
    });
    renderApp("/plans/plan-ledger/ledger");
    await screen.findAllByRole("option", {name:/Main account/});
    fireEvent.click(screen.getByRole("button", {name:"+ Add transaction"}));
    const entry = within(await screen.findByRole("form", {name:"Transaction entry"}));
    expect(entry.getByRole("button", {name:"Save"})).toBeDisabled();
    fireEvent.change(entry.getByLabelText("Transaction account"), {target:{value:"account-ledger"}});
    fireEvent.change(entry.getByLabelText("Outflow"), {target:{value:"15.00"}});
    fireEvent.click(entry.getByRole("button", {name:"Save"}));
    expect(await entry.findByRole("alert")).toHaveTextContent("Response lost");
    fireEvent.click(entry.getByRole("button", {name:"Save"}));
    await screen.findByText("Transaction added. Balances and budget have been refreshed.");
    expect(ids).toHaveLength(2);
    expect(ids[0]).toBe(ids[1]);
  });

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

    expect(await screen.findByRole("heading", { name: "Accounts", level: 1 })).toBeInTheDocument();
    const accountList=within(screen.getByRole("region",{name:"Accounts"}));
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "USDT wallet" } });
    fireEvent.change(screen.getByLabelText("Type"), { target: { value: "Crypto" } });
    fireEvent.change(screen.getByLabelText("Currency"), { target: { value: "USDT" } });
    fireEvent.click(screen.getByRole("button", { name: "Create Account" }));

    expect(await accountList.findByText("USDT wallet")).toBeInTheDocument();
    expect(accountList.getByText("0,000000 USDT")).toBeInTheDocument();
    const accountCard = () => accountList.getByText(/USDT wallet|Renamed wallet/).closest("article") as HTMLElement;

    fireEvent.click(within(accountCard()).getByRole("button", { name: "Rename" }));
    fireEvent.change(screen.getByLabelText("New name"), { target: { value: "Renamed wallet" } });
    fireEvent.click(within(accountCard()).getByRole("button", { name: "Save" }));
    expect(await accountList.findByText("Renamed wallet")).toBeInTheDocument();

    fireEvent.click(within(accountCard()).getByRole("button", { name: "Archive" }));
    const archivedCard = await accountList.findByText("Renamed wallet");
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

    expect(await screen.findByRole("heading", { name: "All activity" })).toBeInTheDocument();
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

    const groceries = within(screen.getByRole("region", { name: "Categories and Tags" })).getByText("Groceries", { selector: "strong" })
      .closest(".taxonomy-item") as HTMLElement;
    fireEvent.click(within(groceries).getByRole("button", { name: "Archive" }));
    await waitFor(() => expect(within(groceries).getByText("archived")).toBeInTheDocument());
  });

  it("posts, corrects, assigns, and refetches authoritative ledger projections", async () => {
    const server = createLedgerServer();
    renderApp("/plans/plan-ledger/ledger");

    expect(await screen.findByRole("heading", { name: "All activity" })).toBeInTheDocument();
    expect((await screen.findAllByRole("option", { name: /Main account/ })).length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("button", {name:"+ Add transaction"}));
    fireEvent.change(screen.getByLabelText("Transaction account"), {target:{value:"account-ledger"}});
    fireEvent.change(screen.getByLabelText("Outflow"), {
      target: { value: "12.00" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    const register = () => screen.getByRole("region", { name: "Transaction register" });
    expect(await within(register()).findByText("Bs 12,00")).toBeInTheDocument();
    expect(within(screen.getByRole("complementary",{name:"Budget accounts"})).getByRole("link",{name:/Main account/})).toHaveTextContent("-Bs 12,00");

    fireEvent.click(within(register()).getByRole("button", { name: /^Edit / }));
    const correctionInput = await screen.findByLabelText("Replacement amount");
    fireEvent.change(correctionInput, { target: { value: "15.00" } });
    fireEvent.click(screen.getByRole("button", { name: "Save correction" }));
    expect(await within(register()).findByText("Bs 15,00")).toBeInTheDocument();
    expect(within(screen.getByRole("complementary",{name:"Budget accounts"})).getByRole("link",{name:/Main account/})).toHaveTextContent("-Bs 15,00");
    expect(await screen.findByText("#1: 12.00 → 15.00")).toBeInTheDocument();

    fireEvent.click(within(screen.getByRole("navigation",{name:"Workspace navigation"})).getByRole("link",{name:"Budget"}));
    fireEvent.click(await screen.findByRole("button",{name:"View Groceries details"}));
    fireEvent.change(screen.getByLabelText("Assigned this month"), {target:{value:"20.00"}});
    fireEvent.click(screen.getByRole("button",{name:"Save assigned amount"}));
    await screen.findByText("Budget updated.");
    expect(screen.getByRole("button",{name:"Assign money to Groceries"})).toHaveTextContent("20,00");
    expect(screen.getAllByText(/Unconverted USDT: -1,000000/).length).toBeGreaterThan(0);
    expect(server.fetchMock.mock.calls.some(([path]) => String(path).includes("/budget/months/"))).toBe(true);
  });

  it("filters the register and submits a full correction payload", async () => {
    const server = createLedgerServer();
    renderApp("/plans/plan-ledger/ledger");

    await screen.findByRole("heading", { name: "All activity" });
    await screen.findAllByRole("option", { name: /Main account/ });
    const register = () => screen.getByRole("region", { name: "Transaction register" });

    fireEvent.click(screen.getByRole("button", {name:"+ Add transaction"}));
    fireEvent.change(screen.getByLabelText("Transaction account"), {target:{value:"account-ledger"}});
    fireEvent.change(screen.getByLabelText("Outflow"), { target: { value: "12.00" } });
    fireEvent.change(screen.getByLabelText("Payee"), { target: { value: "Cafe" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await screen.findByText("Transaction added. Balances and budget have been refreshed.");

    fireEvent.click(screen.getByRole("button", {name:"+ Add transaction"}));
    fireEvent.change(screen.getByLabelText("Transaction account"), {target:{value:"account-ledger"}});
    fireEvent.change(screen.getByLabelText("Outflow"), { target: { value: "20.00" } });
    fireEvent.change(screen.getByLabelText("Payee"), { target: { value: "Rent" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(within(register()).getAllByRole("button", { name: /^Edit / })).toHaveLength(2));

    fireEvent.change(screen.getByLabelText("Search"), { target: { value: "Cafe" } });
    expect(within(register()).getByText("Cafe")).toBeInTheDocument();
    expect(within(register()).queryByText("Rent")).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Search"), { target: { value: "" } });
    fireEvent.change(within(register()).getByLabelText("Account"), { target: { value: "account-usdt" } });
    expect(await screen.findByText("No transactions match this view.")).toBeInTheDocument();

    fireEvent.change(within(register()).getByLabelText("Account"), { target: { value: "" } });
    fireEvent.click(within(register()).getAllByRole("button", { name: /^Edit / })[0]);
    fireEvent.change(screen.getByLabelText("Replacement amount"), { target: { value: "15.00" } });
    fireEvent.change(screen.getByLabelText("Correction merchant"), { target: { value: "Cafe Updated" } });
    fireEvent.change(screen.getByLabelText("Correction memo"), { target: { value: "Latte" } });
    fireEvent.change(screen.getByLabelText("Correction category"), { target: { value: "category-groceries" } });
    fireEvent.click(screen.getByRole("button", { name: "Save correction" }));
    expect(await screen.findByText("Correction saved. The original entry remains in the audit history.")).toBeInTheDocument();

    const correctionCall = server.fetchMock.mock.calls.find(([path, init]) =>
      String(path).includes("/corrections/") && init?.method === "PUT");
    expect(JSON.parse(String(correctionCall?.[1]?.body))).toMatchObject({
      amount: "15.00",
      merchant: "Cafe Updated",
      memo: "Latte",
      category_id: "category-groceries",
    });
  });

  it("posts an exact cross-currency Transfer, renders grouped facts, and refetches after reversal", async () => {
    const server = createLedgerServer();
    renderApp("/plans/plan-ledger/ledger");

    await screen.findByLabelText("Sent (exact)");
    fireEvent.change(screen.getByLabelText("Sent (exact)"), { target: { value: "99999999999999999999.99" } });
    fireEvent.change(screen.getByLabelText("Received (exact)"), { target: { value: "10.000000" } });
    fireEvent.change(screen.getByLabelText("Rate source evidence"), { target: { value: "bank receipt" } });
    fireEvent.click(screen.getByRole("button", { name: "Create Transfer" }));

    expect(await screen.findByText(/Transfer Bs 99(?:\.999){6},99/)).toBeInTheDocument();
    expect(screen.getByText(/Event 2026-/)).toBeInTheDocument();
    expect(screen.getByText(/outbound leg leg-out, transaction transaction-out/)).toBeInTheDocument();
    const transferCard = screen.getByText(/Transfer Bs 99(?:\.999){6},99/).closest("article") as HTMLElement;
    expect(within(transferCard).queryByRole("button", { name: /correct|delete|unlink|edit/i })).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Reversal reason"), { target: { value: "duplicate" } });
    fireEvent.click(screen.getByRole("button", { name: "Reverse transfer" }));
    expect(await screen.findByText("Reversal reason: duplicate")).toBeInTheDocument();
    await waitFor(() => expect(server.fetchMock.mock.calls.filter(([path]) => String(path).includes("/transfers")).length).toBeGreaterThan(2));
  });

  it("previews, explicitly accepts a warning, confirms, and refetches immutable reconciliation history", async () => {
    const server = createLedgerServer();
    renderApp("/plans/plan-ledger/ledger");

    const balance = await screen.findByLabelText("Statement balance (exact)");
    await waitFor(() => expect(screen.getByLabelText("Reconciliation Account")).toHaveValue("account-ledger"));
    fireEvent.change(balance, { target: { value: "5.00" } });
    fireEvent.click(screen.getByRole("button", { name: "Preview reconciliation" }));
    expect(await screen.findByText("Discrepancy Bs 5,00")).toBeInTheDocument();
    const confirm = screen.getByRole("button", { name: "Confirm reconciliation" });
    expect(confirm).toBeDisabled();
    fireEvent.click(screen.getByLabelText("I explicitly accept this discrepancy warning."));
    fireEvent.click(confirm);

    expect(await screen.findByText(/Adjustment adjustment-/)).toBeInTheDocument();
    await waitFor(() => expect(server.fetchMock.mock.calls.filter(([path]) => String(path).includes("/accounts")).length).toBeGreaterThan(2));

    fireEvent.click(screen.getByRole("button", { name: "Preview reconciliation" }));
    expect(await screen.findByText("Discrepancy Bs 0,00")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Confirm reconciliation" }));
    expect(await screen.findByText("Confirmed without adjustment")).toBeInTheDocument();
  });

  it("ignores an obsolete Account A preview that resolves after Account B", async () => {
    const server = createLedgerServer({ deferReconciliationPreviews: true });
    renderApp("/plans/plan-ledger/ledger");

    const balance = await screen.findByLabelText("Statement balance (exact)");
    await waitFor(() => expect(screen.getByLabelText("Reconciliation Account")).toHaveValue("account-ledger"));
    fireEvent.change(balance, { target: { value: "5.00" } });
    fireEvent.click(screen.getByRole("button", { name: "Preview reconciliation" }));
    await waitFor(() => expect(server.pendingReconciliationPreviews).toHaveLength(1));

    fireEvent.change(screen.getByLabelText("Reconciliation Account"), { target: { value: "account-usdt" } });
    fireEvent.change(balance, { target: { value: "7.000000" } });
    fireEvent.click(screen.getByRole("button", { name: "Preview reconciliation" }));
    await waitFor(() => expect(server.pendingReconciliationPreviews).toHaveLength(2));

    expect(server.pendingReconciliationPreviews.map((item) => item.accountId)).toEqual([
      "account-ledger",
      "account-usdt",
    ]);
    await act(async () => { server.pendingReconciliationPreviews[1].release(); });
    expect(await screen.findByText("Discrepancy 7,000000 USDT")).toBeInTheDocument();

    await act(async () => {
      server.pendingReconciliationPreviews[0].release();
      await Promise.resolve();
    });
    expect(screen.getByText("Discrepancy 7,000000 USDT")).toBeInTheDocument();
    expect(screen.queryByText("Discrepancy Bs 5,00")).not.toBeInTheDocument();
  });

  it("confirms exactly the immutable request snapshot represented by the preview", async () => {
    const server = createLedgerServer();
    renderApp("/plans/plan-ledger/ledger");

    const balance = await screen.findByLabelText("Statement balance (exact)");
    await waitFor(() => expect(screen.getByLabelText("Reconciliation Account")).toHaveValue("account-ledger"));
    fireEvent.change(balance, { target: { value: "5.00" } });
    fireEvent.change(screen.getByLabelText("Statement timestamp (UTC)"), {
      target: { value: "2026-01-15T12:00" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Preview reconciliation" }));

    expect(await screen.findByText("Discrepancy Bs 5,00")).toBeInTheDocument();
    expect(screen.getByText("Policy warn · tolerance Bs 0,00")).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText("I explicitly accept this discrepancy warning."));
    fireEvent.click(screen.getByRole("button", { name: "Confirm reconciliation" }));
    await screen.findByText(/Adjustment adjustment-/);

    const previewCall = server.fetchMock.mock.calls.find(([path, init]) =>
      String(path).endsWith("/preview") && init?.method === "POST");
    const confirmCall = server.fetchMock.mock.calls.find(([path, init]) =>
      String(path).includes("/reconciliations/") && !String(path).endsWith("/preview") && init?.method === "PUT");
    expect(previewCall).toBeDefined();
    expect(confirmCall).toBeDefined();
    expect(String(confirmCall?.[0])).toBe(String(previewCall?.[0]).replace(/\/preview$/, ""));
    expect(JSON.parse(String(confirmCall?.[1]?.body))).toEqual({
      statement_balance: "5.00",
      currency_code: "BOB",
      statement_at: "2026-01-15T12:00:00.000Z",
      warning_accepted: true,
    });
  });
});


it("keeps one persistent workspace sidebar across Budget, activity, Accounts and Gmail",async()=>{
  createLedgerServer();
  renderApp("/plans/plan-ledger/budget");
  await screen.findByRole("button",{name:"View Groceries details"});
  const sidebar=screen.getByRole("complementary",{name:"Budget accounts"});
  for (const [destination,heading] of [["All activity","All activity"],["Accounts","Accounts"],["Gmail","Gmail"]]) {
    fireEvent.click(within(screen.getByRole("navigation",{name:"Workspace navigation"})).getByRole("link",{name:destination}));
    await screen.findByRole("heading",{name:heading,level:1});
    expect(screen.getByRole("complementary",{name:"Budget accounts"})).toBe(sidebar);
    expect(screen.getAllByRole("navigation",{name:"Workspace navigation"})).toHaveLength(1);
    expect(screen.queryByRole("navigation",{name:"Plan navigation"})).not.toBeInTheDocument();
    expect(within(sidebar).getByRole("link",{name:destination})).toHaveAttribute("aria-current","page");
  }
  fireEvent.click(within(sidebar).getByRole("link",{name:"Budget"}));
  await screen.findByRole("button",{name:"View Groceries details"});
  expect(screen.getByRole("complementary",{name:"Budget accounts"})).toBe(sidebar);
});

it("keeps workspace navigation available when Budget content fails",async()=>{
  const server=createLedgerServer();
  vi.stubGlobal("fetch",(input:RequestInfo|URL,init?:RequestInit)=>String(input).endsWith("/categories")
    ? Promise.resolve(jsonResponse({detail:"Unavailable"},503)) : server.fetchMock(input,init));
  renderApp("/plans/plan-ledger/budget");
  await screen.findByText("The budget workspace could not be loaded.");
  const sidebar=screen.getByRole("complementary",{name:"Budget accounts"});
  fireEvent.click(within(screen.getByRole("navigation",{name:"Workspace navigation"})).getByRole("link",{name:"Gmail"}));
  await screen.findByRole("heading",{name:"Gmail",level:1});
  expect(screen.getByRole("complementary",{name:"Budget accounts"})).toBe(sidebar);
});
