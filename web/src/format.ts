// SPDX-FileCopyrightText: 2026 Curtis Galloway
// SPDX-License-Identifier: Apache-2.0

const SYM: Record<string, string> = { USD: "$", GBP: "£", EUR: "€" };

export function money(amount: string | undefined, currency: string): string {
  if (!amount) return "";
  const n = Number(amount);
  const s = Number.isFinite(n)
    ? n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
    : amount;
  const sym = SYM[currency];
  return sym ? (s.startsWith("-") ? "-" + sym + s.slice(1) : sym + s) : s + " " + currency;
}

export function stampClass(status: string): string {
  const t = status.toLowerCase();
  if (t.includes("cancel") || t.includes("fail")) return "bad";
  if (t.includes("closed") || t.includes("ship") || t.includes("success")) return "ok";
  return "mid";
}
