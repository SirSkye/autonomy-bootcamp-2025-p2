"""
Bootcamp F2025

Main process to setup and manage all the other working processes
"""

import multiprocessing as mp
import time
import queue

from pymavlink import mavutil

from modules.common.modules.logger import logger
from modules.common.modules.logger import logger_main_setup
from modules.common.modules.read_yaml import read_yaml
from modules.command import command
from modules.command import command_worker
from modules.heartbeat import heartbeat_receiver_worker
from modules.heartbeat import heartbeat_sender_worker
from modules.telemetry import telemetry_worker
from utilities.workers import queue_proxy_wrapper
from utilities.workers import worker_controller
from utilities.workers import worker_manager


# MAVLink connection
CONNECTION_STRING = "tcp:localhost:12345"

# =================================================================================================
#                            ↓ BOOTCAMPERS MODIFY BELOW THIS COMMENT ↓
# =================================================================================================
# Set queue max sizes (<= 0 for infinity)
HEARTBEAT_RECEIVER_TO_MAIN_QUEUE_MAX_SIZE = 5
TELEMETRY_TO_COMMAND_QUEUE_MAX_SIZE = 5
COMMAND_TO_MAIN_QUEUE_MAX_SIZE = 5

# Set worker counts
HEARTBEAT_SENDER_WORKER_COUNT = 1
HEARTBEAT_RECIEVER_WORKER_COUNT = 1
TELEMETRY_WORKER_COUNT = 1
COMMAND_WORKER_COUNT = 1

# Any other constants
TELEMETRY_PERIOD = 0.5
TARGET = command.Position(10, 20, 30)
HEIGHT_TOLERANCE = 0.5
Z_SPEED = 1  # m/s
ANGLE_TOLERANCE = 5  # deg
TURNING_SPEED = 5  # deg/s
HEARTBEAT_PERIOD = 1


# =================================================================================================
#                            ↑ BOOTCAMPERS MODIFY ABOVE THIS COMMENT ↑
# =================================================================================================


