export const metadata = { title: "How anonymity works · Nexus Chennai" };

const STORED = [
  "What you wrote, and the category you picked.",
  "The week your tip arrived (for example 2026-W43), not the date or time.",
  "If you picked one, the area: a hexagon you sized yourself, from about 0.015 to 0.7 km². The point you tapped never leaves your browser.",
  "Photos after your browser removed their location and camera details (and blurred faces, if you asked). Audio files as sent.",
  "If you chose a tip code: the code, and your passphrase scrambled with bcrypt so nobody can read it back.",
];
const NOT_STORED = [
  "What you type in the place search. It goes through our own server to OpenStreetMap search, never straight from your browser, and is not logged or kept.",
  "Your IP address, browser, device or cookies. The tip form does not set any cookies.",
  "Your name, phone number or email. We never ask for them.",
  "The exact time you sent the tip.",
  "GPS or camera details from photos. Our server rejects any photo where they survived.",
];

/** Plain-words privacy page (spec G1 /about/privacy, J1). */
export default function Privacy() {
  return (
    <article className="prose prose-neutral mx-auto max-w-2xl dark:prose-invert">
      <h1>How anonymity works</h1>
      <p>Nexus is a hackathon prototype and all its case data is synthetic. This page says plainly what happens to a tip.</p>
      <h2>What is stored</h2>
      <ul>{STORED.map((s) => <li key={s}>{s}</li>)}</ul>
      <h2>What is not stored</h2>
      <ul>{NOT_STORED.map((s) => <li key={s}>{s}</li>)}</ul>
      <h2>Limits you should know</h2>
      <ul>
        <li>The hosting provider (Vercel) keeps its own request logs, which include IP addresses. We cannot switch those off. Using Tor or a VPN is supported but not required.</li>
        <li>What you write can identify you. Leave out names, phone numbers and details only you would know.</li>
        <li>The tip code and passphrase cannot be recovered. After 5 wrong tries a code is locked for 15 minutes.</li>
        <li>Tips are read by an automatic screen and then by police officers. They are treated as untrusted information, never as instructions.</li>
      </ul>
      <p>In an emergency, call 112.</p>
    </article>
  );
}
