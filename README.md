# Arcane for Home Assistant

[![CI](https://github.com/panic175/homeassistant-arcane/actions/workflows/ci.yml/badge.svg)](https://github.com/panic175/homeassistant-arcane/actions/workflows/ci.yml)
[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz/docs/use/custom/default-repo/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Custom integration that connects [Arcane](https://getarcane.app) to Home
Assistant. It follows the architecture and entity set of the official
Portainer integration: one config entry per Arcane instance, one subentry per
Arcane environment, and devices for environments, projects and containers.

## Features

| Platform | Contents |
|---|---|
| Sensor | Container state/status/image, CPU %, memory usage/%/limit, start time · Environment: Docker version, kernel, OS, total memory, CPU cores, container/image/volume counts, image disk usage · Project: status, service count, running services |
| Binary sensor | Container running · Environment connected |
| Switch | Start/stop a container · Deploy/stop a project |
| Button | Restart/pause/resume/recreate a container · Update a project · Prune images/volumes/networks of an environment |
| Update | Image update per container (installs via Arcane) · Arcane manager version (report-only) |
| Event | Arcane event log per environment (container, project, image, git and environment events) |
| Services | `arcane.prune_images`, `arcane.prune_volumes`, `arcane.prune_networks`, `arcane.recreate_container` |

Data is polled every 60 seconds; the Arcane version is checked every 6 hours.

## Installation

### HACS (custom repository)

1. HACS → Integrations → ⋮ → **Custom repositories**
2. Repository: `https://github.com/panic175/homeassistant-arcane`, category **Integration**
3. Install **Arcane** and restart Home Assistant.

### Manual

Copy `custom_components/arcane` into the `custom_components` directory of your
Home Assistant configuration and restart Home Assistant.

## Configuration

1. In Arcane open **Settings → API Keys → Add API Key** and copy the key.
2. In Home Assistant: **Settings → Devices & services → Add integration → Arcane**
3. Enter the Arcane URL (for example `http://192.168.3.4:3552`) and the API key.

All environments found on the instance are added automatically as subentries;
additional environments can be added later via the integration's *Add
environment* action. Reauth and reconfigure are supported.

## Entity structure

- **Arcane server** (manager) device: version update entity
- **Environment** device (one per subentry): connectivity, host sensors, prune buttons
- **Project** device (child of an environment): status sensors, deploy/stop switch, update button
- **Container** device (child of its project, otherwise of the environment): state, resource usage, control switch, lifecycle buttons, image update

## Services

| Service | Target | Description |
|---|---|---|
| `arcane.prune_images` | Environment device | Remove unused images (optional: only dangling) |
| `arcane.prune_volumes` | Environment device | Remove unused volumes |
| `arcane.prune_networks` | Environment device | Remove unused networks |
| `arcane.recreate_container` | Container device | Pull the latest image and recreate the container |

## Events

Each environment exposes an event entity fed from Arcane's event log
(`container.*`, `project.*`, `image.*`, `git.*`, `environment.*`, ...).
Entities start with a baseline: events that happened before Home Assistant
picked up the integration are not replayed. Events unknown to this integration
are skipped.

## Known limitations

- **No container disk usage / restart count / OOM sensor**: the Arcane API does not expose Docker's `system df` per container, restart counts or OOM-kill flags.
- **No build cache prune button/service**: Arcane's `system/prune` requires prune modes this integration does not guess; use the Arcane UI.
- **Update availability depends on Arcane's own image update checks** (Arcane persists `updateInfo`); this integration does not trigger extra registry checks.
- **The Arcane manager update entity is report-only**: installing an update would recreate the Arcane manager (and its ingress) from inside Home Assistant. Update the manager via CLI/Compose instead.
- **No raw Docker event stream**: events come from Arcane's polled event log, not from the Docker daemon socket.
- Event log fetching is best-effort; if it fails, sensors keep working and no events fire.

## Development

```bash
pip install ruff pytest aiohttp
ruff check .
ruff format --check .
pytest tests/ -v
```

CI runs Ruff, [hassfest](https://github.com/home-assistant/actions), HACS
validation and the tests on every push.

## Tested versions

| Component | Version |
|---|---|
| Arcane | 2.17.3 (API) |
| Home Assistant | >= 2026.9 (probatio, config subentries) |

## License

[MIT](LICENSE)
