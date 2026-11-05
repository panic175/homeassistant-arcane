"""Constants for the Arcane integration."""

from datetime import timedelta

DOMAIN = "arcane"
DEFAULT_NAME = "Arcane"

API_MAX_RETRIES = 3

SUBENTRY_TYPE_ENVIRONMENT = "environment"
CONF_ENVIRONMENT_ID = "environment_id"

# Event types known to Arcane (backend/internal/event/model.go). Events with
# unknown types are skipped, so Arcane can add types without breaking us.
EVENT_TYPES: tuple[str, ...] = (
    "container.create",
    "container.delete",
    "container.deploy",
    "container.die",
    "container.error",
    "container.kill",
    "container.oom",
    "container.pause",
    "container.rename",
    "container.restart",
    "container.scan",
    "container.start",
    "container.stop",
    "container.unhealthy",
    "container.unpause",
    "container.update",
    "enrollment_token.create",
    "enrollment_token.delete",
    "enrollment_token.reveal",
    "environment.api_key.regenerated",
    "environment.connect",
    "environment.create",
    "environment.delete",
    "environment.disconnect",
    "environment.mtls.ca_generated",
    "environment.mtls.cert_issued",
    "environment.mtls.download",
    "environment.mtls.enroll",
    "environment.tunnel.restarted",
    "environment.update",
    "federated.exchange",
    "git.repository.create",
    "git.repository.delete",
    "git.repository.error",
    "git.repository.test",
    "git.repository.update",
    "git.sync.create",
    "git.sync.delete",
    "git.sync.error",
    "git.sync.run",
    "image.commit",
    "image.delete",
    "image.error",
    "image.import",
    "image.load",
    "image.pull",
    "image.prune",
    "image.scan",
    "image.tag",
    "image.untag",
    "image.vulnerability_scan",
    "network.prune",
    "project.create",
    "project.delete",
    "project.deploy",
    "project.error",
    "project.start",
    "project.stop",
    "project.update",
    "volume.prune",
)

DEFAULT_SCAN_INTERVAL = timedelta(seconds=60)
DEFAULT_USAGE_SCAN_INTERVAL = timedelta(minutes=30)
DEFAULT_VERSION_SCAN_INTERVAL = timedelta(hours=6)
