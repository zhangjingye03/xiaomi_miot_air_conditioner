"""
Support for Xiaomi Air Conditioner Miot Version
"""

import logging
from datetime import timedelta

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_TOKEN
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import PlatformNotReady
from homeassistant.helpers.entity_component import EntityComponent
from miio import Device
from miio.airconditioner_miot import AirConditionerMiot

from .const import (
    CONF_RETRIES,
    DOMAIN,
    MIOT_DEVICE_OFFLINE,
    MIOT_DEVICE_OK,
    MIOT_UNSUPPORTED_DEVICE,
    MODELS_SUPPORTED,
)

_LOGGER = logging.getLogger(__name__)


SUPPORTED_DOMAINS = [
    "climate",
    "switch",
]

SCAN_INTERVAL = timedelta(seconds=60)


async def check_miot_device(host, token):
    ret = {}
    try:
        miio_device = Device(host, token)
        device_info = miio_device.info()
        model = device_info.model
        unique_id = f"{model}-{device_info.mac_address}"
        _LOGGER.info(
            "%s %s %s detected",
            model,
            device_info.firmware_version,
            device_info.hardware_version,
        )
    except Exception:
        ret["code"] = MIOT_DEVICE_OFFLINE
        ret["err"] = "platform_not_ready"
        return ret

    if model not in MODELS_SUPPORTED:
        ret["code"] = MIOT_UNSUPPORTED_DEVICE
        ret["err"] = "unsupported_device"
        _LOGGER.error("Unsupported device %s found!" % model)
        return ret

    ret["device_info"] = device_info
    ret["model"] = model
    ret["unique_id"] = unique_id
    ret["code"] = MIOT_DEVICE_OK
    return ret


async def async_setup(hass, hass_config):
    hass.data.setdefault(DOMAIN, {})
    config = hass_config.get(DOMAIN) or {}
    hass.data[DOMAIN]["config"] = config

    component = EntityComponent(_LOGGER, DOMAIN, hass, SCAN_INTERVAL)
    await component.async_setup(config)

    return True


async def async_setup_entry(
    hass: HomeAssistant, config_entry: config_entries.ConfigEntry
):
    """ Parse device config from config flow. """

    entry_id = config_entry.entry_id
    unique_id = config_entry.unique_id

    config = dict(config_entry.data)
    host = config.get(CONF_HOST)
    token = config.get(CONF_TOKEN)
    name = config.get(CONF_NAME)
    retries = config.get(CONF_RETRIES)

    _LOGGER.debug(
        "Xiaomi Miot air conditioner config entry: %s",
        {
            "host": host,
            "token": token,
            "name": name,
        },
    )

    ret = await check_miot_device(host, token)
    if ret["code"] != MIOT_DEVICE_OK:
        if ret["code"] == MIOT_DEVICE_OFFLINE:
            raise PlatformNotReady
        else:
            _LOGGER.error(ret["err"])
        return False

    hass.data.setdefault(DOMAIN, {})

    info = {
        "miot_device": AirConditionerMiot(host, token),
        "host": host,
        "token": token,
        "name": name,
        "retries": retries,
        "unique_id": unique_id,
        "device_info": ret["device_info"],
    }

    hass.data[DOMAIN][entry_id] = info

    # Forward config entry to all platforms
    # `async_setup_entry` would be called in <platform>.py
    for sd in SUPPORTED_DOMAINS:
        hass.async_create_task(
            hass.config_entries.async_forward_entry_setup(config_entry, sd)
        )

    return True
