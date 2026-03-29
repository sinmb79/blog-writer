"""
blogwriter/cli.py
Blog Writer MVP CLI - 8 commands

Usage:
    bw                      # Interactive menu
    bw write [TOPIC]        # Write a blog post
    bw shorts               # Create a shorts video
    bw publish              # Publish pending articles
    bw distribute           # Distribute to SNS platforms
    bw status               # Show system status
    bw doctor               # Check API keys and dependencies
    bw config show          # Show resolved configuration
    bw init                 # Setup wizard (implemented in PR 10)
"""
import json
import logging
import os
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table
from rich import print as rprint

BASE_DIR = Path(__file__).parent.parent
console = Console()
logger = logging.getLogger(__name__)


def _load_resolved_config() -> dict:
    """Load resolved config from ConfigResolver."""
    try:
        sys.path.insert(0, str(BASE_DIR))
        from bots.config_resolver import ConfigResolver
        return ConfigResolver().resolve()
    except Exception as e:
        return {'error': str(e), 'budget': 'free', 'level': 'beginner'}


@click.group(invoke_without_command=True)
@click.pass_context
def app(ctx):
    """Blog Writer - AI 콘텐츠 자동화 도구 (v3.0)"""
    if ctx.invoked_subcommand is None:
        _interactive_menu()


def _interactive_menu():
    """Display interactive menu when no subcommand given."""
    console.print("\n[bold cyan]Blog Writer v3.0[/bold cyan] - AI 콘텐츠 자동화\n")
    console.print("사용 가능한 명령어:")
    commands = [
        ("  bw init",       "설정 마법사 - 처음 설정 시 실행"),
        ("  bw write",      "블로그 글 작성"),
        ("  bw shorts",     "쇼츠 영상 생성"),
        ("  bw publish",    "대기 중인 글 발행"),
        ("  bw distribute", "SNS 플랫폼에 배포"),
        ("  bw status",     "시스템 상태 확인"),
        ("  bw doctor",     "API 키 및 의존성 점검"),
        ("  bw config show","현재 설정 보기"),
    ]
    for cmd, desc in commands:
        console.print(f"[green]{cmd:<20}[/green] {desc}")
    console.print()


@app.command()
@click.argument('topic', required=False)
@click.option('--publish', '-p', is_flag=True, help='작성 후 즉시 발행')
@click.option('--shorts', '-s', is_flag=True, help='쇼츠 영상도 생성')
@click.option('--dry-run', is_flag=True, help='실제 API 호출 없이 테스트')
def write(topic, publish, shorts, dry_run):
    """블로그 글 작성."""
    cfg = _load_resolved_config()

    if dry_run:
        console.print("[yellow]Dry run 모드[/yellow] - API 호출 없이 실행")

    if not topic:
        topic = click.prompt('주제를 입력하세요')

    console.print(f"\n[bold]블로그 글 작성 시작[/bold]")
    console.print(f"주제: {topic}")
    console.print(f"글쓰기 엔진: [cyan]{cfg.get('writing', 'auto')}[/cyan]")

    if dry_run:
        console.print("[yellow]Dry run 완료 (실제 작성 없음)[/yellow]")
        return

    try:
        sys.path.insert(0, str(BASE_DIR))
        from bots.writer_bot import WriterBot
        bot = WriterBot()
        result = bot.write(topic)
        if result:
            console.print(f"[green]✓ 작성 완료[/green]: {result.get('title', topic)}")
            if publish:
                ctx = click.get_current_context()
                ctx.invoke(publish_cmd)
            if shorts:
                ctx = click.get_current_context()
                ctx.invoke(shorts_cmd)
        else:
            console.print("[red]✗ 작성 실패[/red]")
    except ImportError:
        console.print("[red]writer_bot 로드 실패 - bots/ 경로 확인[/red]")
    except Exception as e:
        console.print(f"[red]오류: {e}[/red]")


@app.command()
@click.option('--slug', help='특정 글 slug 지정')
@click.option('--text', '-t', help='직접 텍스트 입력 (글 없이 쇼츠 생성)')
@click.option('--dry-run', is_flag=True, help='실제 렌더링 없이 테스트')
def shorts(slug, text, dry_run):
    """쇼츠 영상 생성."""
    cfg = _load_resolved_config()

    console.print(f"\n[bold]쇼츠 영상 생성[/bold]")
    console.print(f"비디오 엔진: [cyan]{cfg.get('video', 'ffmpeg_slides')}[/cyan]")
    console.print(f"TTS 엔진: [cyan]{cfg.get('tts', 'edge_tts')}[/cyan]")

    if dry_run:
        console.print("[yellow]Dry run 모드 - 렌더링 없이 설정 확인 완료[/yellow]")
        return

    try:
        sys.path.insert(0, str(BASE_DIR))
        from bots.shorts_bot import ShortsBot
        bot = ShortsBot()
        if text:
            result = bot.create_from_text(text)
        elif slug:
            result = bot.create_from_slug(slug)
        else:
            result = bot.create_latest()

        if result:
            console.print(f"[green]✓ 쇼츠 생성 완료[/green]: {result}")
        else:
            console.print("[red]✗ 쇼츠 생성 실패[/red]")
    except ImportError:
        console.print("[red]shorts_bot 로드 실패 - bots/ 경로 확인[/red]")
    except Exception as e:
        console.print(f"[red]오류: {e}[/red]")


