"""
Heartbeat receiving logic.
"""

from pymavlink import mavutil

from ..common.modules.logger import logger


# =================================================================================================
#                            ↓ BOOTCAMPERS MODIFY BELOW THIS COMMENT ↓
# =================================================================================================
class HeartbeatReceiver:
    """
    HeartbeatReceiver class to send a heartbeat
    """

    __private_key = object()

    @classmethod
    def create(
        cls,
        connection: mavutil.mavfile,
        local_logger: logger.Logger,
    ) -> "tuple[True, HeartbeatReceiver] | tuple[False, None]":
        """
        Falliable create (instantiation) method to create a HeartbeatReceiver object.
        """
        try:
            return True, HeartbeatReceiver(cls.__private_key, connection, local_logger)
        except Exception as e:
            local_logger.info(f"Failed to create HeartbeatSender: {e}")
            return False, None

    def __init__(
        self, key: object, connection: mavutil.mavfile, local_logger: logger.Logger
    ) -> None:
        assert key is HeartbeatReceiver.__private_key, "Use create() method"
        # Do any intializiation here
        self.__logger = local_logger
        self.__connection = connection
        self.__missed_count = 0
        self.__is_connected = False

    def run(
        self,
    ) -> bool:
        """
        Attempt to recieve a heartbeat message.
        If disconnected for over a threshold number of periods,
        the connection is considered disconnected.
        """
        try:
            msg = self.__connection.recv_match(type="HEARTBEAT", blocking=False)
        except Exception as e:
            self.__logger.error(f"Error while attempting to recieve heartbeat: {e}")
            return False

        if not msg:
            self.__missed_count += 1
            self.__logger.warning(f"Missed heartbeat. Missed count: {self.__missed_count}")

            if self.__missed_count >= 5:
                self.__is_connected = False
                self.__logger.warning(
                    f"Disconnected from drone. Missed count: {self.__missed_count}"
                )
        else:
            self.__logger.info(f"Recieved heartbeat. Connected")
            self.__missed_count = 0
            self.__is_connected = True

        return self.__is_connected


# =================================================================================================
#                            ↑ BOOTCAMPERS MODIFY ABOVE THIS COMMENT ↑
# =================================================================================================
