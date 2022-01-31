"""
Support for Xiaomi Air Conditioner Miot Version
"""

import asyncio
import logging
from enum import Enum
from functools import partial

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import DOMAIN as CLIMATE_DOMAIN
from homeassistant.components.climate.const import (
    HVAC_MODE_COOL,
    HVAC_MODE_DRY,
    HVAC_MODE_FAN_ONLY,
    HVAC_MODE_HEAT,
    HVAC_MODE_OFF,
    SUPPORT_AUX_HEAT,
    SUPPORT_FAN_MODE,
    SUPPORT_SWING_MODE,
    SUPPORT_TARGET_TEMPERATURE,
    SWING_OFF,
    SWING_VERTICAL,
)
from homeassistant.const import ATTR_ENTITY_ID, TEMP_CELSIUS
from miio import DeviceException
from miio.airconditioner_miot import FanSpeed, OperationMode

from .const import (
    ATTR_CURRENT_TEMPERATURE,
    ATTR_FAN_SPEED,
    ATTR_FAN_SPEED_PERCENT,
    ATTR_HEATER,
    ATTR_MODE,
    ATTR_TARGET_TEMPERATURE,
    ATTR_TEMPERATURE,
    ATTR_TIMER_MINUTES,
    ATTR_VERTICAL_SWING,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


# Key-Value reference for miio -> hass
# key: key in state_attr (for hass use)
# value: key from miio
AVAILABLE_ATTRIBUTES_CLIMATE = {
    # ATTR_BUZZER: "buzzer",
    # ATTR_CLEAN: "clean",
    ATTR_CURRENT_TEMPERATURE: "temperature",
    # ATTR_DRYER: "dryer",
    # ATTR_ECO: "eco",
    ATTR_FAN_SPEED: "fan_speed",
    ATTR_FAN_SPEED_PERCENT: "fan_speed_percent",
    ATTR_HEATER: "heater",
    # ATTR_LED: "led",
    ATTR_MODE: "mode",
    # ATTR_RUNNING_DURATION: "total_running_duration",
    # ATTR_SLEEP_MODE: "sleep_mode",
    ATTR_TARGET_TEMPERATURE: "target_temperature",
    # hass use `temperature` as target temperature
    ATTR_TEMPERATURE: "target_temperature",
    # ATTR_TIMER: "timer",
    ATTR_VERTICAL_SWING: "vertical_swing",
}

CONF_MODEL = "model"

DATA_KEY = "climate.xiaomi_air_conditioner_miot"

DEFAULT_MIN_TEMP = 16
DEFAULT_MAX_TEMP = 31
DEFAULT_TEMP_STEP = 0.5
DEFAULT_RETRIES = 20

DEFAULT_NAME = "Xiaomi Mi Smart Air Conditioner A"


# SERVICE_SET_BUZZER_ON = "xiaomi_miio_set_buzzer_on"
# SERVICE_SET_BUZZER_OFF = "xiaomi_miio_set_buzzer_off"
# SERVICE_SET_SLEEP_MODE_ON = "xiaomi_miio_set_sleep_mode_on"
# SERVICE_SET_SLEEP_MODE_OFF = "xiaomi_miio_set_sleep_mode_off"
# SERVICE_SET_LED_ON = "xiaomi_miio_set_led_on"
# SERVICE_SET_LED_OFF = "xiaomi_miio_set_led_off"
# SERVICE_SET_ECO_ON = "xiaomi_miio_set_eco_on"
# SERVICE_SET_ECO_OFF = "xiaomi_miio_set_eco_off"
# SERVICE_SET_DRYER_ON = "xiaomi_miio_set_dryer_on"
# SERVICE_SET_DRYER_OFF = "xiaomi_miio_set_dryer_off"
# SERVICE_BEGIN_CLEAN = "xiaomi_miio_begin_clean"
# SERVICE_ABORT_CLEAN = "xiaomi_miio_abort_clean"
SERVICE_SET_FAN_SPEED_PERCENT = "miot_ac_set_fan_speed_percent"
SERVICE_SET_DELAY_ON_TIMER = "miot_ac_set_delay_on_timer"
SERVICE_SET_DELAY_OFF_TIMER = "miot_ac_set_delay_off_timer"
SERVICE_CANCEL_TIMER = "miot_ac_cancel_timer"

SUCCESS = ["ok"]

AIRCONDITIONERMIOT_SERVICE_SCHEMA = vol.Schema(
    {vol.Optional(ATTR_ENTITY_ID): cv.entity_ids}
)

SERVICE_SCHEMA_FAN_SPEED_PERCENT = AIRCONDITIONERMIOT_SERVICE_SCHEMA.extend(
    {
        vol.Required(ATTR_FAN_SPEED_PERCENT): vol.All(
            vol.Coerce(int), vol.Clamp(min=1, max=101)
        )
    }
)

SERVICE_SCHEMA_TIMER = AIRCONDITIONERMIOT_SERVICE_SCHEMA.extend(
    {
        vol.Required(ATTR_TIMER_MINUTES): vol.All(
            vol.Coerce(int), vol.Clamp(min=0, max=720)
        )
    }
)

SERVICE_TO_METHOD = {
    SERVICE_SET_FAN_SPEED_PERCENT: {
        "method": "async_set_fan_speed_percent",
        "schema": SERVICE_SCHEMA_FAN_SPEED_PERCENT,
    },
    SERVICE_SET_DELAY_ON_TIMER: {
        "method": "async_set_delay_on_timer",
        "schema": SERVICE_SCHEMA_TIMER,
    },
    SERVICE_SET_DELAY_OFF_TIMER: {
        "method": "async_set_delay_off_timer",
        "schema": SERVICE_SCHEMA_TIMER,
    },
    SERVICE_CANCEL_TIMER: {"method": "async_cancel_timer"},
}

SUPPORTED_FEATURES = (
    SUPPORT_AUX_HEAT
    | SUPPORT_FAN_MODE
    | SUPPORT_SWING_MODE
    | SUPPORT_TARGET_TEMPERATURE
)

SUPPORTED_MODES = [
    HVAC_MODE_COOL,
    HVAC_MODE_DRY,
    HVAC_MODE_FAN_ONLY,
    HVAC_MODE_HEAT,
    HVAC_MODE_OFF,
]

MODES_TO_MIIO = {
    HVAC_MODE_COOL: OperationMode.Cool,
    HVAC_MODE_DRY: OperationMode.Dry,
    HVAC_MODE_FAN_ONLY: OperationMode.Fan,
    HVAC_MODE_HEAT: OperationMode.Heat,
}

MODES_TO_HASS = {v.value: k for k, v in MODES_TO_MIIO.items()}


async def async_setup_entry(hass, config_entry, async_add_entities):
    """ Setup one climate entity with config entry forwarded. """
    entry_id = config_entry.entry_id
    config = hass.data[DOMAIN][entry_id]
    device = config["miot_device"]
    name = config["name"]
    retries = config["retries"]
    uniq_id = config["unique_id"]
    device_info = config['device_info']

    entity = XiaomiClimateEntity(name, device, retries, uniq_id, device_info)
    async_add_entities([entity], update_before_add=True)

    # Storage devices info to hass, for later device-specified service invoking.
    config["entity"] = entity

    async def async_service_handler(service):
        """Map services to methods on XiaomiClimateEntity."""
        method = SERVICE_TO_METHOD.get(service.service)
        params = {
            key: value for key, value in service.data.items() if key != ATTR_ENTITY_ID
        }

        entity_ids = service.data.get(ATTR_ENTITY_ID)
        # If entity_ids included in service.data,
        # only invoke service to specified devices.
        if entity_ids:
            devices = [
                device
                for device in hass.data[DOMAIN].values()
                if device["entity"].entity_id in entity_ids
            ]
        # If entity_ids not mentioned in service.data,
        # then invokoe service to all registered devices.
        else:
            devices = hass.data[DOMAIN].values()

        update_tasks = []
        for device in devices:
            if not hasattr(device["entity"], method["method"]):
                continue
            await getattr(device["entity"], method["method"])(**params)
            update_tasks.append(device["entity"].async_update_ha_state(True))

        if update_tasks:
            await asyncio.wait(update_tasks, loop=hass.loop)

    # Register services and handler
    for ac_service in SERVICE_TO_METHOD:
        schema = SERVICE_TO_METHOD[ac_service].get(
            "schema", AIRCONDITIONERMIOT_SERVICE_SCHEMA
        )
        hass.services.async_register(
            CLIMATE_DOMAIN, ac_service, async_service_handler, schema=schema
        )


# # pylint: disable=unused-argument
# @asyncio.coroutine
# def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
#     """Set up the air conditioner Miot from config."""

#     name = hass.data[DOMAIN][CONF_NAME]
#     retries = hass.data[DOMAIN][CONF_RETRIES]


class AirConditionerMiotException(DeviceException):
    pass


class XiaomiClimateEntity(ClimateEntity):
    """Representation of Xiaomi Air Conditioner Miot device."""

    # Device initialization and registration

    def __init__(self, name, device, retries, unique_id, device_info):
        """Initialize the climate entity."""
        self._name = name
        self._device = device
        self._retry = 0
        self._retries = retries
        self._identifier = {(DOMAIN, unique_id)}
        self._unique_id = f"{unique_id}-climate"
        self._device_info = device_info

        self._state = None
        self._swing_mode = None

        self._available = False
        self._state_attrs = {}
        self._available_attributes = AVAILABLE_ATTRIBUTES_CLIMATE

    async def async_update(self):
        """Fetch state from the device."""
        try:
            state = await self.hass.async_add_executor_job(self._device.status)
            _LOGGER.debug("Got new state: %s", state)

            self._available = True
            self._state = state.is_on

            # TODO: Support horizontal for other devices
            if state.vertical_swing:
                self._swing_mode = SWING_VERTICAL
            else:
                self._swing_mode = SWING_OFF

            self._state_attrs.update(
                {
                    key: self._extract_value_from_attribute(state, value)
                    for key, value in self._available_attributes.items()
                }
            )
            self.temperature = self.target_temperature
            # self._state_attrs[ATTR_TIMER] = str(self._state_attrs[ATTR_TIMER])
            # self._state_attrs[ATTR_CLEAN] = str(self._state_attrs[ATTR_CLEAN])
            self._retry = 0

        except DeviceException as ex:
            self._retry = self._retry + 1
            if self._retry < self._retries:
                _LOGGER.info(
                    "Got exception while fetching the state: %s , _retry=%s",
                    ex,
                    self._retry,
                )
            else:
                self._available = False
                _LOGGER.error(
                    "Got exception while fetching the state: %s , _retry=%s",
                    ex,
                    self._retry,
                )

    # Implement abstract `Entity` class

    @property
    def should_poll(self):
        """Poll the device."""
        return True

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
        return "mdi:air-conditioner"

    @property
    def available(self):
        """Return true when state is known."""
        return self._available

    @property
    def device_state_attributes(self):
        """Return the state attributes of the device."""
        return self._state_attrs

    # Implement `ClimateEntity` class

    @property
    def temperature_unit(self) -> str:
        """Return the unit of measurement used by the platform."""
        return TEMP_CELSIUS

    @property
    def hvac_mode(self) -> str:
        """Return current HVAC mode."""
        if not self._state:
            return HVAC_MODE_OFF

        return MODES_TO_HASS[self._state_attrs[ATTR_MODE]]

    @property
    def hvac_modes(self) -> list:
        """Return the list of available operation modes."""
        return SUPPORTED_MODES

    @property
    def current_temperature(self) -> float:
        return self._state_attrs[ATTR_TEMPERATURE]

    @property
    def target_temperature(self) -> float:
        return self._state_attrs[ATTR_TARGET_TEMPERATURE]

    @property
    def target_temperature_step(self) -> float:
        return DEFAULT_TEMP_STEP

    @property
    def is_aux_heat(self) -> bool:
        return self._state_attrs[ATTR_HEATER]

    @property
    def fan_mode(self) -> str:
        return FanSpeed(self._state_attrs[ATTR_FAN_SPEED]).name

    @property
    def fan_modes(self) -> list:
        return [i.name for i in FanSpeed]

    @property
    def swing_mode(self) -> str:
        """Return the swing setting."""
        return self._swing_mode

    @property
    def swing_modes(self) -> list:
        """Return the list of available swing modes."""
        return [SWING_OFF, SWING_VERTICAL]

    async def async_set_temperature(self, **kwargs) -> None:
        """Set new target temperature."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is not None:
            t_float = temperature - int(temperature)
            if t_float < 0.25:
                temperature = int(temperature)
            elif t_float < 0.75:
                temperature = int(temperature) + 0.5
            else:
                temperature = int(temperature) + 1

            await self._try_command(
                "Setting target temperature of the miio device failed.",
                self._device.set_target_temperature,
                temperature,
            )

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set new target fan mode."""
        await self._try_command(
            "Setting fan mode of the miio device failed.",
            self._device.set_fan_speed,
            FanSpeed[fan_mode],
        )

    async def async_set_hvac_mode(self, hvac_mode: str) -> None:
        """Set new target hvac mode."""
        if hvac_mode == HVAC_MODE_OFF:
            await self.async_turn_off()
            return

        elif not self._state:
            await self.async_turn_on()

        await self._try_command(
            "Setting operation mode of the miio device failed.",
            self._device.set_mode,
            OperationMode(MODES_TO_MIIO[hvac_mode]),
        )

    async def async_set_swing_mode(self, swing_mode: str) -> None:
        """Set new target swing operation."""
        # horizontal = swing_mode == SWING_HORIZONTAL or swing_mode == SWING_BOTH
        vertical = swing_mode == SWING_VERTICAL  # or swing_mode == SWING_BOTH

        # TODO: horizontal swing
        await self._try_command(
            "Setting swing mode of the miio device failed.",
            self._device.set_vertical_swing,
            vertical,
        )

    async def async_turn_aux_heat_on(self) -> None:
        """Turn auxiliary heater on."""
        await self._try_command(
            "Turning on aux heat of the miio device failed.",
            self._device.set_heater,
            True,
        )

    async def async_turn_aux_heat_off(self) -> None:
        """Turn auxiliary heater off."""
        await self._try_command(
            "Turning off aux heat of the miio device failed.",
            self._device.set_heater,
            False,
        )

    async def async_turn_on(self):
        """Turn on HVAC."""
        result = await self._try_command(
            "Turning the miio device on failed.", self._device.on
        )

        if result:
            self._state = True

    async def async_turn_off(self):
        """Turn off HVAC."""
        result = await self._try_command(
            "Turning the miio device off failed.", self._device.off
        )

        if result:
            self._state = False

    @property
    def supported_features(self) -> int:
        """Return the list of supported features."""
        return SUPPORTED_FEATURES

    @property
    def min_temp(self) -> float:
        """Return the minimum temperature."""
        return DEFAULT_MIN_TEMP

    @property
    def max_temp(self) -> float:
        """Return the maximum temperature."""
        return DEFAULT_MAX_TEMP

    async def async_set_fan_speed_percent(self, fan_speed_percent: int):
        """Set fan percent."""
        await self._try_command(
            "Setting fan percent of the miio device failed.",
            self._device.set_fan_speed_percent,
            fan_speed_percent,
        )

    async def async_set_delay_on_timer(self, minutes: int):
        """Set delay on timer."""
        await self._try_command(
            "Setting delay on timer of the miio device failed.",
            self._device.set_timer,
            minutes,
            True,
        )

    async def async_set_delay_off_timer(self, minutes: int):
        """Set delay off timer."""
        await self._try_command(
            "Setting delay off timer of the miio device failed.",
            self._device.set_timer,
            minutes,
            False,
        )

    async def async_cancel_timer(self, minutes: int):
        """Cancel delay timer."""
        await self._try_command(
            "Cancelling delay timer of the miio device failed.",
            self._device.set_timer,
            0,
            False,
        )

    # Methods to fetch values from miio

    @staticmethod
    def _extract_value_from_attribute(state, attribute):
        value = getattr(state, attribute)
        if isinstance(value, Enum):
            return value.value

        return value

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
