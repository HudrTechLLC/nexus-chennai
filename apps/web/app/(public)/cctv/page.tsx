import Link from "next/link";

export const metadata = { title: "Share CCTV · Nexus Chennai" };

/** CCTV drop for shop owners (spec G1 /cctv): same anonymity rules as a tip. */
export default function Cctv() {
  return (
    <div className="mx-auto max-w-2xl space-y-5">
      <h1 className="text-3xl font-bold">Shop owners: share CCTV</h1>
      <p className="text-muted">
        If your camera may have recorded something police are asking about, you can help without giving your identity.
        The same anonymity rules apply as for any tip.
      </p>
      <ol className="list-decimal space-y-2 pl-5">
        <li>Find the appeal (or describe the date, time and area).</li>
        <li>Upload still frames (photos or screenshots). Their location and camera details are removed in your browser.</li>
        <li>Choose a tip code if you are willing to share the full video later. Police can then reply and arrange it.</li>
      </ol>
      <p className="rounded-md border border-line bg-surface p-3 text-sm">
        Video files can&apos;t be cleaned in the browser yet, so this prototype accepts still frames only.
      </p>
      <div className="flex flex-wrap gap-3">
        <Link href="/appeals" className="rounded-md border border-line px-4 py-2">Browse appeals</Link>
        <Link href="/tip/new?kind=cctv" className="rounded-md bg-signal px-4 py-2 font-medium text-white">Share footage stills</Link>
      </div>
    </div>
  );
}
