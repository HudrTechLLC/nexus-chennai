"use client";
import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { addNote, decideTaskforce, linkCases, proposeTaskforce, setMember } from "@/app/console/(app)/taskforces/actions";
import { validateNote, validateProposal } from "@/lib/taskforces";

const input = "w-full rounded-md border border-line bg-bg px-3 py-2 text-sm";
const primary = "rounded-md bg-signal px-3 py-2 text-sm font-medium text-white disabled:opacity-60";
const secondary = "rounded-md border border-line px-3 py-2 text-sm hover:bg-bg disabled:opacity-60";

function Msg({ error, ok }: { error: string | null; ok?: string | null }) {
  if (error) return <p role="alert" className="text-sm text-red-600">{error}</p>;
  if (ok) return <p className="text-sm text-signal">{ok}</p>;
  return null;
}

/** Propose a joint task force (LNK-09). Prefilled from ?series_id / ?alert_id. */
export function ProposeForm({ defaults }: { defaults: { name: string; series_id: string | null; alert_id: string | null; sourceLabel: string | null } }) {
  const router = useRouter();
  const [name, setName] = useState(defaults.name);
  const [purpose, setPurpose] = useState("");
  const [crimeIds, setCrimeIds] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, start] = useTransition();
  return (
    <form
      className="space-y-3"
      onSubmit={(e) => {
        e.preventDefault();
        const problem = validateProposal({ name, purpose });
        if (problem) return setError(problem);
        setError(null);
        start(async () => {
          const r = await proposeTaskforce({ name, purpose, series_id: defaults.series_id, alert_id: defaults.alert_id, crime_ids: crimeIds });
          if (r.ok && r.id) router.push(`/console/taskforces/${encodeURIComponent(r.id)}`);
          else if (!r.ok) setError(r.error);
        });
      }}
    >
      {defaults.sourceLabel && <p className="text-sm text-muted">From {defaults.sourceLabel}. Its cases are linked automatically.</p>}
      <label className="block space-y-1">
        <span className="text-sm font-medium">Name</span>
        <input value={name} onChange={(e) => setName(e.target.value)} maxLength={120} required className={input} />
      </label>
      <label className="block space-y-1">
        <span className="text-sm font-medium">Purpose</span>
        <textarea value={purpose} onChange={(e) => setPurpose(e.target.value)} rows={3} maxLength={2000} className={input}
          placeholder="What the joint team should do: shared footage requests, common suspects, a joint review…" />
      </label>
      <label className="block space-y-1">
        <span className="text-sm font-medium">More cases <span className="font-normal text-muted">(optional, case ids separated by commas or spaces)</span></span>
        <textarea value={crimeIds} onChange={(e) => setCrimeIds(e.target.value)} rows={2} className={`${input} font-mono`} placeholder="CHN-AD-2026-001182 CHN-VL-2026-000877" />
      </label>
      <Msg error={error} />
      <div className="flex items-center gap-3">
        <button disabled={pending} className={primary}>{pending ? "Proposing…" : "Propose task force"}</button>
        <span className="text-xs text-muted">A supervisor approves it before it becomes active.</span>
      </div>
    </form>
  );
}

/** Supervisor: approve / decline a proposal, or close an active task force. */
export function DecidePanel({ id, status }: { id: string; status: "proposed" | "active" }) {
  const router = useRouter();
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, start] = useTransition();
  const act = (d: "approve" | "decline" | "close") => start(async () => {
    const r = await decideTaskforce(id, d, note);
    if (r.ok) { setNote(""); setError(null); router.refresh(); } else setError(r.error);
  });
  return (
    <div className="space-y-2">
      <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={2} maxLength={2000} className={input}
        placeholder={status === "proposed" ? "Decision note (optional): why approved or declined" : "Closing note (optional): outcome"} />
      <div className="flex flex-wrap gap-2">
        {status === "proposed" ? (
          <>
            <button disabled={pending} onClick={() => act("approve")} className={primary}>Approve joint task force</button>
            <button disabled={pending} onClick={() => act("decline")} className={secondary}>Decline</button>
          </>
        ) : (
          <button disabled={pending} onClick={() => act("close")} className={secondary}>Close task force</button>
        )}
      </div>
      <Msg error={error} />
    </div>
  );
}

