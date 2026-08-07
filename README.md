# foundry-cli

An **agent-native** command-line interface for Palantir Foundry.

> **Derivative work.** `foundry-cli` began as a fork of the original CLI by [@anjor](https://github.com/anjor). It has since been detached from the fork network and is maintained independently, with its own release line and distribution name. The console command is `pfoundry`. MIT-licensed, same as the original — see [LICENSE](LICENSE), which carries both copyrights.

`foundry-cli` wraps the official [`foundry-platform-sdk`](https://github.com/palantir/foundry-platform-python) and adds three things:

1. **A stable machine contract.** Every command can emit one JSON envelope (`foundry-agent-v1`) with `--agent`, so an autonomous caller never has to parse tables or scrape text.
2. **A read-only dependency and change-impact gate.** Before you touch a Foundry resource, `pfoundry dependency` tells you what breaks — with explicit coverage gaps, provenance, and a CI exit code.
3. **A drop-in skill bundle.** `skills/foundry-cli/` teaches any coding agent (Claude, Codex, others) how to drive the CLI safely.

**Why this exists.** The JSON contract, the change-impact gate, and the skill bundle let an autonomous agent operate Foundry safely and cheaply, with no human in the loop. The full interactive surface — Rich tables, the shell, multi-profile switching, and the commands across datasets, SQL, ontology, orchestration, filesystem, and admin — works the same way.

---

## Install

### One-paste install — hand this to your agent

Copy the block below into Claude Code, Codex, or any coding agent. It installs, authenticates, and verifies `foundry` for you:

```
Install the foundry CLI (Palantir Foundry) for me, end to end:
1. Install from git: `uv pip install "git+https://github.com/zaycruz/foundry-cli"` (fall back to `pip install "git+https://github.com/zaycruz/foundry-cli"` if uv is missing).
2. Confirm it works: run `pfoundry --help` and show me the command groups.
3. Set up auth: ask me for my Foundry host and API token, then export FOUNDRY_HOST and FOUNDRY_TOKEN, or run `pfoundry configure configure`. I may have more than one Foundry environment — support named profiles.
4. Verify the connection: run `pfoundry verify`.
5. For automation, note that every command accepts `--agent` for a stable JSON envelope; run `pfoundry --agent agent-manifest` to show the machine-readable command surface.
```

### Install it yourself

Install the published package from PyPI. The command is `foundry`.

```bash
uv tool install foundry-cli
```

To install the current source directly from Git, or to clone for development:

```bash
uv tool install "git+https://github.com/zaycruz/foundry-cli"
```

For an editable development checkout:

```bash
git clone https://github.com/zaycruz/foundry-cli.git
cd foundry-cli
uv sync
uv run pfoundry --help
```

---

## Authenticate

```bash
# Interactive setup (token or OAuth2). Credentials go in the system keyring, never plain text.
pfoundry configure configure

# Or use environment variables (CI / automation):
export FOUNDRY_TOKEN="your-api-token"
export FOUNDRY_HOST="foundry.company.com"
# Used only when no --profile is given and no profile is configured,
# so an exported variable never overrides a stored profile.

# Confirm it works:
pfoundry verify
```

OAuth2 uses `FOUNDRY_CLIENT_ID` and `FOUNDRY_CLIENT_SECRET` instead of `FOUNDRY_TOKEN`.

---

## Capabilities

Nine capability areas and two global flags:

| Area | What you get |
|------|--------------|
| Machine output | `--agent` on agent-aware commands → one `foundry-agent-v1` JSON envelope |
| Non-interactive mode | `--non-interactive` — no prompts, no envelope switch |
| Change impact | `pfoundry dependency` — 6 target types, evidence graph, CI exit codes |
| Grammar discovery | `pfoundry agent-manifest`, `pfoundry capabilities` |
| Resource search | `pfoundry search` — title or path-scoped paginated discovery |
| Lineage | `pfoundry lineage graph` |
| Proposals | `pfoundry proposal` — 9 subcommands |
| Namespaces | `pfoundry namespace list` |
| Notepads | `pfoundry notepad list`, `pfoundry notepad get` |
| Agent skill bundle | `skills/foundry-cli/` — workflows + 17 references |
| Tracing | optional Langfuse |
| Leaf commands | 236 |

### Change-impact gate

`pfoundry dependency` resolves a Foundry target, walks a bounded dependency graph, and reports what breaks — with explicit coverage gaps, provenance, and a CI exit code. It never mutates Foundry. Six targets: `resource`, `object-type`, `property`, `link-type`, `action-type`, `query-type`. [Details below](#dependency-and-change-impact-analysis).

### Machine-readable grammar

`pfoundry agent-manifest` emits every registered command as deterministic JSON, so an agent discovers the surface without parsing `--help` text. `pfoundry capabilities` is a parity scorecard against Palantir's published MCP tool catalog, not a list of this CLI's commands. [Details below](#agent-interface).

### Proposals

`pfoundry proposal` drives the full review lifecycle for code pull requests and Ontology Global Proposals: `create`, `list`, `get`, `comment`, `approve`, `request-changes`, `merge`, `accept`, `close`.

### Lineage and discovery

- `pfoundry lineage graph <rid>` — build a bounded graph from native filesystem relationships.
- `pfoundry search <text>` — search by title, or add `--path-prefix` for bounded paginated resource discovery.
- `pfoundry namespace list` — list Compass namespaces via the verified internal hierarchy API.
- `pfoundry notepad list --path-prefix <path>` — enumerate notepads without guessing an instance root.
- `pfoundry notepad get <rid>` — read a notepad's latest body and its embedded resource references.

### Agent skill bundle

`skills/foundry-cli/` is a drop-in, model-agnostic bundle that teaches any coding agent to drive `foundry` safely — including the mandatory change-impact gate before any Foundry mutation. [Details below](#skill-bundle-for-coding-agents).

---

## Agent interface

Add the global `--agent` flag to any command. The command then returns a single stable JSON envelope on stdout instead of a table:

```bash
pfoundry --agent agent-manifest
pfoundry --agent resource list --folder-rid ri.compass.main.folder.0
pfoundry --agent dataset files list ri.foundry.main.dataset.abc123 --page-size 50
```

Every envelope has the same shape:

```json
{
  "schema_version": "foundry-agent-v1",
  "data": {},
  "meta": {},
  "warnings": [],
  "errors": [],
  "pagination": null,
  "artifacts": []
}
```

**Contract guarantees:**

- **Exactly one document.** `json.loads(stdout)` succeeds for every command. Status messages that a human sees as separate lines are collected into `meta.messages` (each with a `level`) rather than emitted as extra JSON documents. Human-readable output, progress spinners and Rich tables go to **stderr** under `--agent`, so stdout carries the envelope and nothing else. A contract test invokes every registered command under `--agent` and enforces this.
- **Stable schema.** `schema_version` is `foundry-agent-v1`. Fields do not move between commands. Additions are additive.
- **Credential redaction.** Any field whose name contains `token`, `secret`, `password`, `private_key`, or `authorization` is replaced with `[REDACTED]`. Pagination cursors (`page_token`) are kept, because a caller needs them to resume.
- **Resumable pagination.** When a result is paged, `pagination` carries the next cursor.
- **Non-interactive by default.** `--agent` forbids prompts. A mutation that would normally ask for confirmation fails with a policy error naming the exact flag to pass — `--yes`, `--confirm` or `--force`, depending on the command — and that flag name is checked against the command's real options by a test. The refusal always produces an envelope, but the **exit code is not yet uniform**: it is `1` where the command handles the refusal itself and `2` where it propagates. Branch on the envelope's `errors`, not on the exit code. Use `--non-interactive` to get the same no-prompt behavior without switching output to the envelope.

Two shapes are worth knowing:

- If a command reports more than one result in a single run, `data` is a list and `meta.results` holds each result's metadata, positionally aligned with `data`.
- A few commands still report errors through a plain console rather than the structured path. Their text is wrapped in one envelope with `meta.result_type` set to `"unstructured"` and the message under `errors`. That is a known gap, flagged honestly rather than dressed up as a structured result.

Start every agent session with `pfoundry --agent agent-manifest` to discover the available command surface: it emits every registered command with its path, arguments and flags.

`pfoundry --agent capabilities` answers a different question. It is a parity scorecard against [Palantir's published MCP tool catalog](https://www.palantir.com/docs/foundry/palantir-mcp/available-tools/): each of the ~73 MCP tools is marked **implemented** (a real CLI command exists), **planned** (a genuine gap), **blocked** (the SDK cannot do it), or **unsupported** (out of scope for a Foundry CLI — documentation retrieval, SDK codegen, dev-console). The implemented-vs-planned split is derived from the live command surface, so it can never disagree with `agent-manifest` about what ships; `blocked` and `unsupported` are classified explicitly (an SDK limit, or out of scope for a CLI) and stay authoritative. On foundry-platform-sdk 1.95.0 that is 20 implemented, 28 planned, 2 blocked, 23 unsupported — the CLI already covers more Foundry operations than the MCP exposes. It does **not** list this CLI's commands; `agent-manifest` does.

---

## Dependency and change-impact analysis

`pfoundry dependency` runs a **read-only, evidence-backed** assessment of one Foundry target. One invocation resolves the target, discovers a bounded dependency graph, writes the complete graph as a JSON artifact, and renders the view you asked for. It never mutates Foundry.

```bash
# What depends on this dataset? Retain the full evidence graph.
pfoundry dependency resource ri.foundry.main.dataset.abc123 \
  --change "rename a column" \
  --change-type rename \
  --output-mode agent \
  --graph-output ./before.json
```

**Targets:** `resource`, `object-type`, `property`, `link-type`, `action-type`, `query-type`.

**Three output modes:**

| Mode | Use for | Result |
|------|---------|--------|
| `graph` | Full programmatic detail | The complete result (nodes, edges, paths, evidence, provenance) |
| `agent` | Compact machine reasoning | Status, ranked impacts, blast-radius + release-risk scores, action/query contracts, coverage, `must_verify_before_merge`, `should_verify_before_deploy` |
| `ci`    | Pipeline gating | A one-line payload and an exit code |

**CI exit codes:** `0` clean, `2` needs verification, `1` fatal.

**Honest about coverage.** Outcomes are `covered`, `covered-empty`, `partial`, `inaccessible`, `unsupported`, `unresolved`, or `budget-exhausted`. Anything other than covered is reported as a **gap** — never silently treated as "no impact." Each result carries provenance: SDK method, capability IDs, branch/preview resolution, timestamps, and known limitations.

**Merge gate (baseline → change → compare):**

```bash
# 1. Capture a baseline before the change (retained artifact).
pfoundry dependency property ri.ontology.main.ontology.example Employee email \
  --change "email string -> struct" --change-type type-change \
  --direction downstream --output-mode agent \
  --graph-output ./employee-email-before.json

# 2. After the change, compare against the baseline and gate CI.
pfoundry dependency property ri.ontology.main.ontology.example Employee email \
  --change "email string -> struct" --change-type type-change \
  --direction downstream \
  --compare-artifact ./employee-email-before.json \
  --output-mode ci --graph-output ./employee-email-after.json
```

Artifacts are written atomically with mode `0600`, to `--graph-output` or to `${XDG_STATE_HOME:-~/.local/state}/foundry/dependency/<analysis-id>.json`. Bounds (`--depth`, `--max-nodes`, `--time-budget-seconds`, …) are configurable with hard ceilings.

Full command reference: [`skills/foundry-cli/reference/dependency-commands.md`](skills/foundry-cli/reference/dependency-commands.md). Full operating sequence: [`skills/foundry-cli/workflows/change-impact-assessment.md`](skills/foundry-cli/workflows/change-impact-assessment.md).

---

## Skill bundle for coding agents

`skills/foundry-cli/` is the single, model-agnostic source of truth for driving `foundry` from an agent. Point your agent client at it; do not create per-provider copies.

- **[`SKILL.md`](skills/foundry-cli/SKILL.md)** — overview, critical concepts, when to load which reference.
- **[`AGENTS.md`](AGENTS.md)** — repository rules, including the **mandatory change-impact gate**: assess with `pfoundry dependency` before proposing or applying any Foundry change, and do not merge while status is `needs-verification`.
- **`workflows/`** — [change-impact-assessment](skills/foundry-cli/workflows/change-impact-assessment.md), [data-pipeline](skills/foundry-cli/workflows/data-pipeline.md), [data-analysis](skills/foundry-cli/workflows/data-analysis.md), [permission-management](skills/foundry-cli/workflows/permission-management.md).
- **`reference/`** — 17 per-module command references (datasets, SQL, ontology, orchestration, filesystem, admin, connectivity, mediasets, streams, functions, AIP agents, models, language models, dependency).

---

## Human use

For interactive work, every command supports `--format table|json|csv`, `--output <file>`, and `--profile <name>`.

```bash
pfoundry sql execute "SELECT * FROM my_table LIMIT 10"
pfoundry dataset get ri.foundry.main.dataset.abc123
pfoundry ontology list
pfoundry orchestration builds search
pfoundry folder list ri.compass.main.folder.0        # root folder
pfoundry resource-role grant <resource-rid> --principal-id <user-id> --principal-type User --role viewer
pfoundry shell                                         # REPL with tab completion + history
pfoundry completion install                            # bash / zsh / fish completion
```

Full command list: `pfoundry --help`, or per command `pfoundry <command> --help`.

---

## Configuration

Manage multiple Foundry environments as named **profiles** — switch the default, or pick one per command:

```bash
pfoundry configure configure          # add or edit a profile (interactive)
pfoundry configure list               # list profiles
pfoundry configure use <name>         # switch the default profile
pfoundry configure delete <name>      # remove a profile
pfoundry <command> --profile <name>   # use a specific profile for one command
```

- **Profiles:** `~/.config/foundry/profiles.json`
- **Credentials:** encrypted in the system keyring
- **Shell history:** `~/.config/foundry/repl_history`

### Optional Langfuse tracing

Install the extra and set all three variables to trace command paths, redacted arguments, duration, and exit codes. Tracing is a no-op when the variables are absent, and a tracing failure never changes the command result.

```bash
uv pip install "foundry-cli[langfuse] @ git+https://github.com/zaycruz/foundry-cli"
export LANGFUSE_HOST="https://cloud.langfuse.com"
export LANGFUSE_PUBLIC_KEY="pk-lf-..."
export LANGFUSE_SECRET_KEY="sk-lf-..."
```

---

## Development

Requires Python 3.10+ and [uv](https://github.com/astral-sh/uv).

```bash
uv sync
uv run pre-commit install
uv run pytest
uv run ruff check src/ && uv run ruff format src/
uv run mypy src/
```

**Architecture** is layered: CLI (Typer) → command layer (validation) → service layer (`foundry-platform-sdk`) → auth (keyring). Agent output and dependency analysis live in `src/foundry_cli/utils/` and `src/foundry_cli/services/`. See [`CONCEPTS.md`](CONCEPTS.md).

When extending the SDK surface, be exact about what Foundry exposes and preserve explicit gaps instead of guessing — see [`AGENTS.md`](AGENTS.md).

## License

MIT. See [LICENSE](LICENSE), which retains the original copyright of [@anjor](https://github.com/anjor) alongside the current maintainer's.

Derived from the original CLI by [@anjor](https://github.com/anjor). Built on the official [Palantir Foundry Platform Python SDK](https://github.com/palantir/foundry-platform-python).
