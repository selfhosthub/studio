# Production / Operator Documentation

Documentation for deploying and operating a Studio instance. These docs are written for the person running the install, not the engineers building Studio itself.

## Start here

| Doc | When to read it |
|-----|-----------------|
| [bootstrap.md](bootstrap.md) | First-run bootstrap sequence - what happens on initial boot, where secrets come from, what the wizard collects |
| [deployment-matrix.md](deployment-matrix.md) | Picking a deployment shape (Split, Core, Full) and worker topology - resource requirements and a decision tree |
| [operator-checklist.md](operator-checklist.md) | Pre-launch checklist before pointing real users at your instance |

## Reference

| Doc | Purpose |
|-----|---------|
| [env-vars.md](env-vars.md) | Every environment variable Studio reads, with defaults and whether it is required |
| [docker-images.md](docker-images.md) | Image inventory, what each image runs, how they are built |
| [logging.md](logging.md) | Logging configuration, retention, and shipping to external sinks |

## Topic guides

| Doc | Topic |
|-----|-------|
| [worker-access.md](worker-access.md) | How workers reach the API per shape, the auth model and its accepted risks, and the localhost-only internal-ports migration |
| [super-admin.md](super-admin.md) | Super-admin capabilities, password reset, multi-org operator account |

## Where to go next

- Quick start and high-level orientation: the [project README](../../README.md) at the repo root.
- License and operator responsibilities: [LEGAL.md](../../LEGAL.md).
- Day-to-day management: the `studio-console` CLI installed in the quick-start.
