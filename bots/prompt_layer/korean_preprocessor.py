"""
bots/prompt_layer/korean_preprocessor.py
Korean TTS text preprocessing.

Functions:
- preprocess_korean(text): apply pronunciation map + number conversion
- insert_pauses(script): insert SSML/marker pauses by sentence type
"""
import re
import logging

logger = logging.getLogger(__name__)

# English/acronym → Korean phonetic pronunciation
# 200+ entries covering tech, finance, social media, brands, etc.
PRONUNCIATION_MAP = {
    # AI/Tech terms
    'AI': '에이아이',
    'API': '에이피아이',
    'GPT': '지피티',
    'ChatGPT': '챗지피티',
    'Claude': '클로드',
    'GitHub': '깃허브',
    'OpenAI': '오픈에이아이',
    'YouTube': '유튜브',
    'TikTok': '틱톡',
    'SEO': '에스이오',
    'SaaS': '사스',
    'UI': '유아이',
    'UX': '유엑스',
    'LLM': '엘엘엠',
    'NFT': '엔에프티',
    'DeFi': '디파이',
    'IoT': '아이오티',
    'AR': '에이알',
    'VR': '브이알',
    'ML': '머신러닝',
    'NLP': '엔엘피',
    'DevOps': '데브옵스',
    'SQL': '에스큐엘',
    'HTML': '에이치티엠엘',
    'CSS': '씨에스에스',
    'JSON': '제이슨',
    'URL': '유알엘',
    'HTTP': '에이치티티피',
    'HTTPS': '에이치티티피에스',
    'PC': '피씨',
    'CPU': '씨피유',
    'GPU': '지피유',
    'RAM': '램',
    'SSD': '에스에스디',
    'USB': '유에스비',
    'WiFi': '와이파이',
    'Bluetooth': '블루투스',
    'iOS': '아이오에스',
    'Android': '안드로이드',
    'App': '앱',
    'IT': '아이티',
    'ICT': '아이씨티',
    'SNS': '에스엔에스',
    'KPI': '케이피아이',
    'ROI': '알오아이',
    'B2B': '비투비',
    'B2C': '비투씨',
    'MVP': '엠브이피',
    'OKR': '오케이알',
    'CTO': '씨티오',
    'CEO': '씨이오',
    'CFO': '씨에프오',
    'HR': '에이치알',
    'PR': '피알',
    'IR': '아이알',
    # Social/Platforms
    'Instagram': '인스타그램',
    'Facebook': '페이스북',
    'Twitter': '트위터',
    'LinkedIn': '링크드인',
    'Netflix': '넷플릭스',
    'Spotify': '스포티파이',
    'Uber': '우버',
    'Airbnb': '에어비앤비',
    'Amazon': '아마존',
    'Google': '구글',
    'Apple': '애플',
    'Microsoft': '마이크로소프트',
    'Samsung': '삼성',
    'LG': '엘지',
    'SK': '에스케이',
    'KT': '케이티',
    # Finance
    'ETF': '이티에프',
    'IPO': '아이피오',
    'S&P': '에스앤피',
    'NASDAQ': '나스닥',
    'KOSPI': '코스피',
    'KOSDAQ': '코스닥',
    'GDP': '지디피',
    'IMF': '아이엠에프',
    'ECB': '이씨비',
    'Fed': '연준',
    'P/E': '주가수익비율',
    # Health/Science
    'DNA': '디엔에이',
    'RNA': '알엔에이',
    'BMI': '비엠아이',
    'COVID': '코비드',
    'PCR': '피씨알',
    # Education/Certification
    'MBA': '엠비에이',
    'PhD': '박사',
    'IELTS': '아이엘츠',
    'TOEIC': '토익',
    'TOEFL': '토플',
    # Measurement units
    'km': '킬로미터',
    'kg': '킬로그램',
    'MB': '메가바이트',
    'GB': '기가바이트',
    'TB': '테라바이트',
    'Hz': '헤르츠',
    'MHz': '메가헤르츠',
    'GHz': '기가헤르츠',
    # Media/Entertainment
    'OTT': '오티티',
    'VOD': '브이오디',
    'BGM': '비지엠',
    'OST': '오에스티',
    'DJ': '디제이',
    'MC': '엠씨',
    'PD': '피디',
    'CP': '씨피',
    # Common English words used in Korean context
    'App Store': '앱 스토어',
    'Play Store': '플레이 스토어',
    'ChatBot': '챗봇',
    'Web3': '웹쓰리',
    'Metaverse': '메타버스',
    'Blockchain': '블록체인',
    'Crypto': '크립토',
    'Bitcoin': '비트코인',
    'Ethereum': '이더리움',
    'Cloud': '클라우드',
    'Big Data': '빅데이터',
    'Startup': '스타트업',
    'Fintech': '핀테크',
    'Edtech': '에드테크',
    'Healthtech': '헬스테크',
    'PropTech': '프롭테크',
    'LegalTech': '리걸테크',
    'FOMO': '포모',
    'YOLO': '욜로',
    'MZ': '엠제트',
    # More tech
    'Python': '파이썬',
    'JavaScript': '자바스크립트',
    'TypeScript': '타입스크립트',
    'React': '리액트',
    'Node.js': '노드제이에스',
    'Docker': '도커',
    'Kubernetes': '쿠버네티스',
    'AWS': '에이더블유에스',
    'GCP': '지씨피',
    'Azure': '애저',
    'Slack': '슬랙',
    'Zoom': '줌',
    'Discord': '디스코드',
    'Notion': '노션',
    'Figma': '피그마',
    'Canva': '캔바',
    # Business/Strategy
    'OEM': '오이엠',
    'ODM': '오디엠',
    'SCM': '에스씨엠',
    'ERP': '이알피',
    'CRM': '씨알엠',
    # More social media
    'Reels': '릴스',
    'Stories': '스토리',
    'Live': '라이브',
    'Feed': '피드',
    'DM': '디엠',
    'PM': '피엠',
    'QA': '큐에이',
    # Content
    'Blog': '블로그',
    'Vlog': '브이로그',
    'Podcast': '팟캐스트',
    'Newsletter': '뉴스레터',
    'Shorts': '쇼츠',
    'Reel': '릴',
    # Misc
    'OK': '오케이',
    'NO': '노',
    'YES': '예스',
    'WOW': '와우',
    'LOL': '엘오엘',
    'BTW': '그런데',
    'FYI': '참고로',
    'ASAP': '최대한 빨리',
    'FAQ': '자주 묻는 질문',
    'Q&A': '질의응답',
    'A/S': '에이에스',
    'DIY': '디아이와이',
    'PPT': '피피티',
    'PDF': '피디에프',
    'ZIP': '집',
    # AI/LLM extended
    'Gemini': '제미나이',
    'Grok': '그록',
    'Copilot': '코파일럿',
    'Perplexity': '퍼플렉시티',
    'Midjourney': '미드저니',
    'Stable Diffusion': '스테이블 디퓨전',
    'DALL-E': '달리',
    'Sora': '소라',
    'Kling': '클링',
    'Runway': '런웨이',
    # Dev tools / infra
    'Git': '깃',
    'Linux': '리눅스',
    'Ubuntu': '우분투',
    'Windows': '윈도우',
    'macOS': '맥오에스',
    'Terminal': '터미널',
    'CI/CD': '씨아이씨디',
    'API Gateway': '에이피아이 게이트웨이',
    # Finance extended
    'PER': '주가수익비율',
    'PBR': '주가순자산비율',
    'EPS': '주당순이익',
    'ROE': '자기자본이익률',
    'CAGR': '연평균성장률',
    # E-commerce / marketing
    'CPC': '클릭당비용',
    'CPM': '천회노출당비용',
    'CTA': '씨티에이',
    'CTR': '클릭률',
    'ROAS': '광고수익률',
    'LTV': '고객생애가치',
}

