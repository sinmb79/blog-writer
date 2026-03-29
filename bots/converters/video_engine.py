"""
비디오 엔진 추상화 (bots/converters/video_engine.py)
역할: engine.json video_generation 설정에 따라 적절한 영상 생성 엔진 인스턴스 반환
설계서: blog-engine-final-masterplan-v3.txt

지원 엔진:
  - FFmpegSlidesEngine: 기존 shorts_converter.py 파이프라인 (슬라이드 + TTS + ffmpeg)
  - SeedanceEngine: Seedance 2.0 API (AI 영상 생성)
  - RunwayEngine: Runway Gen-3 API
  - VeoEngine: Google Veo 3.1 (미지원 → ffmpeg_slides 폴백)
"""
import json
import logging
import os
import shutil
import subprocess
import tempfile
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv(dotenv_path='D:/key/blog-writer.env.env')

BASE_DIR = Path(__file__).parent.parent.parent
LOG_DIR = BASE_DIR / 'logs'
OUTPUT_DIR = BASE_DIR / 'data' / 'outputs'
ASSETS_DIR = BASE_DIR / 'assets'
BGM_PATH = ASSETS_DIR / 'bgm.mp3'

LOG_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.FileHandler(LOG_DIR / 'video_engine.log', encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
    logger.addHandler(handler)
    logger.addHandler(logging.StreamHandler())
    logger.setLevel(logging.INFO)


# ─── 추상 기본 클래스 ──────────────────────────────────

class VideoEngine(ABC):
    @abstractmethod
    def generate(self, scenes: list, output_path: str, **kwargs) -> str:
        """
        scenes로 영상 생성.

        scenes 형식:
            [
                {
                    "text": str,         # 자막/TTS 텍스트
                    "type": str,         # "intro"|"headline"|"point"|"data"|"outro"
                    "image_prompt": str, # DALL-E 배경 프롬프트 (선택)
                    "slide_path": str,   # 슬라이드 PNG 경로 (있으면 사용)
                    "audio_path": str,   # TTS WAV 경로 (있으면 사용)
                }
            ]

        Returns: 생성된 MP4 파일 경로 (실패 시 빈 문자열)
        """


# ─── FFmpegSlidesEngine ────────────────────────────────

class FFmpegSlidesEngine(VideoEngine):
    """
    기존 shorts_converter.py의 ffmpeg 파이프라인을 재사용하는 엔진.
    scenes에 slide_path + audio_path가 있으면 그대로 사용,
    없으면 빈 슬라이드와 gTTS로 생성 후 진행.
    """

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.ffmpeg_path = os.getenv('FFMPEG_PATH', 'ffmpeg')
        self.ffprobe_path = os.getenv('FFPROBE_PATH', 'ffprobe')
        self.resolution = cfg.get('resolution', '1080x1920')
        self.fps = cfg.get('fps', 30)
        self.transition = cfg.get('transition', 'fade')
        self.trans_dur = cfg.get('transition_duration', 0.5)
        self.bgm_volume = cfg.get('bgm_volume', 0.08)
        self.burn_subs = cfg.get('burn_subtitles', True)

    def _check_ffmpeg(self) -> bool:
        try:
            r = subprocess.run(
                [self.ffmpeg_path, '-version'],
                capture_output=True, timeout=5,
            )
            return r.returncode == 0
        except Exception:
            return False

    def _run_ffmpeg(self, args: list, quiet: bool = True) -> bool:
        cmd = [self.ffmpeg_path, '-y']
        if quiet:
            cmd += ['-loglevel', 'error']
        cmd += args
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            logger.error(f"ffmpeg 오류: {result.stderr[-400:]}")
        return result.returncode == 0

    def _get_audio_duration(self, wav_path: str) -> float:
        try:
            result = subprocess.run(
                [self.ffprobe_path, '-v', 'quiet', '-print_format', 'json',
                 '-show_format', wav_path],
                capture_output=True, text=True, timeout=10,
            )
            data = json.loads(result.stdout)
            return float(data['format']['duration'])
        except Exception:
            return 5.0

    def _make_silent_wav(self, output_path: str, duration: float = 2.0) -> bool:
        return self._run_ffmpeg([
            '-f', 'lavfi', '-i', f'anullsrc=r=24000:cl=mono',
            '-t', str(duration), output_path,
        ])

    def _make_blank_slide(self, output_path: str) -> bool:
        """단색(어두운) 빈 슬라이드 PNG 생성"""
        try:
            from PIL import Image, ImageDraw
            img = Image.new('RGB', (1080, 1920), (10, 10, 13))
            draw = ImageDraw.Draw(img)
            draw.rectangle([60, 950, 1020, 954], fill=(200, 168, 78))
            img.save(output_path)
            return True
        except ImportError:
            # Pillow 없으면 ffmpeg lavfi로 단색 이미지 생성
            return self._run_ffmpeg([
                '-f', 'lavfi', '-i', 'color=c=black:s=1080x1920:r=1',
                '-frames:v', '1', output_path,
            ])

    def _tts_gtts(self, text: str, output_path: str) -> bool:
        try:
            from gtts import gTTS
            mp3_path = str(output_path).replace('.wav', '_tmp.mp3')
            tts = gTTS(text=text, lang='ko', slow=False)
            tts.save(mp3_path)
            ok = self._run_ffmpeg(['-i', mp3_path, '-ar', '24000', output_path])
            Path(mp3_path).unlink(missing_ok=True)
            return ok and Path(output_path).exists()
        except Exception as e:
            logger.warning(f"gTTS 실패: {e}")
            return False

    def _make_clip(self, slide_png: str, audio_wav: str, output_mp4: str) -> float:
        """슬라이드 PNG + 오디오 WAV → MP4 클립 (Ken Burns zoompan). 클립 길이(초) 반환."""
        duration = self._get_audio_duration(audio_wav) + 0.3
        ok = self._run_ffmpeg([
            '-loop', '1', '-i', slide_png,
            '-i', audio_wav,
            '-c:v', 'libx264', '-tune', 'stillimage',
            '-c:a', 'aac', '-b:a', '192k',
            '-pix_fmt', 'yuv420p',
            '-vf', (
                'scale=1080:1920,'
                'zoompan=z=\'min(zoom+0.0003,1.05)\':'
                'x=\'iw/2-(iw/zoom/2)\':'
                'y=\'ih/2-(ih/zoom/2)\':'
                'd=1:s=1080x1920:fps=30'
            ),
            '-shortest',
            '-r', '30',
            output_mp4,
        ])
        return duration if ok else 0.0

    def _concat_clips_xfade(self, clips: list, output_mp4: str) -> bool:
        """여러 클립을 xfade 전환으로 결합"""
        if len(clips) == 1:
            shutil.copy2(clips[0]['mp4'], output_mp4)
            return True

        n = len(clips)
        inputs = []
        for c in clips:
            inputs += ['-i', c['mp4']]

        filter_parts = []
        prev_v = '[0:v]'
        prev_a = '[0:a]'
        for i in range(1, n):
            offset = sum(c['duration'] for c in clips[:i]) - self.trans_dur * i
            out_v = f'[f{i}v]' if i < n - 1 else '[video]'
            out_a = f'[f{i}a]' if i < n - 1 else '[audio]'
            filter_parts.append(
                f'{prev_v}[{i}:v]xfade=transition={self.transition}:'
                f'duration={self.trans_dur}:offset={offset:.3f}{out_v}'
            )
            filter_parts.append(
                f'{prev_a}[{i}:a]acrossfade=d={self.trans_dur}{out_a}'
            )
            prev_v = out_v
            prev_a = out_a

        return self._run_ffmpeg(
            inputs + [
                '-filter_complex', '; '.join(filter_parts),
                '-map', '[video]', '-map', '[audio]',
                '-c:v', 'libx264', '-c:a', 'aac',
                '-pix_fmt', 'yuv420p',
                output_mp4,
            ]
        )

    def _mix_bgm(self, video_mp4: str, output_mp4: str) -> bool:
        if not BGM_PATH.exists():
            logger.warning(f"BGM 파일 없음 ({BGM_PATH}) — BGM 없이 진행")
            shutil.copy2(video_mp4, output_mp4)
            return True
        return self._run_ffmpeg([
            '-i', video_mp4,
            '-i', str(BGM_PATH),
            '-filter_complex',
            f'[1:a]volume={self.bgm_volume}[bgm];[0:a][bgm]amix=inputs=2:duration=first[a]',
            '-map', '0:v', '-map', '[a]',
            '-c:v', 'copy', '-c:a', 'aac',
            '-shortest',
            output_mp4,
        ])

    def _burn_subtitles(self, video_mp4: str, srt_path: str, output_mp4: str) -> bool:
        font_name = 'NanumGothic'
        fonts_dir = ASSETS_DIR / 'fonts'
        for fname in ['NotoSansKR-Regular.ttf', 'malgun.ttf']:
            fp = fonts_dir / fname
            if not fp.exists():
                fp = Path(f'C:/Windows/Fonts/{fname}')
            if fp.exists():
                font_name = fp.stem
                break
        style = (
            f'FontName={font_name},'
            'FontSize=22,'
            'PrimaryColour=&H00FFFFFF,'
            'OutlineColour=&H80000000,'
            'BorderStyle=4,'
            'BackColour=&H80000000,'
            'Outline=0,Shadow=0,'
            'MarginV=120,'
            'Alignment=2,'
            'Bold=1'
        )
        srt_esc = str(srt_path).replace('\\', '/').replace(':', '\\:').replace("'", r"\'")
        return self._run_ffmpeg([
            '-i', video_mp4,
            '-vf', f"subtitles=filename='{srt_esc}':force_style='{style}'",
            '-c:v', 'libx264', '-c:a', 'copy',
            output_mp4,
        ])

    def _build_srt(self, scenes: list, clips: list) -> str:
        lines = []
        t = 0.0
        for i, (scene, clip) in enumerate(zip(scenes, clips), 1):
            text = scene.get('text', '')
            if not text:
                t += clip['duration'] - self.trans_dur
                continue
            end = t + clip['duration']
            mid = len(text) // 2
            if len(text) > 30:
                space = text.rfind(' ', 0, mid)
                if space > 0:
                    text = text[:space] + '\n' + text[space + 1:]
            lines += [
                str(i),
                f'{self._sec_to_srt(t)} --> {self._sec_to_srt(end)}',
                text,
                '',
            ]
            t += clip['duration'] - self.trans_dur
        return '\n'.join(lines)

    @staticmethod
    def _sec_to_srt(s: float) -> str:
        h, rem = divmod(int(s), 3600)
        m, sec = divmod(rem, 60)
        ms = int((s - int(s)) * 1000)
        return f'{h:02d}:{m:02d}:{sec:02d},{ms:03d}'

    def generate(self, scenes: list, output_path: str, **kwargs) -> str:
        """
        scenes 리스트로 쇼츠 MP4 생성.

        kwargs:
            article (dict): 원본 article 데이터 (슬라이드 합성에 사용)
            tts_engine: BaseTTS 인스턴스 (없으면 GTTSEngine 사용)
        """
        if not self._check_ffmpeg():
            logger.error("ffmpeg 없음. PATH 또는 FFMPEG_PATH 환경변수 확인")
            return ''

        if not scenes:
            logger.warning("scenes 비어 있음 — 영상 생성 불가")
            return ''

        logger.info(f"FFmpegSlidesEngine 시작: {len(scenes)}개 씬 → {output_path}")

        tts_engine = kwargs.get('tts_engine', None)

        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            clips = []

            for idx, scene in enumerate(scenes):
                scene_key = scene.get('type', f'scene{idx}')

                # ── 슬라이드 준비 ──────────────────────
                slide_path = scene.get('slide_path', '')
                if not slide_path or not Path(slide_path).exists():
                    # shorts_converter의 슬라이드 합성 함수 재사용 시도
                    slide_path = str(tmp_dir / f'slide_{idx}.png')
                    article = kwargs.get('article', {})
                    composed = self._compose_scene_slide(
                        scene, idx, article, tmp_dir
                    )
                    if composed:
                        slide_path = composed
                    else:
                        self._make_blank_slide(slide_path)

                # ── 오디오 준비 ────────────────────────
                audio_path = scene.get('audio_path', '')
                if not audio_path or not Path(audio_path).exists():
                    audio_path = str(tmp_dir / f'tts_{idx}.wav')
                    text = scene.get('text', '')
                    ok = False
                    if tts_engine and text:
                        try:
                            ok = tts_engine.synthesize(text, audio_path)
                        except Exception as e:
                            logger.warning(f"TTS 엔진 실패: {e}")
                    if not ok and text:
                        ok = self._tts_gtts(text, audio_path)
                    if not ok:
                        self._make_silent_wav(audio_path)

                # ── 클립 생성 ──────────────────────────
                clip_path = str(tmp_dir / f'clip_{idx}.mp4')
                dur = self._make_clip(slide_path, audio_path, clip_path)
                if dur > 0:
                    clips.append({'mp4': clip_path, 'duration': dur})
                else:
                    logger.warning(f"씬 {idx} ({scene_key}) 클립 생성 실패 — 건너뜀")

            if not clips:
                logger.error("생성된 클립 없음")
                return ''

            # ── 클립 결합 ──────────────────────────────
            merged = str(tmp_dir / 'merged.mp4')
            if not self._concat_clips_xfade(clips, merged):
                logger.error("클립 결합 실패")
                return ''

            # ── BGM 믹스 ───────────────────────────────
            with_bgm = str(tmp_dir / 'with_bgm.mp4')
            self._mix_bgm(merged, with_bgm)
            source_for_srt = with_bgm if Path(with_bgm).exists() else merged

            # ── 자막 burn-in ───────────────────────────
            if self.burn_subs:
                srt_content = self._build_srt(scenes, clips)
                srt_path = str(tmp_dir / 'subtitles.srt')
                Path(srt_path).write_text(srt_content, encoding='utf-8-sig')

                Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                if not self._burn_subtitles(source_for_srt, srt_path, output_path):
                    logger.warning("자막 burn-in 실패 — 자막 없는 버전으로 저장")
                    shutil.copy2(source_for_srt, output_path)
            else:
                Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_for_srt, output_path)

        if Path(output_path).exists():
            logger.info(f"FFmpegSlidesEngine 완료: {output_path}")
            return output_path
        else:
            logger.error(f"최종 파일 없음: {output_path}")
            return ''

    def _compose_scene_slide(self, scene: dict, idx: int,
                              article: dict, tmp_dir: Path) -> Optional[str]:
        """
        shorts_converter의 슬라이드 합성 함수를 재사용해 씬별 슬라이드 생성.
        임포트 실패 시 None 반환 (blank slide 폴백).
        """
        try:
            from bots.converters.shorts_converter import (
                compose_intro_slide,
                compose_headline_slide,
                compose_point_slide,
                compose_outro_slide,
                compose_data_slide,
                _set_tmp_dir,
                _load_template,
            )
            _set_tmp_dir(tmp_dir)
            cfg = _load_template()
            scene_type = scene.get('type', '')
            out_path = str(tmp_dir / f'slide_{idx}.png')

            if scene_type == 'intro':
                return compose_intro_slide(cfg)
            elif scene_type == 'headline':
                return compose_headline_slide(article, cfg)
            elif scene_type in ('point', 'point1', 'point2', 'point3'):
                num = int(scene_type[-1]) if scene_type[-1].isdigit() else 1
                return compose_point_slide(scene.get('text', ''), num, article, cfg)
            elif scene_type == 'data':
                return compose_data_slide(article, cfg)
            elif scene_type == 'outro':
                return compose_outro_slide(cfg)
            else:
                # 알 수 없는 타입 → 헤드라인 슬라이드로 대체
                return compose_headline_slide(article, cfg)
        except ImportError as e:
            logger.warning(f"shorts_converter 임포트 실패: {e}")
            return None
        except Exception as e:
            logger.warning(f"슬라이드 합성 실패 (씬 {idx}): {e}")
            return None


