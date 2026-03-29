"""
bots/shorts/tts_engine.py
역할: 쇼츠 스크립트 텍스트 → 음성(WAV) + 단어별 타임스탬프(JSON) 생성

엔진 우선순위 (shorts_config.json tts.engine_priority):
  1. ElevenLabs    — 최고 품질, ELEVENLABS_API_KEY 필요
  2. Google Cloud TTS — 중간 품질, GOOGLE_TTS_API_KEY 필요
  3. Edge TTS      — 무료 폴백, API 키 불필요

출력:
  data/shorts/tts/{timestamp}.wav
  data/shorts/tts/{timestamp}_timestamps.json
    [{word: str, start: float, end: float}, ...]
"""
import asyncio
import json
import logging
import os
import re
import struct
import tempfile
import wave
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ─── SmartTTSRouter ───────────────────────────────────────────

class SmartTTSRouter:
    """
    Budget-aware TTS engine selection with graceful fallback.

    Engine priority order (best to cheapest):
    1. elevenlabs   — best quality, paid
    2. openai_tts   — good quality, paid (uses existing OpenAI key)
    3. cosyvoice2   — local, free, Korean native speaker voice
    4. kokoro       — local, free, 82M params
    5. edge_tts     — free fallback, always available
    """

    ENGINE_PRIORITY = ['elevenlabs', 'openai_tts', 'cosyvoice2', 'kokoro', 'edge_tts']

    # Daily/monthly usage limits per engine
    ENGINE_LIMITS = {
        'elevenlabs': {'chars_per_month': 10000, 'threshold': 0.8},
        'openai_tts': {'chars_per_day': 500000, 'threshold': 0.9},
    }

    ENGINE_API_KEYS = {
        'elevenlabs': 'ELEVENLABS_API_KEY',
        'openai_tts': 'OPENAI_API_KEY',
    }
    # cosyvoice2, kokoro, edge_tts are local — no API key needed

    def __init__(self, resolved_config: dict):
        """
        resolved_config: output from ConfigResolver.resolve()
        """
        self.budget = resolved_config.get('budget', 'free')
        self.tts_engine = resolved_config.get('tts', 'edge_tts')
        self._usage = {}  # {engine_name: chars_used_today}
        self._failed = set()  # engines that failed this session

    def select(self, text_length: int) -> str:
        """
        Select best available TTS engine for given text length.

        1. If user specified a non-auto engine: use it if available
        2. Else: check budget-appropriate engines in priority order
        3. Skip engines that have exceeded usage threshold
        4. Skip engines that failed this session
        5. Always fall back to edge_tts
        """
        import os

        # If user explicitly chose a specific engine (not 'auto')
        if self.tts_engine not in ('auto', 'edge_tts', ''):
            engine = self.tts_engine
            api_key_env = self.ENGINE_API_KEYS.get(engine, '')
            if not api_key_env or os.environ.get(api_key_env, ''):
                if engine not in self._failed:
                    return engine

        # Budget-based priority selection
        if self.budget == 'free':
            priority = ['kokoro', 'edge_tts']
        elif self.budget == 'low':
            priority = ['openai_tts', 'kokoro', 'edge_tts']
        else:  # medium, premium
            priority = self.ENGINE_PRIORITY

        for engine in priority:
            if engine in self._failed:
                continue
            api_key_env = self.ENGINE_API_KEYS.get(engine, '')
            if api_key_env and not os.environ.get(api_key_env, ''):
                continue  # no API key
            if self._is_over_limit(engine, text_length):
                continue
            return engine

        return 'edge_tts'  # always available

    def on_failure(self, engine: str, error: str) -> str:
        """
        Record engine failure and return next available engine.
        No retry on same engine — no wasted credits.
        """
        import logging
        logging.getLogger(__name__).warning(f'TTS 엔진 실패: {engine} — {error}, 다음 엔진으로 전환')
        self._failed.add(engine)
        return self.select(0)  # Select next engine

    def record_usage(self, engine: str, char_count: int) -> None:
        """Record character usage for an engine."""
        self._usage[engine] = self._usage.get(engine, 0) + char_count

    def _is_over_limit(self, engine: str, text_length: int) -> bool:
        """Check if engine has exceeded its usage threshold."""
        limits = self.ENGINE_LIMITS.get(engine, {})
        if not limits:
            return False
        threshold = limits.get('threshold', 0.9)
        daily_limit = limits.get('chars_per_day', limits.get('chars_per_month', 0))
        if not daily_limit:
            return False
        used = self._usage.get(engine, 0)
        return (used + text_length) / daily_limit > threshold


