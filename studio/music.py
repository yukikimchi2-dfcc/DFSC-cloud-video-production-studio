"""Original background music, composed as MIDI and rendered with real instrument samples.

Brief (measured from the reference reel's BGM after vocal separation): warm, uplifting
corporate-pop, ~99 BPM, F major; a quiet, sparse piano + warm bass/pad bed for the
first ~2/3 of the talk, then a fuller groove (strings, bass pulse, kick/clap/hats)
for the last third. This piece follows that brief with its own chord progression,
melody and arrangement, so it sounds in the same family without copying it.

Instruments: FluidR3_GM soundfont (MIT licence) -> royalty-free, safe for commercial
use on Facebook / Instagram.

usage (module): render_music(duration, build_at, dip_at, out_wav)
"""
import random
import subprocess

import mido

SF2 = "/usr/share/sounds/sf2/FluidR3_GM.sf2"
BPM = 100
TPB = 480                                   # ticks per beat

CHORDS = {                                  # bass root, close voicing around F3..C5 (MIDI numbers)
    "F": (41, [53, 57, 60, 65]),
    "Am": (45, [52, 57, 60, 64]),
    "Bb": (46, [53, 58, 62, 65]),
    "C": (48, [52, 55, 60, 64]),
    "Dm": (50, [53, 57, 62, 65]),
    "Gm": (43, [55, 58, 62, 67]),
}
PROG_A = ["F", "Am", "Bb", "C"]             # I  iii IV V
PROG_B = ["Dm", "Bb", "F", "C"]             # vi IV  I  V
PROG_C = ["Bb", "C", "Am", "Dm", "Gm", "C", "F", "F"]   # lift into the last section

# melody for the full section, one list per chord: (beat offset, length in beats, pitch)
MELODY = {
    "F": [(0, 1, 69), (1.5, 0.5, 72), (2, 1, 74), (3, 1, 72)],
    "Am": [(0, 1.5, 69), (1.5, 0.5, 67), (2, 2, 64)],
    "Bb": [(0, 1, 70), (1, 0.5, 69), (1.5, 0.5, 67), (2, 1, 65), (3, 1, 67)],
    "C": [(0, 2, 67), (2, 1, 72), (3, 1, 76)],
    "Dm": [(0, 1, 74), (1, 1, 72), (2, 2, 69)],
    "Gm": [(0, 1, 70), (1, 1, 74), (2, 2, 72)],
}


def _sec_to_tick(t):
    return int(round(t * BPM / 60 * TPB))


def compose(duration, build_at, dip_at=None, seed=11):
    rnd = random.Random(seed)
    bar = 4 * 60 / BPM
    nbars = int(duration / bar) + 2
    build_bar = int(round(build_at / bar))
    dip_bar = int(dip_at / bar) if dip_at is not None else -1
    ev = []                                  # (tick, msg)

    def note(ch, t_beats, dur_beats, pitch, vel):
        t0 = int(t_beats * TPB + rnd.randint(-6, 6))
        t1 = int((t_beats + dur_beats) * TPB) - 10
        vel = max(1, min(127, vel + rnd.randint(-5, 5)))
        ev.append((max(0, t0), mido.Message("note_on", channel=ch, note=pitch, velocity=vel)))
        ev.append((max(1, t1), mido.Message("note_off", channel=ch, note=pitch, velocity=0)))

    # programs: 0 piano, 1 pad, 2 bass, 3 strings, 4 bell/vibes melody, 9 drums
    for ch, prog in [(0, 0), (1, 89), (2, 33), (3, 48), (4, 11)]:
        ev.append((0, mido.Message("program_change", channel=ch, program=prog)))
    ev.append((0, mido.Message("control_change", channel=1, control=7, value=70)))
    ev.append((0, mido.Message("control_change", channel=3, control=7, value=78)))
    ev.append((0, mido.Message("control_change", channel=4, control=7, value=72)))
    for ch in range(5):
        ev.append((0, mido.Message("control_change", channel=ch, control=91, value=70)))   # reverb

    chords = []
    while len(chords) < nbars:
        if len(chords) < build_bar:
            chords += PROG_A + PROG_A + PROG_B + PROG_A
        else:
            chords += PROG_C + PROG_A + PROG_B
    chords = chords[:build_bar] + (PROG_C + PROG_A + PROG_B + PROG_A) * 3
    chords = chords[:nbars]

    for b, name in enumerate(chords):
        beat0 = b * 4
        root, voicing = CHORDS[name]
        last = b >= nbars - 2
        full = b >= build_bar and not last
        dip = b == dip_bar
        if last:                               # final bars: one held F chord
            if b == nbars - 2:
                for p in CHORDS["F"][1]:
                    note(0, beat0, 8, p + 12, 52)
                    note(1, beat0, 8, p + 12, 40)
                note(2, beat0, 8, 41, 60)
            continue
        # pad: always, whole bar
        for p in voicing[1:]:                  # an octave up: keeps 150-300 Hz free for the voice
            note(1, beat0, 4, p + 12, 34 if not full else 42)
        if dip:                                # "掉到最谷底": everything else drops out for a bar
            continue
        # piano: sparse syncopated arpeggio in the quiet part, fuller comping later
        if not full:
            for k, (off, idx) in enumerate([(0, 0), (1.5, 1), (2, 2), (3.5, 3)]):
                note(0, beat0 + off, 1.5, voicing[idx] + 12, 46 if k else 52)
        else:
            for off in (0, 1.5, 2.5, 3):
                for p in voicing[1:]:
                    note(0, beat0 + off, 0.45, p + 12, 50)
        # bass: long roots first, eighth-note pulse in the full section
        if not full:
            note(2, beat0, 3.8, root, 62)
        else:
            for k in range(8):
                note(2, beat0 + k * 0.5, 0.45, root + (12 if k == 5 else 0), 78 if k % 2 == 0 else 64)
        # strings + melody + drums only in the full section
        if full:
            for p in voicing[:3]:
                note(3, beat0, 4, p + 12, 58)
            for off, ln, p in MELODY[name]:
                note(4, beat0 + off, ln, p, 74)
            for k in range(4):
                if k in (0, 2):
                    note(9, beat0 + k, 0.4, 36, 92)                       # kick
                if k in (1, 3):
                    note(9, beat0 + k, 0.4, 39, 70)                       # clap
                note(9, beat0 + k + 0.5, 0.2, 42, 52)                     # off-beat hat
                note(9, beat0 + k, 0.2, 42, 38)
            if (b - build_bar) % 2 == 1:
                note(9, beat0 + 3.5, 0.4, 36, 70)
            if b == build_bar:
                note(9, beat0, 2, 49, 72)                                 # crash into the build
        elif b >= 2:                                                      # soft shaker for motion
            for k in range(8):
                note(9, beat0 + k * 0.5, 0.2, 70, 34 if k % 2 else 44)

    ev.sort(key=lambda x: x[0])
    mid = mido.MidiFile(ticks_per_beat=TPB)
    tr = mido.MidiTrack()
    mid.tracks.append(tr)
    tr.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(BPM)))
    last_t = 0
    for t, m in ev:
        tr.append(m.copy(time=t - last_t))
        last_t = t
    return mid


def render_music(duration, build_at, dip_at, out_wav, mid_path=None):
    mid = compose(duration, build_at, dip_at)
    mid_path = mid_path or out_wav.replace(".wav", ".mid")
    mid.save(mid_path)
    subprocess.run(["fluidsynth", "-ni", "-q", "-g", "0.7", "-r", "48000", "-F", out_wav, SF2, mid_path],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return out_wav, mid_path
