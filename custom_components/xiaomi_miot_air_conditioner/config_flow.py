import logging

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_TOKEN

from . import check_miot_device
from .const import CONF_RETRIES, DOMAIN, MIOT_DEVICE_OK

_LOGGER = logging.getLogger(__name__)


@config_entries.HANDLERS.register(DOMAIN)
class XiaomiMiotClimateFlow(config_entries.ConfigFlow, domain=DOMAIN):

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLL

    async def async_step_init(self, user_input=None):
        return await self.async_step_user(user_input)

    async def async_step_user(self, user_input=None):
        errors = {}

        # User add integration the first time
        if user_input is None:
            user_input = {}

        # User post device ip and token, try to connect
        else:
            host = user_input.get(CONF_HOST)
            token = user_input.get(CONF_TOKEN)
            ret = await check_miot_device(host, token)
            if ret["code"] == MIOT_DEVICE_OK:
                await self.async_set_unique_id(ret["unique_id"])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=user_input.get(CONF_NAME), data=user_input
                )

            errors["base"] = ret["err"]

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST, default=user_input.get(CONF_HOST, "")): str,
                    vol.Required(
                        CONF_TOKEN, default=user_input.get(CONF_TOKEN, "")
                    ): str,
                    vol.Required(CONF_NAME, default=user_input.get(CONF_NAME, "")): str,
                    # vol.Optional(CONF_SCAN_INTERVAL, default=60): int,
                    vol.Optional(CONF_RETRIES, default=10): int,
                }
            ),
            errors=errors,
        )
