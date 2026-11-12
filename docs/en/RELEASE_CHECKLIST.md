# Release checklist (maintainers)

This checklist governs Home Assistant Laundry Monitor GitHub Releases and HACS
updates. The English version is authoritative; see also the
[Russian translation](../ru/RELEASE_CHECKLIST.md).

**No release is published by merging a pull request.** Publishing and any
edits to historical releases are explicit maintainer actions. Follow this
checklist for every release candidate (RC) and stable release.

## 1. Release policy

- Versions and tags have **no `v` prefix**: `X.Y.Z-rcN` (e.g.,
  `0.1.8-rc8`) or `X.Y.Z` (e.g., `0.1.8`).
- The Git tag, GitHub Release tag and the tagged commit's
  `custom_components/laundry_monitor/manifest.json` `version` **must match
  exactly**.
- A release with an `-rcN` suffix **must** have GitHub
  `prerelease=true` (check **Set as a pre-release**). A version without
  an RC suffix **must** have `prerelease=false`.
- Never mark an RC **Latest**. Stable releases can become Latest after
  validation; do not assume GitHub's automatic selection always does what
  was intended.
- The minimum declared Home Assistant version is in `hacs.json`; do not
  increase it as part of a release without separate compatibility review.
- Keep version increments in **one release-preparation PR** per published
  release, not in individual issue-fix PRs. Do not release directly from
  an unpublished feature branch.
- Each release must have GitHub Release notes and a dated section in
  `CHANGELOG.md`; the changelog is not retroactively fabricated for old RCs.

## 2. Select scope and freeze a candidate

- [ ] Identify the previous *published* release tag (not merely the
      latest commit or an unannotated Git tag).
- [ ] Review merged PRs and compare the candidate to that published tag;
      distinguish already-shipped changes from changes still unreleased.
- [ ] Decide whether this is an **RC** (needs more field validation)
      or **stable** (supported behavior is validated). Do not call an RC
      stable just because CI is green.
- [ ] Review open regression issues and known limitations, including
      detector behavior, restart recovery, Diagnostics and Recorder.
- [ ] Choose one unique next version/tag. Do not re-use or force-move
      an existing published tag.

## 3. Prepare and review the release PR

- [ ] Create a branch from current `main` (for example,
      `release/0.1.8-rc8`), update only the manifest version and
      release documentation/notes as necessary.
- [ ] Move verified, user-facing changes from the `[Unreleased]`
      section of `CHANGELOG.md` to
      `## [X.Y.Z-rcN] - YYYY-MM-DD` or `## [X.Y.Z] - YYYY-MM-DD`.
      Do not invent field-test results or omit migration impacts.
- [ ] Draft GitHub Release notes in a local text file following this
      minimal outline. Replace all placeholders before publication:

      ```markdown
      ## Changes
      - Actual user-visible fixes, features and linked PRs/issues.

      ## Compatibility and upgrade notes
      - Minimum supported HA Core; CI-tested Core versions; breaking
        changes, migration, Recorder/entity impact, or "None".

      ## Validation
      - CI run and exact commit; HACS/Hassfest; installation/upgrade
        smoke checks; actual field tests performed (if any).

      ## Known limitations / rollback
      - Open risks and how to return to the previous published version.
      ```

- [ ] Review the PR and confirm the entire CI is green on its *latest HEAD*:
      `Tests (minimum)`, `Tests (current)`, aggregate `Tests`,
      `Ruff check`, `Hassfest` and `HACS`.
- [ ] Confirm version targets shown in the CI logs; never claim testing
      against newer Core than actually verified.

Run the same read-only metadata preflight **before** publishing, once the
manifest/changelog and notes file are prepared (use `false` for stable):

```bash
python scripts/verify_release.py \
  --tag 0.1.8-rc8 \
  --prerelease true \
  --notes-file /path/to/release-notes.md
```

The version above is **illustrative**, not an instruction to publish it now.

## 4. Installation and field smoke test

- [ ] On a backup-enabled test Home Assistant installation, confirm
      installation/reinstallation through HACS on the intended channel:
      a prerelease may require enabling the repository's prerelease switch.
- [ ] Check an **upgrade** from the previous published version, restart
      Home Assistant, confirm Config Flow/Options and existing entities are
      retained, and check logs/Repairs.
- [ ] Check a **fresh install** (power-only minimum and, when relevant,
      optional vibration/current/heating sensors). Confirm diagnostics and
      translations.
- [ ] Check snapshot recovery after restart without corrupting active
      cycle state. For behavior-changing builds, observe at least one
      real cycle with appropriate instrumentation; record what was tested
      rather than declaring field validation automatically complete.
- [ ] Verify HACS does not unexpectedly promote an RC to users who have
      not opted in. If an update/rollback pathway behaves unexpectedly,
      do not publish until resolved.
- [ ] Make a backup before any upgrade on the production HA instance.
      Avoid treating temporary changes in Recorder history as runtime faults.

## 5. Tag and publish (after merge)

- [ ] Merge the approved release-preparation PR to `main`. Wait for the
      **Validate run on the resulting main commit** to pass all required
      checks. The **tag must point to that verified main commit**, not the
      original release branch HEAD if squash merging changed its SHA.
- [ ] Confirm `manifest.json` at the to-be-tagged commit has the
      intended version. Create the tag using **GitHub → Releases →
      Draft a new release → Choose a tag → Create new tag on main**,
      selecting the intended `main` commit.
- [ ] Paste the reviewed notes, choose **Set as a pre-release** for RC
      and leave it off for stable. Do not choose **Latest** for RC.
- [ ] Publish a GitHub **Release** (a bare tag alone is not sufficient
      for the HACS release-version workflow).
- [ ] Inspect the published release page: correct tag, commit, notes,
      `Pre-release` badge (or its absence), and Latest designation.
- [ ] Check the read-only `Audit published release / Release metadata`
      workflow. **It runs after publication and cannot prevent a bad
      release; the preflight and manual checks above are still mandatory.**
      It checks tag, manifest, changelog, notes, metadata and ancestry to
      `main`.
- [ ] Verify installation/update using HACS and its prerelease opt-in
      behavior, then monitor issues. Record the published tag, date,
      CI link, smoke-test result and field-validation scope.

## 6. Rollback / incident procedure

If a release is faulty, identify affected users and publish a **new**
corrected version/tag after validating the fix. Do not force-push,
delete/re-create or silently repoint published tags: users and HACS may
have cached their content. For affected installations, document how to
select the previous known-good published version through HACS and restore
HA backups if configuration/state migrations require it. Correct a
mistaken GitHub Release prerelease flag explicitly, verify HACS channels,
and explain the impact in release notes.

## 7. Existing RC metadata (historical exception)

Releases `0.1.8-rc3` through `0.1.8-rc7` were reported in issue #17 as
`prerelease=false` despite their RC suffix. Do **not** change their
tags, commit targets or assets while introducing this checklist.
Do **not** automatically bulk-edit these historical releases: changing
the prerelease flag may affect the versions shown to HACS users, especially
if no stable release exists yet. Revisit metadata correction separately
after checking the actual HACS upgrade/selection behavior for existing
installations. All **new** RC releases must use `prerelease=true`.

See [HACS versioning guidance](https://hacs.dev/docs/publish/start/) and
[Home Assistant marketplace versioning](https://contributors.home-assistant.io/marketplace/how-it-works/).
