"""
bots/shorts/caption_renderer.py
역할: 단어별 타임스탬프 → ASS 자막 파일 생성 (단어별 하이라이트)

스타일:
  - 기본: 흰색 볼드, 검정 아웃라인 3px
  - 하이라이트: 노란색 (#FFD700) — 현재 발음 중인 단어
  - 훅 텍스트: 중앙 상단, 72px, 1.5초 표시
  - 본문 자막: 하단 200px, 48px, 최대 2줄

출력:
  data/shorts/captions/{timestamp}.ass
"""
import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent.parent.parent

CAPTION_TEMPLATES = {
    'hormozi': {
        'font_size': 64,
        'highlight_color': '#FFD700',
        'animation': 'pop_in',
        'position': 'center',
        'outline_width': 4,
        'auto_emoji': False,
    },
    'tiktok_viral': {
        'font_size': 56,
        'highlight_color': '#FF6B6B',
        'animation': 'bounce',
        'auto_emoji': True,
        'position': 'center_bottom',
    },
    'brand_4thpath': {
        'font_size': 52,
        'highlight_color': '#00D4FF',
        'animation': 'typewriter',
        'position': 'center',
        'overlay_gradient': True,
    },
}

# Corner → caption template mapping
CORNER_CAPTION_MAP = {
    '쉬운세상': 'hormozi',
    '숨은보물': 'tiktok_viral',
    '바이브리포트': 'hormozi',
    '팩트체크': 'brand_4thpath',
    '한컷': 'tiktok_viral',
    '웹소설': 'brand_4thpath',
}


def smart_line_break(text: str, max_chars: int = 18) -> list[str]:
    """
    Break Korean text at semantic boundaries, not mid-word.
    Never break before 조사 (particles) or 어미 (endings).

    Returns list of line strings.
    """
    # Common Korean particles/endings that should not start a new line
    PARTICLES = ['은', '는', '이', '가', '을', '를', '의', '에', '에서', '으로', '로',
                 '과', '와', '도', '만', '까지', '부터', '보다', '처럼', '같이',
                 '한테', '에게', '이라', '라고', '이고', '이며', '고', '며', '면',
                 '이면', '이나', '나', '든지', '거나', '지만', '이지만', '지만',
                 '니까', '으니까', '이니까', '서', '아서', '어서', '며', '고']

    if len(text) <= max_chars:
        return [text] if text else []

    lines = []
    remaining = text

    while len(remaining) > max_chars:
        # Find best break point near max_chars
        break_at = max_chars

        # Look for space or punctuation near the limit
        for i in range(max_chars, max(0, max_chars - 6), -1):
            if i >= len(remaining):
                continue
            char = remaining[i]
            prev_char = remaining[i-1] if i > 0 else ''
            next_char = remaining[i+1] if i+1 < len(remaining) else ''

            # Break at space
            if char == ' ':
                # Check if next word starts with a particle
                next_word = remaining[i+1:i+4]
                is_particle_start = any(next_word.startswith(p) for p in PARTICLES)
                if not is_particle_start:
                    break_at = i
                    break

            # Break after punctuation
            if prev_char in ('。', '，', ',', '.', '!', '?', '~'):
                break_at = i
                break

        lines.append(remaining[:break_at].strip())
        remaining = remaining[break_at:].strip()

    if remaining:
        lines.append(remaining)

    return [l for l in lines if l]


def get_template_for_corner(corner: str) -> dict:
    """
    Get caption template config for a given content corner.
    Falls back to 'hormozi' template if corner not in map.
    """
    template_name = CORNER_CAPTION_MAP.get(corner, 'hormozi')
    return CAPTION_TEMPLATES.get(template_name, CAPTION_TEMPLATES['hormozi'])


def _load_config() -> dict:
    cfg_path = BASE_DIR / 'config' / 'shorts_config.json'
    if cfg_path.exists():
        return json.loads(cfg_path.read_text(encoding='utf-8'))
    return {}


# ─── 색상 변환 ────────────────────────────────────────────────

def _hex_to_ass(hex_color: str, alpha: int = 0) -> str:
    """
    HTML hex (#RRGGBB) → ASS 색상 &HAABBGGRR 변환.
    ASS는 BGR 순서이며 alpha는 00(불투명)~FF(투명).
    """
    c = hex_color.lstrip('#')
    r, g, b = c[0:2], c[2:4], c[4:6]
    return f'&H{alpha:02X}{b}{g}{r}'


# ─── 시간 포맷 ────────────────────────────────────────────────

def _sec_to_ass_time(seconds: float) -> str:
    """초(float) → ASS 시간 포맷 H:MM:SS.cc."""
    cs = int(round(seconds * 100))
    h = cs // 360000
    cs %= 360000
    m = cs // 6000
    cs %= 6000
    s = cs // 100
    cs %= 100
    return f'{h}:{m:02d}:{s:02d}.{cs:02d}'


# ─── ASS 헤더 ────────────────────────────────────────────────

