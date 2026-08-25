# Onboarding limitations (V2)

Read this when dedicated-infra is blocked or a team hits a gap. Coordinate with the Rehor platform team — do not invent a workaround.

## Dedicated proxy deployment

`deploy-template.yaml.j2` hardcodes ~15 service references to shared infrastructure: `devbot-proxy` (ports 3128, 8443, 8444, 8446, 9090), `devbot-memory-server` (port 8080), and `devbot-secrets`. These are string literals in the Jinja2 template, not OpenShift template parameters. A team needing separate credentials (different Jira/GitHub/GitLab accounts) requires a dedicated proxy, which means either:

- Parameterizing the deploy template to accept proxy/memory-server/secret names
- Creating a separate deploy template variant for dedicated-proxy deployments

The NetworkPolicy also hardcodes pod label selectors for `devbot-proxy` and `memory-server`.

## Arbitrary GitLab hosts

`generate_instance.py` hardcodes `gitlab.cee.redhat.com` for GitLab fork URL construction. Teams using a different GitLab instance (e.g., `gitlab.com`) would get wrong fork URLs in `project-repos.json`, causing git-clone failures at runtime.

## Separate namespace / app-interface service

The `separate` SaaS pattern requires `service_tree` and supports `app_ref`, `namespace_ref`, `pipelines_ref` overrides. However, it cannot bootstrap the service tree itself. For a team that needs their own namespace on a different cluster, the following must be created manually (with app-sre):

- A new `app.yml` in app-interface
- A new namespace YAML under the team's service tree
- A new pipeline provider definition

**`namespace_ref` fallback risk**: if `namespace_ref` is not explicitly provided, the generator falls back to discovering it from the shared `deploy.yml`. For a team on a different cluster/namespace, this fallback gives the wrong namespace. Always require `namespace_ref` for separate pattern teams on their own namespace — do not rely on the fallback.

## Arbitrary Konflux clusters

`generate_konflux.py` discovers cluster FQDN suffixes at runtime from the `config/` directory in the cloned `konflux-release-data` repo. A cluster that doesn't have an existing `config/<cluster>.*` directory will raise a `ValueError` with the list of available clusters.
