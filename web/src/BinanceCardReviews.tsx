import { useInfiniteQuery } from "@tanstack/react-query";
import { request } from "./api";

type Review = {
  id: number;
  disposition: "candidate" | "needs_review";
  reason: string;
  reported_amount: string | null;
  reported_currency: string | null;
  merchant: string | null;
  event_at: string | null;
  notification_at: string | null;
  settlement_amount: null;
  settlement_currency: null;
  account_id: null;
  provenance: {
    source_id: string;
    source_email: string | null;
    gmail_message_id: string;
    header_message_id: string | null;
    parser_version: string;
    ingested_at: string;
    processed_at: string;
    sender_authentication: string;
  };
};

type ReviewPage = {
  candidate_count: number;
  needs_review_count: number;
  items: Review[];
  next_after: number | null;
};

const reasonLabels: Record<string, string> = {
  unsupported_subject: "Notice type is not supported yet.",
  unsupported_currency: "Reported currency is outside the validated USD template.",
  unsupported_body: "The payment sentence could not be read unambiguously.",
  ambiguous_sender: "Sender headers are ambiguous.",
  ambiguous_subject: "Subject headers are ambiguous.",
  ambiguous_metadata: "Notification metadata is missing or ambiguous.",
  invalid_timestamp: "Event or notification time could not be verified.",
  invalid_amount: "The reported amount needs inspection.",
  invalid_merchant: "Merchant details need inspection.",
  ambiguous_html: "Email contains missing or ambiguous HTML evidence.",
  unsupported_mime: "Email encoding is outside the validated template.",
  mime_decode_issues: "Email could not be decoded reliably.",
  unreadable_evidence: "Stored evidence could not be read reliably.",
};

function utcTime(value: string) {
  return new Date(value).toISOString().replace("T", " ").replace(/\.\d{3}Z$/, " UTC");
}

export function BinanceCardReviews({ planId }: { planId: string }) {
  const reviews = useInfiniteQuery({
    queryKey: ["plans", planId, "binance-card-reviews"],
    initialPageParam: 0,
    queryFn: ({ pageParam }) => request<ReviewPage>(
      `/plans/${planId}/gmail/binance-card-reviews?after=${pageParam}&limit=25`,
    ),
    getNextPageParam: page => page.next_after ?? undefined,
    refetchInterval: 10_000,
  });
  const items = reviews.data?.pages.flatMap(page => page.items) ?? [];
  const summary = reviews.data?.pages[0];
  return <section className="panel" aria-labelledby="binance-review-heading">
    <div className="section-heading">
      <h2 id="binance-review-heading">Binance Card review</h2>
      <span className="connection-status">Review only · no balance changes</span>
    </div>
    <p className="review-safety-note">Reported USD stays USD. Settlement asset and amount are unresolved; these notices do not create transactions.</p>
    {reviews.isPending && <p role="status">Loading Binance notices…</p>}
    {reviews.isError && <p role="alert" className="error">Binance notices could not be loaded. Existing financial records are unchanged.</p>}
    {summary && <p className="collection-count">{summary.candidate_count} purchase candidate{summary.candidate_count === 1 ? "" : "s"} · {summary.needs_review_count} unsupported notice{summary.needs_review_count === 1 ? "" : "s"}</p>}
    {summary && items.length === 0 && <p className="empty-state">No Binance notices to inspect yet. Stored emails are processed automatically; failed transactions do not become purchases.</p>}
    <div className="card-list">{items.map(item => <article className="card" key={item.id}>
      {item.disposition === "candidate" ? <>
        <div className="section-heading">
          <h3>{item.merchant}</h3>
          <strong className="review-amount">{item.reported_amount} {item.reported_currency}</strong>
        </div>
        {item.event_at && <p>Event: <time dateTime={item.event_at}>{utcTime(item.event_at)}</time></p>}
        <p className="unconverted">Settlement unresolved · not posted</p>
      </> : <>
        <h3>Notice needs inspection</h3>
        <p>{reasonLabels[item.reason] ?? "This notice is outside the validated purchase contract."}</p>
        <p className="unconverted">No financial amount inferred · not posted</p>
      </>}
      <details className="advanced-options">
        <summary>Source evidence <span>Mailbox, message and parser version</span></summary>
        <dl className="review-provenance">
          <dt>Mailbox</dt><dd>{item.provenance.source_email ?? "Saved Gmail connection"}</dd>
          <dt>Gmail message</dt><dd>{item.provenance.gmail_message_id}</dd>
          {item.provenance.header_message_id && <><dt>Message-ID</dt><dd>{item.provenance.header_message_id}</dd></>}
          {item.notification_at && <><dt>Notification time</dt><dd>{utcTime(item.notification_at)}</dd></>}
          <dt>Parser</dt><dd>{item.provenance.parser_version}</dd>
        </dl>
        <p className="field-help">Sender matching is not authentication. Raw source evidence is retained; separate Gmail messages are not merged using amounts or merchant names.</p>
      </details>
    </article>)}</div>
    {reviews.hasNextPage && <button type="button" disabled={reviews.isFetching}
      onClick={() => reviews.fetchNextPage()}>{reviews.isFetchingNextPage ? "Loading more notices…" : "Load more notices"}</button>}
    {reviews.isError && !reviews.hasNextPage && <button type="button" disabled={reviews.isFetching}
      onClick={() => reviews.refetch()}>Retry loading notices</button>}
  </section>;
}