@app.command('publish')
def publish_cmd():
    """대기 중인 글 발행."""
    console.print("\n[bold]발행 시작[/bold]")
    try:
        sys.path.insert(0, str(BASE_DIR))
        from bots.publisher_bot import PublisherBot
        bot = PublisherBot()
        result = bot.publish_pending()
        console.print(f"[green]✓ 발행 완료[/green]: {result} 건")
    except ImportError:
        console.print("[red]publisher_bot 로드 실패[/red]")
    except Exception as e:
        console.print(f"[red]오류: {e}[/red]")


@app.command()
@click.option('--to', help='특정 플랫폼으로만 배포 (예: youtube,tiktok)')
def distribute(to):
    """SNS 플랫폼에 콘텐츠 배포."""
    platforms = to.split(',') if to else None
    console.print(f"\n[bold]배포 시작[/bold]")
    if platforms:
        console.print(f"대상: {', '.join(platforms)}")

    try:
        sys.path.insert(0, str(BASE_DIR))
        # Use scheduler or direct bot calls
        console.print("[yellow]배포 기능은 현재 개발 중입니다[/yellow]")
    except Exception as e:
        console.print(f"[red]오류: {e}[/red]")


@app.command()
def status():
    """시스템 상태 확인 (대시보드 서버 없이 동작)."""
    console.print("\n[bold]시스템 상태[/bold]\n")

    cfg = _load_resolved_config()

    # Config table
    table = Table(title="설정 현황", show_header=True)
    table.add_column("항목", style="cyan")
    table.add_column("값", style="green")

    table.add_row("예산", cfg.get('budget', 'N/A'))
    table.add_row("레벨", cfg.get('level', 'N/A'))
    table.add_row("글쓰기 엔진", str(cfg.get('writing', 'N/A')))
    table.add_row("TTS 엔진", str(cfg.get('tts', 'N/A')))
    table.add_row("비디오 엔진", str(cfg.get('video', 'N/A')))
    table.add_row("플랫폼", ', '.join(cfg.get('platforms', [])))
    console.print(table)

    # Check data dirs
    data_dirs = ['data/shorts', 'data/outputs', 'logs']
    console.print("\n[bold]데이터 디렉터리[/bold]")
    for d in data_dirs:
        path = BASE_DIR / d
        exists = "✓" if path.exists() else "✗"
        count = len(list(path.glob('*'))) if path.exists() else 0
        console.print(f"  {exists} {d}: {count}개 파일")

    # Prompt tracker stats
    try:
        from bots.prompt_layer.prompt_tracker import PromptTracker
        tracker = PromptTracker()
        stats = tracker.get_stats()
        if stats.get('total', 0) > 0:
            console.print(f"\n[bold]프롬프트 로그[/bold]: {stats['total']}건 기록됨")
    except Exception:
        pass


@app.command()
def doctor():
    """API 키 및 의존성 점검."""
    console.print("\n[bold]시스템 점검[/bold]\n")

    # Check API keys
    api_keys = {
        'OPENAI_API_KEY': 'OpenAI (GPT + TTS)',
        'ANTHROPIC_API_KEY': 'Anthropic (Claude)',
        'GEMINI_API_KEY': 'Google Gemini / Veo',
        'ELEVENLABS_API_KEY': 'ElevenLabs TTS',
        'KLING_API_KEY': 'Kling AI 영상',
        'FAL_API_KEY': 'Seedance 2.0 영상',
        'RUNWAY_API_KEY': 'Runway 영상',
        'YOUTUBE_CHANNEL_ID': 'YouTube 채널',
    }

    table = Table(title="API 키 상태", show_header=True)
    table.add_column("서비스", style="cyan")
    table.add_column("상태", style="bold")
    table.add_column("설명")

    for key, desc in api_keys.items():
        value = os.environ.get(key, '')
        if value:
            status_str = "[green]✓ 설정됨[/green]"
        else:
            status_str = "[red]✗ 미설정[/red]"
        table.add_row(desc, status_str, key)

    console.print(table)

    # Check Python dependencies
    console.print("\n[bold]의존성 점검[/bold]")
    deps = ['click', 'rich', 'edge_tts', 'requests', 'Pillow', 'dotenv']
    for dep in deps:
        try:
            import importlib
            importlib.import_module(dep.replace('-', '_').lower().replace('pillow', 'PIL'))
            console.print(f"  [green]✓[/green] {dep}")
        except ImportError:
            console.print(f"  [red]✗[/red] {dep} - pip install {dep}")

    # Check FFmpeg
    import subprocess
    try:
        r = subprocess.run(['ffmpeg', '-version'], capture_output=True, timeout=5)
        if r.returncode == 0:
            console.print(f"  [green]✓[/green] FFmpeg")
        else:
            console.print(f"  [red]✗[/red] FFmpeg - PATH 확인 필요")
    except Exception:
        console.print(f"  [red]✗[/red] FFmpeg - 설치 필요")


