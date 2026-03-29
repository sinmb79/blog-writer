"""
dashboard/backend/api_connections.py
Settings > Connections 탭 API — AI 서비스 연결 상태 확인/테스트
"""
import json
import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent.parent.parent
CONFIG_PATH = BASE_DIR / "config" / "engine.json"
ENV_PATH = BASE_DIR / ".env"

router = APIRouter()

AI_SERVICES = [
    {
        "id": "claude",
        "name": "Claude (Anthropic)",
        "env_key": "ANTHROPIC_API_KEY",
        "category": "writing",
        "description": "글쓰기 엔진 — claude-opus-4-5",
    },
    {
        "id": "gemini",
        "name": "Google Gemini",
        "env_key": "GEMINI_API_KEY",
        "category": "writing",
        "description": "글쓰기 엔진 — gemini-2.0-flash",
    },
    {
        "id": "openai",
        "name": "OpenAI (GPT + DALL-E + TTS)",
        "env_key": "OPENAI_API_KEY",
        "category": "multi",
        "description": "이미지(DALL-E 3) + TTS(tts-1-hd)",
    },
    {
        "id": "elevenlabs",
        "name": "ElevenLabs TTS",
        "env_key": "ELEVENLABS_API_KEY",
        "category": "tts",
        "description": "고품질 한국어 TTS",
    },
    {
        "id": "google_tts",
        "name": "Google Cloud TTS",
        "env_key": "GOOGLE_TTS_API_KEY",
        "category": "tts",
        "description": "Google Wavenet TTS",
    },
    {
        "id": "seedance",
        "name": "Seedance AI Video",
        "env_key": "SEEDANCE_API_KEY",
        "category": "video",
        "description": "AI 영상 생성 — Seedance 2.0",
    },
    {
        "id": "runway",
        "name": "Runway Gen-3",
        "env_key": "RUNWAY_API_KEY",
        "category": "video",
        "description": "AI 영상 생성 — Gen-3 Turbo",
    },
]


class ApiKeyUpdate(BaseModel):
    api_key: str


def _mask_key(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 8:
        return "****"
    return key[:4] + "****" + key[-4:]


def _get_connections():
    connections = []
    for svc in AI_SERVICES:
        key = os.getenv(svc["env_key"], "")
        connections.append({
            **svc,
            "connected": bool(key),
            "key_masked": _mask_key(key),
        })
    return connections


@router.get("/connections")
async def get_connections():
    return {"connections": _get_connections()}


@router.post("/connections/{service_id}/test")
async def test_connection(service_id: str):
    """서비스 연결 테스트"""
    svc = next((s for s in AI_SERVICES if s["id"] == service_id), None)
    if not svc:
        raise HTTPException(status_code=404, detail="서비스를 찾을 수 없습니다.")

    api_key = os.getenv(svc["env_key"], "")
    if not api_key:
        return {"success": False, "message": "API 키가 설정되지 않았습니다."}

    # 간단한 연결 테스트
    try:
        if service_id == "claude":
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
            # 모델 목록으로 연결 테스트
            client.messages.create(
                model="claude-haiku-4-5",
                max_tokens=10,
                messages=[{"role": "user", "content": "ping"}],
            )
            return {"success": True, "message": "Claude 연결 성공"}

        elif service_id == "openai":
            from openai import OpenAI
            client = OpenAI(api_key=api_key)
            client.models.list()
            return {"success": True, "message": "OpenAI 연결 성공"}

        elif service_id == "gemini":
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel("gemini-2.0-flash")
            model.generate_content("ping", generation_config={"max_output_tokens": 5})
            return {"success": True, "message": "Gemini 연결 성공"}

        elif service_id in ("elevenlabs", "seedance", "runway", "google_tts"):
            import requests
            test_urls = {
                "elevenlabs": "https://api.elevenlabs.io/v1/models",
                "google_tts": f"https://texttospeech.googleapis.com/v1/voices?key={api_key}",
                "seedance": "https://api.seedance2.ai/v1/models",
                "runway": "https://api.runwayml.com/v1/organization",
            }
            headers_map = {
                "elevenlabs": {"xi-api-key": api_key},
                "runway": {"Authorization": f"Bearer {api_key}"},
            }
            url = test_urls.get(service_id, "")
            headers = headers_map.get(service_id, {})
            if url:
                resp = requests.get(url, headers=headers, timeout=10)
                if resp.status_code < 400:
                    return {"success": True, "message": f"{svc['name']} 연결 성공"}
                else:
                    return {"success": False, "message": f"HTTP {resp.status_code}"}

        return {"success": True, "message": "키 존재 확인됨 (심층 테스트 미지원)"}

    except ImportError as e:
        return {"success": False, "message": f"라이브러리 미설치: {e}"}
    except Exception as e:
        return {"success": False, "message": str(e)[:200]}


@router.put("/connections/{service_id}")
async def update_api_key(service_id: str, req: ApiKeyUpdate):
    """API 키를 .env 파일에 저장"""
    svc = next((s for s in AI_SERVICES if s["id"] == service_id), None)
    if not svc:
        raise HTTPException(status_code=404, detail="서비스를 찾을 수 없습니다.")

    env_key = svc["env_key"]
    api_key = req.api_key.strip()

    try:
        # .env 파일 읽기
        if ENV_PATH.exists():
            lines = ENV_PATH.read_text(encoding="utf-8").splitlines()
        else:
            lines = []

        # 기존 키 교체 또는 추가
        updated = False
        new_lines = []
        for line in lines:
            if line.startswith(f"{env_key}=") or line.startswith(f"{env_key} ="):
                new_lines.append(f"{env_key}={api_key}")
                updated = True
            else:
                new_lines.append(line)

        if not updated:
            new_lines.append(f"{env_key}={api_key}")

        ENV_PATH.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

        # 현재 프로세스 환경 변수도 업데이트
        os.environ[env_key] = api_key

        return {"success": True, "message": f"{env_key} 키 저장 완료"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"키 저장 실패: {e}")
