import { TipStatus } from "@/components/public/TipStatus";

export const metadata = { title: "Check a tip · Nexus Chennai" };

export default function Status() {
  return (
    <div className="mx-auto max-w-xl">
      <h1 className="text-3xl font-bold">Check a tip</h1>
      <p className="mt-1 text-muted">Enter the tip code and passphrase you chose. After 5 wrong tries the code is locked for 15 minutes.</p>
      <div className="mt-6"><TipStatus /></div>
    </div>
  );
}
