"""Config flow for the Arcane integration."""

from collections.abc import Mapping
import logging
from typing import Any, override

from homeassistant.config_entries import (
    ConfigEntryState,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryData,
    ConfigSubentryFlow,
    SubentryFlowResult,
)
from homeassistant.const import CONF_API_TOKEN, CONF_URL, CONF_VERIFY_SSL
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
import probatio
from yarl import URL

from .api import (
    ArcaneAuthenticationError,
    ArcaneClient,
    ArcaneConnectionError,
    ArcaneTimeoutError,
)
from .const import CONF_ENVIRONMENT_ID, DOMAIN, SUBENTRY_TYPE_ENVIRONMENT
from .coordinator import ArcaneConfigEntry

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = probatio.Schema(
    {
        probatio.Required(CONF_URL): TextSelector(
            TextSelectorConfig(type=TextSelectorType.URL)
        ),
        probatio.Required(probatio.Secret(CONF_API_TOKEN)): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        ),
        probatio.Optional(CONF_VERIFY_SSL, default=True): BooleanSelector(),
    }
)


async def _validate_input(
    hass: HomeAssistant, data: dict[str, Any]
) -> list[dict[str, Any]]:
    """Validate the user input allows us to connect."""
    client = ArcaneClient(
        api_url=data[CONF_URL],
        api_key=data[CONF_API_TOKEN],
        session=async_get_clientsession(hass=hass, verify_ssl=data[CONF_VERIFY_SSL]),
    )
    try:
        environments = await client.async_get_environments()
    except ArcaneAuthenticationError:
        raise InvalidAuth from None
    except ArcaneConnectionError as err:
        raise CannotConnect from err
    except ArcaneTimeoutError as err:
        raise ArcaneTimeout from err

    _LOGGER.debug("Connected to Arcane API: %s", data[CONF_URL])
    return environments


class ArcaneConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Arcane."""

    VERSION = 1
    MINOR_VERSION = 1

    @classmethod
    @callback
    @override
    def async_get_supported_subentry_types(
        cls, config_entry: ArcaneConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """Return subentries supported by this integration."""
        return {SUBENTRY_TYPE_ENVIRONMENT: EnvironmentSubentryFlowHandler}

    @override
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                environments = await _validate_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except ArcaneTimeout:
                errors["base"] = "timeout_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(str(URL(user_input[CONF_URL]).origin()))
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=user_input[CONF_URL],
                    data=user_input,
                    subentries=[
                        ConfigSubentryData(
                            data={},
                            subentry_type=SUBENTRY_TYPE_ENVIRONMENT,
                            title=environment.get("name")
                            or f"Environment {environment['id']}",
                            unique_id=environment["id"],
                        )
                        for environment in environments
                    ],
                )

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Perform reauth when Arcane API authentication fails."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reauth: ask for new API key and validate."""
        errors: dict[str, str] = {}
        reauth_entry = self._get_reauth_entry()
        if user_input is not None:
            try:
                await _validate_input(
                    self.hass,
                    data={
                        **reauth_entry.data,
                        CONF_API_TOKEN: user_input[CONF_API_TOKEN],
                    },
                )
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except ArcaneTimeout:
                errors["base"] = "timeout_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                return self.async_update_reload_and_abort(
                    reauth_entry,
                    data_updates={CONF_API_TOKEN: user_input[CONF_API_TOKEN]},
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=probatio.Schema(
                {
                    probatio.Required(probatio.Secret(CONF_API_TOKEN)): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    )
                }
            ),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reconfiguration of the integration."""
        errors: dict[str, str] = {}
        reconf_entry = self._get_reconfigure_entry()
        suggested_values = {
            CONF_URL: reconf_entry.data[CONF_URL],
            CONF_API_TOKEN: reconf_entry.data[CONF_API_TOKEN],
            CONF_VERIFY_SSL: reconf_entry.data[CONF_VERIFY_SSL],
        }

        if user_input:
            try:
                await _validate_input(
                    self.hass,
                    data={
                        **reconf_entry.data,
                        **user_input,
                    },
                )
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except ArcaneTimeout:
                errors["base"] = "timeout_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(str(URL(user_input[CONF_URL]).origin()))
                self._abort_if_unique_id_mismatch()
                return self.async_update_reload_and_abort(
                    reconf_entry,
                    data_updates={
                        CONF_URL: user_input[CONF_URL],
                        CONF_API_TOKEN: user_input[CONF_API_TOKEN],
                        CONF_VERIFY_SSL: user_input[CONF_VERIFY_SSL],
                    },
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                data_schema=STEP_USER_DATA_SCHEMA,
                suggested_values=user_input or suggested_values,
            ),
            errors=errors,
        )


class EnvironmentSubentryFlowHandler(ConfigSubentryFlow):
    """Handle a subentry flow for adding an Arcane environment."""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Add an environment as a subentry."""
        entry: ArcaneConfigEntry = self._get_entry()
        if entry.state is not ConfigEntryState.LOADED:
            return self.async_abort(reason="config_entry_not_loaded")

        try:
            environments = await entry.runtime_data.client.async_get_environments()
        except ArcaneConnectionError:
            return self.async_abort(reason="cannot_connect")
        except ArcaneTimeoutError:
            return self.async_abort(reason="timeout_connect")
        except ArcaneAuthenticationError:
            return self.async_abort(reason="invalid_auth")
        except Exception:
            _LOGGER.exception("Unexpected exception")
            return self.async_abort(reason="unknown")

        configured_environment_ids = {
            subentry.unique_id for subentry in entry.subentries.values()
        }
        available_environments = {
            environment["id"]: environment.get("name")
            or f"Environment {environment['id']}"
            for environment in environments
            if environment["id"] not in configured_environment_ids
        }
        if not available_environments:
            return self.async_abort(reason="no_new_environments")

        if user_input is not None:
            environment_id = user_input[CONF_ENVIRONMENT_ID]
            if environment_id not in available_environments:
                return self.async_abort(reason="no_new_environments")
            return self.async_create_entry(
                title=available_environments[environment_id],
                data={},
                unique_id=environment_id,
            )

        return self.async_show_form(
            step_id="user",
            data_schema=probatio.Schema(
                {
                    probatio.Required(CONF_ENVIRONMENT_ID): SelectSelector(
                        SelectSelectorConfig(
                            options=[
                                SelectOptionDict(value=env_id, label=env_name)
                                for env_id, env_name in available_environments.items()
                            ]
                        )
                    )
                }
            ),
        )


class CannotConnect(Exception):
    """Error to indicate we cannot connect."""


class InvalidAuth(Exception):
    """Error to indicate there is invalid auth."""


class ArcaneTimeout(Exception):
    """Error to indicate a timeout occurred."""