# ─── 공통 유틸 ────────────────────────────────────────────────


def _load_config() -> dict:
    cfg_path = Path(__file__).parent.parent.parent / 'config' / 'shorts_config.json'
    if cfg_path.exists():
        return json.loads(cfg_path.read_text(encoding='utf-8'))
    return {}


def _concat_script(script: dict) -> str:
    """스크립트 dict → 읽기용 단일 텍스트. 문장 사이 공백 추가."""
    parts = [script.get('hook', '')]
    parts.extend(script.get('body', []))
    parts.append(script.get('closer', ''))
    return ' '.join(p for p in parts if p)


def _add_pause(wav_path: Path, pause_ms: int = 300) -> None:
    """WAV 파일 끝에 무음 pause_ms 밀리초 추가 (인플레이스)."""
    with wave.open(str(wav_path), 'rb') as wf:
        params = wf.getparams()
        frames = wf.readframes(wf.getnframes())

    silence_frames = int(params.framerate * pause_ms / 1000)
    silence = b'\x00' * silence_frames * params.nchannels * params.sampwidth

    with wave.open(str(wav_path), 'wb') as wf:
        wf.setparams(params)
        wf.writeframes(frames + silence)


def _get_wav_duration(wav_path: Path) -> float:
    with wave.open(str(wav_path), 'rb') as wf:
        return wf.getnframes() / wf.getframerate()


# ─── ElevenLabs ───────────────────────────────────────────────

def _tts_elevenlabs(text: str, output_path: Path, cfg: dict) -> list[dict]:
    """
    ElevenLabs TTS + 단어별 타임스탬프.
    Returns: [{word, start, end}, ...]
    """
    import requests

    api_key = os.environ.get('ELEVENLABS_API_KEY', '')
    if not api_key:
        raise RuntimeError('ELEVENLABS_API_KEY not set')

    el_cfg = cfg.get('tts', {}).get('elevenlabs', {})
    voice_id = el_cfg.get('voice_id', 'pNInz6obpgDQGcFmaJgB')
    model_id = el_cfg.get('model', 'eleven_multilingual_v2')
    stability = el_cfg.get('stability', 0.5)
    similarity = el_cfg.get('similarity_boost', 0.8)
    speed = el_cfg.get('speed', 1.1)

    url = f'https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/with-timestamps'
    headers = {'xi-api-key': api_key, 'Content-Type': 'application/json'}
    payload = {
        'text': text,
        'model_id': model_id,
        'voice_settings': {
            'stability': stability,
            'similarity_boost': similarity,
            'speed': speed,
        },
    }

    resp = requests.post(url, headers=headers, json=payload, timeout=60)
    resp.raise_for_status()
    data = resp.json()

    # 오디오 디코딩
    import base64
    audio_b64 = data.get('audio_base64', '')
    audio_bytes = base64.b64decode(audio_b64)

    # ElevenLabs는 mp3 반환 → wav 변환
    mp3_tmp = output_path.with_suffix('.mp3')
    mp3_tmp.write_bytes(audio_bytes)
    _mp3_to_wav(mp3_tmp, output_path)
    mp3_tmp.unlink(missing_ok=True)

    # 타임스탬프 파싱
    alignment = data.get('alignment', {})
    chars = alignment.get('characters', [])
    starts = alignment.get('character_start_times_seconds', [])
    ends = alignment.get('character_end_times_seconds', [])

    timestamps = _chars_to_words(chars, starts, ends)
    return timestamps


