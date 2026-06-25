## 1. Backend foundation

- [ ] 1.1 Confirm current referral_code model/service paths and identify exact endpoint(s) for bulk generation
- [ ] 1.2 Implement or adjust bulk generation so only users with `referral_code = null` are processed
- [ ] 1.3 Ensure generated codes are unique and persisted safely
- [ ] 1.4 Expose backend data needed by admin for button visibility and table rendering

## 2. Admin contract

- [ ] 2.1 Define the admin API payload for referral code, referral rate percent, and balance columns
- [ ] 2.2 Add a signal for whether at least one user with `referral_code = null` exists
- [ ] 2.3 Verify the contract is compatible with all table variants used in admin

## 3. Verification

- [ ] 3.1 Add/update backend tests for null-only bulk generation
- [ ] 3.2 Add/update tests for uniqueness and non-overwrite behavior
- [ ] 3.3 Run backend test/lint subset relevant to referral changes
- [ ] 3.4 Summarize changed files and any open questions for admin/design handoff
