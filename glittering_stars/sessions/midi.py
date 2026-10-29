"""Export frozen events with rounded absolute times, including final gaps."""
from pathlib import Path
import math
import mido

KEY_NAMES = ('C', 'Db', 'D', 'Eb', 'E', 'F', 'F#', 'G', 'Ab', 'A', 'Bb', 'B')


def export_midi(path, events, repetitions=1, override=None, channel=None):
    events = list(events)
    if not events or type(repetitions) is not int or repetitions < 1:
        raise ValueError('Choose events and a positive finite repetition count')
    if channel is not None and (type(channel) is not int or not 0 <= channel <= 15):
        raise ValueError('MIDI channel must be an integer from 0 to 15')
    if override is not None and not isinstance(override, dict):
        raise ValueError('Timing override must contain hold, silence, and velocity')
    if override is not None and not {'hold', 'silence', 'velocity'} <= set(override):
        raise ValueError('Timing override must contain hold, silence, and velocity')
    for index, event in enumerate(events):
        if not isinstance(event, dict):
            raise ValueError(f'Event {index} must be an object')
        if type(event.get('key')) is not int or not 0 <= event['key'] < len(KEY_NAMES):
            raise ValueError(f'Event {index} has an invalid key')
        voices = event.get('voices')
        if (not isinstance(voices, list) or len(voices) != 3 or any(not isinstance(v, dict) for v in voices)
                or any(type(v.get('pitch')) is not int or not 0 <= v['pitch'] <= 127 for v in voices)
                or len({v['pitch'] for v in voices}) != 3
                or any(type(v.get('id')) is not int for v in voices)
                or sorted(v['id'] for v in voices) != [0, 1, 2]):
            raise ValueError(f'Event {index} must contain three distinct, identified MIDI pitches')
        if max(v['pitch'] for v in voices) - min(v['pitch'] for v in voices) < 7:
            raise ValueError(f'Event {index} violates the minimum chord span')
        if type(event.get('channel', 0)) is not int or not 0 <= event.get('channel', 0) <= 15:
            raise ValueError(f'Event {index} has an invalid MIDI channel')
        timing = override if override is not None else event
        if not {'hold', 'silence', 'velocity'} <= set(timing):
            raise ValueError('Each event or timing override must include hold, silence, and velocity')
        if type(timing.get('velocity')) is not int or not 1 <= timing['velocity'] <= 127:
            raise ValueError('Velocity must be an integer from 1 to 127')
    midi = mido.MidiFile(ticks_per_beat=480)
    track = mido.MidiTrack()
    midi.tracks.append(track)
    track.append(mido.MetaMessage('set_tempo', tempo=1000000))
    previous_tick = 0
    seconds = 0.0
    last_key = None
    for _ in range(repetitions):
        for event in events:
            timing = override if override is not None else event
            hold, gap, velocity = timing['hold'], timing['silence'], timing['velocity']
            if any(isinstance(n, bool) or not isinstance(n, (int, float)) or not math.isfinite(n) for n in (hold, gap)) or hold <= 0 or gap < 0:
                raise ValueError('Invalid export timing')
            output_channel = event.get('channel', 0) if channel is None else channel
            onset = round(seconds * 480)
            if event['key'] != last_key:
                track.append(mido.MetaMessage('key_signature', key=KEY_NAMES[event['key']], time=onset-previous_tick))
                previous_tick = onset
                last_key = event['key']
            track.append(mido.MetaMessage('marker', text=f"{event['id']} | {KEY_NAMES[event['key']]} major | {event.get('decision', {}).get('status', '')}", time=onset-previous_tick))
            previous_tick = onset
            for timestamp, kind in ((seconds, 'note_on'), (seconds+hold, 'note_off')):
                tick = round(timestamp * 480)
                for voice in event['voices']:
                    track.append(mido.Message(kind, note=voice['pitch'], velocity=velocity if kind == 'note_on' else 0, channel=output_channel, time=tick-previous_tick))
                    previous_tick = tick
            seconds += hold + gap
    track.append(mido.MetaMessage('end_of_track', time=round(seconds*480)-previous_tick))
    midi.save(Path(path))
    return seconds