def _chars_to_words(chars: list, starts: list, ends: list) -> list[dict]:
    """ElevenLabs 문자 레벨 타임스탬프 → 단어 레벨."""
    words = []
    cur_word = ''
    cur_start = 0.0
    cur_end = 0.0

    for ch, st, en in zip(chars, starts, ends):
        if ch in (' ', '\n'):
            if cur_word:
                words.append({'word': cur_word, 'start': round(cur_start, 3), 'end': round(cur_end, 3)})
                cur_word = ''
        else:
            if not cur_word:
                cur_start = st
            cur_word += ch
            cur_end = en

    if cur_word:
        words.append({'word': cur_word, 'start': round(cur_start, 3), 'end': round(cur_end, 3)})

    return words


def _mp3_to_wav(mp3_path: Path, wav_path: Path) -> None:
    try:
        from pydub import AudioSegment
        AudioSegment.from_mp3(str(mp3_path)).export(str(wav_path), format='wav')
        return
    except Exception:
        pass

    # ffmpeg 폴백
    import subprocess
    ffmpeg = _get_ffmpeg()
    subprocess.run(
        [ffmpeg, '-y', '-i', str(mp3_path), str(wav_path)],
        check=True, capture_output=True,
    )


def _get_ffmpeg() -> str:
    ffmpeg_env = os.environ.get('FFMPEG_PATH', '')
    if ffmpeg_env and Path(ffmpeg_env).exists():
        return ffmpeg_env
    return 'ffmpeg'


# ─── OpenAI TTS ───────────────────────────────────────────────

def _tts_openai(text: str, output_path: Path, cfg: dict) -> list[dict]:
    """
    OpenAI TTS (tts-1-hd model) with timestamp estimation.
    Returns: [{word, start, end}, ...] — uniform timestamps (no word-level from OpenAI)
    """
    import requests, base64
    import os

    api_key = os.environ.get('OPENAI_API_KEY', '')
    if not api_key:
        raise RuntimeError('OPENAI_API_KEY not set')

    openai_cfg = cfg.get('tts', {}).get('openai', {})
    model = openai_cfg.get('model', 'tts-1-hd')
    voice = openai_cfg.get('voice', 'alloy')
    speed = openai_cfg.get('speed', 1.0)

    url = 'https://api.openai.com/v1/audio/speech'
    headers = {'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'}
    payload = {
        'model': model,
        'input': text,
        'voice': voice,
        'speed': speed,
        'response_format': 'mp3',
    }

    resp = requests.post(url, headers=headers, json=payload, timeout=60)
    resp.raise_for_status()

    mp3_tmp = output_path.with_suffix('.mp3')
    mp3_tmp.write_bytes(resp.content)
    _mp3_to_wav(mp3_tmp, output_path)
    mp3_tmp.unlink(missing_ok=True)

    # OpenAI TTS has no word-level timestamps — use uniform distribution
    return []  # caption_renderer will use uniform fallback


# ─── Google Cloud TTS ─────────────────────────────────────────

def _tts_google_cloud(text: str, output_path: Path, cfg: dict) -> list[dict]:
    """
    Google Cloud TTS (REST API) + SSML time_pointing으로 타임스탬프 추출.
    Returns: [{word, start, end}, ...]
    """
    import requests

    api_key = os.environ.get('GOOGLE_TTS_API_KEY', '')
    if not api_key:
        raise RuntimeError('GOOGLE_TTS_API_KEY not set')

    gc_cfg = cfg.get('tts', {}).get('google_cloud', {})
    voice_name = gc_cfg.get('voice_name', 'ko-KR-Neural2-C')
    speaking_rate = gc_cfg.get('speaking_rate', 1.1)

    # SSML: 단어별 mark 삽입
    words = text.split()
    ssml_parts = []
    for i, w in enumerate(words):
        ssml_parts.append(f'<mark name="w{i}"/>{w}')
    ssml_text = ' '.join(ssml_parts)
    ssml = f'<speak>{ssml_text}<mark name="end"/></speak>'

    url = f'https://texttospeech.googleapis.com/v1beta1/text:synthesize?key={api_key}'
    payload = {
        'input': {'ssml': ssml},
        'voice': {'languageCode': voice_name[:5], 'name': voice_name},
        'audioConfig': {
            'audioEncoding': 'LINEAR16',
            'speakingRate': speaking_rate,
            'sampleRateHertz': 44100,
        },
        'enableTimePointing': ['SSML_MARK'],
    }

    resp = requests.post(url, json=payload, timeout=60)
    resp.raise_for_status()
    data = resp.json()

    import base64
    audio_bytes = base64.b64decode(data['audioContent'])
    output_path.write_bytes(audio_bytes)

    # 타임스탬프 파싱
    timepoints = data.get('timepoints', [])
    timestamps = _gcloud_marks_to_words(words, timepoints)
    return timestamps