# ─── SeedanceEngine ────────────────────────────────────

class SeedanceEngine(VideoEngine):
    """
    Seedance 2.0 API를 사용한 AI 영상 생성 엔진.
    API 키 없거나 실패 시 FFmpegSlidesEngine으로 자동 폴백.
    """

    def __init__(self, cfg: dict):
        self.api_url = cfg.get('api_url', 'https://api.seedance2.ai/v1/generate')
        self.api_key = os.getenv(cfg.get('api_key_env', 'SEEDANCE_API_KEY'), '')
        self.resolution = cfg.get('resolution', '1080x1920')
        self.duration = cfg.get('duration', '10s')
        self.audio = cfg.get('audio', True)
        self._fallback_cfg = cfg

    def _fallback(self, scenes: list, output_path: str, **kwargs) -> str:
        logger.info("SeedanceEngine → FFmpegSlidesEngine 폴백")
        return FFmpegSlidesEngine(self._fallback_cfg).generate(
            scenes, output_path, **kwargs
        )

    def _download_file(self, url: str, dest: str, timeout: int = 120) -> bool:
        try:
            import requests as req
            resp = req.get(url, timeout=timeout, stream=True)
            resp.raise_for_status()
            with open(dest, 'wb') as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            return True
        except Exception as e:
            logger.error(f"파일 다운로드 실패 ({url}): {e}")
            return False

    def _concat_clips_ffmpeg(self, clip_paths: list, output_path: str) -> bool:
        """ffmpeg concat demuxer로 클립 결합 (인트로 2초 + 씬 + 아웃트로 3초)"""
        if not clip_paths:
            return False
        ffmpeg = os.getenv('FFMPEG_PATH', 'ffmpeg')
        with tempfile.TemporaryDirectory() as tmp:
            list_file = str(Path(tmp) / 'clips.txt')
            with open(list_file, 'w', encoding='utf-8') as f:
                for p in clip_paths:
                    f.write(f"file '{p}'\n")
            result = subprocess.run(
                [ffmpeg, '-y', '-loglevel', 'error',
                 '-f', 'concat', '-safe', '0',
                 '-i', list_file,
                 '-c', 'copy', output_path],
                capture_output=True, timeout=300,
            )
            return result.returncode == 0

    def _generate_scene_clip(self, scene: dict, output_path: str) -> bool:
        """단일 씬에 대해 Seedance API 호출 → 클립 다운로드"""
        try:
            import requests as req
            prompt = scene.get('image_prompt') or scene.get('text', '')
            if not prompt:
                return False

            payload = {
                'prompt': prompt,
                'resolution': self.resolution,
                'duration': self.duration,
                'audio': self.audio,
            }
            headers = {
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json',
            }
            logger.info(f"Seedance API 호출: {prompt[:60]}...")
            resp = req.post(self.api_url, json=payload, headers=headers, timeout=120)
            resp.raise_for_status()

            data = resp.json()
            video_url = data.get('video_url') or data.get('url', '')
            if not video_url:
                logger.error(f"Seedance 응답에 video_url 없음: {data}")
                return False

            return self._download_file(video_url, output_path)
        except Exception as e:
            logger.error(f"Seedance API 오류: {e}")
            return False

    def generate(self, scenes: list, output_path: str, **kwargs) -> str:
        if not self.api_key:
            logger.warning("SEEDANCE_API_KEY 없음 — FFmpegSlidesEngine으로 폴백")
            return self._fallback(scenes, output_path, **kwargs)

        if not scenes:
            logger.warning("scenes 비어 있음")
            return ''

        logger.info(f"SeedanceEngine 시작: {len(scenes)}개 씬")

        ffmpeg = os.getenv('FFMPEG_PATH', 'ffmpeg')

        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            clip_paths = []

            # 인트로 클립 (2초 단색)
            intro_path = str(tmp_dir / 'intro.mp4')
            subprocess.run(
                [ffmpeg, '-y', '-loglevel', 'error',
                 '-f', 'lavfi', '-i', 'color=c=black:s=1080x1920:r=30',
                 '-t', '2', '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
                 intro_path],
                capture_output=True, timeout=30,
            )
            if Path(intro_path).exists():
                clip_paths.append(intro_path)

            # 씬별 클립 생성
            success_count = 0
            for idx, scene in enumerate(scenes):
                clip_path = str(tmp_dir / f'scene_{idx}.mp4')
                if self._generate_scene_clip(scene, clip_path):
                    clip_paths.append(clip_path)
                    success_count += 1
                else:
                    logger.warning(f"씬 {idx} Seedance 실패 — 폴백으로 전환")
                    return self._fallback(scenes, output_path, **kwargs)

            if success_count == 0:
                logger.warning("모든 씬 실패 — FFmpegSlidesEngine으로 폴백")
                return self._fallback(scenes, output_path, **kwargs)

            # 아웃트로 클립 (3초 단색)
            outro_path = str(tmp_dir / 'outro.mp4')
            subprocess.run(
                [ffmpeg, '-y', '-loglevel', 'error',
                 '-f', 'lavfi', '-i', 'color=c=black:s=1080x1920:r=30',
                 '-t', '3', '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
                 outro_path],
                capture_output=True, timeout=30,
            )
            if Path(outro_path).exists():
                clip_paths.append(outro_path)

            # 클립 결합
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            if not self._concat_clips_ffmpeg(clip_paths, output_path):
                logger.error("SeedanceEngine 클립 결합 실패")
                return self._fallback(scenes, output_path, **kwargs)

        if Path(output_path).exists():
            logger.info(f"SeedanceEngine 완료: {output_path}")
            return output_path
        return self._fallback(scenes, output_path, **kwargs)


