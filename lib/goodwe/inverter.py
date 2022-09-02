from __future__ import annotations

import asyncio
import io
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, Tuple, Optional

from .exceptions import MaxRetriesException, RequestFailedException
from .protocol import ProtocolCommand

logger = logging.getLogger(__name__)


class SensorKind(Enum):
    """
    Enumeration of sensor kinds.

    Possible values are:
    PV - inverter photo-voltaic (e.g. dc voltage of pv panels)
    AC - inverter grid output (e.g. ac voltage of grid connected output)
    UPS - inverter ups/eps/backup output (e.g. ac voltage of backup/off-grid connected output)
    BAT - battery (e.g. dc voltage of connected battery pack)
    GRID - power grid/smart meter (e.g. active power exported to grid)
    """

    PV = 1
    AC = 2
    UPS = 3
    BAT = 4
    GRID = 5


@dataclass
class Sensor:
    """Definition of inverter sensor and its attributes"""

    id_: str
    offset: int
    name: str
    size_: int
    unit: str
    kind: Optional[SensorKind]

    def read_value(self, data: io.BytesIO) -> Any:
        """Read the sensor value from data at current position"""
        raise NotImplementedError()

    def read(self, data: io.BytesIO) -> Any:
        """Read the sensor value from data (at sensor offset)"""
        data.seek(self.offset)
        return self.read_value(data)

    def encode_value(self, value: Any) -> bytes:
        """Encode the (setting mostly) value to (usually) 2 byte raw register value"""
        raise NotImplementedError()


