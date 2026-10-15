# Maintaining documentation

Use this guide when adding or changing LuxNix instructions. Keep documentation
in the same change as the behavior it describes, so readers can use the guides
from their configuration's branch or commit.

## Choose a home

- Put maintained operator and contributor guides in `docs/` as Markdown.
- Keep one canonical procedure per topic; link to it from other guides.
- Add a new guide to `mkdocs.yaml` and the relevant section of
  [Documentation Home](index.md).
- Keep command names, effects, and risk labels aligned with `luxnix.yml` and
  `devenv/commands.yml` in the repository root.
- Edit `mkdocs.yaml` to change navigation. `TABLE_OF_CONTENTS.md` is generated.

## Write for the reader

Start with the task, intended audience, and expected outcome. Use descriptive
headings, short paragraphs, numbered steps for procedures, and bullets for
choices. Explain unfamiliar terms where they first appear.

For an operational procedure, include:

1. **Prerequisites:** tools, access, source revision, target, and required inputs.
2. **Scope:** where each command runs and which files or machines it changes.
3. **Steps:** canonical commands, with every placeholder explained before use.
4. **Verification:** expected output or state and what constitutes success.
5. **Failure handling:** when to stop, which logs to retain, and the applicable
   rollback or recovery procedure.

Avoid copying command catalogs into several guides. Link to detailed secret,
installation, and recovery procedures instead of shortening away prerequisites.
Distinguish an implemented feature from a deployed or independently verified one.

## Make information accessible

Use relative links between guides, descriptive link text, and language labels
on code blocks. Do not rely on color, icons, or a screenshot to convey a required
step. Introduce diagrams with a text explanation, and give images meaningful
alternative text. Prefer small text diagrams for flows that should also work in
a terminal or an offline Markdown viewer; see [Architecture](architecture.md).

Readers can browse Markdown directly in the repository or a local checkout.
The MkDocs navigation defines the documentation site's structure; publishing a
site is a separate deployment task. Check long commands and tables in a narrow
window, and use browser print preview when distributing a printed guide.
Never include credentials, host facts, or sensitive logs in screenshots.

## Validate a change

Run from the repository root with Devenv available. When navigation changes,
regenerate the table of contents first:

```bash
devenv tasks run docs:toc-generator
```

Then check navigation and local links, and review the changed files:

```bash
devenv tasks run docs:check
git diff --check
git diff --stat
```

Expect both checks to exit successfully. Review the generated table of contents
alongside the navigation change. The documentation tests check repository
contracts and portable links; they do not prove that external links are live,
that every command works operationally, or that a new reader understands a guide.
Verify command examples against their current scripts, templates, and tests.
Do not execute installation, activation, or secret changes merely to test prose.

## Test with a first-time reader

Before releasing a new or substantially changed workflow, ask a colleague
unfamiliar with it to follow this walkthrough:

1. Start at the README and find the relevant guide without a direct link from you.
2. Explain the prerequisites, command location, placeholders, and expected outcome.
3. Follow the read-only steps in an appropriate environment. For state-changing
   steps, describe the intended action and stop before execution unless a
   separately authorized test environment and target are available.
4. Identify how to recognize success, where to find errors, and when to stop.
5. Record confusing wording, missing steps, the repository revision, and which
   steps were actually tested in the review or pull request.

Revise the guide and repeat the affected steps. If no independent reader is
available, record that gap; automated checks are not a substitute for this review.

## Keep guides current

Review related guides whenever commands, options, ownership, or recovery behavior
change, and before a release that depends on them. Search for the old command or
path to find cross-references. Remove obsolete instructions or label their exact
compatibility scope and link to the replacement. Record verification results
and unresolved gaps in the change review; use the existing feature tracker for
tracked readiness work rather than creating another completion checklist.
