# Severity Format — Code Audit

> Core format: read `probekit-core/references/severity-format.md` for markers, output syntax, decision tree, diff format, honesty rules.

## Code-Audit Escalation Rules

- Slopsquatting / unverified dependency → always CRITICAL
- Hardcoded secret / credential → always CRITICAL
- Missing auth check on protected endpoint → always CRITICAL
- SQL/NoSQL injection, XSS, path traversal, SSRF → always CRITICAL
- Privilege escalation path → always CRITICAL
- Silent exception catch with no logging → WARNING minimum
- Missing input validation on user-controlled data → WARNING minimum
- God class (size outlier) → WARNING
- Phantom code, prompt residue → SUGGESTION unless in a security-sensitive path
- Exceptionally clean error hierarchy, dependency injection, composition pattern → 💎 DIAMOND

### Section 12 (Test Quality) Escalation

- Assert-free test → WARNING (silently passes always, provides false confidence)
- Test with only trivial assertions on critical path → WARNING
- Flaky test (sleep-based, time-dependent, order-dependent) → WARNING
- Skipped/xfail test with no reason or tracking issue → SUGGESTION
- Copy-paste tests that should be parameterized → SUGGESTION
- God test (tests multiple unrelated behaviors) → SUGGESTION
- Missing regression test for a known shipped bug → WARNING

### AI Patterns (Section 10) Escalation

Any AI pattern escalates to CRITICAL if in auth/payment/PII code or public endpoint without auth.
Any AI pattern de-escalates to SUGGESTION if in test files, dev-only scripts, or explicitly marked intentional.
- Vibe coding in business logic (10.11) → CRITICAL
- Context window artifact copying security checks (10.12) → CRITICAL
- Confident incorrectness with SQL injection (10.13) → CRITICAL
- `encrypt_*` that hashes with md5 (10.19) → CRITICAL
- Duplicate auth/secrets management (10.20) → CRITICAL
- Stale pattern causing runtime error (10.18) → CRITICAL
- Training data leakage with credentials (10.16) → CRITICAL
- Approximate implementation in financial calc (10.17) → CRITICAL
