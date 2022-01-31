"""
Support for Xiaomi Air Conditioner Miot Version
"""

import logging
from datetime import timedelta
from functools import partial

from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)
from miio import DeviceException

from .const import (
    ATTR_BUZZER,
    ATTR_CLEAN,
    ATTR_DRYER,
    ATTR_ECO,
    ATTR_LED,
    ATTR_SLEEP_MODE,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

SWITCH_PROPS = {
    ATTR_BUZZER: {
        "name": "buzzer",
        "icon": "mdi:bell-ring",
        "state": "buzzer",
        "func": "set_buzzer",
    },
    ATTR_CLEAN: {
        "name": "clean mode",
        "icon": "mdi:broom",
        "state": "clean",
        "func": "set_clean",
    },
    ATTR_DRYER: {
        "name": "dryer mode",
        "icon": "mdi:water-off",
        "state": "dryer",
        "func": "set_dryer",
    },
    ATTR_ECO: {
        "name": "eco mode",
        "icon": "mdi:flash",
        "state": "eco",
        "func": "set_eco",
    },
    ATTR_LED: {
        "name": "LED enabled",
        "icon": "mdi:lightbulb",
        "state": "led",
        "func": "set_led",
    },
    ATTR_SLEEP_MODE: {
        "name": "sleep mode",
        "icon": "mdi:power-sleep",
        "state": "sleep_mode",
        "func": "set_sleep_mode",
    },
}

CONF_MODEL = "model"

DEFAULT_RETRIES = 20

DEFAULT_NAME = "Xiaomi Mi Smart Air Conditioner A"


SUCCESS = ["ok"]

SCAN_INTERVAL = timedelta(seconds=60)


async def async_setup_entry(hass, config_entry, async_add_entities):
    """ Setup one switch entity with config entry forwarded. """
    entry_id = config_entry.entry_id
    config = hass.data[DOMAIN][entry_id]
    device = config["miot_device"]
    name = config["name"]
    retries = config["retries"]
    uniq_id = config["unique_id"]
    device_info = config["device_info"]

    config["switch_data"] = {"retry": 0, "retries": retries}

    async def async_update_data():
        data = hass.data[DOMAIN][entry_id]["switch_data"]
        data["retry"] = 0
        _LOGGER.debug("Updating, retry: " + str(data["retry"]))
        while data["retry"] < data["retries"]:
            try:
                state = await hass.async_add_executor_job(device.status)
                _LOGGER.debug("Got new state: %s", state)
                data["retry"] = 0
                return state

            except DeviceException as ex:
                data["retry"] = data["retry"] + 1
                _LOGGER.info(
                    "Got exception while fetching the state: %s , _retry=%s",
                    ex,
                    data["retry"],
                )
                if data["retry"] >= data["retries"]:
                    raise UpdateFailed(
                        f"Error communicating with air conditioner: {ex}"
                    )

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="xiaomi_miot_air_conditioner_switch",
        update_method=async_update_data,
        update_interval=SCAN_INTERVAL,
    )

    await coordinator.async_refresh()

    entities = [
        XiaomiSwitchEntity(coordinator, name, hass_key, device, retries, uniq_id, device_info)
        for hass_key in SWITCH_PROPS
    ]

    async_add_entities(entities, update_before_add=True)


class AirConditionerMiotException(DeviceException):
    pass


class XiaomiSwitchEntity(SwitchEntity, CoordinatorEntity):
    """Representation of Xiaomi Air Conditioner Miot device."""

    # Device initialization and registration

    def __init__(self, coordinator, name, hass_key, device, retries, unique_id, device_info):
        """Initialize the climate entity."""
        super().__init__(coordinator)
        self._name = "%s %s" % (name, SWITCH_PROPS[hass_key]["name"])
        self._icon = SWITCH_PROPS[hass_key]["icon"]
        self._device = device
        self._retry = 0
        self._retries = retries
        self._hass_key = hass_key
        self._unique_id = f"{unique_id}-{hass_key}"
        self._identifier = {(DOMAIN, unique_id)}
        self._device_info = device_info
        self._state_name = SWITCH_PROPS[hass_key]["state"]
        self._func_name = SWITCH_PROPS[hass_key]["func"]

    # Implement abstract `Entity` class

    @property
    def name(self):
        """Return the name of the device if any."""
        return self._name

    @property
    def unique_id(self):
        """Return an unique ID."""
        return self._unique_id

    @property
    def device_info(self):
        return {
            "name": self._device_info.model,
            "manufacturer": "Xiaomi",
            "model": self._device_info.model,
            "sw_version": self._device_info.firmware_version,
            "hw_version": self._device_info.hardware_version,
            "identifiers": self._identifier,
        }

    @property
    def icon(self) -> str:
        return self._icon

    @property
    def is_on(self):
        state = getattr(self.coordinator.data, self._state_name)
        if self._state_name == SWITCH_PROPS[ATTR_CLEAN]["state"]:
            return state.cleaning
        return state

    async def _try_command(self, mask_error, func, *args, **kwargs):
        """Call a miio device command handling error messages."""
        from miio import DeviceException

        try:
            result = await self.hass.async_add_job(partial(func, *args, **kwargs))

            _LOGGER.debug("Response received from miio device: %s", result)

            return result == SUCCESS
        except DeviceException as exc:
            _LOGGER.error(mask_error, exc)
            self._available = False
            return False

    async def async_turn_on(self, **kwargs):
        func = getattr(self._device, self._func_name)
        await self._try_command(
            "Turning on %s of the device failed." % self._state_name,
            func,
            True,
        )
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs):
        func = getattr(self._device, self._func_name)
        await self._try_command(
            "Turning off %s of the device failed." % self._state_name,
            func,
            False,
        )
        await self.coordinator.async_request_refresh()