def _ass_header(cfg: dict) -> str:
    cap_cfg = cfg.get('caption', {})
    font_ko = cap_cfg.get('font_ko', 'Pretendard')
    font_size = cap_cfg.get('font_size', 48)
    hook_size = cap_cfg.get('hook_font_size', 72)
    default_color = _hex_to_ass(cap_cfg.get('default_color', '#FFFFFF'))
    highlight_color = _hex_to_ass(cap_cfg.get('highlight_color', '#FFD700'))
    outline_color = _hex_to_ass(cap_cfg.get('outline_color', '#000000'))
    outline_w = cap_cfg.get('outline_width', 3)
    margin_v = cap_cfg.get('position_from_bottom', 200)

    return f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_ko},{font_size},{default_color},{default_color},{outline_color},&H80000000,-1,0,0,0,100,100,0,0,1,{outline_w},1,2,20,20,{margin_v},1
Style: Highlight,{font_ko},{font_size},{highlight_color},{highlight_color},{outline_color},&H80000000,-1,0,0,0,100,100,0,0,1,{outline_w},1,2,20,20,{margin_v},1
Style: Hook,{font_ko},{hook_size},{default_color},{default_color},{outline_color},&H80000000,-1,0,0,0,100,100,0,0,1,{outline_w+1},2,5,20,20,100,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


# ─── 단어 → 자막 라인 분할 ────────────────────────────────────

def _split_into_lines(words: list[dict], max_chars: int = 18) -> list[list[dict]]:
    """
    단어 리스트 → 라인 리스트 (최대 max_chars 자).
    반환: [[{word, start, end}, ...], ...]
    """
    lines = []
    cur_line: list[dict] = []
    cur_len = 0

    for w in words:
        word_text = w['word']
        if cur_line and cur_len + len(word_text) + 1 > max_chars:
            lines.append(cur_line)
            cur_line = [w]
            cur_len = len(word_text)
        else:
            cur_line.append(w)
            cur_len += len(word_text) + (1 if cur_line else 0)

    if cur_line:
        lines.append(cur_line)

    return lines


def _line_start_end(line: list[dict]) -> tuple[float, float]:
    return line[0]['start'], line[-1]['end']


# ─── ASS 이벤트 생성 ─────────────────────────────────────────

def _word_highlight_event(
    line: list[dict],
    highlight_color_hex: str,
    default_color_hex: str,
    outline_color_hex: str,
    outline_w: int,
) -> str:
    """
    한 라인의 모든 단어에 대해 단어별 하이라이트 오버라이드 태그 생성.
    각 단어 재생 시간 동안 해당 단어만 highlight_color로 표시.
    ASS override tag: {\\c&Hxxxxxx&} 로 색상 변경.

    반환: 단어별 ASS 이벤트 문자열 목록
    """
    hi_ass = _hex_to_ass(highlight_color_hex)
    df_ass = _hex_to_ass(default_color_hex)

    events = []
    for i, w in enumerate(line):
        start_t = w['start']
        end_t = w['end']

        # 전체 라인 텍스트: 현재 단어만 하이라이트
        parts = []
        for j, other in enumerate(line):
            if j == i:
                parts.append(f'{{\\c{hi_ass}}}{other["word"]}{{\\c{df_ass}}}')
            else:
                parts.append(other['word'])
        text = ' '.join(parts)

        event = (
            f'Dialogue: 0,{_sec_to_ass_time(start_t)},{_sec_to_ass_time(end_t)},'
            f'Default,,0,0,0,,{text}'
        )
        events.append(event)

    return '\n'.join(events)


def _hook_event(hook_text: str, duration: float = 1.5) -> str:
    """훅 텍스트 — 중앙 상단, 72px, 1.5초 표시."""
    return (
        f'Dialogue: 1,{_sec_to_ass_time(0.0)},{_sec_to_ass_time(duration)},'
        f'Hook,,0,0,0,,{hook_text}'
    )


# ─── 균등 분할 타임스탬프 폴백 ───────────────────────────────

def _build_uniform_timestamps(script: dict, total_duration: float) -> list[dict]:
    """
    Whisper 타임스탬프 없을 때 텍스트를 균등 시간으로 분할.
    """
    parts = [script.get('hook', '')]
    parts.extend(script.get('body', []))
    parts.append(script.get('closer', ''))
    text = ' '.join(p for p in parts if p)
    words = text.split()

    if not words:
        return []

    dur_per_word = total_duration / len(words)
    return [
        {
            'word': w,
            'start': round(i * dur_per_word, 3),
            'end': round((i + 1) * dur_per_word, 3),
        }
        for i, w in enumerate(words)
    ]


# ─── 메인 엔트리포인트 ────────────────────────────────────────