# ─── RunwayEngine ──────────────────────────────────────

class RunwayEngine(VideoEngine):
    """
    Runway Gen-3 API를 사용한 AI 영상 생성 엔진.
    API 키 없거나 실패 시 FFmpegSlidesEngine으로 자동 폴백.
    """

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.api_key = os.getenv(cfg.get('api_key_env', 'RUNWAY_API_KEY'), '')
        self.api_url = cfg.get('api_url', 'https://api.runwayml.com/v1/image_to_video')
        self.model = cfg.get('model', 'gen3a_turbo')
        self.duration = cfg.get('duration', 10)
        self.ratio = cfg.get('ratio', '768:1344')

    def _fallback(self, scenes: list, output_path: str, **kwargs) -> str:
        logger.info("RunwayEngine → FFmpegSlidesEngine 폴백")
        return FFmpegSlidesEngine(self.cfg).generate(scenes, output_path, **kwargs)

    def _generate_scene_clip(self, scene: dict, output_path: str) -> bool:
        """단일 씬에 대해 Runway API 호출 → 클립 다운로드"""
        try:
            import requests as req
            prompt = scene.get('image_prompt') or scene.get('text', '')
            if not prompt:
                return False

            headers = {
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json',
                'X-Runway-Version': '2024-11-06',
            }
            payload = {
                'model': self.model,
                'promptText': prompt,
                'duration': self.duration,
                'ratio': self.ratio,
            }
            logger.info(f"Runway API 호출: {prompt[:60]}...")
            resp = req.post(self.api_url, json=payload, headers=headers, timeout=30)
            resp.raise_for_status()

            data = resp.json()
            task_id = data.get('id', '')
            if not task_id:
                logger.error(f"Runway 태스크 ID 없음: {data}")
                return False

            # 폴링: 태스크 완료 대기
            poll_url = f'https://api.runwayml.com/v1/tasks/{task_id}'
            import time
            for _ in range(60):
                time.sleep(10)
                poll = req.get(poll_url, headers=headers, timeout=30)
                poll.raise_for_status()
                status_data = poll.json()
                status = status_data.get('status', '')
                if status == 'SUCCEEDED':
                    video_url = (status_data.get('output') or [''])[0]
                    if not video_url:
                        logger.error("Runway 완료됐으나 video_url 없음")
                        return False
                    return self._download_file(video_url, output_path)
                elif status in ('FAILED', 'CANCELLED'):
                    logger.error(f"Runway 태스크 실패: {status_data}")
                    return False
            logger.error("Runway 태스크 타임아웃 (10분)")
            return False
        except Exception as e:
            logger.error(f"Runway API 오류: {e}")
            return False

    def _download_file(self, url: str, dest: str, timeout: int = 120) -> bool:
        try:
            import requests as req
            resp = req.get(url, timeout=timeout, stream=True)
            resp.raise_for_status()
            with open(dest, 'wb') as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            return True
        except Exception as e:
            logger.error(f"파일 다운로드 실패 ({url}): {e}")
            return False

    def generate(self, scenes: list, output_path: str, **kwargs) -> str:
        if not self.api_key:
            logger.warning("RUNWAY_API_KEY 없음 — FFmpegSlidesEngine으로 폴백")
            return self._fallback(scenes, output_path, **kwargs)

        if not scenes:
            logger.warning("scenes 비어 있음")
            return ''

        logger.info(f"RunwayEngine 시작: {len(scenes)}개 씬")

        ffmpeg = os.getenv('FFMPEG_PATH', 'ffmpeg')

        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            clip_paths = []

            for idx, scene in enumerate(scenes):
                clip_path = str(tmp_dir / f'scene_{idx}.mp4')
                if self._generate_scene_clip(scene, clip_path):
                    clip_paths.append(clip_path)
                else:
                    logger.warning(f"씬 {idx} Runway 실패 — FFmpegSlidesEngine 폴백")
                    return self._fallback(scenes, output_path, **kwargs)

            if not clip_paths:
                return self._fallback(scenes, output_path, **kwargs)

            # concat
            list_file = str(tmp_dir / 'clips.txt')
            with open(list_file, 'w', encoding='utf-8') as f:
                for p in clip_paths:
                    f.write(f"file '{p}'\n")

            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            result = subprocess.run(
                [ffmpeg, '-y', '-loglevel', 'error',
                 '-f', 'concat', '-safe', '0',
                 '-i', list_file, '-c', 'copy', output_path],
                capture_output=True, timeout=300,
            )
            if result.returncode != 0:
                logger.error("RunwayEngine 클립 결합 실패")
                return self._fallback(scenes, output_path, **kwargs)

        if Path(output_path).exists():
            logger.info(f"RunwayEngine 완료: {output_path}")
            return output_path
        return self._fallback(scenes, output_path, **kwargs)