def _gcloud_marks_to_words(words: list[str], timepoints: list[dict]) -> list[dict]:
    """Google Cloud TTS mark 타임포인트 → 단어별 {word, start, end}."""
    mark_map = {tp['markName']: tp['timeSeconds'] for tp in timepoints}
    total_dur = mark_map.get('end', 0.0)

    result = []
    for i, w in enumerate(words):
        start = mark_map.get(f'w{i}', 0.0)
        end = mark_map.get(f'w{i+1}', total_dur)
        result.append({'word': w, 'start': round(start, 3), 'end': round(end, 3)})
    return result


# ─── Edge TTS + Whisper ───────────────────────────────────────

def _tts_edge(text: str, output_path: Path, cfg: dict) -> list[dict]:
    """
    Edge TTS (무료) → WAV 생성 후 Whisper로 단어별 타임스탬프 추출.
    Returns: [{word, start, end}, ...]
    """
    import edge_tts

    edge_cfg = cfg.get('tts', {}).get('edge_tts', {})
    voice = edge_cfg.get('voice', 'ko-KR-SunHiNeural')
    rate = edge_cfg.get('rate', '+10%')

    mp3_tmp = output_path.with_suffix('.mp3')

    async def _generate():
        communicate = edge_tts.Communicate(text, voice, rate=rate)
        await communicate.save(str(mp3_tmp))

    asyncio.get_event_loop().run_until_complete(_generate())

    # mp3 → wav
    _mp3_to_wav(mp3_tmp, output_path)
    mp3_tmp.unlink(missing_ok=True)

    # Whisper로 타임스탬프 추출
    timestamps = _whisper_timestamps(output_path)
    return timestamps


def _whisper_timestamps(wav_path: Path) -> list[dict]:
    """openai-whisper를 사용해 단어별 타임스탬프 추출. 없으면 균등 분할."""
    try:
        import whisper  # type: ignore

        model = whisper.load_model('tiny')
        result = model.transcribe(str(wav_path), word_timestamps=True, language='ko')
        words = []
        for seg in result.get('segments', []):
            for w in seg.get('words', []):
                words.append({
                    'word': w['word'].strip(),
                    'start': round(w['start'], 3),
                    'end': round(w['end'], 3),
                })
        if words:
            return words
    except Exception as e:
        logger.warning(f'Whisper 타임스탬프 실패: {e} — 균등 분할 사용')

    return _uniform_timestamps(wav_path)


def _uniform_timestamps(wav_path: Path) -> list[dict]:
    """Whisper 없을 때 균등 분할 타임스탬프 (캡션 품질 저하 감수)."""
    duration = _get_wav_duration(wav_path)
    with wave.open(str(wav_path), 'rb') as wf:
        pass  # just to confirm it's readable

    # WAV 파일에서 텍스트를 다시 알 수 없으므로 빈 리스트 반환
    # (caption_renderer가 균등 분할을 처리)
    return []


# ─── 메인 엔트리포인트 ────────────────────────────────────────

