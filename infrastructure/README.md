# Infrastructure

Empty on purpose. The homelab target for this repo is a Kubernetes cluster (driven with
k9s day to day, provisioned with Terraform), but nothing here is worth deploying yet — the
server runs from `./scripts/run-server.sh` and the CLI needs no runtime at all.

When it is time, the shape is:

```
infrastructure/
  terraform/     cluster-level resources (namespace, secrets, ingress, DNS)
  k8s/           deployment + service for suwalski_investing_server, per-environment values
```

Ground rules for when that day comes, inherited from the sibling repos:

- Pinned image tags, never `latest` and never `pull_policy: always` — a reproducible
  environment beats a silently drifting one.
- Secrets stay out of git and out of image layers; they arrive as cluster secrets.
- The server is stateless (every request carries its own assumptions), so it scales
  horizontally and needs no volumes. Keep it that way as long as possible.
