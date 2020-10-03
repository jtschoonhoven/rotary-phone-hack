import os
import logging
import asyncio
import pygame
import RPi.GPIO as GPIO
from typing import Any, Callable, Coroutine, Dict
from pygame import mixer


# Configure logging
logging.basicConfig()
logging.root.setLevel(logging.DEBUG)
log = logging.getLogger(__name__)

# Declare timeouts and intervals
SLEEP_SECS = 1
DEFAULT_SHELL_CMD_TIMEOUT_SECS = 5
DEFAULT_GPIO_EVENT_POLL_SECS = 0.2
DEFAULT_GPIO_EVENT_DEBOUNCE_SECS = 0.8

# Declare GPIO pins
PIN_OUT_RINGER = 11
PIN_IN_HANGAR = 13

# Declare paths
MODULE_PATH = os.path.dirname(os.path.abspath(__file__))
SOUNDS_PATH = os.path.join(MODULE_PATH, '..', 'sounds')

# Declare audio file manifest
SOUNDS_MANIFESET: Dict[str, str] = {
    'APPLAUSE': os.path.join(SOUNDS_PATH, 'applause.wav'),
}
SOUNDS: Dict[str, pygame.mixer.Sound] = {}  # Populated from manifest during setup


async def async_cmd(cmd: str, timeout_secs: float = DEFAULT_SHELL_CMD_TIMEOUT_SECS) -> None:
    """
    Run a shell command async and handle stderr/stdout.
    """
    log.debug(f'Executing async shell command "{cmd}"')
    process = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=timeout_secs,
        )
    except asyncio.TimeoutError as e:
        raise Exception(f'Shell command "{cmd}" timed out') from e
    if process.returncode != 0:
        err = stderr.decode('utf8')
        raise Exception(
            f'Shell command "{cmd}" exited with status {process.returncode}:\n{err}',
        )
    output = stdout.decode('utf8')
    log.debug(f'Shell command "{cmd}" successful with stdout:\n{output}')


def get_gpio_event_detector(
    pin: int,
    event: int,  # 0 (low) or 1 (high)
    reusable: bool = False,
    poll_interval_secs: float = DEFAULT_GPIO_EVENT_POLL_SECS,
    debounce_secs: float = DEFAULT_GPIO_EVENT_DEBOUNCE_SECS,
) -> Callable[[], Coroutine[Any, Any, int]]:
    """
    Return an awaitable function that resolves when a GPIO event is detected
    """
    async def _event_detector() -> int:
        """Poll async until an event is detected"""
        debounce_timer_secs: float = 0
        log.debug(f'Pin {pin} awaiting event {event}')

        while True:
            # Poll async for events: sleep until GPIO pin is in target state
            if GPIO.input(pin) != event:
                debounce_timer_secs = 0
                await asyncio.sleep(poll_interval_secs)
                continue

            # If pin is in desired state, keep polling until debounce timer is met
            if debounce_timer_secs < debounce_secs:
                log.debug(
                    f'Pin {pin} matched state {event} for {debounce_timer_secs} of {debounce_secs}s'
                )
                debounce_timer_secs += poll_interval_secs
                continue

            # Stop listening if this event detector is not reusable
            if not reusable:
                log.debug(f'Pin {pin} removing detector for event {event}')
                GPIO.remove_event_detect(pin)

            # Return the pin state, 0 (low) or 1 (high)
            log.debug(f'Pin {pin} in state {event}')
            return event
    return _event_detector


async def setup() -> None:
    global SOUNDS

    # Use GPIO.BOARD mode for better portability
    # See https://sourceforge.net/p/raspberry-gpio-python/wiki/BasicUsage/
    GPIO.setmode(GPIO.BOARD)

    # Prepare GPIO pins
    log.info('Preparing GPIO pins')
    GPIO.setup(PIN_OUT_RINGER, GPIO.OUT, initial=GPIO.LOW)
    GPIO.setup(PIN_IN_HANGAR, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

    # Initialize pygame mixer
    log.info('Initializing Python audio mixer')
    mixer.init()

    # Load sounds
    for key in SOUNDS_MANIFESET.keys():
        log.info(f'Loading sound file "{SOUNDS_MANIFESET[key]}"')
        SOUNDS[key] = mixer.Sound(SOUNDS_MANIFESET[key])

    # Unmute RPI at system level
    log.info('Unmuting RPI')
    await async_cmd('amixer set Headphone unmute')
    log.info('Setting RPI system volume 100%')
    await async_cmd('amixer set Headphone 100%')


async def ring_until_answered() -> None:
    # is_answered = get_gpio_event_detector(PIN_IN_HANGAR, GPIO.LOW)
    pass


async def main() -> None:
    await setup()

    # Wait for phone to be placed in the hangar before proceeding
    is_in_hangar = get_gpio_event_detector(PIN_IN_HANGAR, GPIO.HIGH)
    await is_in_hangar()

try:
    asyncio.run(main())
except KeyboardInterrupt:
    print('Cleaning up before exit...')
    GPIO.cleanup()
