# HLS backfill dispatch

This record preserves the findings and verification reported for the source
revisions and dates below. Conversion to Markdown does not revalidate runtime
state or resolve recorded blockers.

**Schema version:** 1

**Scope:** LX-Annotate queued HLS backfill

## Source

**Repository:** `/home/admin/luxnix`

**Branch:** `lx-annotate_ollama`

**Recovery merge:** fd8a8937702703ff2cf255a80f0db683bde20887

**Flake lock sha256:** aac5cc82ffc23649a62dde7fd515b1a2f7131e816e6c69cdb075866380ca8d36

**Target:** gc-10

**Lx annotate version:** `1.2.3`

**Wheel digest:** `sha256-5UkRdJDjc2jhZlM56CmuD+moyr1muE0cTCjhMdANM6Q=`

## Dispatch

**Default artifact kind:** both

**Owner:** `endoreg_db.management.commands.materialize_video_hls`

**Behavior:** Invoke the application once so its processed-video pass, including annotation-aware video ordering, completes before its raw-video pass. Explicit --artifact-kind selections remain supported.

**Queue:** `ffmpeg_media`

## Limitations

- Existing broker deliveries are not reordered or removed by this change.
- The verified source hash cache is process-local; worker recycling clears it.
- Worker concurrency, resource limits, encryption and GPU policy are unchanged.

## Verification

**Regression:** `tests/lx-annotate/test_hls_startup_ordering.py`

**Deployment acceptance:** After an operator activates the generation, verify the deployed wrapper, worker queue, successful web startup and a completed playable HLS artifact.