def render_captions(
    script: dict,
    timestamps: list[dict],
    output_dir: Path,
    timestamp: str,
    wav_duration: float = 0.0,
    cfg: Optional[dict] = None,
    corner: str = '',
) -> Path:
    """
    스크립트 + 단어별 타임스탬프 → ASS 자막 파일 생성.

    Args:
        script:       {hook, body, closer, ...}
        timestamps:   [{word, start, end}, ...] — 비어있으면 균등 분할
        output_dir:   data/shorts/captions/
        timestamp:    파일명 prefix
        wav_duration: TTS 오디오 총 길이 (균등 분할 폴백용)
        cfg:          shorts_config.json dict
        corner:       content corner name (e.g. '쉬운세상') for template selection

    Returns:
        ass_path
    """
    if cfg is None:
        cfg = _load_config()

    output_dir.mkdir(parents=True, exist_ok=True)
    ass_path = output_dir / f'{timestamp}.ass'

    cap_cfg = cfg.get('caption', {})

    # Apply corner-specific template overrides if corner is provided
    if corner:
        template = get_template_for_corner(corner)
        # Override cfg caption section with template values
        cap_cfg = dict(cap_cfg)  # make a shallow copy to avoid mutating original
        if 'font_size' in template:
            cap_cfg['font_size'] = template['font_size']
        if 'highlight_color' in template:
            cap_cfg['highlight_color'] = template['highlight_color']
        if 'outline_width' in template:
            cap_cfg['outline_width'] = template['outline_width']
        logger.info(f'[캡션] 코너 "{corner}" → 템플릿 적용: {template}')

    max_chars = cap_cfg.get('max_chars_per_line_ko', 18)
    highlight_color = cap_cfg.get('highlight_color', '#FFD700')
    default_color = cap_cfg.get('default_color', '#FFFFFF')
    outline_color = cap_cfg.get('outline_color', '#000000')
    outline_w = cap_cfg.get('outline_width', 3)

    # 타임스탬프 없으면 균등 분할
    if not timestamps:
        logger.warning('단어별 타임스탬프 없음 — 균등 분할 사용 (캡션 품질 저하)')
        if wav_duration <= 0:
            wav_duration = 20.0
        timestamps = _build_uniform_timestamps(script, wav_duration)

    # ASS 헤더 (rebuild cfg with updated cap_cfg so header reflects template overrides)
    effective_cfg = dict(cfg)
    effective_cfg['caption'] = cap_cfg
    header = _ass_header(effective_cfg)
    events = []

    # 훅 이벤트 (첫 1.5초 중앙 표시)
    hook_text = script.get('hook', '')
    if hook_text and timestamps:
        hook_end = min(1.5, timestamps[0]['start'] + 1.5) if timestamps else 1.5
        events.append(_hook_event(hook_text, hook_end))

    # 단어별 하이라이트 이벤트
    lines = _split_into_lines(timestamps, max_chars)
    for line in lines:
        if not line:
            continue
        line_event = _word_highlight_event(
            line, highlight_color, default_color, outline_color, outline_w
        )
        events.append(line_event)

    ass_content = header + '\n'.join(events) + '\n'
    ass_path.write_text(ass_content, encoding='utf-8-sig')  # BOM for Windows compatibility
    logger.info(f'ASS 자막 생성: {ass_path.name} ({len(timestamps)}단어, {len(lines)}라인)')


# ── Standalone test ──────────────────────────────────────────────

if __name__ == '__main__':
    import sys
    import tempfile
    from pathlib import Path

    if '--test' not in sys.argv:
        print("사용법: python -m bots.shorts.caption_renderer --test")
        sys.exit(0)

    print("=== Caption Renderer Test ===")

    # Test smart_line_break
    test_texts = [
        ("AI를 활용한 자동화 방법입니다", 18),
        ("단 3가지만 알면 됩니다", 12),
    ]
    print("\n[1] smart_line_break:")
    for text, max_c in test_texts:
        lines = smart_line_break(text, max_c)
        print(f"  입력: {text!r}")
        print(f"  결과: {lines}")

    # Test template lookup
    print("\n[2] get_template_for_corner:")
    for corner in ['쉬운세상', '숨은보물', '팩트체크', '없는코너']:
        tpl = get_template_for_corner(corner)
        print(f"  {corner}: font_size={tpl.get('font_size')}, animation={tpl.get('animation')}")

    # Test render_captions with dummy timestamps
    print("\n[3] render_captions (dry-run):")
    sample_timestamps = [
        {'word': '이거', 'start': 0.0, 'end': 0.3},
        {'word': '모르면', 'start': 0.4, 'end': 0.8},
        {'word': '손해입니다', 'start': 0.9, 'end': 1.5},
    ]
    sample_script = {'hook': '이거 모르면 손해입니다'}
    with tempfile.TemporaryDirectory() as tmpdir:
        out = Path(tmpdir) / 'test.ass'
        render_captions(
            timestamps=sample_timestamps,
            script=sample_script,
            output_path=out,
            corner='쉬운세상',
        )
        exists = out.exists()
        size = out.stat().st_size if exists else 0
        print(f"  ASS 파일 생성: {exists}, 크기: {size}bytes")
        assert exists and size > 0, "ASS 파일 생성 실패"

    print("\n✅ 모든 테스트 통과")
    return ass_path
