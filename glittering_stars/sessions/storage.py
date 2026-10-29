"""Persistence never mutates a live controller or opens a MIDI device."""
import copy
import json
import math
import os
from pathlib import Path
import tempfile

SCHEMA_VERSION = 1


def app_data_dir():
    path = Path(os.environ.get('LOCALAPPDATA', Path.home() / '.local' / 'share')) / 'GlitteringStars'
    path.mkdir(parents=True, exist_ok=True)
    return path


def _number(value, name, low, high=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < low or (high is not None and value > high):
        raise ValueError(f'Invalid {name}')


def validate_session(document):
    from glittering_stars.domain import Config, Engine, key_number
    if not isinstance(document, dict):
        raise ValueError('Session must be a JSON object')
    # Events/snapshots are immutable once published. Validation only adds
    # top-level capability flags; copying millions of PRNG integers here would
    # cause long stop-the-world GC pauses in the MIDI scheduler's process.
    result = dict(document)
    version = result.get('schema_version', SCHEMA_VERSION)
    if type(version) is not int or version < 1:
        raise ValueError('Unsupported session schema')
    future = version > SCHEMA_VERSION
    Config.from_dict(result['config']).validate()
    if result.get('pending_config') is not None:
        Config.from_dict(result['pending_config']).validate()
    output_channel=result.get('output_channel',result['config'].get('channel',0))
    if type(output_channel) is not int or not 0 <= output_channel <= 15:
        raise ValueError('Invalid output channel')
    result['output_channel']=output_channel
    for field in ('applied_revision', 'run_events'):
        if type(result.get(field, 0)) is not int or result.get(field, 0) < 0:
            raise ValueError(f'Invalid {field}')
    for field in ('start_from_anchor', 'run_complete'):
        if type(result.get(field, False)) is not bool:
            raise ValueError(f'Invalid {field}')
    if result.get('pending_reseed') is not None and type(result['pending_reseed']) is not int:
        raise ValueError('Invalid pending reseed')
    if result.get('pending_key') is not None:
        key_number(result['pending_key'])
    context = result.get('context_log', [])
    if not isinstance(context, list):
        raise ValueError('Context log must be an array')
    for command in context:
        if not isinstance(command, dict) or command.get('kind') not in ('reseed', 'set_key'):
            raise ValueError('Invalid context command')
        if type(command.get('before_event')) is not int or not 0 <= command['before_event'] <= len(result.get('history', [])):
            raise ValueError('Invalid context command ordering')
        if command['kind'] == 'reseed' and type(command.get('seed')) is not int:
            raise ValueError('Invalid context seed')
        if command['kind'] == 'set_key':
            key_number(command.get('key_before'))
            key_number(command.get('key_after'))
    history = result.get('history', [])
    branches = result.get('branches', [])
    if not isinstance(history, list) or not isinstance(branches, list):
        raise ValueError('History and branches must be arrays')
    branch_ids = set()
    for branch in branches:
        if (not isinstance(branch, dict) or not isinstance(branch.get('id'), str) or not branch['id']
                or branch['id'] in branch_ids or not isinstance(branch.get('name', ''), str)):
            raise ValueError('Invalid or duplicate branch ID')
        branch_ids.add(branch['id'])
    ids = set()
    unsupported = future
    for event in history:
        if (not isinstance(event, dict) or not isinstance(event.get('id'), str) or not event['id']
                or event['id'] in ids):
            raise ValueError('Invalid or duplicate event ID')
        ids.add(event['id'])
        if event.get('branch_id') not in branch_ids:
            raise ValueError('Event references missing branch')
        voices = event.get('voices')
        if not isinstance(voices, list) or len(voices) != 3 or any(not isinstance(v, dict) for v in voices):
            raise ValueError('Event requires exactly three voices')
        pitches = [v.get('pitch') for v in voices]
        voice_ids = [v.get('id') for v in voices]
        if any(type(n) is not int or not 0 <= n <= 127 for n in pitches) or len(set(pitches)) != 3 or max(pitches)-min(pitches) < 7:
            raise ValueError('Invalid recorded chord')
        if any(type(i) is not int for i in voice_ids) or sorted(voice_ids) != [0, 1, 2]:
            raise ValueError('Invalid stable voice IDs')
        if type(event.get('key')) is not int or not 0 <= event['key'] <= 11:
            raise ValueError('Invalid event key')
        _number(event.get('hold'), 'hold', 0)
        if event['hold'] <= 0:
            raise ValueError('Hold must be positive')
        _number(event.get('silence'), 'silence', 0)
        if type(event.get('velocity')) is not int or not 1 <= event['velocity'] <= 127:
            raise ValueError('Invalid velocity')
        if type(event.get('channel', 0)) is not int or not 0 <= event.get('channel', 0) <= 15:
            raise ValueError('Invalid channel')
        if type(event.get('revision', 0)) is not int or event.get('revision', 0) < 0:
            raise ValueError('Invalid event configuration revision')
        if not isinstance(event.get('decision', {}), dict):
            raise ValueError('Invalid event decision metadata')
        snapshot = event.get('snapshot')
        try:
            restored = Engine.restore(snapshot)
            if restored.snapshot()['voices'] != voices or restored.key != event['key']:
                raise ValueError('Recorded event disagrees with its continuation snapshot')
        except ValueError as exc:
            # Future format is replayable only when its recorded musical data is valid.
            if future or (isinstance(snapshot, dict) and snapshot.get('schema_version', 1) != 1):
                unsupported = True
            else:
                raise ValueError(f'Invalid event snapshot: {exc}') from exc
    for branch in branches:
        if branch.get('parent_id') is not None and branch['parent_id'] not in branch_ids:
            raise ValueError('Branch parent is missing')
        if branch.get('anchor_id') is not None and branch['anchor_id'] not in ids:
            raise ValueError('Branch anchor is missing')
        seen = {branch['id']}
        parent = branch.get('parent_id')
        by_id = {b['id']: b for b in branches}
        while parent is not None:
            if parent in seen:
                raise ValueError('Cyclic branch ancestry')
            seen.add(parent)
            parent = by_id[parent].get('parent_id')
    for field in ('selection', 'playback_ids'):
        references = result.get(field, [])
        if not isinstance(references, list) or any(not isinstance(i, str) for i in references):
            raise ValueError(f'{field} must be an array of event IDs')
        if len(references) != len(set(references)):
            raise ValueError(f'{field} contains duplicate event IDs')
        if any(i not in ids for i in references):
            raise ValueError(f'{field} references missing events')
        positions = [next(index for index, event in enumerate(history) if event['id'] == item) for item in references]
        if positions and positions != list(range(positions[0], positions[0] + len(positions))):
            raise ValueError(f'{field} must be a contiguous history range')
    active_branch = result.get('active_branch')
    if ((active_branch is not None and (not isinstance(active_branch, str) or active_branch not in branch_ids))
            or (branch_ids and active_branch is None)):
        raise ValueError('Active branch references a missing branch')
    mode = result.get('mode', 'generate')
    if not isinstance(mode, str) or mode not in ('idle', 'generate', 'replay', 'loop'):
        raise ValueError('Invalid saved playback mode')
    cursor = result.get('cursor', 0)
    if type(cursor) is not int or cursor < 0:
        raise ValueError('Invalid saved playback cursor')
    playback_ids = result.get('playback_ids', [])
    if mode in ('replay', 'loop'):
        if cursor > len(playback_ids):
            raise ValueError('Playback cursor is outside the frozen event range')
    elif cursor > len(history):
        raise ValueError('History cursor is outside recorded history')
    if type(result.get('override', False)) is not bool:
        raise ValueError('Invalid live timing override flag')
    if result.get('engine') is not None:
        try:
            Engine.restore(result['engine'])
        except ValueError:
            if future or (isinstance(result['engine'], dict) and result['engine'].get('schema_version', 1) != 1):
                unsupported = True
            else:
                raise
    result['continuation_supported'] = not unsupported
    result['compatibility_warning'] = 'Future session/engine format: inspection and replay only.' if unsupported else ''
    result['schema_version'] = version
    # Loading always remains silent; controller must also enforce this.
    result['phase'] = 'Idle'
    result['pause_pending'] = False
    return result


def _atomic_json(path, document):
    destination = Path(path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=destination.parent, prefix='.' + destination.name + '.', suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            # Keep a readable top-level object and one inspectable event per
            # line. Encoding each event separately bounds GIL-held C encoder
            # work; a monolithic dumps(10k events) can delay note-off.
            stream.write('{\n')
            for field_index, (key, value) in enumerate(document.items()):
                if field_index:
                    stream.write(',\n')
                stream.write('  ' + json.dumps(key) + ': ')
                if key == 'history':
                    stream.write('[\n')
                    for index, event in enumerate(value):
                        if index:
                            stream.write(',\n')
                        stream.write('    ' + json.dumps(event, allow_nan=False, separators=(',', ':')))
                    stream.write('\n  ]')
                else:
                    stream.write(json.dumps(value, allow_nan=False, indent=2))
            stream.write('\n}\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def save(path, view):
    document = dict(view)
    document.setdefault('schema_version', SCHEMA_VERSION)
    if type(document['schema_version']) is not int or document['schema_version'] != SCHEMA_VERSION:
        raise ValueError('Cannot save an unsupported session schema as the current version')
    validated = validate_session(document)
    if not validated['continuation_supported']:
        raise ValueError('Cannot save a session with an unsupported engine snapshot')
    _atomic_json(path, document)


def load(path):
    try:
        return validate_session(json.loads(Path(path).read_text(encoding='utf-8'),
                                            parse_constant=lambda value: (_ for _ in ()).throw(ValueError(f'Invalid JSON number {value}'))))
    except (KeyError, TypeError, AttributeError, OverflowError, RecursionError) as exc:
        raise ValueError(f'Malformed session: {exc}') from exc


def save_preset(path, config):
    from glittering_stars.domain import Config
    values = config.to_dict() if hasattr(config, 'to_dict') else config
    Config.from_dict(values).validate()
    _atomic_json(path, {'preset_version': 1, 'config': values})


def load_preset(path):
    from glittering_stars.domain import Config
    document = json.loads(Path(path).read_text(encoding='utf-8'))
    if 'preset_version' in document and document['preset_version'] != 1:
        raise ValueError('Unsupported preset version')
    return Config.from_dict(document.get('config', document))
