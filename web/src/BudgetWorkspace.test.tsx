import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { BudgetWorkspace, moneyState } from "./BudgetWorkspace";
import type { Account, Category, MonthlySummary, Plan } from "./api";

afterEach(()=>{cleanup();vi.unstubAllGlobals();});
const plan:Plan={id:"plan-one",name:"My plan",reporting_currency_code:"BOB",budget_timezone:"America/La_Paz",created_at:"",updated_at:""};
const categories:Category[]=[
  {id:"food",plan_id:plan.id,name:"Food",group_id:"needs",is_pending:false,status:"active",goal_type:"monthly_funding",goal_target:"100.00",goal_due_month:null,created_at:"",updated_at:""},
  {id:"travel",plan_id:plan.id,name:"Travel",group_id:"needs",is_pending:false,status:"active",created_at:"",updated_at:""},
];
const accounts:Account[]=[{id:"bank",plan_id:plan.id,name:"Main bank",account_type:"Bank",currency_code:"BOB",status:"active",balance:{amount:"500.00",currency:"BOB"},created_at:"",updated_at:""}];
function setup({failure=false, overspent=false}={}) {
  const summary:MonthlySummary={plan_id:plan.id,month:"2026-10",currency:"BOB",ready_to_assign:"200.00",assigned_total:"300.00",activity_total:"-20.00",available_total:"280.00",assigned_in_future:"50.00",unconverted_by_currency:[],categories:[
    {plan_id:plan.id,month:"2026-10",category_id:"food",currency:"BOB",assigned:"30.00",activity:"-20.00",available:overspent?"-10.00":"10.00",rollover:"0.00",cash_overspending:overspent?"10.00":"0.00",credit_card_overspending:"0.00",goal:{type:"monthly_funding",target:"100.00",required_contribution:"70.00",progress:30,status:"underfunded"},unconverted_by_currency:[]},
    {plan_id:plan.id,month:"2026-10",category_id:"travel",currency:"BOB",assigned:"270.00",activity:"0.00",available:"270.00",unconverted_by_currency:[]},
  ]};
  const requests:{path:string;body:Record<string,unknown>}[]=[];
  const fetchMock=vi.fn(async(input:RequestInfo|URL,init?:RequestInit)=>{
    const path=String(input);const body=init?.body?JSON.parse(String(init.body)):{};
    if (init?.method) {
      requests.push({path,body});
      if(failure) return new Response(JSON.stringify({detail:"Not enough money available in the source"}),{status:422});
      return new Response(JSON.stringify({}),{status:200});
    }
    return new Response(JSON.stringify(summary),{status:200});
  });
  vi.stubGlobal("fetch",fetchMock);
  const cache=new QueryClient({defaultOptions:{queries:{retry:false},mutations:{retry:false}}});
  render(<MemoryRouter><QueryClientProvider client={cache}><BudgetWorkspace plan={plan} categories={categories} accounts={accounts} groups={[{id:"needs",plan_id:plan.id,name:"Needs",status:"active",created_at:"",updated_at:""}]} /></QueryClientProvider></MemoryRouter>);
  return {requests,fetchMock};
}

describe("budget workspace",()=>{
  it("shows grouped authoritative figures and account navigation",async()=>{
    setup();expect(await screen.findByRole("button",{name:"View Food details"})).toBeInTheDocument();
    expect(screen.getByRole("button",{name:"Needs"})).toHaveAttribute("aria-expanded","true");
    expect(screen.getByRole("link",{name:/Main bank/})).toHaveAttribute("href","/plans/plan-one/ledger?account=bank");
    expect(within(screen.getByLabelText("Ready to Assign")).getByText(/200,00/)).toBeInTheDocument();
    expect(screen.getAllByText("Underfunded").length).toBeGreaterThan(0);
    expect(document.querySelector(".budget-progress > span")).toHaveStyle({width:"30%"});
  });
  it("filters underfunded categories and exposes signed overspending",async()=>{
    setup({overspent:true});await screen.findByRole("button",{name:"View Food details"});
    fireEvent.click(screen.getByRole("button",{name:"Overspent"}));
    expect(screen.queryByRole("button",{name:"View Travel details"})).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button",{name:"View Food details"}));
    expect(screen.getByText(/Cash overspending: Bs 10,00/)).toBeInTheDocument();
  });
  it("sets an exact assigned total through the server action",async()=>{
    const {requests}=setup();fireEvent.click(await screen.findByRole("button",{name:"View Food details"}));
    fireEvent.change(screen.getByLabelText("Assigned this month"),{target:{value:"9007199254740993.01"}});
    fireEvent.click(screen.getByRole("button",{name:"Save assigned amount"}));
    await screen.findByText("Budget updated.");
    expect(requests[0].body).toMatchObject({kind:"set_assigned",category_id:"food",amount:"9007199254740993.01"});
  });
  it("moves money using explicit source/destination without account transactions",async()=>{
    const {requests}=setup();fireEvent.click(await screen.findByRole("button",{name:"View Food details"}));
    fireEvent.change(screen.getByLabelText("From"),{target:{value:"travel"}});
    fireEvent.change(screen.getByLabelText("Amount to move"),{target:{value:"25.00"}});
    fireEvent.click(screen.getByRole("button",{name:"Move money"}));await screen.findByText("Budget updated.");
    expect(requests[0].body).toMatchObject({kind:"move",source_category_id:"travel",category_id:"food",amount:"25.00"});
    expect(requests[0].path).toContain("/budget-actions/");
  });
  it("keeps the idempotency identity for a failed action retry",async()=>{
    const {requests}=setup({failure:true});fireEvent.click(await screen.findByRole("button",{name:"View Food details"}));
    fireEvent.click(screen.getByRole("button",{name:"Save assigned amount"}));await screen.findByRole("alert");
    fireEvent.click(screen.getByRole("button",{name:"Save assigned amount"}));
    await vi.waitFor(()=>expect(requests).toHaveLength(2));expect(requests[0].path).toBe(requests[1].path);
  });
  it("saves and funds an existing target with separate explicit actions",async()=>{
    const {requests}=setup();fireEvent.click(await screen.findByRole("button",{name:"View Food details"}));
    fireEvent.change(screen.getByLabelText("Target amount"),{target:{value:"150.00"}});
    fireEvent.click(screen.getByRole("button",{name:"Save target"}));await screen.findByText("Target saved.");
    expect(requests[0].body).toEqual({goal_type:"monthly_funding",goal_target:"150.00",goal_due_month:null});
    fireEvent.click(screen.getByRole("button",{name:"Fund target"}));await screen.findByText("Budget updated.");
    expect(requests[1].body).toMatchObject({kind:"fund_target",category_id:"food"});
  });
  it("changes months and refetches the selected Plan",async()=>{
    const {fetchMock}=setup();await screen.findByRole("button",{name:"View Food details"});
    const before=(screen.getByLabelText("Choose month") as HTMLInputElement).value;
    fireEvent.click(screen.getByRole("button",{name:"Next month"}));
    await vi.waitFor(()=>expect((screen.getByLabelText("Choose month") as HTMLInputElement).value).not.toBe(before));
    expect(fetchMock.mock.calls.at(-1)?.[0]).toContain("/plans/plan-one/budget/months/");
  });
});

it("classifies exact decimal strings without converting to Number",()=>{
  expect(moneyState("-0.00")).toBe("zero");expect(moneyState("-0.01")).toBe("negative");
  expect(moneyState("9007199254740993.000000000000000001")).toBe("positive");
});
