# Release retention

Retain the newest **five published GitHub releases**, ordered by publication time, and **all Git tags**. Preserve drafts and any release explicitly protected by an operator. Releases and tags are separate: deleting an old release removes its downloadable packages and release-page metadata, not its tagged source history. Container images have a separate lifecycle and are not deleted by this policy.

## Before removing a release

1. Enumerate the complete release collection and freeze exact release IDs, tag names, retained releases, and tag-to-commit refs. Do not assume the first API page contains everything.
2. Back up each candidate's title, notes, prerelease flag, timestamps, complete release/asset metadata, and every attached package/checksum file to a durable directory **outside the repository**. Keep that directory private and include it in the operator's normal backup system.
3. Verify each downloaded size and SHA-256 against GitHub's asset digest where available and the published checksum file. Retain a machine-readable inventory of verified filenames, sizes, and hashes. Back up every candidate before deleting the first release.
4. Recheck candidate metadata, exact IDs, retained releases, and tag refs. Download counts may change during backup; package identity, content, notes, and release ownership must not change.
5. Delete only the approved exact release IDs. Never pass `--cleanup-tag`, prune release tags, rewrite commits, or delete GHCR images as part of this task.
6. Read back the remaining releases and verify that every tag ref is unchanged. Record the deletion list and archive location for recovery.

Run cleanup only during an explicitly authorized release/maintenance task, not from the application worker. A new release must be fully published and verified before it counts toward retention. This policy does not authorize pushing unpublished application changes.

## Recovery

The retained tag identifies the original source commit. An authorized operator can recreate a prerelease from that existing tag, restore its backed-up title/notes, upload the verified packages and checksum file, then independently verify the restored downloads. GitHub's original release/asset IDs, publication timestamps, and download counts will not be preserved. Old package download links stop working while the release is absent.

The initial cleanup on 09.05.2026 retained v0.7.0, v0.6.7, v0.6.6, v0.6.5, and v0.6.4. Its verified archive contains the 28 older releases and their 84 attached assets; all Git tags were retained.