/** Supervisor: add an officer, change lead/member, or remove. */
export function MemberManager({ id, directory, current }: {
  id: string;
  directory: { user_id: string; name: string; role: string; station_id: string | null }[];
  current: { user_id: string; role: "lead" | "member" }[];
}) {
  const router = useRouter();
  const [user, setUser] = useState("");
  const [role, setRole] = useState<"lead" | "member">("member");
  const [error, setError] = useState<string | null>(null);
  const [pending, start] = useTransition();
  const inTf = new Set(current.map((m) => m.user_id));
  const run = (userId: string, r: "lead" | "member" | null) => start(async () => {
    const res = await setMember(id, userId, r);
    if (res.ok) { setError(null); setUser(""); router.refresh(); } else setError(res.error);
  });
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-2">
        <select value={user} onChange={(e) => setUser(e.target.value)} className="min-w-[14rem] flex-1 rounded-md border border-line bg-bg px-2 py-2 text-sm" aria-label="Officer">
          <option value="">Add an officer…</option>
          {directory.filter((d) => !inTf.has(d.user_id)).map((d) => (
            <option key={d.user_id} value={d.user_id}>{d.name} · {d.role.replace("_", " ")}{d.station_id ? ` · ${d.station_id}` : ""}</option>
          ))}
        </select>
        <select value={role} onChange={(e) => setRole(e.target.value as "lead" | "member")} className="rounded-md border border-line bg-bg px-2 py-2 text-sm" aria-label="Role">
          <option value="member">Member</option>
          <option value="lead">Lead</option>
        </select>
        <button disabled={pending || !user} onClick={() => run(user, role)} className={secondary}>Add</button>
      </div>
      <Msg error={error} />
    </div>
  );
}

/** Supervisor: per-member controls (make lead / member, remove). */
export function MemberControls({ id, userId, role }: { id: string; userId: string; role: "lead" | "member" }) {
  const router = useRouter();
  const [pending, start] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const run = (r: "lead" | "member" | null) => start(async () => {
    const res = await setMember(id, userId, r);
    if (res.ok) router.refresh(); else setError(res.error);
  });
  return (
    <span className="inline-flex items-center gap-2 text-xs">
      <button disabled={pending} onClick={() => run(role === "lead" ? "member" : "lead")} className="text-muted hover:text-ink">{role === "lead" ? "Make member" : "Make lead"}</button>
      <button disabled={pending} onClick={() => run(null)} className="text-red-600 hover:underline">Remove</button>
      {error && <span className="text-red-600">{error}</span>}
    </span>
  );
}

export function NoteForm({ id }: { id: string }) {
  const router = useRouter();
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, start] = useTransition();
  return (
    <form className="space-y-2" onSubmit={(e) => {
      e.preventDefault();
      const problem = validateNote(text);
      if (problem) return setError(problem);
      start(async () => {
        const r = await addNote(id, text);
        if (r.ok) { setText(""); setError(null); router.refresh(); } else setError(r.error);
      });
    }}>
      <textarea value={text} onChange={(e) => setText(e.target.value)} rows={3} maxLength={2000} className={input}
        placeholder="Add a note for the joint team. Notes are permanent: they cannot be edited or deleted." />
      <Msg error={error} />
      <button disabled={pending} className={primary}>{pending ? "Adding…" : "Add note"}</button>
    </form>
  );
}

export function LinkCasesForm({ id }: { id: string }) {
  const router = useRouter();
  const [raw, setRaw] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);
  const [pending, start] = useTransition();
  return (
    <form className="flex flex-wrap gap-2" onSubmit={(e) => {
      e.preventDefault();
      start(async () => {
        const r = await linkCases(id, raw);
        if (r.ok) { setRaw(""); setError(null); setOk(r.status ?? null); router.refresh(); } else { setOk(null); setError(r.error); }
      });
    }}>
      <input value={raw} onChange={(e) => setRaw(e.target.value)} placeholder="Link more cases: CHN-AD-2026-001182 …" className={`${input} min-w-[16rem] flex-1 font-mono`} />
      <button disabled={pending || !raw.trim()} className={secondary}>Link</button>
      <div className="basis-full"><Msg error={error} ok={ok} /></div>
    </form>
  );
}
