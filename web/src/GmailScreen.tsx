import { useState } from "react";
import { Link, Navigate, useParams } from "react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { newClientId, request } from "./api";
import { BinanceCardReviews } from "./BinanceCardReviews";

type GmailSource = {
  id: string;
  email: string | null;
  status: "connecting" | "active" | "needs_authorization" | "disconnected";
  sync_mode: "full" | "history";
  allowed_senders: string[];
  last_synced_at: string | null;
  last_error: string | null;
  message_count: number;
  review_count: number;
};

const labels = {
  connecting: "Authorization pending",
  active: "Connected",
  needs_authorization: "Reconnect to resume synchronization",
  disconnected: "Disconnected",
};

export function GmailScreen() {
  const { planId } = useParams<{ planId: string }>();
  const queryClient = useQueryClient();
  const [newSourceId] = useState(newClientId);
  const sources = useQuery({
    queryKey: ["plans", planId, "gmail"],
    queryFn: () => request<{ configured: boolean; configured_senders: string[]; sources: GmailSource[] }>(`/plans/${planId}/gmail`),
    enabled: Boolean(planId),
    refetchInterval: 10_000,
  });
  const connect = useMutation({
    mutationFn: (sourceId: string) => request<{ authorization_url: string }>(
      `/plans/${planId}/gmail/${sourceId}/oauth`, { method: "POST", body: "{}" }),
    onSuccess: ({ authorization_url }) => { window.location.assign(authorization_url); },
  });
  const disconnect = useMutation({
    mutationFn: (sourceId: string) => request<GmailSource>(
      `/plans/${planId}/gmail/${sourceId}/disconnect`, { method: "POST", body: "{}" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["plans", planId, "gmail"] }),
  });
  if (!planId) return <Navigate to="/plans" replace />;

  return <main className="workspace-page">
    <header className="page-header">
      <div>
        <p className="eyebrow">Connected sources</p>
        <h1>Gmail</h1>
        <p>Connect Gmail to collect email notices for this plan. You can keep using Numa without it.</p>
      </div>
      <Link className="text-action" to={`/plans/${planId}/accounts`}>← Accounts</Link>
    </header>
    <BinanceCardReviews key={planId} planId={planId} />
    <section className="panel" aria-labelledby="gmail-connections-heading">
      <h2 id="gmail-connections-heading">Connections</h2>
      {sources.isPending && <p role="status">Loading connections…</p>}
      {sources.isError && <p role="alert" className="error">{sources.error.message}</p>}
      {sources.data && sources.data.sources.length === 0 && <p className="empty-state">No Gmail connections yet. Connect a mailbox when you are ready; manual tracking stays available.</p>}
      <div className="card-list">{sources.data?.sources.map(source => <article className="card" key={source.id}>
        <div className="section-heading">
          <h3>{source.email ?? "New Gmail connection"}</h3>
          <p className={`connection-status connection-status-${source.status}`}>{labels[source.status]}</p>
        </div>
        {source.status === "active" && <p role="status">{source.sync_mode === "full" ? "Initial synchronization in progress" : "Checking for new notices periodically"}</p>}
        <p className="collection-count">{source.message_count} emails collected · {source.review_count} require review</p>
        {source.last_synced_at && <p>Last synchronized: {new Date(source.last_synced_at).toLocaleString()}</p>}
        {source.last_error && source.status === "active" && <p role="status">Synchronization is temporarily unavailable. Numa will retry automatically.</p>}
        <details className="advanced-options">
          <summary>Connection settings <span>Sender scope, reconnect or disconnect</span></summary>
          <h4>Saved sender scope</h4>
          {source.allowed_senders.length > 0
            ? <ul>{source.allowed_senders.map(sender => <li key={sender}>{sender}</li>)}</ul>
            : <p>No saved sender scope. Reconnect before collection can resume.</p>}
          <div className="card-actions">
            <button type="button" disabled={!sources.data.configured || connect.isPending || disconnect.isPending}
              onClick={() => connect.mutate(source.id)}>Reconnect</button>
            {source.status !== "disconnected" && <button type="button" disabled={disconnect.isPending || connect.isPending}
              onClick={() => disconnect.mutate(source.id)}>Disconnect</button>}
          </div>
        </details>
      </article>)}</div>
      <p>Google will ask for read-only access to your mailbox. Numa stores the emails for later processing; this connection does not create transactions.</p>
      <p>Google's permission is mailbox-wide. Numa applies a local exact-sender filter before downloading email bodies, excluding spam and trash. This does not authenticate senders and may include non-financial notices from allowed addresses.</p>
      {sources.data && <div className="new-connection">
        <h3>Configured senders for new connections</h3>
        {sources.data.configured_senders.length > 0
          ? <ul>{sources.data.configured_senders.map(sender => <li key={sender}>{sender}</li>)}</ul>
          : <p>No allowed senders configured; new connections are disabled.</p>}
      </div>}
      {sources.data && !sources.data.configured && <p role="status">Gmail is not configured on the server yet.</p>}
      <button type="button" disabled={!sources.data?.configured || connect.isPending || disconnect.isPending}
        onClick={() => connect.mutate(newSourceId)}>
        {connect.isPending ? "Opening Google…" : "Connect Gmail"}
      </button>
      {connect.isError && <p role="alert" className="error">{connect.error.message}</p>}
      {disconnect.isError && <p role="alert" className="error">{disconnect.error.message}</p>}
      <p>Disconnecting stops collection and removes the saved credential. Previously collected emails are retained.</p>
      <p>Changing server settings does not change a saved sender scope. Reconnect to adopt the configured senders; previously collected emails are still retained.</p>
    </section>
  </main>;
}