# Pause durations in milliseconds by sentence type
DYNAMIC_PAUSES = {
    'hook_after': 500,      # ms — impact emphasis after hook
    'question_after': 400,  # thinking time after question
    'normal_after': 300,    # standard sentence end
    'section_break': 600,   # body → closer transition
    'comma': 150,           # comma pause
    'exclamation': 200,     # exclamation mark pause
}

# Number → Korean word conversion rules
_NUM_TO_KO = {
    0: '영', 1: '일', 2: '이', 3: '삼', 4: '사', 5: '오',
    6: '육', 7: '칠', 8: '팔', 9: '구', 10: '십',
    100: '백', 1000: '천', 10000: '만',
}

# Counter words for common units (for better number reading)
_COUNTER_MAP = {
    '개': ('개', False),   # items
    '명': ('명', False),   # people
    '번': ('번', False),   # times
    '배': ('배', False),   # times/multiples
    '위': ('위', False),   # rank
    '가지': ('가지', True), # types (use sino-Korean)
    '초': ('초', False),   # seconds
    '분': ('분', False),   # minutes
    '시간': ('시간', False), # hours
    '일': ('일', False),   # days
    '월': ('월', False),   # months
    '년': ('년', False),   # years
    '%': ('퍼센트', False), # percent
}


def preprocess_korean(text: str) -> str:
    """
    Apply pronunciation map and number conversion to Korean text.

    1. Replace English/acronym terms with Korean phonetics
    2. Convert Arabic numerals with counter words to Korean

    Returns processed text ready for TTS.
    """
    # Apply pronunciation map (longer strings first to avoid partial replacement)
    sorted_map = sorted(PRONUNCIATION_MAP.items(), key=lambda x: -len(x[0]))
    for en, ko in sorted_map:
        # Word boundary replacement to avoid partial matches
        text = re.sub(r'(?<![가-힣\w])' + re.escape(en) + r'(?![가-힣\w])', ko, text)

    # Convert numbers
    text = _convert_numbers(text)

    return text


