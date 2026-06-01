# Teenager-care checkpoint v0.10.0

## Current stable release

- Project: Teenager-care
- Runtime path: `/opt/controlbabies`
- Runtime container: `controlbabies`
- Public service name: `Teenager-care`
- Current version: `0.10.0`
- Current commit: `f987606`
- Current tag: `v0.10.0-runtime-pwa-status`
- GitHub repo: `git@github.com:kaciker/Teenager-care.git`

## Validated milestones

- v0.5.2: unified action history
- v0.6.0: action transfer workflow
- v0.7.0: incidents and consequences
- v0.8.0: points, rewards and allowance model
- v0.9.0: role navigation and hidden legacy UI
- v0.9.1: Teenager-care branding and initial PWA shell
- v0.9.2: repaired PWA response endpoints
- v0.9.3: installable PWA PNG icons
- v0.10.0: runtime/PWA status endpoint

## Runtime validation

Expected checks:

- `/api/health` returns `Teenager-care / 0.10.0`
- `/api/runtime-status` returns:
  - `containerized=true`
  - `git_available_in_container=false`
  - manifest URL
  - service worker URL
  - service worker cache `teenager-care-v0.10.0`
  - icons `/icon.svg`, `/icon-192.png`, `/icon-512.png`

## Product model

Canonical model:

- goals
- responsibilities
- actions
- daily_actions
- action_history
- action_transfers
- incidents
- consequences
- point_ledger
- reward_items
- reward_redemptions
- allowance_settings

Legacy tables still exist but are hidden from the main UI:

- tasks
- task_events
- penalties
- rewards
- reward_claims

Do not delete legacy tables yet.

## Current UX state

Role navigation exists:

Parent:

- `/parent`
- `/today`
- `/admin/goals`
- `/incidents`
- `/allowance`

Child:

- `/today`
- `/my/rewards`
- `/my/incidents`

`/child` redirects to `/today`.

## Next recommended milestone

v0.10.1 or v0.11.0:

- review real phone/PWA install experience
- improve visual design
- reduce remaining legacy routes
- prepare cleaner README
- optionally add parent/child smoke tests as scripts