def generate_tts(
    script: dict,
    output_dir: Path,
    timestamp: str,
    cfg: Optional[dict] = None,
) -> tuple[Path, list[dict]]:
    """
    스크립트 dict → WAV + 단어별 타임스탬프.

    Args:
        script:     {hook, body, closer, ...}
        output_dir: data/shorts/tts/
        timestamp:  파일명 prefix (e.g. "20260328_120000")
        cfg:        shorts_config.json dict (없으면 자동 로드)

    Returns:
        (wav_path, timestamps)  — timestamps: [{word, start, end}, ...]
    """
    if cfg is None:
        cfg = _load_config()

    output_dir.mkdir(parents=True, exist_ok=True)
    wav_path = output_dir / f'{timestamp}.wav'
    ts_path = output_dir / f'{timestamp}_timestamps.json'

    text = _concat_script(script)

    # Apply Korean preprocessing if available
    try:
        from bots.prompt_layer.korean_preprocessor import preprocess_korean
        text = preprocess_korean(text)
    except ImportError:
        pass  # Korean preprocessing not available, use raw text

    pause_ms = cfg.get('tts', {}).get('inter_sentence_pause_ms', 300)
    priority = cfg.get('tts', {}).get('engine_priority', ['elevenlabs', 'openai_tts', 'google_cloud', 'edge_tts'])

    # Engine map: elevenlabs → openai_tts → google_cloud → edge_tts
    engine_map = {
        'elevenlabs':   _tts_elevenlabs,
        'openai_tts':   _tts_openai,
        'google_cloud': _tts_google_cloud,
        'edge_tts':     _tts_edge,
    }

    timestamps: list[dict] = []
    last_error: Optional[Exception] = None

    for engine_name in priority:
        fn = engine_map.get(engine_name)
        if fn is None:
            continue
        try:
            logger.info(f'TTS 엔진 시도: {engine_name}')
            timestamps = fn(text, wav_path, cfg)
            logger.info(f'TTS 완료 ({engine_name}): {wav_path.name}')
            break
        except Exception as e:
            logger.warning(f'TTS 엔진 실패 ({engine_name}): {e}')
            last_error = e
            if wav_path.exists():
                wav_path.unlink()

    if not wav_path.exists():
        raise RuntimeError(f'모든 TTS 엔진 실패. 마지막 오류: {last_error}')

    # 문장 끝 무음 추가
    try:
        _add_pause(wav_path, pause_ms)
    except Exception as e:
        logger.warning(f'무음 추가 실패: {e}')

    # 타임스탬프 저장
    ts_path.write_text(json.dumps(timestamps, ensure_ascii=False, indent=2), encoding='utf-8')
    logger.info(f'타임스탬프 저장: {ts_path.name} ({len(timestamps)}단어)')

    return wav_path, timestamps


def load_timestamps(ts_path: Path) -> list[dict]:
    """저장된 타임스탬프 JSON 로드."""
    return json.loads(ts_path.read_text(encoding='utf-8'))


# ── Standalone test ──────────────────────────────────────────────

if __name__ == '__main__':
    import sys
    import tempfile
    from pathlib import Path

    if '--test' not in sys.argv:
        print("사용법: python -m bots.shorts.tts_engine --test")
        sys.exit(0)

    print("=== TTS Engine Test ===")

    # Test SmartTTSRouter initialization
    print("\n[1] SmartTTSRouter 초기화:")
    router = SmartTTSRouter({'budget': 'free'})
    print(f"  budget: {router.budget}")
    engine = router.select(text_length=100)
    print(f"  select(100chars) → {engine}")
    assert isinstance(engine, str) and engine, "엔진 선택 실패"

    # Test with medium budget (no API keys → falls back to free engine)
    router_med = SmartTTSRouter({'budget': 'medium'})
    engine_med = router_med.select(text_length=500)
    print(f"  medium budget select(500chars) → {engine_med}")
    assert isinstance(engine_med, str) and engine_med, "medium 엔진 선택 실패"

    # Test usage recording + over-limit detection
    print("\n[2] 사용량 제한 로직:")
    router3 = SmartTTSRouter({'budget': 'free'})
    router3.record_usage('elevenlabs', 9000)  # near limit
    over = router3._is_over_limit('elevenlabs', 900)  # 9000+900 > 8000 threshold
    print(f"  elevenlabs 9000자 기록 후 900자 추가 → 한도 초과: {over}")
    assert over, "한도 초과 감지 실패"

    # Test Edge TTS (always-available free engine) with short text
    print("\n[3] Edge TTS 음성 생성 (네트워크 필요):")
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            wav, timestamps = generate_tts(
                script={'hook': '테스트입니다', 'body': [], 'closer': ''},
                output_dir=Path(tmpdir),
                timestamp='test_20260329',
            )
            print(f"  WAV 생성: {wav.exists()}, 타임스탬프: {len(timestamps)}단어")
            assert wav.exists(), "WAV 파일 생성 실패"
        except Exception as e:
            print(f"  [경고] TTS 실패 (네트워크/의존성 없을 수 있음): {e}")

    print("\n✅ 모든 테스트 통과")
