import { CAP_LABEL, type ContextTransfer, type Subtask } from "@/lib/types";

export default function StepDetail({ step, transfers }: { step: Subtask; transfers: ContextTransfer[] }) {
  const r = step.routing, runs = transfers.filter((t) => t.subtask_id === step.id), t = runs[runs.length - 1];
  return (
    <div className="space-y-5 text-sm">
      <section aria-labelledby="why">
        <h3 id="why" className="mb-1 text-base font-semibold">Why this tool?</h3>
        {r?.skipped ? <p>{r.note}</p> : r?.tool_name ? (
          <>
            <p><strong>{r.tool_name}</strong> for {CAP_LABEL[step.capability]?.toLowerCase() ?? step.capability}. Confidence {Math.round((r.confidence ?? 0) * 100)}% (an estimate from the tool's registry entry). Context: {r.context_items ?? 0} items at planning time.</p>
            <ul className="mt-2 list-disc space-y-0.5 pl-5">{r.reasons?.map((x) => <li key={x}>{x}</li>)}</ul>
            {!!r.alternatives?.length && <p className="mt-2 text-mute">If it fails, Flow.io tries {r.alternatives.slice(0, 2).join(", then ")}.</p>}
          </>
        ) : <p className="text-mute">Plan the task to see which tool Flow.io picks and why.</p>}
      </section>
      <section aria-labelledby="ctx">
        <h3 id="ctx" className="mb-1 text-base font-semibold">Context Inspector</h3>
        {!t ? <p className="text-mute">Nothing has been handed to this step yet. After it runs you'll see what it received and what was held back.</p> : (
          <div className="grid gap-4">
            <div>
              <h4 className="font-semibold">Sent ({t.sent.length})</h4>
              <ul className="mt-1 space-y-1.5">{t.sent.map((s) => <li key={s.item_id} className="rounded-input border border-line bg-sunk p-2"><span className="font-medium">{s.label}</span> <span className="text-mute">({s.kind}, {s.chars.toLocaleString()} characters{s.trimmed ? ", trimmed to fit" : ""})</span><span className="block truncate text-mute">{s.preview}</span></li>)}</ul>
            </div>
            <div>
              <h4 className="font-semibold">Held back ({t.withheld.length})</h4>
              {t.withheld.length === 0 ? <p className="text-mute">Nothing was held back.</p> :
                <ul className="mt-1 space-y-1.5">{t.withheld.map((s) => <li key={s.item_id} className="rounded-input border border-line bg-sunk p-2"><span className="font-medium">{s.label}</span> <span className="text-mute">({s.kind})</span><span className="block text-mute">{s.reason}</span></li>)}</ul>}
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
