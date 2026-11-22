import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { MemoryRouter } from "react-router";
import { PlanNavigation } from "./PlanNavigation";

afterEach(cleanup);

it.each(["accounts", "ledger", "gmail"])("marks the current %s destination and stays within its Plan", path => {
  render(<MemoryRouter initialEntries={[`/plans/plan-one/${path}`]}>
    <PlanNavigation planId="plan-one" />
  </MemoryRouter>);
  const links = screen.getAllByRole("link");
  expect(screen.getByRole("navigation", { name: "Plan navigation" })).toBeInTheDocument();
  expect(links.filter(link => link.getAttribute("aria-current") === "page")).toHaveLength(1);
  for (const link of links) {
    expect(link.getAttribute("href")).toMatch(/^\/plans\/plan-one\//);
    if (link.getAttribute("href")?.endsWith(path)) expect(link).toHaveAttribute("aria-current", "page");
  }
});
