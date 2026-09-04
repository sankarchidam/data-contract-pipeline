# data-contract-pipeline

A minimal, working data ingestion pipeline built to demonstrate one idea end to end:
**a producer and consumer share a data contract, and a change that would break the
consumer cannot be pushed** — not by convention, but because two independent
mechanisms actively block it.

```
 producer ──(Avro, schema id N)──▶ Kafka topic ──▶ consumer
     │                                                  │
     └──────────── register / resolve schema ───────────┘
                          │
                    Apicurio Registry
                (BACKWARD compatibility rule
                 on subject orders.order-created-value)
```

- **Broker:** Apache Kafka, KRaft mode (no ZooKeeper), official `apache/kafka` image.
- **Schema registry:** [Apicurio Registry](https://www.apicur.io/registry/) (Apache 2.0), via its
  built-in Confluent-Schema-Registry-compatible API (`/apis/ccompat/v7`) — so producer/consumer
  use the same well-documented `confluent-kafka` client libraries and `SchemaRegistryClient`.
- **Schema format:** Avro.
- **Data contract:** [`schemas/order-created/schema.avsc`](schemas/order-created/schema.avsc) — the
  `OrderCreated` event.

## Why a breaking change can't get through

There are two independent enforcement points, deliberately redundant:

1. **Registry-level, at runtime.** The subject `orders.order-created-value` has its
   compatibility rule set to `BACKWARD` ([`scripts/register_schema.py`](scripts/register_schema.py),
   run once by the `registry-setup` service). If the producer is rebuilt against an
   incompatible schema, the registry rejects the registration with a 409 and the
   producer process fails at startup — it cannot successfully publish a single message
   with the new shape.

2. **CI-level, before merge.** [`.github/workflows/data-contract.yml`](.github/workflows/data-contract.yml)
   runs on every pull request touching `schemas/**`. It spins up a throwaway registry,
   seeds it with whatever schema is currently on `main`, and calls the registry's
   compatibility *test* endpoint (a dry run — nothing is actually registered) against
   the PR's proposed schema. An incompatible change fails the job — see
   [Set up branch protection](#set-up-branch-protection-required-to-actually-block-merges)
   to turn that failure into a real, unbypassable block.

Compatibility here means **BACKWARD**: a new schema version must be able to read data
written under the previous version. Concretely:

| Change | Compatible? | Why |
|---|---|---|
| Add an optional field with a `default` | ✅ | Old records simply resolve to the default for the new field. |
| Add a required field with **no** default | ❌ | Old records have no value for it and nothing to fall back on. |
| Remove a field that had a default | ✅ | Readers of new data just use the default. |
| Rename a field (no alias) | ❌ | Looks like a required-field-with-no-default change to any reader still on the old name. |

See [`demo/schema-compatible-v2.avsc`](demo/schema-compatible-v2.avsc) and
[`demo/schema-breaking-v2.avsc`](demo/schema-breaking-v2.avsc) for worked examples of the
first two rows.

## Run the pipeline

Requires Docker with Compose v2 (`docker compose ...`, not the old standalone `docker-compose`).

```bash
make up      # builds and starts kafka, the registry, the topic, and both services
make logs    # tail the producer/consumer output
make down    # stop everything
```

You should see the producer emitting `OrderCreated` events every 2 seconds and the
consumer logging each one it reads back out, plus a running total.

Apicurio's web console is at http://localhost:8080 — open **Artifacts** to see the
registered `orders.order-created-value` subject and its compatibility rule.

## See the contract actually block a breaking change

With the registry running (`docker compose up -d schema-registry` is enough — you
don't need the full pipeline for this):

```bash
make demo-compatible   # adds an optional field -> PASS
make demo-breaking     # adds a required field with no default -> FAIL, exit code 1
```

`make demo-breaking` is exactly what the CI job runs against a pull request's schema —
this is the local, instant version of the same check.

## Set up branch protection (required to actually block merges)

A failing CI check is only a red X until a branch protection rule tells GitHub to
refuse the merge over it. `check-compatibility` is the job name from the workflow
above — that's the exact string GitHub needs as the required status check context.

**Via the GitHub UI:** repo → **Settings → Branches → Add branch protection rule** →
branch name pattern `main` → check **Require status checks to pass before merging** →
search for and select `check-compatibility` → also check **Do not allow bypassing the
above settings** if you want it enforced on repo admins too → **Create**.

**Via the API** (what this repo actually has configured — run once, requires admin on
the repo and a `gh` token with the `repo` scope):

```bash
cat > /tmp/branch-protection.json <<'EOF'
{
  "required_status_checks": {
    "strict": true,
    "contexts": ["check-compatibility"]
  },
  "enforce_admins": true,
  "required_pull_request_reviews": null,
  "restrictions": null,
  "required_linear_history": false,
  "allow_force_pushes": false,
  "allow_deletions": false
}
EOF

gh api -X PUT repos/<owner>/<repo>/branches/main/protection \
  -H "Accept: application/vnd.github+json" \
  --input /tmp/branch-protection.json
```

`strict: true` also means the PR branch must be up to date with `main` before the
check counts — so a stale approval on an old, safe schema can't sneak a since-broken
one through.

> **Gotcha worth knowing:** the workflow does *not* filter on `paths: schemas/**`,
> even though the check itself is only ever about schema files. A required status
> check that's path-filtered simply never runs — and never posts a result — on a PR
> that doesn't touch that path, which leaves branch protection waiting forever on a
> check that will never come. A docs-only PR would sit `BLOCKED` with no way to pass.
> Since this check finishes in well under a minute, running it unconditionally on
> every PR is the correct trade-off. Once `main` is protected like this, direct
> `git push origin main` is also rejected outright (`GH006: Protected branch update
> failed`) — every change, schema or not, goes through a PR.

## Proof: this was tested against a real PR, not just asserted

This isn't a theoretical claim — it was verified against this exact repo on GitHub,
with branch protection configured as above. The steps, so you can reproduce it on
your own fork:

```bash
git checkout -b test/breaking-schema-should-be-blocked
cp demo/schema-breaking-v2.avsc schemas/order-created/schema.avsc
git commit -am "test: intentionally break the contract"
git push -u origin test/breaking-schema-should-be-blocked
gh pr create --title "TEST: breaking schema (expected to be blocked)" --base main --fill
```

What actually happened when this was run:

1. `gh pr checks <n> --watch` → `check-compatibility` went `pending` → **`fail` in 31s**.
2. `gh pr view <n> --json mergeable,mergeStateStatus` returned:
   ```json
   {"mergeable": "MERGEABLE", "mergeStateStatus": "BLOCKED"}
   ```
   Note the distinction: git has no conflicts to resolve (`mergeable`), but the branch
   protection rule still refuses the merge (`mergeStateStatus`).
3. Forcing it anyway (`gh pr merge <n> --merge`) was rejected outright by GitHub's own
   API, not just the UI:
   ```
   X Pull request .../#<n> is not mergeable: the base branch policy prohibits the merge.
   ```
4. Cleaned up: `gh pr close <n> --delete-branch`, then restored `schemas/order-created/schema.avsc`
   to its real v1 contents and confirmed `git status` showed no diff against `main`.

That third step is the one that matters: it's not `gh`/the UI declining to *offer* a
merge button — the merge endpoint itself refuses the request. There's no `--force`
path around it short of an admin explicitly disabling the branch protection rule.

## Run the automated tests

```bash
make test
```

Registers the v1 contract with a `BACKWARD` rule against a locally running registry,
then runs [`tests/test_schema_compatibility.py`](tests/test_schema_compatibility.py), which
asserts the compatible and breaking demo schemas resolve the way the table above says
they should.

## Project layout

```
schemas/order-created/schema.avsc   the data contract (v1, currently live)
demo/                                worked compatible/breaking v2 examples, not wired into the pipeline
producer/                            publishes OrderCreated events
consumer/                            reads them back, Avro-deserialized against the registry
scripts/register_schema.py           register a schema + set a subject's compatibility rule
scripts/check_compatibility.py       the CI gate: test a candidate schema, don't register it
.github/workflows/data-contract.yml  runs the gate on every PR touching schemas/**
tests/                                pytest wrapper around the same gate, for local use
```

## Changing the contract for real

1. Edit `schemas/order-created/schema.avsc` on a branch, open a PR.
2. CI runs automatically and comments its result via the `check-compatibility` job status.
3. If it's a breaking change on purpose (e.g. you're intentionally retiring old
   consumers), that's a `FULL`/major-version conversation, not something this
   pipeline will let happen quietly — bump to a new subject or coordinate the
   compatibility mode change explicitly, don't just force through a failing check.
