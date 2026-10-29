# Implementation decisions

## Major-scale membership correction (2026-10-28)

SPECIFICATION HARM-01 and M5-A2 incorrectly state that C is outside G major. G major is G A B C D E F#. Therefore C-E-F# passes Whole chord fits membership, subject to other constraints. Implementation uses mathematically correct destination scale membership. The rejection fixture uses C#-E-F# instead. The user explicitly confirmed correct major-scale membership on 2026-10-28; no new harmonic rule is inferred from the erroneous example.

## CLI compatibility

The CLI uses a compatibility ChordWalk facade over the same stable-voice Engine as the desktop. All 12 original regression cases pass without assertion changes. Public sorted pitches and mutable legacy Settings remain available; the internal transition path retains stable IDs. New desktop snapshots explicitly use engine version 1. Seeded sequences are repeatable within the new version, with no promise of bit-identical legacy sequences.

## Immutable history performance

The worker publishes a new outer list referencing immutable-by-contract event dictionaries. Neither UI nor persistence may mutate these records. Persistence uses this consistent view on its I/O thread, validates without copying nested events, and encodes one event at a time. Redundant deep copies caused a measured 136 ms stop-the-world pause; the corrected 10,000-event save test measured a 13.6 ms maximum hold error. Branching and edits always append new records.

## MIDI route versus musical revision

output_channel is transport state. A valid idle channel switch affects replay without applying pending musical settings or changing engine/RNG/history. Replay leaves the recorded event's channel untouched. Load restores the channel but closes the actual MIDI handle; reconnect explicitly. Panic sends sustain-off, owned note-offs, then all-notes/all-sound-off. Normal cleanup preserves tails.

## Native timeline presentation

Three stable voice columns in a virtualized QTableView provide compact chord rows with explicit notes, key, timing, decisions, selection and playhead. Timeline/Inspector tabs stay readable at200% scaling. This native model supports10000 events without allocating one widget per event.