def main() -> int:
    """
    Main function.
    """
    # Configuration settings
    result, config = read_yaml.open_config(logger.CONFIG_FILE_PATH)
    if not result:
        print("ERROR: Failed to load configuration file")
        return -1

    # Get Pylance to stop complaining
    assert config is not None

    # Setup main logger
    result, main_logger, _ = logger_main_setup.setup_main_logger(config)
    if not result:
        print("ERROR: Failed to create main logger")
        return -1

    # Get Pylance to stop complaining
    assert main_logger is not None

    # Create a connection to the drone. Assume that this is safe to pass around to all processes
    # In reality, this will not work, but to simplify the bootamp, preetend it is allowed
    # To test, you will run each of your workers individually to see if they work
    # (test "drones" are provided for you test your workers)
    # NOTE: If you want to have type annotations for the connection, it is of type mavutil.mavfile
    connection = mavutil.mavlink_connection(CONNECTION_STRING)
    connection.wait_heartbeat(timeout=30)  # Wait for the "drone" to connect

    # =============================================================================================
    #                          ↓ BOOTCAMPERS MODIFY BELOW THIS COMMENT ↓
    # =============================================================================================
    # Create a worker controller
    controller = worker_controller.WorkerController()

    # Create a multiprocess manager for synchronized queues
    manager = mp.Manager()

    # Create queues
    heartbeat_status_queue = queue_proxy_wrapper.QueueProxyWrapper(
        manager, HEARTBEAT_RECEIVER_TO_MAIN_QUEUE_MAX_SIZE
    )
    telemetry_to_command_queue = queue_proxy_wrapper.QueueProxyWrapper(
        manager, TELEMETRY_TO_COMMAND_QUEUE_MAX_SIZE
    )
    command_to_main_queue = queue_proxy_wrapper.QueueProxyWrapper(
        manager, COMMAND_TO_MAIN_QUEUE_MAX_SIZE
    )

    # Create worker properties for each worker type (what inputs it takes, how many workers)
    # Heartbeat sender
    result, heartbeat_sender_properties = worker_manager.WorkerProperties.create(
        HEARTBEAT_SENDER_WORKER_COUNT,
        heartbeat_sender_worker.heartbeat_sender_worker,
        (
            connection,
            HEARTBEAT_PERIOD,
        ),
        [],
        [],
        controller,
        main_logger,
    )
    if not result:
        main_logger.error("Failed to create properties for Heartbeat Sender")
        return -1

    result, heartbeat_reciever_properties = worker_manager.WorkerProperties.create(
        HEARTBEAT_RECIEVER_WORKER_COUNT,
        heartbeat_receiver_worker.heartbeat_receiver_worker,
        (connection,),
        [],
        [heartbeat_status_queue],
        controller,
        main_logger,
    )
    if not result:
        main_logger.error("Failed to create properties for Heartbeat Reciever")
        return -1

    result, telemetry_properties = worker_manager.WorkerProperties.create(
        TELEMETRY_WORKER_COUNT,
        telemetry_worker.telemetry_worker,
        (connection),
        [],
        [telemetry_to_command_queue],
        controller,
        main_logger,
    )
    if not result:
        main_logger.error("Failed to create properies for Telemetry")
        return -1

    result, command_properties = worker_manager.WorkerProperties.create(
        COMMAND_WORKER_COUNT,
        command_worker.command_worker,
        (connection, TARGET, HEIGHT_TOLERANCE, ANGLE_TOLERANCE, Z_SPEED, TURNING_SPEED),
        [telemetry_to_command_queue],
        [command_to_main_queue],
        controller,
        main_logger,
    )
    if not result:
        main_logger.error("Failed to create properies for Command")
        return -1

    # Create the workers (processes) and obtain their managers
    worker_managers: list[worker_manager.WorkerManager] = []
    result, heart_beat_sender_manager = worker_manager.WorkerManager.create(
        heartbeat_sender_properties, main_logger
    )
    if not result:
        main_logger.error("Failed to create manager for Heartbeat Sender")
        return -1
    worker_managers.append(heart_beat_sender_manager)

    result, heart_beat_reciever_manager = worker_manager.WorkerManager.create(
        heartbeat_reciever_properties, main_logger
    )
    if not result:
        main_logger.error("Failed to create manager for Heartbeat Reciever")
        return -1
    worker_managers.append(heart_beat_reciever_manager)

    result, telemetry_manager = worker_manager.WorkerManager.create(
        telemetry_properties, main_logger
    )
    if not result:
        main_logger.error("Failed to create manager for Telemetry")
        return -1
    worker_managers.append(telemetry_manager)

    result, command_manager = worker_manager.WorkerManager.create(command_properties, main_logger)
    if not result:
        main_logger.error("Failed to create manager for Commander")
        return -1
    worker_managers.append(command_manager)
    # Start worker processes
    for manager in worker_managers:
        manager.start_workers()

    main_logger.info("Started")

    # Main's work: read from all queues that output to main, and log any commands that we make
    # Continue running for 100 seconds or until the drone disconnects
    start_time = time.time()
    while time.time() - start_time < 100:
        try:
            heartbeat_status = heartbeat_status_queue.queue.get(block=False)
            main_logger.info(f"Heartbeat status: {heartbeat_status}")
            if heartbeat_status == "Disconnected":
                break
        except queue.Empty:
            pass
        try:
            command_output = command_to_main_queue.queue.get(block=False)
            main_logger.info(f"Command output: {command_output}")
        except queue.empty:
            pass

    # Stop the processes
    controller.request_exit()
    main_logger.info("Requested exit")

    # Fill and drain queues from END TO START
    heartbeat_status_queue.fill_and_drain_queue()
    telemetry_to_command_queue.fill_and_drain_queue()
    command_to_main_queue.fill_and_drain_queue()

    main_logger.info("Queues cleared")

    # Clean up worker processes
    for manager in worker_managers:
        manager.join_workers()

    main_logger.info("Stopped")

    # We can reset controller in case we want to reuse it
    # Alternatively, create a new WorkerController instance
    controller.clear_exit()

    # =============================================================================================
    #                          ↑ BOOTCAMPERS MODIFY ABOVE THIS COMMENT ↑
    # =============================================================================================

    return 0


if __name__ == "__main__":
    result_main = main()
    if result_main < 0:
        print(f"Failed with return code {result_main}")
    else:
        print("Success!")