# ─── VeoEngine ─────────────────────────────────────────

class VeoEngine(VideoEngine):
    """
    Google Veo 3.1 영상 생성 엔진.
    현재 API 공개 접근 불가 — ffmpeg_slides로 폴백.
    """

    def __init__(self, cfg: dict):
        self.cfg = cfg

    def generate(self, scenes: list, output_path: str, **kwargs) -> str:
        logger.warning("Veo API 미지원. ffmpeg_slides로 폴백.")
        return FFmpegSlidesEngine(self.cfg).generate(scenes, output_path, **kwargs)


# ─── 팩토리 함수 ───────────────────────────────────────

def get_engine(video_cfg: dict) -> VideoEngine:
    """
    engine.json video_generation 설정에서 엔진 인스턴스 반환.

    사용:
        cfg = {'provider': 'ffmpeg_slides', 'options': {...}}
        engine = get_engine(cfg)
        mp4 = engine.generate(scenes, '/path/to/output.mp4')
    """
    provider = video_cfg.get('provider', 'ffmpeg_slides')
    opts = video_cfg.get('options', {}).get(provider, {})

    engine_map = {
        'ffmpeg_slides': FFmpegSlidesEngine,
        'seedance': SeedanceEngine,
        'runway': RunwayEngine,
        'veo': VeoEngine,
    }
    cls = engine_map.get(provider, FFmpegSlidesEngine)
    logger.info(f"VideoEngine 선택: {provider} ({cls.__name__})")
    return cls(opts)
