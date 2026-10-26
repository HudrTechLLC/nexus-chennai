/**
 * Structural test for migration 0007_03 (audit_log append-only, D-030). The live behaviour was
 * checked against nexus-qa in a rolled-back transaction (see the PR); this keeps the guarantee
 * from being weakened silently in a later edit.
 */
import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

const sql = readFileSync(path.resolve(__dirname, "../../../../supabase/migrations/0007_03_audit_append_only.sql"), "utf8")
  .split("\n").filter((l) => !l.trim().startsWith("--")).join("\n").toLowerCase();

describe("0007_03 audit_log append-only", () => {
  it("rejects UPDATE and DELETE on every row, for every role", () => {
    expect(sql).toMatch(/create trigger trg_audit_log_append_only before update or delete on public\.audit_log\s+for each row/);
    expect(sql).toMatch(/raise exception 'audit_log is append-only/);
  });
  it("rejects TRUNCATE", () => {
    expect(sql).toMatch(/create trigger trg_audit_log_no_truncate before truncate on public\.audit_log\s+for each statement/);
  });
  it("has no exemption by role or setting", () => {
    expect(sql).not.toMatch(/current_user|session_user|current_setting|pg_has_role/);
  });
});