def _convert_numbers(text: str) -> str:
    """
    Convert Arabic numerals in Korean context.
    e.g.: "3가지" → "세 가지", "100%" → "백 퍼센트"
    """
    # Handle percentage
    text = re.sub(r'(\d+)%', lambda m: _num_to_korean(int(m.group(1))) + ' 퍼센트', text)

    # Handle number + counter word
    for counter, (ko_counter, use_sino) in _COUNTER_MAP.items():
        if counter == '%':
            continue
        pattern = r'(\d+)\s*' + re.escape(counter)
        def replace(m, kc=ko_counter):
            n = int(m.group(1))
            return _num_to_korean(n) + ' ' + kc
        text = re.sub(pattern, replace, text)

    return text


def _num_to_korean(n: int) -> str:
    """Convert integer to Korean sino-Korean numeral string."""
    if n == 0:
        return '영'
    if n < 0:
        return '마이너스 ' + _num_to_korean(-n)

    result = ''
    if n >= 10000:
        man = n // 10000
        result += _num_to_korean(man) + '만'
        n %= 10000
    if n >= 1000:
        cheon = n // 1000
        result += ('' if cheon == 1 else _num_to_korean(cheon)) + '천'
        n %= 1000
    if n >= 100:
        baek = n // 100
        result += ('' if baek == 1 else _num_to_korean(baek)) + '백'
        n %= 100
    if n >= 10:
        sip = n // 10
        result += ('' if sip == 1 else _num_to_korean(sip)) + '십'
        n %= 10
    if n > 0:
        result += _NUM_TO_KO[n]

    return result


def insert_pauses(script: dict, engine: str = 'ssml') -> dict:
    """
    Insert pause markers into script by sentence type.

    engine='ssml': insert SSML <break> tags (for ElevenLabs, Google TTS)
    engine='marker': insert [[PAUSE_Xms]] text markers (for Edge TTS, others)

    Returns modified script dict with pauses inserted.
    """
    result = dict(script)

    hook = script.get('hook', '')
    body = script.get('body', [])
    closer = script.get('closer', '')

    # Add pause after hook
    if hook:
        pause_ms = DYNAMIC_PAUSES['hook_after']
        result['hook'] = hook + _pause_marker(pause_ms, engine)

    # Add pauses within body sentences
    processed_body = []
    for i, sentence in enumerate(body):
        processed = _add_inline_pauses(sentence, engine)
        # Add section break before closer transition
        if i == len(body) - 1:
            processed += _pause_marker(DYNAMIC_PAUSES['section_break'], engine)
        else:
            processed += _pause_marker(DYNAMIC_PAUSES['normal_after'], engine)
        processed_body.append(processed)
    result['body'] = processed_body

    return result


def _add_inline_pauses(sentence: str, engine: str) -> str:
    """Add pauses at commas and after exclamation marks."""
    # Comma pauses
    sentence = re.sub(
        r',\s*',
        ',' + _pause_marker(DYNAMIC_PAUSES['comma'], engine),
        sentence
    )
    # Question mark pauses
    sentence = re.sub(
        r'\?\s*',
        '?' + _pause_marker(DYNAMIC_PAUSES['question_after'], engine),
        sentence
    )
    # Exclamation pauses
    sentence = re.sub(
        r'!\s*',
        '!' + _pause_marker(DYNAMIC_PAUSES['exclamation'], engine),
        sentence
    )
    return sentence


def _pause_marker(ms: int, engine: str) -> str:
    """Generate engine-appropriate pause marker."""
    if engine == 'ssml':
        return f'<break time="{ms}ms"/>'
    else:
        return f' [[PAUSE_{ms}ms]] '


# ── Standalone test ──────────────────────────────────────────────

if __name__ == '__main__':
    import sys
    if '--test' in sys.argv:
        print("=== Korean Preprocessor Test ===")
        test_texts = [
            "AI와 ChatGPT가 SEO를 바꾸고 있어요",
            "3가지 방법으로 100%의 수익을 낼 수 있습니다",
            "YouTube와 TikTok에서 SNS 마케팅하기",
            "GPT API를 사용한 SaaS 창업",
        ]
        for text in test_texts:
            result = preprocess_korean(text)
            print(f"원문: {text}")
            print(f"처리: {result}")
            print()

        # Test pause insertion
        test_script = {
            'hook': '이거 모르면 손해입니다!',
            'body': ['첫 번째, AI를 활용하면 10배 빠릅니다.', '두 번째, 자동화가 핵심입니다.'],
            'closer': '지금 바로 시작하세요.'
        }
        processed = insert_pauses(test_script, engine='marker')
        print("=== Pause Insertion Test ===")
        for k, v in processed.items():
            print(f"{k}: {v}")
