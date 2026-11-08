// The server's secret detector (api/mimirsynth/secretscan.py), ported for JavaScript agents: the same rules, so that a client redacts
// what the server would mask before anything leaves the machine. Only what a client needs: scan without a brain's exceptions, and
// redact. A rule added to the server must be added here too; the contract cases (integrations/shared/contract/cases.json) cover one
// value of every rule, and a test checks that the rule ids are the same on both sides.

export interface Rule {
  id: string;
  pattern: RegExp; // always global
  group: number; // the group that is the secret (0: all of it)
  certain: boolean;
}

export interface Finding {
  rule: string;
  start: number;
  end: number;
  certain: boolean;
}

function rule(id: string, source: string, flags = "", group = 0, certain = true): Rule {
  return { id, pattern: new RegExp(source, "g" + flags + (group ? "d" : "")), group, certain };
}

export const RULES: readonly Rule[] = [
  rule("private_key", String.raw`-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY(?: BLOCK)?-----[\s\S]{0,8192}?-----END (?:[A-Z0-9]+ )*PRIVATE KEY(?: BLOCK)?-----`),
  rule("aws_access_key", String.raw`\b(?:AKIA|ASIA|ABIA|ACCA)[0-9A-Z]{16}\b`),
  rule("github_token", String.raw`\b(?:gh[pousr]_[A-Za-z0-9]{36,255}|github_pat_[A-Za-z0-9_]{22,255})\b`),
  rule("gitlab_token", String.raw`\bgl(?:pat|dt|rt|cbt|ptt|ft|imt|agent|oas)-[A-Za-z0-9_\-]{20,}`),
  rule("slack_token", String.raw`\bxox[abposr]-[A-Za-z0-9\-]{10,}`),
  rule("slack_webhook", String.raw`https://hooks\.slack\.com/(?:services|workflows)/[A-Za-z0-9/_\-]{20,}`),
  rule("google_api_key", String.raw`\bAIza[0-9A-Za-z_\-]{35}\b`),
  rule("ai_api_key", String.raw`\bsk-(?:proj-|ant-(?:api|admin)\d\d-|or-v1-)?[A-Za-z0-9_\-]{32,}`),
  rule("stripe_key", String.raw`\b[rs]k_(?:live|test)_[A-Za-z0-9]{16,}\b`),
  rule("npm_token", String.raw`\bnpm_[A-Za-z0-9]{36}\b`),
  rule("huggingface_token", String.raw`\bhf_[A-Za-z0-9]{34,}\b`),
  rule("telegram_bot_token", String.raw`\b\d{8,10}:AA[A-Za-z0-9_\-]{33}\b`),
  rule("sendgrid_key", String.raw`\bSG\.[A-Za-z0-9_\-]{22}\.[A-Za-z0-9_\-]{43}\b`),
  rule("jwt", String.raw`\beyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}`),
  rule("authorization", String.raw`\bauthorization\s*[:=]\s*["']?(?:bearer|basic|token|bot)\s+([A-Za-z0-9._~+/=\-]{8,})`, "i", 1),
  rule("url_credentials", String.raw`\b[a-z][a-z0-9+.\-]{1,20}://[^\s:/@"'<>]{1,128}:([^\s@/"'<>]{1,256})@[^\s@/"'<>]`, "i", 1),
  rule(
    "assigned_secret",
    String.raw`\b(?:[a-z0-9]{1,24}[_\-.]){0,4}(?:password|passwd|pwd|secret|token|api[_\-.]?key|access[_\-.]?key|private[_\-.]?key|client[_\-.]?secret|auth)` +
      String.raw`(?:[_\-.][a-z0-9]{1,24}){0,4}["']?\s*(?::=|=|:)\s*["']?([^\s"'` + "`" + String.raw`,;<>(){}\[\]]{12,256})`,
    "i",
    1,
    false,
  ),
];

// Values shaped like secrets that are placeholders or documentation examples.
const PLACEHOLDER = /example|placeholder|changeme|your[_\-]?|xxxx|\*{3}|\.\.\.|<[^>]*>|\$\{|\{\{|%\(|^\$[A-Za-z_]/i;

/** Shannon entropy per character. */
export function entropy(s: string): number {
  const chars = Array.from(s);
  if (!chars.length) return 0;
  const counts = new Map<string, number>();
  for (const c of chars) counts.set(c, (counts.get(c) ?? 0) + 1);
  let h = 0;
  for (const c of counts.values()) h -= (c / chars.length) * Math.log2(c / chars.length);
  return h;
}

/** A value assigned to «password» that looks generated, not a word or a path. */
function looksRandom(v: string): boolean {
  const classes = [/[a-z]/, /[A-Z]/, /\d/, /[^A-Za-z0-9]/].filter((p) => p.test(v)).length;
  if (v.includes("/") && !/[A-Za-z0-9+/]{20,}={0,2}$/.test(v)) return false; // a path
  return classes >= 3 && entropy(v) >= 3.0;
}

/** Findings in order of position, without overlaps (where two rules cover the same piece, the one that starts first and is sure wins). */
export function scan(text: string): Finding[] {
  const found: Finding[] = [];
  const t = text ?? "";
  for (const r of RULES) {
    r.pattern.lastIndex = 0;
    for (const m of t.matchAll(r.pattern)) {
      const [a, b] = r.group ? (m.indices?.[r.group] ?? [0, 0]) : [m.index ?? 0, (m.index ?? 0) + m[0].length];
      const v = t.slice(a, b);
      if (PLACEHOLDER.test(v)) continue;
      if (r.id === "url_credentials" && ["password", "pass", "secret", "pwd"].includes(v.toLowerCase())) continue;
      if (!r.certain && !looksRandom(v)) continue;
      found.push({ rule: r.id, start: a, end: b, certain: r.certain });
    }
  }
  found.sort((x, y) => x.start - y.start || Number(!x.certain) - Number(!y.certain) || y.end - y.start - (x.end - x.start));
  const out: Finding[] = [];
  for (const f of found) {
    if (out.length && f.start < out[out.length - 1].end) continue;
    out.push(f);
  }
  return out;
}

/** Replaces the sure findings (or all of them, with `everything`) by the marker; possible ones are left as they are. */
export function redactFindings(text: string, findings: Finding[], marker: string, everything = false): string {
  let out = "";
  let last = 0;
  for (const f of findings) {
    out += text.slice(last, f.start) + (f.certain || everything ? marker : text.slice(f.start, f.end));
    last = f.end;
  }
  return out + text.slice(last);
}
