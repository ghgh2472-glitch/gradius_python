"""notifications.py
알림 시스템: 이메일, Slack 자동 알림
"""
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List
from helpers import get_logger
import os

logger = get_logger(__name__)


class EmailNotifier:
    """이메일 알림 발송"""
    
    def __init__(self, smtp_server: str = None, smtp_port: int = 587, 
                 sender_email: str = None, sender_password: str = None):
        """
        Args:
            smtp_server: SMTP 서버 (e.g., 'smtp.gmail.com')
            smtp_port: SMTP 포트 (e.g., 587 TLS, 465 SSL)
            sender_email: 발송자 이메일
            sender_password: 발송자 비밀번호 (또는 앱 비밀번호)
        """
        # 환경 변수에서 로드 (권장)
        self.smtp_server = smtp_server or os.getenv('SMTP_SERVER', 'smtp.gmail.com')
        self.smtp_port = smtp_port
        self.sender_email = sender_email or os.getenv('SENDER_EMAIL', '')
        self.sender_password = sender_password or os.getenv('SENDER_PASSWORD', '')
    
    def send_email(self, to_emails: List[str], subject: str, body: str, 
                   html: bool = False) -> bool:
        """이메일 발송
        
        Args:
            to_emails: 수신자 이메일 리스트
            subject: 제목
            body: 본문
            html: HTML 형식 여부
        
        Returns:
            성공 여부
        """
        try:
            if not self.sender_email or not self.sender_password:
                logger.warning("⚠️ SMTP credentials not configured, skipping email")
                return False
            
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = self.sender_email
            msg['To'] = ', '.join(to_emails)
            
            # 본문 추가
            mime_type = 'html' if html else 'plain'
            msg.attach(MIMEText(body, mime_type, 'utf-8'))
            
            # 발송
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.sender_email, self.sender_password)
                server.send_message(msg)
            
            logger.info(f"✅ Email sent to {', '.join(to_emails)}")
            return True
        
        except Exception as e:
            logger.error(f"❌ Email send failed: {e}")
            return False


class SlackNotifier:
    """Slack 알림 발송"""
    
    def __init__(self, webhook_url: str = None):
        """
        Args:
            webhook_url: Slack Incoming Webhook URL
        """
        self.webhook_url = webhook_url or os.getenv('SLACK_WEBHOOK_URL', '')
    
    def send_message(self, channel: str, text: str, blocks: List[dict] = None) -> bool:
        """Slack 메시지 발송
        
        Args:
            channel: 채널 이름 (e.g., '#alerts')
            text: 평문 메시지
            blocks: 리치 포맷 (Block Kit)
        
        Returns:
            성공 여부
        """
        try:
            if not self.webhook_url:
                logger.warning("⚠️ Slack webhook not configured, skipping")
                return False
            
            import requests
            
            payload = {
                'channel': channel,
                'text': text,
            }
            if blocks:
                payload['blocks'] = blocks
            
            response = requests.post(self.webhook_url, json=payload, timeout=5)
            
            if response.status_code == 200:
                logger.info(f"✅ Slack message sent to {channel}")
                return True
            else:
                logger.error(f"❌ Slack send failed: {response.text}")
                return False
        
        except Exception as e:
            logger.error(f"❌ Slack send error: {e}")
            return False


class KakaoNotifier:
    """카톡 알림 (선택: 카카오 비즈니스 API 또는 봇)"""
    
    def __init__(self, api_key: str = None, sender_key: str = None):
        """
        Args:
            api_key: 카카오 REST API Key
            sender_key: 카카오 비즈니스 Sender Key
        """
        self.api_key = api_key or os.getenv('KAKAO_API_KEY', '')
        self.sender_key = sender_key or os.getenv('KAKAO_SENDER_KEY', '')
    
    def send_message(self, phone: str, text: str) -> bool:
        """카톡 알림 발송 (구현 생략 - 별도 API 필요)"""
        logger.info(f"💬 Kakao message queued for {phone}: {text[:30]}...")
        # 실제 구현은 카카오 비즈니스 API 호출
        return True


# ============================================================
# 편의 함수
# ============================================================

def notify_batch(recipients: List[str], message: str, subject: str = "알림",
                 via: str = 'email', channels: List[str] = None):
    """배치 알림 발송
    
    Args:
        recipients: 수신자 리스트 (이메일 주소 또는 전화번호)
        message: 메시지 내용
        subject: 제목
        via: 채널 ('email', 'slack', 'kakao')
        channels: Slack 채널 (e.g., ['#alerts', '#team'])
    """
    if via == 'email':
        notifier = EmailNotifier()
        return notifier.send_email(recipients, subject, message)
    
    elif via == 'slack':
        notifier = SlackNotifier()
        for channel in (channels or ['#alerts']):
            notifier.send_message(channel, message)
        return True
    
    elif via == 'kakao':
        notifier = KakaoNotifier()
        results = []
        for phone in recipients:
            results.append(notifier.send_message(phone, message))
        return all(results)
    
    else:
        logger.warning(f"Unknown notification channel: {via}")
        return False


def notify_state_change(old_status: str, new_status: str, inquiry_id: str,
                        context: dict = None, via: str = 'email'):
    """상태 변경 알림
    
    문의 → 견적 → 계약 → 배정 → 정산 각 단계에서 자동 알림
    
    Args:
        old_status: 이전 상태
        new_status: 새 상태
        inquiry_id: 문의ID
        context: 추가 정보 (고객명, 행사명 등)
        via: 알림 채널
    """
    context = context or {}
    
    # status_config.STATUS_FLOW 기준 상태 전이 템플릿
    templates = {
        ('접수', '견적'): "🧮 견적이 생성되었습니다. (ID: {inquiry_id})",
        ('견적', '체결'): "📝 계약이 체결되었습니다. (ID: {inquiry_id})",
        ('체결', '배정완료'): "👷 인력 배정이 완료되었습니다. (ID: {inquiry_id})",
        ('배정완료', '진행중'): "🔥 현장 진행이 시작되었습니다. (ID: {inquiry_id})",
        ('진행중', '완료'): "✅ 현장이 종료되었습니다. (ID: {inquiry_id})",
        ('완료', '정산완료'): "🎉 정산이 완료되었습니다. (ID: {inquiry_id})",
        # 이탈 상태
        ('접수', '미체결'): "❌ 문의가 미체결 처리되었습니다. (ID: {inquiry_id})",
        ('견적', '미체결'): "❌ 견적이 미체결 처리되었습니다. (ID: {inquiry_id})",
    }
    
    template = templates.get((old_status, new_status))
    if not template:
        logger.warning(f"No template for {old_status} → {new_status}")
        return
    
    message = template.format(inquiry_id=inquiry_id, **context)
    
    # 받는 사람 (기본값: 관리자)
    recipients = context.get('recipients', ['admin@example.com'])
    
    notify_batch(recipients, message, subject=f"[알림] {new_status}", via=via)


# 초기화
email_notifier = EmailNotifier()
slack_notifier = SlackNotifier()
kakao_notifier = KakaoNotifier()
