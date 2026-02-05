"""Config flow for Contact Energy integration."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_URL

from .const import CONF_API_URL, DEFAULT_API_URL, DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_API_URL, default=DEFAULT_API_URL): str,
    }
)


class ContactEnergyConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Contact Energy."""

    VERSION = 1

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            api_url = user_input[CONF_API_URL].rstrip("/")
            
            # Validate the API URL
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        f"{api_url}/health",
                        timeout=aiohttp.ClientTimeout(total=10),
                    ) as response:
                        if response.status != 200:
                            errors["base"] = "cannot_connect"
                        else:
                            # Check if we can fetch accounts
                            async with session.get(
                                f"{api_url}/accounts",
                                timeout=aiohttp.ClientTimeout(total=30),
                            ) as accounts_response:
                                if accounts_response.status != 200:
                                    errors["base"] = "cannot_connect"
                                else:
                                    data = await accounts_response.json()
                                    accounts = data.get("accounts", [])
                                    
                                    if not accounts:
                                        errors["base"] = "no_accounts"
                                    else:
                                        # Success - create the config entry
                                        # Use the first account as unique ID
                                        first_account = accounts[0]
                                        await self.async_set_unique_id(
                                            first_account.get("account_id", api_url)
                                        )
                                        self._abort_if_unique_id_configured()
                                        
                                        return self.async_create_entry(
                                            title="Contact Energy",
                                            data={CONF_API_URL: api_url},
                                        )
            except aiohttp.ClientError as err:
                _LOGGER.error("Error connecting to API: %s", err)
                errors["base"] = "cannot_connect"
            except Exception as err:
                _LOGGER.exception("Unexpected error: %s", err)
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )
