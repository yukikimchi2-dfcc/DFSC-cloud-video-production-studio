// Dream Factory title card as a ChatCut Motion Graphic (editable per timeline item).
// Mirrors studio/gfx.py: navy box / green box / white tag / big serif (white or green).
// Props: text ("[...]" = green keyword), style, size, emoji (right), emoji2 (left), exitAt (frames).
const DFTitle = ({ item }) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();
  const p = item.props || {};
  const style = p.style || 'navy';
  const size = Number(p.size) || 108;
  const text = String(p.text || '');
  const emoji = p.emoji || '';
  const emoji2 = p.emoji2 || '';
  const dur = Number(p.exitAt) > 0 ? Number(p.exitAt) : durationInFrames;

  const W = 1080;
  const H = 360;
  const scale = Math.min((item?.width || W) / W, (item?.height || H) / H);
  const clamp = { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' };
  const ease = Easing.out(Easing.cubic);

  const chars = [];
  String(text).split(/(\[[^\]]+\])/).forEach((part) => {
    if (!part) return;
    const green = part.startsWith('[');
    Array.from(green ? part.slice(1, -1) : part).forEach((ch) => chars.push({ ch, green }));
  });

  const WHITE = '#F9FAFC';
  const KW = '#6AD969';
  const OUT = '#0C0E14';
  const exitBox = interpolate(frame, [dur - 5, dur], [1, 0.02], clamp);
  const exitText = interpolate(frame, [dur - 5, dur - 2], [1, 0], clamp);

  const Star = ({ s, gold }) => {
    const c = gold ? 'rgba(255,220,140,1)' : 'rgba(255,250,235,1)';
    return (
      <div style={{ position: 'absolute', width: 120, height: 120, left: -60, top: -60,
        transform: 'scale(' + s + ') rotate(' + (s * 20) + 'deg)', opacity: s > 0.02 ? 1 : 0 }}>
        <div style={{ position: 'absolute', left: 0, top: 58, width: 120, height: 4,
          background: 'linear-gradient(90deg, transparent, ' + c + ', transparent)' }} />
        <div style={{ position: 'absolute', left: 58, top: 0, width: 4, height: 120,
          background: 'linear-gradient(180deg, transparent, ' + c + ', transparent)' }} />
        <div style={{ position: 'absolute', left: 45, top: 45, width: 30, height: 30, borderRadius: '50%',
          background: 'radial-gradient(circle, ' + c + ' 0%, rgba(255,240,200,0.5) 35%, transparent 70%)' }} />
      </div>
    );
  };

  const sticker = (ch, delay, px, phase) => {
    if (!ch) return null;
    const t = (frame - delay) / 6;
    if (t <= 0) return <span style={{ width: px, display: 'inline-block' }} />;
    const e = Math.min(1, t);
    let s = (1 - Math.pow(1 - e, 3)) * (1 + 0.18 * Math.sin(Math.PI * e));
    s *= interpolate(frame, [dur - 4, dur], [1, 0], clamp);
    const rot = 5 * Math.sin(2 * Math.PI * 0.6 * frame / fps + phase);
    return (
      <span style={{ display: 'inline-block', fontSize: px, lineHeight: 1, width: px * 1.15, textAlign: 'center',
        transform: 'scale(' + s + ') rotate(' + rot + 'deg)',
        filter: 'drop-shadow(4px 0 0 #fff) drop-shadow(-4px 0 0 #fff) drop-shadow(0 4px 0 #fff) ' +
          'drop-shadow(0 -4px 0 #fff) drop-shadow(0 4px 6px rgba(0,0,0,0.35))' }}>{ch}</span>
    );
  };

  const root = { position: 'absolute', top: 0, left: 0, width: W, height: H, transform: 'scale(' + scale + ')',
    transformOrigin: 'top left', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 18,
    backgroundColor: 'transparent', overflow: 'visible' };

  // ---------------- big serif emphasis ----------------
  if (style === 'serif' || style === 'serifGreen') {
    const fill = style === 'serifGreen' ? KW : WHITE;
    const fade = interpolate(frame, [dur - 4, dur], [1, 0], clamp);
    const stars = [[-0.42, -0.9, 0], [0.38, -0.75, 9], [-0.5, 0.55, 17], [0.47, 0.6, 5], [0.05, -1.05, 23],
      [-0.2, 0.85, 13], [0.25, 0.95, 27]];
    return (
      <div style={root}>
        {sticker(emoji2, 8, 140, 1.3)}
        <div style={{ position: 'relative', display: 'flex', opacity: fade }}>
          {chars.map((c, i) => {
            const pr = interpolate(frame, [2 * i, 2 * i + 5], [0, 1], clamp);
            const s = 1.7 - 0.7 * (1 - Math.pow(1 - pr, 3));
            return (
              <span key={i} style={{ display: 'inline-block', fontFamily: "'Noto Serif TC','Noto Serif CJK TC',serif",
                fontWeight: 900, fontSize: size, lineHeight: 1.1, color: c.green ? KW : fill,
                WebkitTextStroke: (size * 0.05) + 'px ' + OUT, paintOrder: 'stroke fill',
                textShadow: '0 8px 12px rgba(0,0,0,0.6)', transform: 'scale(' + s + ')',
                filter: 'blur(' + ((1 - pr) * 10) + 'px)', opacity: Math.min(1, pr * 1.4) }}>{c.ch}</span>
            );
          })}
          {stars.map(([dx, dy, st], k) => {
            const ph = ((frame - st) % 29 + 29) % 29;
            const s = ph < 17 ? Math.sin(Math.PI * ph / 17) * 0.55 : 0;
            return (
              <div key={'s' + k} style={{ position: 'absolute', left: (50 + dx * 100) + '%', top: (50 + dy * 50) + '%' }}>
                <Star s={frame > st ? s : 0} gold />
              </div>
            );
          })}
        </div>
        {sticker(emoji, 8, 140, 0)}
      </div>
    );
  }

  // ---------------- boxes ----------------
  const isTag = style === 'tag';
  const padX = isTag ? size * 0.6 : size * 0.56;
  const padY = isTag ? size * 0.36 : size * 0.5;
  const bg = style === 'green'
    ? 'linear-gradient(90deg, #54C854 0%, #3A893A 100%)'
    : isTag ? '#EFF1EC'
    : 'repeating-linear-gradient(180deg, rgba(255,255,255,0.05) 0px, rgba(255,255,255,0.05) 3px, transparent 3px, transparent 16px), linear-gradient(180deg, #122648 0%, #0F1A31 100%)';
  const border = style === 'green' ? '2px solid #AAE1AA' : isTag ? 'none' : '2px solid #75777F';
  const grow = interpolate(frame, [0, 5], [0.04, 1], { ...clamp, easing: ease }) * exitBox;
  const n = chars.length;
  const sweepStart = 2.5 + n + 2;
  const sweep = interpolate(frame, [sweepStart, sweepStart + 13], [-30, 130], clamp);
  const glint = frame >= 5 && frame <= 19 ? Math.sin(Math.PI * (frame - 5) / 14) : 0;
  const emojiPx = Math.round(size * 1.3 + 10);

  return (
    <div style={root}>
      {sticker(emoji2, 7, emojiPx, 1.3)}
      <div style={{ position: 'relative', transform: 'scaleX(' + grow + ')', opacity: frame < 2 ? 0.75 : 1 }}>
        <div style={{ position: 'relative', background: bg, border: border, padding: padY + 'px ' + padX + 'px',
          overflow: 'hidden', opacity: isTag ? 0.94 : 1, display: 'flex', whiteSpace: 'nowrap' }}>
          {chars.map((c, i) => {
            const a = interpolate(frame, [2.5 + i, 4.5 + i], [0, 1], clamp) * exitText;
            const col = isTag ? (c.green ? '#969696' : '#181818') : (style === 'green' ? WHITE : (c.green ? KW : WHITE));
            return (
              <span key={i} style={{ fontFamily: "'Noto Sans TC','Noto Sans CJK TC',sans-serif", fontWeight: 900,
                fontSize: size, lineHeight: 1, color: col, opacity: a, whiteSpace: 'pre' }}>{c.ch}</span>
            );
          })}
          {!isTag && (
            <div style={{ position: 'absolute', top: 0, bottom: 0, left: sweep + '%', width: '30%',
              background: 'linear-gradient(105deg, transparent 30%, rgba(255,255,255,0.28) 50%, transparent 70%)' }} />
          )}
        </div>
        {!isTag && (
          <div style={{ position: 'absolute', right: 0, top: 0 }}><Star s={glint * 0.8} /></div>
        )}
      </div>
      {sticker(emoji, 7, emojiPx, 0)}
    </div>
  );
};