class Inverter:
    """
    Common superclass for various inverter models implementations.
    Represents the inverter state and its basic behavior
    """

    def __init__(self, host: str, comm_addr: int = 0, timeout: int = 1, retries: int = 3):
        self.host: str = host
        self.comm_addr: int = comm_addr
        self.timeout: int = timeout
        self.retries: int = retries
        self._running_loop: asyncio.AbstractEventLoop | None = None
        self._lock: asyncio.Lock | None = None
        self._consecutive_failures_count: int = 0

        self.model_name: str | None = None
        self.serial_number: str | None = None
        self.software_version: str | None = None
        self.modbus_version: int | None = None
        self.rated_power: int | None = None
        self.ac_output_type: int | None = None
        self.dsp1_sw_version: int | None = None
        self.dsp2_sw_version: int | None = None
        self.dsp_svn_version: int | None = None
        self.arm_sw_version: int = 0
        self.arm_svn_version: int | None = None
        self.arm_version: str | None = None

    def _ensure_lock(self) -> asyncio.Lock:
        """Validate (or create) asyncio Lock.

           The asyncio.Lock must always be created from within's asyncio loop,
           so it cannot be eagerly created in constructor.
           Additionally, since asyncio.run() creates and closes its own loop,
           the lock's scope (its creating loop) mus be verified to support proper
           behavior in subsequent asyncio.run() invocations.
        """
        if self._lock and self._running_loop == asyncio.get_event_loop():
            return self._lock
        else:
            logger.debug("Creating lock instance for current event loop.")
            self._lock = asyncio.Lock()
            self._running_loop = asyncio.get_event_loop()
            return self._lock

    async def _read_from_socket(self, command: ProtocolCommand) -> bytes:
        async with self._ensure_lock():
            try:
                result = await command.execute(self.host, self.timeout, self.retries)
                self._consecutive_failures_count = 0
                return result
            except MaxRetriesException:
                self._consecutive_failures_count += 1
                raise RequestFailedException(f'No valid response received even after {self.retries} retries',
                                             self._consecutive_failures_count)
            except RequestFailedException as ex:
                self._consecutive_failures_count += 1
                raise RequestFailedException(ex.message, self._consecutive_failures_count)

    async def read_device_info(self):
        """
        Request the device information from the inverter.
        The inverter instance variables will be loaded with relevant data.
        """
        raise NotImplementedError()

    async def read_runtime_data(self, include_unknown_sensors: bool = False) -> Dict[str, Any]:
        """
        Request the runtime data from the inverter.
        Answer dictionary of individual sensors and their values.
        List of supported sensors (and their definitions) is provided by sensors() method.

        If include_unknown_sensors parameter is set to True, return all runtime values,
        including those "xx*" sensors whose meaning is not yet identified.
        """
        raise NotImplementedError()

    async def read_setting(self, setting_id: str) -> Any:
        """
        Read the value of specific inverter setting/configuration parameter.
        Setting must be in list provided by settings() method, otherwise ValueError is raised.
        """
        raise NotImplementedError()

    async def write_setting(self, setting_id: str, value: Any):
        """
        Set the value of specific inverter settings/configuration parameter.
        Setting must be in list provided by settings() method, otherwise ValueError is raised.

        BEWARE !!!
        This method modifies inverter operational parameter (usually accessible to installers only).
        Use with caution and at your own risk !
        """
        raise NotImplementedError()

    async def read_settings_data(self) -> Dict[str, Any]:
        """
        Request the settings data from the inverter.
        Answer dictionary of individual settings and their values.
        List of supported settings (and their definitions) is provided by settings() method.
        """
        raise NotImplementedError()

    async def send_command(
            self, command: bytes, validator: Callable[[bytes], bool] = lambda x: True
    ) -> bytes:
        """
        Send low level udp command (as bytes).
        Answer command's raw response data.
        """
        return await self._read_from_socket(ProtocolCommand(command, validator))

    async def get_grid_export_limit(self) -> int:
        """
        Get the current grid export limit in W
        """
        raise NotImplementedError()

    async def set_grid_export_limit(self, export_limit: int) -> None:
        """
        BEWARE !!!
        This method modifies inverter operational parameter accessible to installers only.
        Use with caution and at your own risk !

        Set the grid export limit in W
        """
        raise NotImplementedError()

    async def get_operation_mode(self) -> int:
        """
        Get the inverter operation mode
        0 - General mode
        1 - Off grid mode
        2 - Backup mode
        3 - Eco mode
        """
        raise NotImplementedError()

    async def set_operation_mode(self, operation_mode: int, eco_mode_power: int = 100) -> None:
        """
        BEWARE !!!
        This method modifies inverter operational parameter accessible to installers only.
        Use with caution and at your own risk !

        Set the inverter operation mode
        0 - General mode
        1 - Off grid mode
        2 - Backup mode
        3 - Eco mode
        4 - Eco mode Charge
        5 - Eco mode Discharge

        The modes 4 and 5 are not real inverter operation modes, but a convenience
        shortcuts to enter Eco Mode with a single group valid all the time (from 00:00-23:69, Mon-Sun)
        charging or discharging with optional charging power (%) parameter.
        """
        raise NotImplementedError()

    async def get_ongrid_battery_dod(self) -> int:
        """
        Get the On-Grid Battery DoD
        0% - 89%
        """
        raise NotImplementedError()

    async def set_ongrid_battery_dod(self, dod: int) -> None:
        """
        BEWARE !!!
        This method modifies On-Grid Battery DoD parameter accessible to installers only.
        Use with caution and at your own risk !

        Set the On-Grid Battery DoD
        0% - 89%
        """
        raise NotImplementedError()

    def sensors(self) -> Tuple[Sensor, ...]:
        """
        Return tuple of sensor definitions
        """
        raise NotImplementedError()

    def settings(self) -> Tuple[Sensor, ...]:
        """
        Return tuple of settings definitions
        """
        raise NotImplementedError()

    @staticmethod
    def _map_response(resp_data: bytes, sensors: Tuple[Sensor, ...], incl_xx: bool = True) -> Dict[str, Any]:
        """Process the response data and return dictionary with runtime values"""
        with io.BytesIO(resp_data) as buffer:
            result = {}
            for sensor in sensors:
                if incl_xx or not sensor.id_.startswith("xx"):
                    try:
                        result[sensor.id_] = sensor.read(buffer)
                    except ValueError:
                        logger.exception("Error reading sensor %s.", sensor.id_)
                        result[sensor.id_] = None
            return result
