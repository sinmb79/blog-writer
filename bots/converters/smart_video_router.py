"""
bots/converters/smart_video_router.py [NEW]

Budget-aware video engine selection and fallback router.

Selection logic:
  1. Kling free credits remaining? → use Kling
  2. Budget allows paid? → cheapest quality engine
  3. Daily limit hit? → FFmpeg fallback
  4. Any engine fails? → next in priority (no retry on same)

Usage:
  from bots.converters.smart_video_router import SmartVideoRouter
  router = SmartVideoRouter(resolved_config)
  engine = router.select(duration_sec=30, needs_audio=True)
  path   = router.generate(prompt, engine, '/tmp/out.mp4')

Test mode:
  python -m bots.converters.smart_video_router --test
"""

import json
import logging
import os
import sys
from datetime import date
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()  # load .env from current directory or parents

BASE_DIR = Path(__file__).parent.parent.parent
LOG_DIR = BASE_DIR / 'logs'
DATA_DIR = BASE_DIR / 'data'
STATE_FILE = DATA_DIR / 'video_router_state.json'

LOG_DIR.mkdir(exist_ok=True)
DATA_DIR.mkdir(exist_ok=True)

logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.FileHandler(LOG_DIR / 'smart_video_router.log', encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
    logger.addHandler(handler)
    logger.addHandler(logging.StreamHandler())
    logger.setLevel(logging.INFO)


class SmartVideoRouter:
    """
    Budget-aware video engine selection and fallback.

    Logic:
    1. Kling free credits remaining? → use Kling
    2. Budget allows paid? → cheapest quality engine
    3. Daily limit hit? → FFmpeg fallback
    4. Any engine fails? → next in priority (no retry on same)
    """

    def __init__(self, resolved_config: dict):
        """
        resolved_config: output from ConfigResolver.resolve(), or raw engine.json dict.
        Expects video_generation key with provider/options structure.
        """
        video_cfg = resolved_config.get('video_generation', {})
        opts = video_cfg.get('options', {})
        router_cfg = opts.get('smart_router', {})

        self.priority: list = router_cfg.get(
            'priority', ['kling_free', 'veo3', 'seedance2', 'ffmpeg_slides']
        )
        self.daily_cost_limit_usd: float = router_cfg.get('daily_cost_limit_usd', 0.50)
        self.prefer_free_first: bool = router_cfg.get('prefer_free_first', True)
        self.fallback_engine: str = router_cfg.get('fallback', 'ffmpeg_slides')

        self.engine_opts: dict = opts  # all engine option blocks
        self._cfg: dict = video_cfg      # full video_generation config block
        self.state: dict = self._get_state()

    # ── State management ────────────────────────────────────

    def _get_state(self) -> dict:
        """Load daily state from disk; reset if date has changed."""
        today = str(date.today())
        default = {
            'date': today,
            'cost_usd': 0.0,
            'kling_credits_used': 0,
        }
        if STATE_FILE.exists():
            try:
                saved = json.loads(STATE_FILE.read_text(encoding='utf-8'))
                if saved.get('date') == today:
                    return saved
                # New day — reset counters, keep structure
                logger.info(f"날짜 변경 감지 ({saved.get('date')} → {today}): 라우터 상태 초기화")
            except Exception as e:
                logger.warning(f"상태 파일 읽기 실패: {e}")
        self._save_state(default)
        return default

    def _save_state(self, state: Optional[dict] = None) -> None:
        """Persist router state to data/video_router_state.json."""
        target = state if state is not None else self.state
        try:
            STATE_FILE.write_text(
                json.dumps(target, ensure_ascii=False, indent=2),
                encoding='utf-8',
            )
        except Exception as e:
            logger.warning(f"상태 파일 저장 실패: {e}")

    # ── Engine availability checks ───────────────────────────

    def _has_api_key(self, engine_name_or_cfg) -> bool:
        """Return True if the engine's API key env var is set and non-empty.

        Accepts either an engine name string or a dict with 'api_key_env' key.
        """
        if isinstance(engine_name_or_cfg, dict):
            cfg = engine_name_or_cfg
        else:
            cfg = self.engine_opts.get(engine_name_or_cfg, {})
        key_env = cfg.get('api_key_env', '')
        if not key_env:
            # ffmpeg_slides has no API key requirement
            return True
        return bool(os.getenv(key_env, '').strip())

    def _kling_credits_available(self) -> bool:
        """Return True if Kling free credits are still available today."""
        kling_cfg = self.engine_opts.get('kling_free', {})
        daily_credits = kling_cfg.get('free_daily_credits', 66)
        used = self.state.get('kling_credits_used', 0)
        return used < daily_credits

    def _budget_allows(self, engine_name: str, duration_sec: float) -> bool:
        """Return True if engine cost fits within remaining daily budget."""
        cfg = self.engine_opts.get(engine_name, {})
        cost_per_sec = cfg.get('cost_per_sec', 0)
        if cost_per_sec == 0:
            return True
        estimated_cost = cost_per_sec * duration_sec
        spent = self.state.get('cost_usd', 0.0)
        return (spent + estimated_cost) <= self.daily_cost_limit_usd

    # ── Public API ────────────────────────────────────────────

    def select(self, duration_sec: float, needs_audio: bool) -> str:
        """
        Select best available engine for the given clip duration.
        Returns engine name string (never empty — falls back to ffmpeg_slides).
        """
        self.state = self._get_state()  # refresh in case of date change

        for engine in self.priority:
            if engine == 'ffmpeg_slides':
                logger.info("영상 라우터: ffmpeg_slides 선택 (최종 폴백)")
                return 'ffmpeg_slides'

            if engine == 'kling_free':
                if self._has_api_key('kling_free') and self._kling_credits_available():
                    logger.info("영상 라우터: kling_free 선택 (무료 크레딧 잔여)")
                    return 'kling_free'
                continue

            # Paid engines (veo3, seedance2, ...)
            if self._has_api_key(engine) and self._budget_allows(engine, duration_sec):
                logger.info(f"영상 라우터: {engine} 선택 (예산 내 유료 엔진)")
                return engine

        # Final safety net
        logger.info("영상 라우터: ffmpeg_slides 최종 폴백 선택")
        return self.fallback_engine

    def generate(self, prompt, engine: str, output_path: str) -> str:
        """
        Generate a video clip using the specified engine.

        prompt: ComposedPrompt object with .text attribute, or plain str.
        Returns path to output MP4, or '' on failure.
        """
        # Normalise prompt to str
        if hasattr(prompt, 'text'):
            prompt_text = prompt.text
        else:
            prompt_text = str(prompt)

        logger.info(f"영상 생성 시작: 엔진={engine}, 출력={output_path}")

        if engine == 'kling_free':
            result = self._generate_kling(prompt_text, output_path)
        elif engine == 'ffmpeg_slides':
            result = self._generate_ffmpeg(prompt_text, output_path)
        else:
            # veo3, seedance2, runway — V3.1 구현 예정, ffmpeg_slides로 자동 폴백
            logger.warning(f"{engine} 구현 미완성 — ffmpeg_slides로 자동 폴백")
            result = self._generate_ffmpeg(prompt_text, output_path)

        if result:
            # Update cost tracking
            cfg = self.engine_opts.get(engine, {})
            cost_per_sec = cfg.get('cost_per_sec', 0)
            if cost_per_sec > 0:
                # Estimate 30s clip cost as a rough default
                self.state['cost_usd'] = round(
                    self.state.get('cost_usd', 0.0) + cost_per_sec * 30, 4
                )
                self._save_state()
            logger.info(f"영상 생성 완료: {result}")
        else:
            logger.warning(f"영상 생성 실패: 엔진={engine}")

        return result

    def on_failure(self, engine: str, error: str) -> str:
        """Called when engine fails. Returns next available engine."""
        logger.warning(f"[영상] 엔진 실패: {engine} — {error}")

        priority = self._cfg.get('options', {}).get('smart_router', {}).get(
            'priority', ['kling_free', 'veo3', 'seedance2', 'ffmpeg_slides']
        )

        # Find next available engine after the failed one
        try:
            idx = priority.index(engine)
            candidates = priority[idx + 1:]
        except ValueError:
            candidates = priority

        for candidate in candidates:
            if candidate == 'ffmpeg_slides':
                return 'ffmpeg_slides'  # always available
            engine_opts = self._cfg.get('options', {}).get(candidate, {})
            api_key_env = engine_opts.get('api_key_env', '')
            if self._has_api_key({'api_key_env': api_key_env}):
                logger.info(f"[영상] 다음 엔진으로 전환: {candidate}")
                return candidate

        logger.warning("[영상] 사용 가능한 엔진 없음 — ffmpeg_slides로 폴백")
        return 'ffmpeg_slides'

    # ── Engine implementations ────────────────────────────────

    def _generate_kling(self, prompt_text: str, output_path: str) -> str:
        """
        Kling free tier stub implementation.

        The actual Kling API integration is pending (V3.1).
        For now, log that the call would be made and fall back to ffmpeg_slides.
        """
        api_key = os.getenv('KLING_API_KEY', '')
        if not api_key:
            logger.warning("KLING_API_KEY 미설정 — ffmpeg_slides 폴백")
            return self._generate_ffmpeg(prompt_text, output_path)

        kling_cfg = self.engine_opts.get('kling_free', {})
        api_url = kling_cfg.get('api_url', 'https://api.klingai.com/v1')

        # Stub: log what would happen, then fall back
        logger.info(
            f"[스텁] Kling API 호출 예정: POST {api_url}/videos/text2video "
            f"(프롬프트: {prompt_text[:60]}...) — 실제 통합 V3.1에서 구현 예정"
        )
        logger.info("Kling 스텁 실행 — ffmpeg_slides로 폴백하여 영상 생성")

        # Track credit usage even for stub (as if 1 credit consumed per call)
        self.state['kling_credits_used'] = self.state.get('kling_credits_used', 0) + 1
        self._save_state()

        return self._generate_ffmpeg(prompt_text, output_path)

    def _generate_ffmpeg(self, prompt_text: str, output_path: str) -> str:
        """
        Generate a minimal single-scene video using FFmpegSlidesEngine.
        Accepts a plain text prompt and wraps it into a scene list.
        """
        try:
            from bots.converters.video_engine import FFmpegSlidesEngine
            ffmpeg_cfg = self.engine_opts.get('ffmpeg_slides', {})
            engine = FFmpegSlidesEngine(ffmpeg_cfg)

            # Wrap prompt into minimal scene structure expected by FFmpegSlidesEngine
            scenes = [
                {
                    'text': prompt_text[:200],  # truncate if very long
                    'type': 'headline',
                }
            ]
            return engine.generate(scenes, output_path)
        except Exception as e:
            logger.error(f"FFmpegSlidesEngine 실패: {e}")
            return ''


# ── Module entry point (--test mode) ─────────────────────────

def _load_engine_config() -> dict:
    """Load engine.json from config directory."""
    config_path = BASE_DIR / 'config' / 'engine.json'
    try:
        return json.loads(config_path.read_text(encoding='utf-8'))
    except Exception as e:
        logger.error(f"engine.json 로드 실패: {e}")
        return {}


def _run_test() -> None:
    """Print current router state and selected engine for a 30s clip."""
    print("=" * 60)
    print("SmartVideoRouter - 테스트 모드")
    print("=" * 60)

    config = _load_engine_config()
    if not config:
        print("[오류] engine.json 로드 실패")
        sys.exit(1)

    router = SmartVideoRouter(config)

    print("\n[현재 상태]")
    state = router._get_state()
    for k, v in state.items():
        print(f"  {k}: {v}")

    print("\n[엔진 우선순위]")
    for i, eng in enumerate(router.priority, 1):
        has_key = router._has_api_key(eng)
        key_env = router.engine_opts.get(eng, {}).get('api_key_env', '(없음)')
        print(f"  {i}. {eng} - API키={key_env} 설정됨={has_key}")

    print("\n[30초 클립 엔진 선택]")
    selected = router.select(duration_sec=30, needs_audio=True)
    print(f"  → 선택된 엔진: {selected}")

    cost_spent = state.get('cost_usd', 0.0)
    cost_limit = router.daily_cost_limit_usd
    kling_used = state.get('kling_credits_used', 0)
    kling_limit = router.engine_opts.get('kling_free', {}).get('free_daily_credits', 66)
    print(f"\n[예산 현황]")
    print(f"  일일 비용: ${cost_spent:.4f} / ${cost_limit:.2f}")
    print(f"  Kling 크레딧: {kling_used} / {kling_limit} 사용")
    print("=" * 60)


if __name__ == '__main__':
    if '--test' in sys.argv:
        _run_test()
    else:
        print("사용법: python -m bots.converters.smart_video_router --test")
