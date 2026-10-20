"""Character-level forced alignment for Mandarin transcripts.

Whisper word timestamps drift by 0.2-0.3 s, which is enough to leave a stray
syllable at a jump cut. This re-times every transcript word with CTC forced
alignment (wav2vec2 XLSR Chinese model, Viterbi over the CTC trellis).

usage: python align.py <transcript.json> <audio16k.wav> <out.json>
"""
import json
import re
import sys
import wave

import numpy as np
import opencc
import torch
from transformers import Wav2Vec2ForCTC, Wav2Vec2Processor

MODEL = "jonatasgrosman/wav2vec2-large-xlsr-53-chinese-zh-cn"
SR = 16000
DIGITS = "零一二三四五六七八九"


def num_to_zh(n):
    n = int(n)
    if n < 10:
        return DIGITS[n]
    if n < 20:
        return "十" + (DIGITS[n % 10] if n % 10 else "")
    if n < 100:
        return DIGITS[n // 10] + "十" + (DIGITS[n % 10] if n % 10 else "")
    if n < 1000:
        r = DIGITS[n // 100] + "百"
        return r + (num_to_zh(n % 100) if n % 100 >= 10 else ("零" + DIGITS[n % 100] if n % 100 else ""))
    if n < 10000:
        r = DIGITS[n // 1000] + "千"
        return r + ("" if n % 1000 == 0 else ("零" + num_to_zh(n % 1000) if n % 1000 < 100 else num_to_zh(n % 1000)))
    return "".join(DIGITS[int(c)] for c in str(n))


def ctc_align(logp, tokens, blank):
    """Viterbi CTC forced alignment. logp: (T, V) log-probs. Returns per-token (start, end) frames."""
    T = logp.shape[0]
    S = 2 * len(tokens) + 1
    ext = np.full(S, blank)
    ext[1::2] = tokens
    NEG = -1e10
    dp = np.full((T, S), NEG, np.float32)
    bp = np.zeros((T, S), np.int8)
    dp[0, 0] = logp[0, blank]
    if S > 1:
        dp[0, 1] = logp[0, ext[1]]
    allow2 = np.zeros(S, bool)
    allow2[3::2] = ext[3::2] != ext[1:-2:2]
    for t in range(1, T):
        prev = dp[t - 1]
        c0 = prev
        c1 = np.concatenate([[NEG], prev[:-1]])
        c2 = np.where(allow2, np.concatenate([[NEG, NEG], prev[:-2]]), NEG)
        stack = np.stack([c0, c1, c2])
        arg = stack.argmax(0)
        dp[t] = stack[arg, np.arange(S)] + logp[t, ext]
        bp[t] = arg
    s = S - 1 if dp[-1, S - 1] >= dp[-1, S - 2] else S - 2
    path = np.zeros(T, np.int32)
    for t in range(T - 1, -1, -1):
        path[t] = s
        s -= int(bp[t, s])
    spans = []
    for k in range(len(tokens)):
        fr = np.where(path == 2 * k + 1)[0]
        spans.append((int(fr[0]), int(fr[-1]) + 1) if len(fr) else None)
    return spans


def main(tr_path, wav_path, out_path):
    tr = json.load(open(tr_path))
    wf = wave.open(wav_path)
    audio = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(np.float32) / 32768
    proc = Wav2Vec2Processor.from_pretrained(MODEL)
    model = Wav2Vec2ForCTC.from_pretrained(MODEL).eval()
    vocab = proc.tokenizer.get_vocab()
    blank = proc.tokenizer.pad_token_id
    t2s = opencc.OpenCC("t2s")

    segs = tr["segments"]
    # group segments into blocks separated by gaps, align each block as a whole
    blocks, cur = [], [0]
    for i in range(1, len(segs)):
        if segs[i]["start"] - segs[i - 1]["end"] > 0.3 or segs[i]["end"] - segs[cur[0]]["start"] > 25:
            blocks.append(cur); cur = []
        cur.append(i)
    blocks.append(cur)

    for b in blocks:
        s0 = max(0.0, segs[b[0]]["start"] - 0.3)
        s1 = min(len(audio) / SR, segs[b[-1]]["end"] + 0.3)
        x = audio[int(s0 * SR):int(s1 * SR)]
        with torch.no_grad():
            inp = proc(x, sampling_rate=SR, return_tensors="pt")
            logits = model(inp.input_values).logits[0]
        logp = torch.log_softmax(logits, -1).numpy()
        frame = (s1 - s0) / logp.shape[0]
        # token list with back-references to (segment, word)
        toks, refs = [], []
        for si in b:
            for wi, w in enumerate(segs[si]["words"]):
                txt = t2s.convert(w["w"].strip())
                txt = re.sub(r"\d+", lambda m: num_to_zh(m.group()), txt)
                for ch in txt:
                    if ch in vocab:
                        toks.append(vocab[ch]); refs.append((si, wi))
        if not toks:
            continue
        spans = ctc_align(logp, np.array(toks), blank)
        timing, chars = {}, {}
        for (si, wi), sp, tk in zip(refs, spans, toks):
            if sp is None:
                continue
            a, e = s0 + sp[0] * frame, s0 + sp[1] * frame
            chars.setdefault((si, wi), []).append([proc.tokenizer.convert_ids_to_tokens(int(tk)), round(a, 3)])
            if (si, wi) in timing:
                timing[(si, wi)][1] = e
            else:
                timing[(si, wi)] = [a, e]
        for si in b:
            for wi, w in enumerate(segs[si]["words"]):
                if (si, wi) in timing:
                    w["s_asr"], w["e_asr"] = w["s"], w["e"]
                    w["s"], w["e"] = round(timing[(si, wi)][0], 3), round(timing[(si, wi)][1], 3)
                    w["aligned"] = True
                    w["chars"] = chars[(si, wi)]
        print(f"block {s0:7.2f}-{s1:7.2f}  {len(toks)} tokens", flush=True)
    json.dump(tr, open(out_path, "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main(*sys.argv[1:4])