@app.group()
def config():
    """설정 관리."""
    pass


@config.command('show')
def config_show():
    """현재 해석된 설정 출력."""
    cfg = _load_resolved_config()

    if 'error' in cfg:
        console.print(f"[red]설정 로드 오류: {cfg['error']}[/red]")
        return

    console.print("\n[bold]현재 설정 (ConfigResolver 기준)[/bold]\n")

    table = Table(show_header=True)
    table.add_column("항목", style="cyan")
    table.add_column("값", style="green")

    for key, value in cfg.items():
        if isinstance(value, list):
            value = ', '.join(str(v) for v in value)
        elif isinstance(value, dict):
            value = json.dumps(value, ensure_ascii=False)
        table.add_row(key, str(value))

    console.print(table)


@app.command()
def init():
    """설정 마법사 - 처음 설치 시 실행."""
    console.print("\n[bold cyan]=== Blog Writer 설정 마법사 ===[/bold cyan]\n")
    console.print("몇 가지 질문에 답하면 자동으로 설정이 완성됩니다.\n")

    profile = {}

    # Step 1: Budget
    console.print("[bold]1. 예산 설정[/bold]")
    console.print("   free   — API 키 없이 무료 도구만 사용")
    console.print("   low    — OpenAI 키 정도만 있으면 사용 가능")
    console.print("   medium — ElevenLabs TTS + AI 영상 사용")
    console.print("   premium — 최고 품질 모든 엔진 사용")
    budget = click.prompt(
        "예산 선택",
        type=click.Choice(['free', 'low', 'medium', 'premium']),
        default='free'
    )
    profile['budget'] = budget

    # Step 2: Level
    console.print("\n[bold]2. 사용자 레벨[/bold]")
    console.print("   beginner     — 처음 사용하는 분")
    console.print("   intermediate — 어느 정도 익숙한 분")
    console.print("   advanced     — 설정을 직접 다루는 분")
    level = click.prompt(
        "레벨 선택",
        type=click.Choice(['beginner', 'intermediate', 'advanced']),
        default='beginner'
    )
    profile['level'] = level

    # Step 3: Platforms
    console.print("\n[bold]3. 발행 플랫폼[/bold]")
    console.print("어디에 콘텐츠를 올리실 건가요? (여러 개 선택 가능)")
    platforms = []
    platform_choices = [
        ('youtube', 'YouTube (쇼츠)'),
        ('tiktok',  'TikTok'),
        ('instagram', 'Instagram (릴스)'),
        ('x',       'X (트위터)'),
        ('blog',    '블로그 (Blogger)'),
    ]
    for key, name in platform_choices:
        if click.confirm(f"   {name}?", default=(key == 'youtube')):
            platforms.append(key)

    if not platforms:
        platforms = ['youtube']  # default
    profile['platforms'] = platforms

    # Step 4: Services (free web clients)
    console.print("\n[bold]4. 무료 서비스 설정[/bold]")
    services = {}

    if click.confirm("   ChatGPT Pro(Web) 사용 중이신가요? (글쓰기에 사용)", default=False):
        services['openclaw'] = True
        console.print("   [yellow]→ OpenClaw 에이전트를 ChatGPT에 등록해야 합니다[/yellow]")
    else:
        services['openclaw'] = False

    if click.confirm("   Claude Max(Web) 사용 중이신가요?", default=False):
        services['claude_web'] = True
    else:
        services['claude_web'] = False

    if click.confirm("   Google Gemini Pro(Web) 사용 중이신가요?", default=False):
        services['gemini_web'] = True
    else:
        services['gemini_web'] = False

    profile['services'] = services

    # Step 5: API Keys
    console.print("\n[bold]5. API 키 설정[/bold]")
    console.print("[dim]키를 지금 입력하면 .env 파일에 저장됩니다.[/dim]")
    console.print("[dim]나중에 .env 파일을 직접 편집해도 됩니다.[/dim]\n")

    env_updates = {}

    api_key_prompts = [
        ('OPENAI_API_KEY', 'OpenAI API 키 (GPT + TTS)', budget in ('low', 'medium', 'premium')),
        ('ANTHROPIC_API_KEY', 'Anthropic API 키 (Claude)', budget in ('medium', 'premium')),
        ('GEMINI_API_KEY', 'Google Gemini API 키 (Veo 영상)', budget in ('medium', 'premium')),
        ('ELEVENLABS_API_KEY', 'ElevenLabs TTS 키', budget in ('medium', 'premium')),
        ('KLING_API_KEY', 'Kling AI 영상 키 (무료 크레딧 있음)', True),
        ('FAL_API_KEY', 'fal.ai API 키 (Seedance 2.0)', budget in ('medium', 'premium')),
    ]

    for env_key, description, suggested in api_key_prompts:
        existing = os.environ.get(env_key, '')
        if existing:
            console.print(f"   [green]✓[/green] {description}: 이미 설정됨")
            continue

        if suggested or click.confirm(f"   {description} 입력하시겠어요?", default=False):
            value = click.prompt(
                f"   {env_key}",
                default='',
                show_default=False,
                hide_input=True,
            )
            if value.strip():
                env_updates[env_key] = value.strip()

    # Step 6: Engine preferences
    console.print("\n[bold]6. 엔진 설정 (선택 — 기본값: 자동)[/bold]")
    profile['engines'] = {
        'writing': {'provider': 'auto'},
        'tts': {'provider': 'auto'},
        'video': {'provider': 'auto'},
        'image': {'provider': 'auto'},
    }

    if click.confirm("   엔진을 직접 지정하시겠어요? (아니면 자동)", default=False):
        # Writing engine
        console.print("\n   [bold]글쓰기 엔진:[/bold] openclaw, claude_web, claude, gemini, auto")
        writing_eng = click.prompt("   글쓰기 엔진", default='auto')
        profile['engines']['writing']['provider'] = writing_eng

        # TTS engine
        console.print("   [bold]TTS 엔진:[/bold] elevenlabs, openai_tts, edge_tts, auto")
        tts_eng = click.prompt("   TTS 엔진", default='auto')
        profile['engines']['tts']['provider'] = tts_eng

    # Save profile
    profile['_comment'] = '사용자 의도 설정 - bw init으로 생성/업데이트'
    profile['_updated'] = __import__('datetime').datetime.now().strftime('%Y-%m-%d')

    profile_path = BASE_DIR / 'config' / 'user_profile.json'
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(
        __import__('json').dumps(profile, ensure_ascii=False, indent=2),
        encoding='utf-8'
    )

    # Update .env if new keys were entered
    if env_updates:
        _update_env_file(env_updates)

    console.print("\n[bold green]✓ 설정 완료![/bold green]")
    console.print(f"  user_profile.json 저장됨: {profile_path}")
    if env_updates:
        console.print(f"  .env 업데이트됨: {len(env_updates)}개 키")
    console.print("\n다음 명령어로 시작하세요:")
    console.print("  [cyan]bw doctor[/cyan]    — 설정 확인")
    console.print("  [cyan]bw write[/cyan]     — 첫 글 작성")
    console.print("  [cyan]bw status[/cyan]    — 시스템 현황\n")


def _update_env_file(updates: dict) -> None:
    """
    Add or update key-value pairs in .env file.
    Creates .env if it doesn't exist.
    """
    env_path = BASE_DIR / '.env'

    # Read existing lines
    existing_lines = []
    if env_path.exists():
        existing_lines = env_path.read_text(encoding='utf-8').splitlines()

    # Update existing keys or append new ones
    updated_keys = set()
    new_lines = []
    for line in existing_lines:
        if '=' in line and not line.startswith('#'):
            key = line.split('=', 1)[0].strip()
            if key in updates:
                new_lines.append(f'{key}={updates[key]}')
                updated_keys.add(key)
                continue
        new_lines.append(line)

    # Append new keys
    for key, value in updates.items():
        if key not in updated_keys:
            new_lines.append(f'{key}={value}')

    env_path.write_text('\n'.join(new_lines) + '\n', encoding='utf-8')
    logger.info(f'[설정] .env 업데이트: {list(updates.keys())}')


# Entry point
def main():
    """Main entry point."""
    app()


if __name__ == '__main__':
    main()
