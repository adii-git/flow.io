"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";

const EXAMPLES = [
  "Create an Instagram post for my clothing brand",
  "Build a landing page for a new idea",
  "Research a topic and turn it into a brief",
];

const SPARKLES = [
  [5, 83, 0.2], [12, 91, 1.4], [18, 78, 2.1], [24, 88, 0.7], [30, 81, 2.7],
  [35, 94, 1.8], [41, 84, 0.1], [46, 91, 2.4], [51, 78, 1.1], [57, 87, 2.9],
  [62, 94, 0.5], [67, 81, 1.7], [72, 89, 0.9], [77, 83, 2.5], [82, 93, 1.2],
  [87, 80, 0.4], [92, 88, 2.2], [97, 82, 1.5], [15, 72, 2.6], [28, 75, 0.8],
  [39, 73, 1.9], [70, 74, 0.3], [85, 72, 2.8], [94, 75, 1.0],
] as const;

export default function IntentField() {
  const [text, setText] = useState("");
  const router = useRouter();

  function submit(e?: FormEvent) {
    e?.preventDefault();
    const objective = text.trim();
    if (!objective) return;
    router.push(`/app?objective=${encodeURIComponent(objective)}`);
  }

  return (
    <main className="conduit-landing">
      <div className="scene" aria-hidden="true">
        <div className="scene-image" />
        <div className="scene-vignette" />
        <div className="monitor-glow" />
        <div className="monitor-flicker" />
        <div className="grass-sparkles">
          {SPARKLES.map(([x, y, delay], i) => (
            <span key={i} style={{ left: `${x}%`, top: `${y}%`, animationDelay: `${delay}s` }} />
          ))}
        </div>
      </div>

      <header className="landing-header">
        <Link href="/" className="wordmark" aria-label="Flow.io home"><span className="wordmark-mark">c</span> flow<span className="wordmark-period">.io</span></Link>
        <div className="header-right"><span className="availability"><i /> AI workspace</span><Link href="/login" className="sign-in">Sign in <span aria-hidden="true">↗</span></Link></div>
      </header>

      <section className="hero-content">
        <div className="eyebrow"><span className="eyebrow-line" /> ONE PROMPT. MANY POSSIBILITIES.</div>
        <h1>What do you<br />want to <em>make?</em></h1>
        <p className="hero-copy">Dream it up. Work it out. Get it done.<br className="desktop-break" /> Flow.io brings the right AI capabilities together to make it happen.</p>

        <form className="prompt-box" onSubmit={submit}>
          <label className="sr-only" htmlFor="conduit-prompt">Describe what you want to create or accomplish</label>
          <textarea id="conduit-prompt" value={text} onChange={(e) => setText(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); } }} placeholder="I want to create…" rows={2} />
          <div className="prompt-footer"><span className="prompt-hint">Be as specific or as open-ended as you like.</span><button type="submit" disabled={!text.trim()} aria-label="Start task">Let’s go <span aria-hidden="true">↗</span></button></div>
        </form>

        <div className="examples"><span className="examples-label">TRY SOMETHING</span>{EXAMPLES.map((example) => <button type="button" key={example} onClick={() => setText(example)}>{example}<span aria-hidden="true">↗</span></button>)}</div>
      </section>

      <footer className="landing-footer"><span>YOUR IDEA IS THE INTERFACE.</span><span className="footer-center"><i /> READY WHEN YOU ARE</span><span>FLOW.IO <b>—</b> AI, IN FLOW</span></footer>
    </main>
  );
}
