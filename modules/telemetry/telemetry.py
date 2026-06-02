"""
Telemetry gathering logic.
"""

import time

from pymavlink import mavutil

from ..common.modules.logger import logger


class TelemetryData:  # pylint: disable=too-many-instance-attributes
    """
    Python struct to represent Telemtry Data. Contains the most recent attitude and position reading.
    """

    def __init__(
        self,
        time_since_boot: int | None = None,  # ms
        x: float | None = None,  # m
        y: float | None = None,  # m
        z: float | None = None,  # m
        x_velocity: float | None = None,  # m/s
        y_velocity: float | None = None,  # m/s
        z_velocity: float | None = None,  # m/s
        roll: float | None = None,  # rad
        pitch: float | None = None,  # rad
        yaw: float | None = None,  # rad
        roll_speed: float | None = None,  # rad/s
        pitch_speed: float | None = None,  # rad/s
        yaw_speed: float | None = None,  # rad/s
    ) -> None:
        self.time_since_boot = time_since_boot
        self.x = x
        self.y = y
        self.z = z
        self.x_velocity = x_velocity
        self.y_velocity = y_velocity
        self.z_velocity = z_velocity
        self.roll = roll
        self.pitch = pitch
        self.yaw = yaw
        self.roll_speed = roll_speed
        self.pitch_speed = pitch_speed
        self.yaw_speed = yaw_speed

    def __str__(self) -> str:
        return f"""{{
            time_since_boot: {self.time_since_boot},
            x: {self.x},
            y: {self.y},
            z: {self.z},
            x_velocity: {self.x_velocity},
            y_velocity: {self.y_velocity},
            z_velocity: {self.z_velocity},
            roll: {self.roll},
            pitch: {self.pitch},
            yaw: {self.yaw},
            roll_speed: {self.roll_speed},
            pitch_speed: {self.pitch_speed},
            yaw_speed: {self.yaw_speed}
        }}"""


# =================================================================================================
#                            ↓ BOOTCAMPERS MODIFY BELOW THIS COMMENT ↓
# =================================================================================================
class Telemetry:
    """
    Telemetry class to read position and attitude (orientation).
    """

    __private_key = object()

    @classmethod
    def create(
        cls,
        connection: mavutil.mavfile,
        local_logger: logger.Logger,
    ) -> "tuple[True, Telemetry] | tuple[False, None]":
        """
        Falliable create (instantiation) method to create a Telemetry object.
        """
        try:
            return True, Telemetry(cls.__private_key, connection, local_logger)
        except Exception as e:  # pylint: disable=broad-exception-caught
            local_logger.error(f"Failed to create Telemetry: {e}")
            return False, None

    def __init__(
        self,
        key: object,
        connection: mavutil.mavfile,
        local_logger: logger.Logger,
    ) -> None:
        assert key is Telemetry.__private_key, "Use create() method"

        # Do any intializiation here
        self.__connection = connection
        self.__logger = local_logger

    def run(
        self,
    ) -> TelemetryData | None:
        """
        Receive LOCAL_POSITION_NED and ATTITUDE messages from the drone,
        combining them together to form a single TelemetryData object.
        """
        # Read MAVLink message LOCAL_POSITION_NED (32)
        # Read MAVLink message ATTITUDE (30)
        # Return the most recent of both, and use the most recent message's timestamp
        start_time = time.time()
        alt_msg = None
        pos_msg = None
        recent_boot_time = None

        while time.time() - start_time <= 1:
            try:
                msg = self.__connection.recv_match()
            except Exception as e:  # pylint: disable=broad-exception-caught
                self.__logger.error(f"Error while attempting to recieve telemetry: {e}")
            if not msg:
                continue

            msg_type = msg.get_type()
            if msg_type == "ATTITUDE":
                alt_msg = msg
            else:
                pos_msg = msg
            recent_boot_time = msg.time_boot_ms

            if alt_msg and pos_msg:
                break

        if not alt_msg or not pos_msg:
            self.__logger.warning("Timedout waiting for altitude and/or position")
            return None
        self.__logger.info("Successfully recieved data for Telemetry")
        return TelemetryData(
            recent_boot_time,
            pos_msg.x,
            pos_msg.y,
            pos_msg.z,
            pos_msg.vx,
            pos_msg.vy,
            pos_msg.vz,
            alt_msg.roll,
            alt_msg.pitch,
            alt_msg.yaw,
            alt_msg.rollspeed,
            alt_msg.pitchspeed,
            alt_msg.yawspeed,
        )


# =================================================================================================
#                            ↑ BOOTCAMPERS MODIFY ABOVE THIS COMMENT ↑
# =================================================================================================
