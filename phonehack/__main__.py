import os
import logging
import asyncio
import RPi.GPIO as GPIO
from typing import Any, Callable, Coroutine, Dict
from pygame import mixer


# Configure logging
logging.basicConfig()
logging.root.setLevel(logging.DEBUG)
log = logging.getLogger(__name__)

# Declare timeouts and intervals
DEFAULT_SHELL_CMD_TIMEOUT_SECS = 5
DEFAULT_GPIO_EVENT_POLL_SECS = 0.2
DEFAULT_GPIO_EVENT_DEBOUNCE_SECS = 0.8
RING_TOGGLE_INTERVAL_SECS = 0.05
RING_DURATION_SECS = 1.6

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

# Declare valid audio outputs, "local" is the builtin 1/8" jack
AUDIO_OUTPUT_HDMI = 'hdmi'
AUDIO_OUTPUT_LOCAL = 'local'
AUDIO_OUTPUT_ALL = 'both'
AUDIO_OUTPUTS = frozenset([AUDIO_OUTPUT_HDMI, AUDIO_OUTPUT_LOCAL, AUDIO_OUTPUT_ALL])


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


def play_audio_file(filepath: str, output: str = AUDIO_OUTPUT_LOCAL) -> Callable[[], Coroutine[Any, Any, None]]:
    """
    Play an audio file from disk using omxplayer.
    """
    log.debug(f'Playing audio file at path "{filepath}" to output "{output}"')
    if output not in AUDIO_OUTPUTS:
        raise Exception(f'Audio output "{output}" invalid: must be one of {AUDIO_OUTPUTS}')
    return async_cmd(f'omxplayer -o {output} "{filepath}"')


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
        event_name = 'HIGH' if event else 'LOW'
        log.debug(f'Pin {pin} awaiting event {event_name}')

        while True:
            # Poll async for events: sleep until GPIO pin is in target state
            if GPIO.input(pin) != event:
                debounce_timer_secs = 0
                await asyncio.sleep(poll_interval_secs)
                continue

            # If pin is in desired state, keep polling until debounce timer is met
            if debounce_timer_secs < debounce_secs:
                log.debug(
                    f'Pin {pin} matched state {event_name} for {debounce_timer_secs} of {debounce_secs}s'
                )
                debounce_timer_secs += poll_interval_secs
                continue

            # Stop listening if this event detector is not reusable
            if not reusable:
                log.debug(f'Pin {pin} removing detector for event {event_name}')
                GPIO.remove_event_detect(pin)

            # Return the pin state, 0 (low) or 1 (high)
            log.debug(f'Pin {pin} in state {event_name}')
            return event
    return _event_detector


async def setup() -> None:
    # Use GPIO.BOARD mode for better portability
    # See https://sourceforge.net/p/raspberry-gpio-python/wiki/BasicUsage/
    GPIO.setmode(GPIO.BOARD)

    # Prepare GPIO pins
    log.debug('Preparing GPIO pins')
    GPIO.setup(PIN_OUT_RINGER, GPIO.OUT, initial=GPIO.LOW)
    GPIO.setup(PIN_IN_HANGAR, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

    # Initialize pygame mixer
    log.debug('Initializing Python audio mixer')
    mixer.init()

    # Unmute RPI at system level
    log.debug('Unmuting RPI')
    await async_cmd('amixer set Headphone unmute')
    log.debug('Setting RPI system volume 100%')
    await async_cmd('amixer set Headphone 100%')


async def ring_once() -> None:
    """
    Rapidly toggle ringer output channel for RING_DURATION_SECS.
    """
    ring_timer_secs: float = 0

    log.debug('Ring! Ring!')
    while ring_timer_secs < RING_DURATION_SECS:
        for v in (GPIO.HIGH, GPIO.LOW):
            GPIO.output(PIN_OUT_RINGER, v)
            ring_timer_secs += RING_TOGGLE_INTERVAL_SECS
            await asyncio.sleep(RING_TOGGLE_INTERVAL_SECS)


async def ring_forever() -> None:
    """
    Ring the phone forever. Wrap in a task and use cancel() to stop ringer.
    """
    while True:
        await ring_once()
        await asyncio.sleep(RING_DURATION_SECS)


async def ring_until_answered() -> None:
    """
    Ring forever until phone is removed from hook.
    """
    log.debug('Ringing...')
    ring_forever_task = asyncio.create_task(ring_forever())

    def on_phone_answered(_: asyncio.Future) -> None:
        log.debug('Stopping ringer...')
        ring_forever_task.cancel()

    is_answered = get_gpio_event_detector(PIN_IN_HANGAR, GPIO.HIGH)
    is_answered_task = asyncio.create_task(is_answered())
    is_answered_task.add_done_callback(on_phone_answered)
    await is_answered_task
    log.info('Phone answered')


async def main() -> None:
    log.info('Initializing')
    await setup()

    is_in_hangar = get_gpio_event_detector(PIN_IN_HANGAR, GPIO.LOW)

    log.info('Starting loop')
    while True:
        log.info('Waiting for phone in hangar')
        await is_in_hangar()

        # Ring while phone is on the hanger
        await ring_until_answered()

        log.info('Starting audio playback')
        await play_audio_file(SOUNDS_MANIFESET['APPLAUSE'])


if __name__ == '__main__':
    try:
        log.debug('Starting event loop')
        asyncio.run(main())
    finally:
        log.info('Cleaning up GPIO state before exit')
        GPIO.cleanup()
